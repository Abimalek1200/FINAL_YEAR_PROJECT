// ========================================
// MAIN APPLICATION CONTROLLER
// ========================================

// Global state management
const AppState = {
    mode: 'manual', // 'manual' or 'auto'
    connected: false,
    devices: {
        pump: { running: false, speed: 0 },
        feed: { running: false, intensity: 0 },
        air: { running: false, intensity: 0 },
        agitator: { running: false, speed: 0 }
    },
    metrics: {
        bubbleCount: 0,
        avgBubbleSize: 0,
        frothCoverage: 0,
        frothStability: 0,
        anomalyStatus: 'NORMAL'
    },
    piController: {
        setpoint: 120,
        kp: 0.5,
        ki: 0.05,
        output: 0,
        error: 0
    },
    alerts: []
};

// WebSocket connection
let ws = null;
let wsReconnectAttempts = 0;
const WS_MAX_RECONNECT = 10;
const WS_RECONNECT_DELAY = 3000;

// Initialize application on load
document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    initializeWebSocket();
    setupEventListeners();
    startClock();
    startUptimeCounter();
    startPolling(); // Start periodic API polling as fallback
});

// ========================================
// WEBSOCKET CONNECTION
// ========================================

function initializeWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.hostname || 'localhost';
    const wsPort = '8000'; // FastAPI backend port
    const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}/ws`;

    console.log('Connecting to WebSocket:', wsUrl);
    updateConnectionStatus('connecting', 'Connecting...');

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        AppState.connected = true;
        wsReconnectAttempts = 0;
        updateConnectionStatus('connected', 'Connected');
        addAlert('success', 'WebSocket connection established');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus('error', 'Connection Error');
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        AppState.connected = false;
        updateConnectionStatus('disconnected', 'Disconnected');
        
        // Attempt reconnection
        if (wsReconnectAttempts < WS_MAX_RECONNECT) {
            wsReconnectAttempts++;
            addAlert('warning', `Reconnecting... (Attempt ${wsReconnectAttempts}/${WS_MAX_RECONNECT})`);
            setTimeout(initializeWebSocket, WS_RECONNECT_DELAY);
        } else {
            addAlert('error', 'Connection lost. Please refresh the page.');
        }
    };
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'frame':
            updateVideoFrame(data.image, data.bubbles);
            break;
        case 'metrics':
            updateMetrics(data.metrics);
            break;
        case 'anomaly':
            handleAnomaly(data);
            break;
        case 'control':
            updateControlState(data);
            break;
        case 'system':
            updateSystemHealth(data);
            break;
        case 'alert':
            addAlert(data.level, data.message);
            break;
        default:
            console.warn('Unknown message type:', data.type);
    }
}

function sendWebSocketMessage(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    } else {
        console.warn('WebSocket not connected');
        addAlert('warning', 'Cannot send command - not connected');
    }
}

// ========================================
// UI INITIALIZATION
// ========================================

function initializeUI() {
    // Set default mode display
    updateModeDisplay();
    
    // Initialize device controls
    updateDeviceUI('pump');
    updateDeviceUI('feed');
    updateDeviceUI('air');
    updateDeviceUI('agitator');
}

// ========================================
// EVENT LISTENERS
// ========================================

function setupEventListeners() {
    // Theme toggle
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
    
    // Mode switches
    document.getElementById('autoModeBtn').addEventListener('click', () => switchMode('auto'));
    document.getElementById('manualModeBtn').addEventListener('click', () => switchMode('manual'));
    
    // Emergency stop
    document.getElementById('emergencyStopBtn').addEventListener('click', handleEmergencyStop);
    
    // Manual mode device toggles
    setupDeviceToggle('pump');
    setupDeviceToggle('feed');
    setupDeviceToggle('air');
    setupDeviceToggle('agitator');
    
    // Manual mode device sliders
    setupDeviceSlider('pump', 'Speed');
    setupDeviceSlider('feed', 'Intensity');
    setupDeviceSlider('air', 'Intensity');
    setupDeviceSlider('agitator', 'Speed');
    
    // Auto mode device toggles (feed, air, agitator)
    setupDeviceToggleAuto('feed');
    setupDeviceToggleAuto('air');
    setupDeviceToggleAuto('agitator');
    
    // Auto mode device sliders (feed, air, agitator)
    setupDeviceSliderAuto('feed', 'Intensity');
    setupDeviceSliderAuto('air', 'Intensity');
    setupDeviceSliderAuto('agitator', 'Speed');
    
    // System control buttons
    document.getElementById('startAllBtn').addEventListener('click', startAllDevices);
    document.getElementById('stopAllBtn').addEventListener('click', stopAllDevices);
    
    // Video controls
    document.getElementById('playPauseBtn').addEventListener('click', toggleVideoPlayback);
    document.getElementById('snapshotBtn').addEventListener('click', takeSnapshot);
    
    // Clear alerts
    document.getElementById('clearAlertsBtn').addEventListener('click', clearAlerts);
}

// ========================================
// MODE SWITCHING
// ========================================

function switchMode(mode) {
    AppState.mode = mode;
    
    // Update UI
    document.getElementById('autoModeBtn').classList.toggle('active', mode === 'auto');
    document.getElementById('manualModeBtn').classList.toggle('active', mode === 'manual');
    
    // Show/hide control panels
    document.getElementById('manualControls').style.display = mode === 'manual' ? 'block' : 'none';
    document.getElementById('autoControls').style.display = mode === 'auto' ? 'block' : 'none';
    
    // Send mode change to backend via REST API
    setPumpMode(mode).catch(err => {
        console.error('Failed to switch pump mode:', err);
        // Revert UI on error
        AppState.mode = mode === 'auto' ? 'manual' : 'auto';
        updateModeDisplay();
    });
    
    addAlert('info', `Switched to ${mode.toUpperCase()} mode`);
}

function updateModeDisplay() {
    switchMode(AppState.mode);
}

// ========================================
// DEVICE CONTROL
// ========================================

function setupDeviceToggle(device) {
    const toggleBtn = document.getElementById(`${device}Toggle`);
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isRunning = AppState.devices[device].running;
            toggleDevice(device, !isRunning);
        });
    }
}

function toggleDevice(device, running) {
    AppState.devices[device].running = running;
    
    // Update UI
    updateDeviceUI(device);
    
    // If turning on, apply current slider value via API
    if (running && device !== 'pump') {
        const motorMap = { 'agitator': 'agitator', 'air': 'air', 'feed': 'feed' };
        const motorId = motorMap[device];
        if (motorId) {
            const dutyCycle = AppState.devices[device].speed || AppState.devices[device].intensity || 0;
            controlMotor(motorId, dutyCycle);
        }
    } else if (running && device === 'pump') {
        setPumpSpeed(AppState.devices.pump.speed);
    } else if (!running) {
        // Stop motor
        if (device === 'pump') {
            setPumpSpeed(0);
        } else {
            const motorMap = { 'agitator': 'agitator', 'air': 'air', 'feed': 'feed' };
            const motorId = motorMap[device];
            if (motorId) {
                controlMotor(motorId, 0);
            }
        }
    }
    
    addAlert('info', `${device.charAt(0).toUpperCase() + device.slice(1)} ${running ? 'started' : 'stopped'}`);
}

function setupDeviceSlider(device, param) {
    const slider = document.getElementById(`${device}${param}`);
    const valueDisplay = document.getElementById(`${device}${param}Value`);
    
    if (slider && valueDisplay) {
        slider.addEventListener('input', (e) => {
            const value = parseInt(e.target.value);
            valueDisplay.textContent = value;
            
            // Update state
            if (param === 'Speed') {
                AppState.devices[device].speed = value;
            } else if (param === 'Intensity') {
                AppState.devices[device].intensity = value;
            }
            
            // Update derived values
            updateDeviceDerivedValues(device, value);
        });
        
        slider.addEventListener('change', async (e) => {
            const value = parseInt(e.target.value);
            
            // Send to backend via REST API
            if (device === 'pump') {
                await setPumpSpeed(value);
            } else {
                const motorMap = { 'agitator': 'agitator', 'air': 'air', 'feed': 'feed' };
                const motorId = motorMap[device];
                if (motorId) {
                    await controlMotor(motorId, value);
                }
            }
        });
    }
}

function updateDeviceUI(device) {
    const toggleBtn = document.getElementById(`${device}Toggle`);
    const statusDot = toggleBtn?.querySelector('.status-dot');
    const statusText = toggleBtn?.querySelector('.status-text');
    
    const isRunning = AppState.devices[device].running;
    
    if (toggleBtn) {
        toggleBtn.classList.toggle('active', isRunning);
    }
    
    if (statusDot) {
        statusDot.classList.toggle('status-active', isRunning);
        statusDot.classList.toggle('status-stopped', !isRunning);
    }
    
    if (statusText) {
        statusText.textContent = isRunning ? 'Running' : 'Stopped';
    }
}

function updateDeviceDerivedValues(device, value) {
    switch (device) {
        case 'pump':
            // Flow rate calculation: assume 0.1 mL/min per %
            const flowRate = (value * 0.1).toFixed(1);
            document.getElementById('pumpFlowRate').textContent = `${flowRate} mL/min`;
            break;
        case 'feed':
            const feedFlow = value > 0 ? (value > 70 ? 'High' : value > 40 ? 'Medium' : 'Low') : 'Stopped';
            document.getElementById('feedFlow').textContent = feedFlow;
            break;
        case 'air':
            const airFlow = value > 0 ? (value > 70 ? 'High' : value > 40 ? 'Medium' : 'Low') : 'Stopped';
            document.getElementById('airFlow').textContent = airFlow;
            break;
        case 'agitator':
            // RPM calculation: assume max 1500 RPM at 100%
            const rpm = Math.round(value * 15);
            document.getElementById('agitatorRPM').textContent = rpm;
            break;
    }
}

// Auto mode device controls
function setupDeviceToggleAuto(device) {
    const toggleBtn = document.getElementById(`${device}ToggleAuto`);
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isRunning = AppState.devices[device].running;
            toggleDevice(device, !isRunning);
        });
    }
}

function setupDeviceSliderAuto(device, param) {
    const slider = document.getElementById(`${device}${param}Auto`);
    const valueDisplay = document.getElementById(`${device}${param}ValueAuto`);
    
    if (slider && valueDisplay) {
        slider.addEventListener('input', (e) => {
            const value = parseInt(e.target.value);
            valueDisplay.textContent = value;
            
            // Update state
            if (param === 'Speed') {
                AppState.devices[device].speed = value;
            } else if (param === 'Intensity') {
                AppState.devices[device].intensity = value;
            }
            
            // Update derived values for auto mode
            updateDeviceDerivedValuesAuto(device, value);
        });
        
        slider.addEventListener('change', async (e) => {
            const value = parseInt(e.target.value);
            
            // Send to backend via REST API (auto mode motors)
            const motorMap = { 'agitator': 'agitator', 'air': 'air', 'feed': 'feed' };
            const motorId = motorMap[device];
            if (motorId) {
                await controlMotor(motorId, value);
            }
        });
    }
}

function updateDeviceDerivedValuesAuto(device, value) {
    switch (device) {
        case 'feed':
            const feedFlow = value > 0 ? (value > 70 ? 'High' : value > 40 ? 'Medium' : 'Low') : 'Stopped';
            document.getElementById('feedFlowAuto').textContent = feedFlow;
            break;
        case 'air':
            const airFlow = value > 0 ? (value > 70 ? 'High' : value > 40 ? 'Medium' : 'Low') : 'Stopped';
            document.getElementById('airFlowAuto').textContent = airFlow;
            break;
        case 'agitator':
            // RPM calculation: assume max 1500 RPM at 100%
            const rpm = Math.round(value * 15);
            document.getElementById('agitatorRPMAuto').textContent = rpm;
            break;
    }
}

// ========================================
// SYSTEM CONTROLS
// ========================================

function startAllDevices() {
    ['pump', 'feed', 'air', 'agitator'].forEach(device => {
        toggleDevice(device, true);
    });
    addAlert('success', 'All devices started');
}

function stopAllDevices() {
    ['pump', 'feed', 'air', 'agitator'].forEach(device => {
        toggleDevice(device, false);
    });
    addAlert('info', 'All devices stopped');
}

function handleEmergencyStop() {
    if (confirm('Are you sure you want to trigger EMERGENCY STOP? This will halt all operations immediately.')) {
        // Call REST API emergency stop endpoint
        emergencyStop();
        
        // Immediately stop all devices in UI
        stopAllDevices();
        
        // Update system status
        document.getElementById('systemStatusPill').textContent = '● EMERGENCY STOP';
        document.getElementById('systemStatusPill').className = 'status-pill';
        document.getElementById('systemStatusPill').style.backgroundColor = 'rgba(231, 76, 60, 0.3)';
        document.getElementById('systemStatusPill').style.color = 'var(--accent-danger)';
        
        addAlert('error', 'EMERGENCY STOP TRIGGERED - All devices stopped');
    }
}

// ========================================
// REST API FUNCTIONS
// ========================================

/**
 * Control motors (agitator, air, feed) via REST API
 */
async function controlMotor(motorId, dutyCycle) {
    try {
        const response = await fetch('/api/motor/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_id: motorId,
                duty_cycle: dutyCycle
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Motor control failed');
        }
        
        const result = await response.json();
        console.log(`Motor ${motorId} set to ${dutyCycle}%:`, result);
        return result;
        
    } catch (error) {
        console.error(`Failed to control ${motorId}:`, error);
        addAlert('error', `Motor control failed: ${error.message}`);
        throw error;
    }
}

/**
 * Set pump mode (auto or manual)
 */
async function setPumpMode(mode) {
    try {
        const response = await fetch('/api/pump/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Pump mode change failed');
        }
        
        const result = await response.json();
        console.log(`Pump mode set to ${mode}:`, result);
        addAlert('success', `Pump mode: ${mode.toUpperCase()}`);
        return result;
        
    } catch (error) {
        console.error('Failed to set pump mode:', error);
        addAlert('error', `Pump mode change failed: ${error.message}`);
        throw error;
    }
}

/**
 * Set pump speed (manual mode only)
 */
async function setPumpSpeed(dutyCycle) {
    try {
        const response = await fetch('/api/pump/speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duty_cycle: dutyCycle })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Pump speed control failed');
        }
        
        const result = await response.json();
        console.log(`Pump speed set to ${dutyCycle}%:`, result);
        return result;
        
    } catch (error) {
        console.error('Failed to set pump speed:', error);
        addAlert('error', `Pump control failed: ${error.message}`);
        throw error;
    }
}

/**
 * Update PI controller parameters (auto mode)
 */
async function updatePIParameters(kp, ki, setpoint) {
    try {
        const params = {};
        if (kp !== null && kp !== undefined) params.kp = kp;
        if (ki !== null && ki !== undefined) params.ki = ki;
        if (setpoint !== null && setpoint !== undefined) params.setpoint = setpoint;
        
        const response = await fetch('/api/pi/parameters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'PI parameter update failed');
        }
        
        const result = await response.json();
        console.log('PI parameters updated:', result);
        addAlert('success', 'PI controller updated');
        return result;
        
    } catch (error) {
        console.error('Failed to update PI parameters:', error);
        addAlert('error', `PI update failed: ${error.message}`);
        throw error;
    }
}

/**
 * Emergency stop - stops all motors immediately
 */
async function emergencyStop() {
    try {
        const response = await fetch('/api/emergency-stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Emergency stop failed');
        }
        
        const result = await response.json();
        console.log('Emergency stop executed:', result);
        addAlert('error', 'EMERGENCY STOP - All motors halted');
        return result;
        
    } catch (error) {
        console.error('Emergency stop failed:', error);
        addAlert('error', `Emergency stop error: ${error.message}`);
        throw error;
    }
}

/**
 * Fetch current metrics from backend
 */
async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics');
        
        if (!response.ok) {
            throw new Error('Failed to fetch metrics');
        }
        
        const metrics = await response.json();
        updateMetrics(metrics);
        return metrics;
        
    } catch (error) {
        console.error('Failed to fetch metrics:', error);
        return null;
    }
}

/**
 * Fetch system status from backend
 */
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        
        if (!response.ok) {
            throw new Error('Failed to fetch status');
        }
        
        const status = await response.json();
        updateControlState(status);
        return status;
        
    } catch (error) {
        console.error('Failed to fetch status:', error);
        return null;
    }
}
        
        addAlert('error', 'EMERGENCY STOP ACTIVATED');
// ========================================
// DATA UPDATES
// ========================================

function updateMetrics(metrics) {
    AppState.metrics = { ...AppState.metrics, ...metrics };
    
    // Bubble count
    if (metrics.bubble_count !== undefined) {
        document.getElementById('bubbleCount').textContent = metrics.bubble_count;
    }
    
    // Average bubble size
    if (metrics.avg_bubble_size !== undefined) {
        document.getElementById('avgBubbleSize').textContent = metrics.avg_bubble_size.toFixed(1);
    }
    
    // Froth coverage
    if (metrics.froth_coverage !== undefined) {
        const coverage = Math.round(metrics.froth_coverage * 100);
        document.getElementById('frothCoverage').textContent = coverage;
    }
    
    // Froth stability
    if (metrics.froth_stability !== undefined) {
        const stability = Math.round(metrics.froth_stability * 100);
        document.getElementById('frothStability').textContent = `${stability}%`;
        document.getElementById('stabilityFill').style.width = `${stability}%`;
    }
}

function updateControlState(data) {
    if (data.pi_output !== undefined) {
        document.getElementById('piOutput').textContent = `${Math.round(data.pi_output)}%`;
    }
    
    if (data.pi_error !== undefined) {
        document.getElementById('piError').textContent = data.pi_error.toFixed(1);
    }
}

function handleAnomaly(data) {
    const statusEl = document.getElementById('anomalyStatus');
    const cardEl = document.getElementById('anomalyCard');
    const timeEl = document.getElementById('anomalyTime');
    
    if (data.status) {
        statusEl.textContent = data.status.toUpperCase();
        statusEl.className = 'metric-value anomaly-status';
        
        if (data.status === 'warning') {
            statusEl.classList.add('warning');
            addAlert('warning', data.message || 'Anomaly detected - Warning level');
        } else if (data.status === 'critical') {
            statusEl.classList.add('critical');
            addAlert('error', data.message || 'Anomaly detected - Critical level');
        }
    }
    
    if (timeEl) {
        timeEl.textContent = `Last check: ${new Date().toLocaleTimeString()}`;
    }
}

function updateSystemHealth(data) {
    // Hardware status only
    if (data.hardware_status) {
        updateHardwareStatus(data.hardware_status);
    }
}

function updateHardwareStatus(status) {
    const indicators = {
        camera: document.getElementById('cameraStatus'),
        pump: document.getElementById('pumpStatusIndicator'),
        network: document.getElementById('networkStatus'),
        storage: document.getElementById('storageStatus')
    };
    
    Object.keys(status).forEach(device => {
        const indicator = indicators[device];
        if (indicator) {
            indicator.className = 'status-indicator';
            indicator.classList.add(status[device] ? 'status-active' : 'status-error');
        }
    });
}

// ========================================
// VIDEO HANDLING
// ========================================

let videoPlaying = true;
let frameCount = 0;
let fpsStartTime = Date.now();

function updateVideoFrame(imageData, bubbles) {
    const canvas = document.getElementById('videoCanvas');
    const ctx = canvas.getContext('2d');
    
    if (!imageData) return;
    
    const img = new Image();
    img.onload = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        
        // Draw bubble overlays if provided
        if (bubbles && bubbles.length > 0) {
            drawBubbleOverlays(ctx, bubbles);
        }
        
        // Update FPS
        frameCount++;
        const now = Date.now();
        if (now - fpsStartTime >= 1000) {
            document.getElementById('frameRate').textContent = `${frameCount} FPS`;
            frameCount = 0;
            fpsStartTime = now;
        }
        
        // Update bubble overlay count
        if (bubbles) {
            document.getElementById('bubbleOverlay').textContent = `Bubbles: ${bubbles.length}`;
        }
    };
    
    img.src = `data:image/jpeg;base64,${imageData}`;
}

function drawBubbleOverlays(ctx, bubbles) {
    ctx.strokeStyle = '#27ae60';
    ctx.lineWidth = 2;
    
    bubbles.forEach(bubble => {
        if (bubble.contour) {
            ctx.beginPath();
            bubble.contour.forEach((point, i) => {
                if (i === 0) {
                    ctx.moveTo(point.x, point.y);
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            });
            ctx.closePath();
            ctx.stroke();
        }
    });
}

function toggleVideoPlayback() {
    videoPlaying = !videoPlaying;
    const btn = document.getElementById('playPauseBtn');
    btn.textContent = videoPlaying ? '⏸️' : '▶️';
    
    sendWebSocketMessage({
        type: 'control',
        action: 'video_playback',
        playing: videoPlaying
    });
}

function takeSnapshot() {
    const canvas = document.getElementById('videoCanvas');
    const dataURL = canvas.toDataURL('image/png');
    
    // Create download link
    const link = document.createElement('a');
    link.download = `flotation_snapshot_${Date.now()}.png`;
    link.href = dataURL;
    link.click();
    
    addAlert('success', 'Snapshot saved');
}

// ========================================
// ALERTS MANAGEMENT
// ======================================== 

function addAlert(level, message) {
    const timestamp = new Date().toLocaleTimeString();
    const alert = {
        timestamp,
        level,
        message
    };
    
    AppState.alerts.unshift(alert);
    
    // Update UI
    const alertsList = document.getElementById('alertsList');
    const alertItem = document.createElement('div');
    alertItem.className = `alert-item alert-${level}`;
    alertItem.innerHTML = `
        <span class="alert-timestamp">${timestamp}</span>
        <span class="alert-message">${message}</span>
    `;
    
    alertsList.insertBefore(alertItem, alertsList.firstChild);
    
    // Limit to 50 alerts
    if (AppState.alerts.length > 50) {
        AppState.alerts = AppState.alerts.slice(0, 50);
        const items = alertsList.querySelectorAll('.alert-item');
        if (items.length > 50) {
            items[items.length - 1].remove();
        }
    }
}

function clearAlerts() {
    AppState.alerts = [];
    document.getElementById('alertsList').innerHTML = `
        <div class="alert-item alert-info">
            <span class="alert-timestamp">--:--:--</span>
            <span class="alert-message">No alerts</span>
        </div>
    `;
}

// ========================================
// CONNECTION STATUS
// ========================================

function updateConnectionStatus(status, text) {
    const statusEl = document.getElementById('connectionStatus');
    const statusDot = statusEl.querySelector('.status-dot');
    const statusText = document.getElementById('statusText');
    
    statusDot.className = 'status-dot';
    
    switch (status) {
        case 'connected':
            statusDot.classList.add('status-active');
            break;
        case 'connecting':
            statusDot.classList.add('status-connecting');
            break;
        case 'error':
        case 'disconnected':
            statusDot.classList.add('status-error');
            break;
    }
    
    statusText.textContent = text;
}

// ========================================
// THEME TOGGLE
// ========================================

function toggleTheme() {
    const body = document.body;
    const themeBtn = document.getElementById('themeToggle');
    
    body.classList.toggle('light-theme');
    const isLight = body.classList.contains('light-theme');
    
    themeBtn.textContent = isLight ? '☀️' : '🌙';
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

// Load saved theme
const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'light') {
    document.body.classList.add('light-theme');
    document.getElementById('themeToggle').textContent = '☀️';
}

// ========================================
// UTILITIES
// ========================================

function startClock() {
    function updateClock() {
        const now = new Date();
        const dateStr = now.toLocaleDateString('en-US', { 
            weekday: 'short', 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
        const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
        document.getElementById('datetime').textContent = `${dateStr} ${timeStr}`;
    }
    
    updateClock();
    setInterval(updateClock, 1000);
}

function startUptimeCounter() {
    const startTime = Date.now();
    
    function updateUptime() {
        const elapsed = Date.now() - startTime;
        const hours = Math.floor(elapsed / 3600000);
        const minutes = Math.floor((elapsed % 3600000) / 60000);
        const seconds = Math.floor((elapsed % 60000) / 1000);
        
        document.getElementById('uptime').textContent = 
            `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    
    setInterval(updateUptime, 1000);
}

/**
 * Start periodic polling of metrics and status via REST API
 * Fallback when WebSocket is not available
 */
function startPolling() {
    // Poll metrics every 2 seconds
    setInterval(async () => {
        if (!AppState.connected) {
            await fetchMetrics();
        }
    }, 2000);
    
    // Poll status every 5 seconds
    setInterval(async () => {
        if (!AppState.connected) {
            await fetchStatus();
        }
    }, 5000);
}

// ========================================
// ERROR HANDLING
// ========================================

window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    addAlert('error', `Error: ${event.error.message}`);
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    addAlert('error', `Promise error: ${event.reason}`);
});

console.log('Dashboard application initialized');
