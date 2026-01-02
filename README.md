# Flotation Control System - Final Year Project

## Project Overview

Automated reagent dosing control system for small-to-medium scale gold flotation operations in Zimbabwe. This Raspberry Pi 5-based system uses real-time computer vision to monitor froth characteristics and automatically adjust frother dosage using a simple PI controller.

**Key Features:**
- Real-time froth bubble detection using OpenCV watershed segmentation
- Dual-mode pump control (automatic PI control or manual PWM)
- Live video streaming via WebSocket to web dashboard
- Hardware control for 4 actuators (frother, agitator, air, feed)
- Emergency stop safety system

## Hardware Requirements

### Core Components
- **Raspberry Pi 5** (4GB+ RAM)
- **32GB+ MicroSD Card**
- **USB Webcam** (1080p, 10+ FPS)
- **USB LED Ring Light** (constant illumination)

### Flotation Equipment
- **Acrylic Flotation Cell** (transparent)
- **Peristaltic Pump** (frother dosing - GPIO 12)
- **Agitator Motor** (GPIO 13)
- **Air Pump** (GPIO 14)
- **Feed Pump** (GPIO 15)
- **Emergency Stop Button** (GPIO 22)

## Software Architecture

```
FINAL_YEAR_PROJECT/
├── config/                     # Configuration files (JSON)
├── dashboard/                  # Web UI (HTML/CSS/JS)
│   ├── index.html             # Main dashboard
│   ├── css/styles.css         # Styling
│   └── js/                    # Client-side logic
│       ├── app.js             # Main application
│       ├── charts.js          # (deprecated)
│       └── video_stream.js    # WebSocket handler
├── data/                       # Runtime data storage
├── logs/                       # Application logs
├── src/
│   ├── api/                    # FastAPI backend (3 files)
│   │   ├── main.py            # App startup, lifecycle (164 lines)
│   │   ├── routes.py          # REST endpoints (195 lines)
│   │   └── websocket.py       # Real-time streaming (123 lines)
│   ├── control/                # Hardware control (2 files)
│   │   ├── hardware_controller.py  # Unified controller (232 lines)
│   │   └── __init__.py
│   ├── ml/                     # Machine learning (optional)
│   │   ├── anomaly_detector.py
│   │   └── __init__.py
│   ├── utils/                  # Logging and data management
│   │   ├── data_manager.py
│   │   ├── logger.py
│   │   └── __init__.py
│   └── vision/                 # Vision processing (2 files)
│       ├── vision_processor.py # Unified processor (275 lines)
│       └── __init__.py
├── tests/                      # Test scripts
│   ├── test_hardware_controller.py
│   └── vision_debug.py
├── requirements.txt
├── run.py                      # Main entry point
└── setup.sh                    # Raspberry Pi setup script
```

## Key Metrics

The vision system extracts these 5 essential metrics:
1. **bubble_count** - Number of bubbles detected
2. **avg_bubble_size** - Average bubble area (pixels²)
3. **size_std_dev** - Bubble size variability
4. **froth_coverage** - Bubble coverage ratio (0-1)
5. **froth_stability** - Stability score (0-1)

## Installation

### Quick Start (Raspberry Pi 5)

```bash
# Clone repository
cd ~
git clone <repository-url> FINAL_YEAR_PROJECT
cd FINAL_YEAR_PROJECT

# Run setup script
chmod +x setup.sh
./setup.sh

# Start system
python3 run.py
```

### Manual Setup

```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-opencv python3-lgpio python3-pip

# Install Python packages
pip3 install -r requirements.txt

# Run application
python3 run.py
```

## Configuration

### Camera Settings (`config/camera_config.json`)
```json
{
  "width": 640,
  "height": 480,
  "fps": 10,
  "device_id": 0
}
```

### Control Parameters (`config/control_config.json`)
```json
{
  "pi_controller": {
    "kp": 0.5,
    "ki": 0.05,
    "setpoint": 120
  },
  "frother_pump": {
    "pin": 12,
    "max_duty_cycle": 80
  },
  "agitator": {"pin": 13},
  "air_pump": {"pin": 14},
  "feed_pump": {"pin": 15}
}
```

### Vision Parameters (`config/vision_config.json`)
```json
{
  "min_bubble_area": 80,
  "max_bubble_area": 5000,
  "distance_threshold": 0.125,
  "min_circularity": 0.45
}
```

## Usage

### Starting the System

```bash
# Start manually
python3 run.py

# Or via systemd (if installed)
sudo systemctl start flotation

# Check status
sudo systemctl status flotation
```

### Accessing Dashboard

Open browser to: `http://raspberrypi.local:8000`

**Dashboard Features:**
- Live video feed from camera
- Real-time metrics display (5 metrics)
- Control panel (auto/manual mode switching)
- Device controls (frother, agitator, air, feed)
- Hardware status indicators

### API Endpoints

**GET** `/api/metrics` - Current froth metrics  
**GET** `/api/status` - System status  
**POST** `/api/pump/mode` - Set auto/manual mode  
**POST** `/api/pump/speed` - Set manual pump speed  
**POST** `/api/pi/parameters` - Update PI gains  
**POST** `/api/motor/control` - Control motors  
**POST** `/api/emergency-stop` - Emergency shutdown  

**WebSocket** `/ws` - Real-time video + metrics stream

## Testing

```bash
# Test vision processing
cd tests
python3 vision_debug.py

# Test hardware controller
python3 test_hardware_controller.py
```

## Hardware Connections

| Device | GPIO Pin | PWM Type |
|--------|----------|----------|
| Frother Pump | 12 | Hardware PWM0 |
| Agitator | 13 | Hardware PWM1 |
| Air Pump | 14 | Software PWM |
| Feed Pump | 15 | Software PWM |
| E-Stop (Input) | 22 | Pull-up enabled |

## Safety Features

1. **E-Stop Monitoring** - GPIO 22 checked continuously
2. **Pump Duty Limit** - Max 80% to prevent overdosing
3. **Watchdog Timer** - Auto-stop if vision fails >5s
4. **Range Validation** - All inputs checked for valid ranges
5. **Emergency Shutdown** - `/api/emergency-stop` endpoint

## Troubleshooting

### Camera Not Detected
```bash
# List USB devices
lsusb

# Test camera
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL')"
```

### GPIO Permission Errors
```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER

# Reboot
sudo reboot
```

### Port Already in Use
```bash
# Check what's using port 8000
sudo lsof -i :8000

# Kill process if needed
sudo kill <PID>
```

## Performance Targets (Raspberry Pi 5)

- Vision processing: <100ms per frame
- Control loop: 1 Hz update rate
- Video streaming: 10 FPS @ 640x480
- API response: <20ms
- Memory usage: <800MB
- CPU utilization: <60%

## Project Structure Highlights

**Consolidated Modules:**
- **vision_processor.py** (275 lines) - Replaces 4 legacy files (1,249 lines)
- **hardware_controller.py** (232 lines) - Replaces 4 legacy files
- **API folder** (482 total lines) - Down from 1,197 lines

**Removed Complexity:**
- Authentication/authorization
- Rate limiting
- Complex PID algorithms (simple PI only)
- Database integration
- Advanced error recovery
- Configuration management layers
- Extensive logging

## Development

### Code Style
- Type hints on all functions
- Docstrings with examples
- Student-friendly comments explaining "why"
- Functions under 50 lines
- Files under 300 lines

### Adding New Features

1. Vision changes → edit `src/vision/vision_processor.py`
2. Control logic → edit `src/control/hardware_controller.py`
3. API endpoints → edit `src/api/routes.py`
4. Dashboard UI → edit `dashboard/index.html` and `dashboard/js/app.js`

## License

[Specify your license]

## Contributors

[Add contributor names]

## Acknowledgments

Built as a final year project for automated flotation control in small-scale gold mining operations.
