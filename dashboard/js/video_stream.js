// ========================================
// VIDEO STREAM HANDLER
// ========================================

class VideoStreamHandler {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.isPlaying = true;
        this.frameRate = 0;
        this.frameCount = 0;
        this.lastFrameTime = Date.now();
        this.fpsInterval = null;
    }

    initialize() {
        this.startFPSCounter();
        console.log('Video stream handler initialized');
    }

    startFPSCounter() {
        this.fpsInterval = setInterval(() => {
            const now = Date.now();
            const elapsed = now - this.lastFrameTime;
            
            if (elapsed >= 1000) {
                this.frameRate = Math.round((this.frameCount * 1000) / elapsed);
                this.updateFPSDisplay();
                this.frameCount = 0;
                this.lastFrameTime = now;
            }
        }, 1000);
    }

    updateFPSDisplay() {
        const fpsEl = document.getElementById('frameRate');
        if (fpsEl) {
            fpsEl.textContent = `${this.frameRate} FPS`;
            
            // Color code based on performance
            if (this.frameRate >= 10) {
                fpsEl.style.color = '#27ae60'; // Good
            } else if (this.frameRate >= 5) {
                fpsEl.style.color = '#f39c12'; // Warning
            } else {
                fpsEl.style.color = '#e74c3c'; // Poor
            }
        }
    }

    processFrame(imageData, bubbleData = null) {
        if (!this.isPlaying) return;

        const img = new Image();
        
        img.onload = () => {
            // Clear canvas
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            
            // Draw video frame
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
            
            // Draw bubble overlays if available
            if (bubbleData && bubbleData.bubbles) {
                this.drawBubbleOverlays(bubbleData.bubbles);
            }
            
            // Update bubble count overlay
            if (bubbleData) {
                this.updateBubbleCountOverlay(bubbleData);
            }
            
            // Increment frame count for FPS
            this.frameCount++;
        };

        img.onerror = (error) => {
            console.error('Error loading video frame:', error);
        };

        // Set image source (Base64 JPEG from backend)
        img.src = `data:image/jpeg;base64,${imageData}`;
    }

    drawBubbleOverlays(bubbles) {
        if (!Array.isArray(bubbles) || bubbles.length === 0) return;

        this.ctx.save();
        
        bubbles.forEach((bubble, index) => {
            // Different colors based on bubble size
            const size = bubble.area || 100;
            const color = this.getBubbleSizeColor(size);
            
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = 2;
            this.ctx.fillStyle = `${color}33`; // Semi-transparent fill

            if (bubble.contour && Array.isArray(bubble.contour)) {
                // Draw contour
                this.ctx.beginPath();
                bubble.contour.forEach((point, i) => {
                    if (i === 0) {
                        this.ctx.moveTo(point.x, point.y);
                    } else {
                        this.ctx.lineTo(point.x, point.y);
                    }
                });
                this.ctx.closePath();
                this.ctx.stroke();
                this.ctx.fill();
            } else if (bubble.center && bubble.radius) {
                // Draw circle approximation
                this.ctx.beginPath();
                this.ctx.arc(bubble.center.x, bubble.center.y, bubble.radius, 0, 2 * Math.PI);
                this.ctx.stroke();
                this.ctx.fill();
            }

            // Draw bubble ID (for debugging)
            if (bubble.center && index < 10) { // Only show first 10
                this.ctx.fillStyle = '#ffffff';
                this.ctx.font = '12px sans-serif';
                this.ctx.fillText(`#${index + 1}`, bubble.center.x - 10, bubble.center.y);
            }
        });

        this.ctx.restore();
    }

    getBubbleSizeColor(area) {
        // Color code: Small=Blue, Medium=Green, Large=Yellow, XLarge=Red
        if (area < 100) return '#3498db';       // Small - Blue
        if (area < 500) return '#27ae60';       // Medium - Green
        if (area < 2000) return '#f39c12';      // Large - Yellow
        return '#e74c3c';                       // XLarge - Red
    }

    updateBubbleCountOverlay(bubbleData) {
        const overlayEl = document.getElementById('bubbleOverlay');
        if (overlayEl && bubbleData.bubble_count !== undefined) {
            overlayEl.textContent = `Bubbles: ${bubbleData.bubble_count}`;
        }
    }

    togglePlayback() {
        this.isPlaying = !this.isPlaying;
        const btn = document.getElementById('playPauseBtn');
        if (btn) {
            btn.textContent = this.isPlaying ? '⏸️' : '▶️';
        }
        return this.isPlaying;
    }

    takeSnapshot() {
        try {
            const dataURL = this.canvas.toDataURL('image/png');
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const filename = `flotation_snapshot_${timestamp}.png`;
            
            // Create and trigger download
            const link = document.createElement('a');
            link.download = filename;
            link.href = dataURL;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            return true;
        } catch (error) {
            console.error('Error taking snapshot:', error);
            return false;
        }
    }

    drawCrosshair(x, y) {
        this.ctx.save();
        this.ctx.strokeStyle = '#ff0000';
        this.ctx.lineWidth = 1;
        
        // Vertical line
        this.ctx.beginPath();
        this.ctx.moveTo(x, 0);
        this.ctx.lineTo(x, this.canvas.height);
        this.ctx.stroke();
        
        // Horizontal line
        this.ctx.beginPath();
        this.ctx.moveTo(0, y);
        this.ctx.lineTo(this.canvas.width, y);
        this.ctx.stroke();
        
        this.ctx.restore();
    }

    drawROI(x, y, width, height) {
        this.ctx.save();
        this.ctx.strokeStyle = '#00ff00';
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);
        this.ctx.strokeRect(x, y, width, height);
        this.ctx.restore();
    }

    clearCanvas() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw "No Signal" message
        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = '24px sans-serif';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('No Video Signal', this.canvas.width / 2, this.canvas.height / 2);
    }

    destroy() {
        if (this.fpsInterval) {
            clearInterval(this.fpsInterval);
        }
    }
}

// Initialize video stream handler
let videoHandler = null;

document.addEventListener('DOMContentLoaded', () => {
    videoHandler = new VideoStreamHandler('videoCanvas');
    videoHandler.initialize();
});

// Export for use in app.js
window.updateVideoFrame = (imageData, bubbles) => {
    if (videoHandler) {
        const bubbleData = {
            bubbles: bubbles,
            bubble_count: bubbles ? bubbles.length : 0
        };
        videoHandler.processFrame(imageData, bubbleData);
    }
};

window.toggleVideoPlayback = () => {
    if (videoHandler) {
        return videoHandler.togglePlayback();
    }
};

window.takeSnapshot = () => {
    if (videoHandler) {
        const success = videoHandler.takeSnapshot();
        if (success && typeof addAlert === 'function') {
            addAlert('success', 'Snapshot saved successfully');
        } else if (typeof addAlert === 'function') {
            addAlert('error', 'Failed to save snapshot');
        }
    }
};

console.log('Video stream module loaded');
