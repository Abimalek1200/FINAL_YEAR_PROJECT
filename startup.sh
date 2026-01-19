#!/bin/bash

# =============================================================================
# Flotation Control System - Auto-Startup Configuration Script
# For Raspberry Pi 5
# =============================================================================

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="flotation-control"
SERVICE_FILE="${SERVICE_NAME}.service"
SYSTEMD_PATH="/etc/systemd/system/${SERVICE_FILE}"

# Print colored message
print_msg() {
    local color=$1
    shift
    echo -e "${color}$@${NC}"
}

print_header() {
    echo ""
    print_msg "$BLUE" "===================================================================="
    print_msg "$BLUE" "$@"
    print_msg "$BLUE" "===================================================================="
    echo ""
}

print_success() {
    print_msg "$GREEN" "✓ $@"
}

print_error() {
    print_msg "$RED" "✗ $@"
}

print_warning() {
    print_msg "$YELLOW" "⚠ $@"
}

print_info() {
    print_msg "$BLUE" "ℹ $@"
}

# Check if script is run with sudo
check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run with sudo privileges"
        print_info "Please run: sudo bash startup.sh"
        exit 1
    fi
    
    # Get the actual user (not root)
    if [ -n "$SUDO_USER" ]; then
        ACTUAL_USER="$SUDO_USER"
    else
        ACTUAL_USER="pi"
    fi
    
    print_success "Running with sudo as user: $ACTUAL_USER"
}

# Check if Python virtual environment exists
check_venv() {
    print_info "Checking Python virtual environment..."
    
    if [ ! -d "${PROJECT_DIR}/venv" ]; then
        print_warning "Virtual environment not found at ${PROJECT_DIR}/venv"
        print_info "Creating virtual environment..."
        
        sudo -u "$ACTUAL_USER" python3 -m venv "${PROJECT_DIR}/venv"
        
        if [ -d "${PROJECT_DIR}/venv" ]; then
            print_success "Virtual environment created"
            
            # Install requirements if requirements.txt exists
            if [ -f "${PROJECT_DIR}/requirements.txt" ]; then
                print_info "Installing Python dependencies..."
                sudo -u "$ACTUAL_USER" "${PROJECT_DIR}/venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"
                print_success "Dependencies installed"
            fi
        else
            print_error "Failed to create virtual environment"
            exit 1
        fi
    else
        print_success "Virtual environment found at ${PROJECT_DIR}/venv"
    fi
}

# Check if run.py exists
check_run_script() {
    print_info "Checking for run.py..."
    
    if [ ! -f "${PROJECT_DIR}/run.py" ]; then
        print_error "run.py not found at ${PROJECT_DIR}/run.py"
        exit 1
    fi
    
    print_success "run.py found"
}

# Create logs directory
create_logs_dir() {
    print_info "Setting up logs directory..."
    
    mkdir -p "${PROJECT_DIR}/logs"
    chown "$ACTUAL_USER:$ACTUAL_USER" "${PROJECT_DIR}/logs"
    
    print_success "Logs directory ready at ${PROJECT_DIR}/logs"
}

# Create systemd service file
create_service_file() {
    print_info "Creating systemd service file..."
    
    cat > "$SYSTEMD_PATH" << EOF
[Unit]
Description=Flotation Control System
Documentation=https://github.com/yourusername/flotation-control
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"

# Main execution command
ExecStart=${PROJECT_DIR}/venv/bin/python ${PROJECT_DIR}/run.py

# Restart policy
Restart=always
RestartSec=10

# Resource limits (optional - adjust as needed)
# MemoryLimit=512M
# CPUQuota=80%

# Logging
StandardOutput=append:${PROJECT_DIR}/logs/flotation.log
StandardError=append:${PROJECT_DIR}/logs/flotation-error.log
SyslogIdentifier=${SERVICE_NAME}

# Security hardening (optional)
# NoNewPrivileges=true
# PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    print_success "Service file created at $SYSTEMD_PATH"
}

# Display service file content
display_service_file() {
    print_header "Service File Content"
    cat "$SYSTEMD_PATH"
    echo ""
}

# Install and enable the service
install_service() {
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload
    print_success "Systemd daemon reloaded"
    
    print_info "Enabling ${SERVICE_NAME} service..."
    systemctl enable "$SERVICE_NAME"
    print_success "Service enabled for auto-start on boot"
}

# Start the service
start_service() {
    print_info "Starting ${SERVICE_NAME} service..."
    
    if systemctl start "$SERVICE_NAME"; then
        print_success "Service started successfully"
    else
        print_error "Failed to start service"
        print_info "Check logs with: sudo journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
}

# Check service status
check_service_status() {
    print_header "Service Status"
    systemctl status "$SERVICE_NAME" --no-pager || true
    echo ""
}

# Add user to gpio group if needed
setup_gpio_permissions() {
    print_info "Checking GPIO permissions..."
    
    if groups "$ACTUAL_USER" | grep -q "gpio"; then
        print_success "User $ACTUAL_USER is already in gpio group"
    else
        print_warning "Adding user $ACTUAL_USER to gpio group..."
        usermod -a -G gpio "$ACTUAL_USER"
        print_success "User added to gpio group (logout/login required for changes to take effect)"
    fi
}

# Create startup log rotation config
create_logrotate_config() {
    print_info "Setting up log rotation..."
    
    cat > "/etc/logrotate.d/${SERVICE_NAME}" << EOF
${PROJECT_DIR}/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $ACTUAL_USER $ACTUAL_USER
}
EOF

    print_success "Log rotation configured"
}

# Display final instructions
display_final_instructions() {
    print_header "Installation Complete!"
    
    print_success "The Flotation Control System has been configured to start automatically on boot"
    echo ""
    print_info "Useful Commands:"
    echo ""
    echo "  Check service status:"
    echo "    sudo systemctl status ${SERVICE_NAME}"
    echo ""
    echo "  View live logs:"
    echo "    sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "  View recent logs:"
    echo "    sudo journalctl -u ${SERVICE_NAME} -n 50"
    echo ""
    echo "  Stop the service:"
    echo "    sudo systemctl stop ${SERVICE_NAME}"
    echo ""
    echo "  Start the service:"
    echo "    sudo systemctl start ${SERVICE_NAME}"
    echo ""
    echo "  Restart the service:"
    echo "    sudo systemctl restart ${SERVICE_NAME}"
    echo ""
    echo "  Disable auto-start:"
    echo "    sudo systemctl disable ${SERVICE_NAME}"
    echo ""
    echo "  Re-enable auto-start:"
    echo "    sudo systemctl enable ${SERVICE_NAME}"
    echo ""
    print_info "Log Files:"
    echo "  Standard output: ${PROJECT_DIR}/logs/flotation.log"
    echo "  Error output:    ${PROJECT_DIR}/logs/flotation-error.log"
    echo ""
    print_info "Web Dashboard (when service is running):"
    echo "  http://$(hostname -I | awk '{print $1}'):8000"
    echo "  or http://localhost:8000"
    echo ""
    print_warning "Note: The service will start automatically on next reboot"
    print_info "To test, you can reboot now with: sudo reboot"
    echo ""
}

# Main execution
main() {
    print_header "Flotation Control System - Auto-Startup Setup"
    print_info "Project Directory: $PROJECT_DIR"
    print_info "Service Name: $SERVICE_NAME"
    echo ""
    
    # Run all setup steps
    check_sudo
    check_run_script
    check_venv
    create_logs_dir
    setup_gpio_permissions
    create_service_file
    display_service_file
    install_service
    create_logrotate_config
    start_service
    sleep 2  # Give service a moment to start
    check_service_status
    display_final_instructions
}

# Run main function
main
