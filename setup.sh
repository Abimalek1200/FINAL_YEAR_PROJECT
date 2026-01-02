#!/bin/bash

# ========================================
# Flotation Control System - Setup Script
# Raspberry Pi 5 Installation
# ========================================

set -e  # Exit on error

echo "========================================="
echo "Flotation Control System - Setup"
echo "Raspberry Pi 5 Configuration"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "Please do not run this script as root"
    exit 1
fi

# ========================================
# STEP 1: System Update
# ========================================

echo "[1/6] Updating system packages..."
sudo apt update
sudo apt upgrade -y
echo "✓ System updated"

# ========================================
# STEP 2: Install System Dependencies
# ========================================

echo ""
echo "[2/6] Installing system dependencies..."

# Core Python dependencies
sudo apt install -y \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential

# OpenCV dependencies
sudo apt install -y \
    python3-opencv \
    libopencv-dev

# Camera dependencies for Raspberry Pi 5 (libcamera)
sudo apt install -y \
    libcamera-apps \
    libcamera-dev \
    python3-picamera2 \
    python3-libcamera

# GPIO library for Raspberry Pi 5
sudo apt install -y python3-lgpio python3-rpi-lgpio

# Verify lgpio installation
if python3 -c "import lgpio" 2>/dev/null; then
    echo "✓ lgpio installed successfully"
    python3 << 'PYEOF'
import lgpio
try:
    chip = lgpio.gpiochip_open(0)
    print("✓ GPIO connection test SUCCESSFUL")
    lgpio.gpiochip_close(chip)
except Exception as e:
    print(f"⚠ GPIO test failed: {e}")
PYEOF
else
    echo "⚠ lgpio installation failed"
    exit 1
fi

echo "✓ System dependencies installed"

# ========================================
# STEP 3: Enable Hardware Interfaces
# ========================================

echo ""
echo "[3/6] Enabling hardware interfaces..."

# Raspberry Pi 5 uses /boot/firmware/config.txt instead of /boot/config.txt
BOOT_CONFIG="/boot/firmware/config.txt"
if [ ! -f "$BOOT_CONFIG" ]; then
    BOOT_CONFIG="/boot/config.txt"  # Fallback for older Pi models
fi

# Enable camera interface for Raspberry Pi 5 (uses libcamera)
if [ -f "$BOOT_CONFIG" ]; then
    # For Pi 5, camera is enabled by default with libcamera
    # Ensure GPU memory is adequate
    if ! grep -q "gpu_mem" "$BOOT_CONFIG" 2>/dev/null; then
        echo "gpu_mem=128" | sudo tee -a "$BOOT_CONFIG" > /dev/null
        echo "✓ Camera memory allocated"
    fi
    
    # Enable I2C if needed
    if ! grep -q "dtparam=i2c_arm=on" "$BOOT_CONFIG" 2>/dev/null; then
        echo "dtparam=i2c_arm=on" | sudo tee -a "$BOOT_CONFIG" > /dev/null
    fi
fi

# Add user to required groups for Raspberry Pi 5
sudo usermod -a -G gpio,video,i2c $USER

echo "✓ Hardware interfaces enabled"
echo "  Note: You may need to reboot for changes to take effect"

# ========================================
# STEP 4: Install Python Packages
# ========================================

echo ""
echo "[4/6] Installing Python packages..."

# Create virtual environment with access to system packages (for GPIO and camera)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv --system-site-packages venv
    echo "✓ Virtual environment created with system-site-packages"
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
python3 -m pip install --upgrade pip

# Install from requirements.txt
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✓ Python packages installed from requirements.txt"
else
    # Fallback: install essential packages manually
    pip install fastapi uvicorn[standard] numpy scikit-learn websockets python-multipart
    echo "✓ Essential Python packages installed"
    echo "  ⚠ requirements.txt not found, installed core packages only"
fi

# ========================================
# STEP 5: Create Project Structure
# ========================================

echo ""
echo "[5/6] Creating project directories..."

# Create directories if they don't exist
mkdir -p config data logs snapshots tests

# Create default config files if they don't exist
if [ ! -f "config/camera_config.json" ]; then
    cat > config/camera_config.json << 'EOF'
{
  "width": 640,
  "height": 480,
  "fps": 10,
  "device_id": 0
}
EOF
    echo "✓ Created config/camera_config.json"
fi

if [ ! -f "config/control_config.json" ]; then
    cat > config/control_config.json << 'EOF'
{
  "pi_controller": {
    "kp": 0.5,
    "ki": 0.05,
    "setpoint": 120
  },
  "frother_pump": {
    "pin": 12,
    "frequency_hz": 1000,
    "max_duty_cycle": 80
  },
  "agitator": {
    "pin": 13,
    "frequency_hz": 1000
  },
  "air_pump": {
    "pin": 14,
    "frequency_hz": 1000
  },
  "feed_pump": {
    "pin": 15,
    "frequency_hz": 1000
  },
  "estop_pin": 22
}
EOF
    echo "✓ Created config/control_config.json"
fi

if [ ! -f "config/vision_config.json" ]; then
    cat > config/vision_config.json << 'EOF'
{
  "min_bubble_area": 80,
  "max_bubble_area": 5000,
  "distance_threshold": 0.125,
  "min_circularity": 0.45,
  "gaussian_blur_kernel": 5,
  "morphology_kernel": 3
}
EOF
    echo "✓ Created config/vision_config.json"
fi

echo "✓ Project structure created"

# ========================================
# STEP 6: Setup Systemd Service (Optional)
# ========================================

echo ""
echo "[6/6] Setting up systemd service (optional)..."

# Create systemd service file
cat > flotation.service << EOF
[Unit]
Description=Flotation Control System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Ask user if they want to install the service
read -p "Install systemd service for auto-start on boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo cp flotation.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable flotation.service
    echo "✓ Systemd service installed and enabled"
    echo "  Start: sudo systemctl start flotation"
    echo "  Stop: sudo systemctl stop flotation"
    echo "  Status: sudo systemctl status flotation"
else
    echo "  Systemd service not installed (you can install it manually later)"
fi

# Clean up temporary service file
rm -f flotation.service

# ========================================
# Completion Message
# ========================================

echo ""
echo "========================================="
echo "✓ Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Reboot to apply changes: sudo reboot"
echo "  2. Activate virtual environment: source venv/bin/activate"
echo "  3. Test camera: python tests/vision_debug.py"
echo "  4. Test hardware: python tests/test_hardware_controller.py"
echo "  5. Run system: python run.py"
echo "  6. Access dashboard: http://raspberrypi.local:8000"
echo ""
echo "Configuration files:"
echo "  - config/camera_config.json"
echo "  - config/control_config.json"
echo "  - config/vision_config.json"
echo ""
echo "For help, see README.md and STUDENT_GUIDE.md"
echo ""
