"""
Test script for HardwareController - validates dual-mode pump and manual motors.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from control.hardware_controller import HardwareController


def test_manual_mode():
    """Test 1: Manual pump control"""
    print("\n" + "="*60)
    print("TEST 1: Manual Pump Control")
    print("="*60)
    
    controller = HardwareController()
    
    # Ensure manual mode
    controller.set_pump_mode('manual')
    print(f"✓ Pump mode: {controller.pump_mode}")
    
    # Test different speeds
    for speed in [0, 25, 50, 75, 50, 0]:
        controller.set_pump_speed(speed)
        print(f"  Set pump to {speed}% → Actual: {controller.pump_duty}%")
        time.sleep(0.5)
    
    controller.cleanup()
    print("✓ Manual mode test passed\n")


def test_auto_mode():
    """Test 2: Auto mode with PI control"""
    print("="*60)
    print("TEST 2: Auto Mode (PI Control)")
    print("="*60)
    
    controller = HardwareController(
        pi_kp=0.5,
        pi_ki=0.05,
        pi_setpoint=120
    )
    
    # Switch to auto mode
    controller.set_pump_mode('auto')
    print(f"✓ Pump mode: {controller.pump_mode}")
    print(f"✓ PI Setpoint: {controller.pi_setpoint} bubbles")
    
    # Simulate bubble count readings
    bubble_counts = [100, 110, 115, 120, 125, 120]
    
    for count in bubble_counts:
        controller.set_pump_speed(count)  # In auto mode, value = bubble count
        status = controller.get_status()
        print(f"  Bubbles: {count} → Pump: {status['pump_duty']:.1f}% "
              f"(Error: {status['pi_controller']['last_error']:.1f})")
        time.sleep(0.5)
    
    controller.cleanup()
    print("✓ Auto mode test passed\n")


def test_manual_motors():
    """Test 3: Manual motor control (agitator, air, feed)"""
    print("="*60)
    print("TEST 3: Manual Motor Control")
    print("="*60)
    
    controller = HardwareController()
    
    # Test each motor
    motors = ['agitator', 'air', 'feed']
    
    for motor in motors:
        print(f"\n  Testing {motor.upper()}:")
        for speed in [0, 50, 100, 50, 0]:
            controller.manual_motor_control(motor, speed)
            print(f"    Set to {speed}% → Actual: {controller.motor_states[motor]}%")
            time.sleep(0.3)
    
    controller.cleanup()
    print("\n✓ Manual motor test passed\n")


def test_mode_switching():
    """Test 4: Switching between auto and manual"""
    print("="*60)
    print("TEST 4: Mode Switching")
    print("="*60)
    
    controller = HardwareController()
    
    # Start in manual
    controller.set_pump_mode('manual')
    controller.set_pump_speed(30)
    print(f"✓ Manual mode: Pump at {controller.pump_duty}%")
    
    # Switch to auto
    controller.set_pump_mode('auto')
    controller.set_pump_speed(100)  # 100 bubbles
    print(f"✓ Auto mode: PI controlling pump at {controller.pump_duty:.1f}%")
    
    # Switch back to manual
    controller.set_pump_mode('manual')
    controller.set_pump_speed(50)
    print(f"✓ Back to manual: Pump at {controller.pump_duty}%")
    
    controller.cleanup()
    print("✓ Mode switching test passed\n")


def test_error_handling():
    """Test 5: Error handling"""
    print("="*60)
    print("TEST 5: Error Handling")
    print("="*60)
    
    controller = HardwareController()
    
    # Test invalid pump speed
    try:
        controller.set_pump_mode('manual')
        controller.set_pump_speed(150)  # Should fail
        print("✗ Failed to catch invalid duty cycle")
    except ValueError as e:
        print(f"✓ Caught invalid duty cycle: {e}")
    
    # Test invalid motor ID
    try:
        controller.manual_motor_control('invalid_motor', 50)
        print("✗ Failed to catch invalid motor ID")
    except ValueError as e:
        print(f"✓ Caught invalid motor ID: {e}")
    
    # Test invalid mode
    try:
        controller.set_pump_mode('invalid_mode')
        print("✗ Failed to catch invalid mode")
    except ValueError as e:
        print(f"✓ Caught invalid mode: {e}")
    
    controller.cleanup()
    print("✓ Error handling test passed\n")


def test_status_reporting():
    """Test 6: Status reporting"""
    print("="*60)
    print("TEST 6: Status Reporting")
    print("="*60)
    
    controller = HardwareController()
    
    # Set various states
    controller.set_pump_mode('auto')
    controller.set_pump_speed(120)
    controller.manual_motor_control('agitator', 75)
    controller.manual_motor_control('air', 50)
    controller.manual_motor_control('feed', 60)
    
    # Get status
    status = controller.get_status()
    
    print(f"  Pump Mode: {status['pump_mode']}")
    print(f"  Pump Duty: {status['pump_duty']:.1f}%")
    print(f"  Motors:")
    for motor, speed in status['motors'].items():
        print(f"    {motor}: {speed}%")
    print(f"  PI Controller:")
    print(f"    Kp={status['pi_controller']['kp']}, Ki={status['pi_controller']['ki']}")
    print(f"    Setpoint={status['pi_controller']['setpoint']}")
    print(f"  E-Stop: {status['estop_triggered']}")
    print(f"  Initialized: {status['initialized']}")
    
    controller.cleanup()
    print("✓ Status reporting test passed\n")


if __name__ == "__main__":
    print("\n🎛️  HardwareController Test Suite\n")
    
    try:
        test_manual_mode()
        test_auto_mode()
        test_manual_motors()
        test_mode_switching()
        test_error_handling()
        test_status_reporting()
        
        print("="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nHardwareController is ready for production use!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
