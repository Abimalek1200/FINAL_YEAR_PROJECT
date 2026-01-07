"""
GPIO Diagnostic Tool - Test motor control from dashboard
Run this to verify GPIO is working and check what the dashboard sees
"""
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_gpio_init():
    """Test 1: Check if GPIO initializes properly"""
    print("\n" + "="*60)
    print("TEST 1: GPIO Initialization")
    print("="*60)
    
    from control.hardware_controller import HardwareController, GPIO_AVAILABLE
    
    print(f"GPIO Library Available: {GPIO_AVAILABLE}")
    
    if not GPIO_AVAILABLE:
        print("⚠ WARNING: lgpio not available - running in SIMULATION mode")
        print("  Install with: sudo apt install python3-lgpio")
        print()
    
    controller = HardwareController()
    print(f"Controller Initialized: {controller.is_initialized}")
    print(f"E-Stop Enabled: {controller.estop_enabled}")
    print(f"E-Stop Triggered: {controller.estop_triggered}")
    print()
    
    return controller


def test_motor_control(controller):
    """Test 2: Test manual motor control"""
    print("="*60)
    print("TEST 2: Manual Motor Control")
    print("="*60)
    
    test_motors = [
        ('agitator', 50),
        ('air', 75),
        ('feed', 25)
    ]
    
    for motor_id, duty in test_motors:
        print(f"\nTesting {motor_id} at {duty}%...")
        try:
            controller.manual_motor_control(motor_id, duty)
            state = controller.motor_states[motor_id]
            print(f"  State updated: {state}%")
            print(f"  ✓ {motor_id} command sent successfully")
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
    
    print()


def test_status_endpoint():
    """Test 3: Check what the API returns"""
    print("="*60)
    print("TEST 3: API Status Check")
    print("="*60)
    
    import requests
    
    try:
        response = requests.get('http://localhost:8000/api/status', timeout=5)
        print(f"HTTP Status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print("\nStatus Response:")
            print(f"  Running: {data.get('running')}")
            print(f"  Pump Mode: {data.get('pump_mode')}")
            print(f"  Motor States: {data.get('motor_states')}")
            print(f"  Hardware Status: {data.get('hardware_status', {})}")
            print("  ✓ API responding correctly")
        else:
            print(f"  ✗ API error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("  ✗ Cannot connect to API - is the server running?")
        print("    Start with: python run.py")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print()


def test_motor_api():
    """Test 4: Test motor control via API"""
    print("="*60)
    print("TEST 4: Motor Control API")
    print("="*60)
    
    import requests
    
    test_command = {
        'motor_id': 'agitator',
        'duty_cycle': 60.0
    }
    
    try:
        print(f"\nSending: {test_command}")
        response = requests.post(
            'http://localhost:8000/api/motor/control',
            json=test_command,
            timeout=5
        )
        
        print(f"HTTP Status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print(f"Response: {data}")
            print("  ✓ Motor control API working")
        else:
            error = response.json()
            print(f"  ✗ API error: {error.get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        print("  ✗ Cannot connect to API - is the server running?")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print()


def main():
    print("\n" + "="*60)
    print("GPIO DIAGNOSTIC TOOL")
    print("="*60)
    
    # Test 1: GPIO Initialization
    controller = test_gpio_init()
    
    # Test 2: Direct motor control
    test_motor_control(controller)
    
    # Clean up
    controller.stop_all()
    
    print("="*60)
    print("API TESTS (requires server running)")
    print("="*60)
    
    # Test 3: Status endpoint
    test_status_endpoint()
    
    # Test 4: Motor control API
    test_motor_api()
    
    # Cleanup
    controller.cleanup()
    
    print("="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)
    print("\nWhat to check:")
    print("  1. If 'SIMULATION MODE' appears, install lgpio:")
    print("     sudo apt install python3-lgpio python3-rpi-lgpio")
    print("  2. Check server logs for 'Motor control request' messages")
    print("  3. Use multimeter to verify PWM output on GPIO pins 13, 14, 15")
    print("  4. Verify no E-Stop condition is active (pin 22)")
    print()


if __name__ == "__main__":
    main()
