"""Unified hardware control: auto/manual control + E-Stop (GPIO 12-15,2)."""

import logging
from typing import Dict

try:
    import lgpio
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("lgpio not available - simulation mode")

logger = logging.getLogger(__name__)


class HardwareController:
    """Unified control: PI auto loop + manual overrides."""
    
    PIN_PERISTALTIC, PIN_AGITATOR, PIN_AIR_PUMP, PIN_FEED_PUMP, PIN_ESTOP = 12, 13, 14, 15, 2
    # Indicator outputs requested by operator
    # Assign LEDs per user request:
    # GPIO 23 - RED: ON when abnormal condition detected
    # GPIO 24 - AMBER: ON when camera is NOT detected
    # GPIO 25 - GREEN: ON when any of the pumps are operational
    # GPIO 8  - WHITE: ON when the Pi/controller is powered/initialized
    PIN_LED_RED, PIN_LED_AMBER, PIN_LED_GREEN, PIN_LED_WHITE = 23, 24, 25, 8
    PWM_FREQUENCY = 3000

    def __init__(self, target_bubble_count: int = 100,
                 max_pump_duty: float = 80.0, estop_enabled: bool = True):
        """Initialize controller with setpoint, limits, and safety settings."""
        self.target_bubble_count = target_bubble_count
        self.max_pump_duty, self.estop_enabled = max_pump_duty, estop_enabled
        
        self.pump_mode, self.pump_duty = 'manual', 0.0
        self.motor_states = {'agitator': 0.0, 'air': 0.0, 'feed': 0.0}
        self.chip, self.is_initialized, self.estop_triggered = None, False, False
        # LED state flags
        self.led_states = {'red': False, 'amber': False, 'green': False, 'white': False}

        # PI controller defaults (student-friendly auto mode)
        self.pi_kp = 1.0
        self.pi_ki = 0.001
        self.pi_integral = 0.0
        self.pi_last_error = 0.0

        # Requested auto-control attributes
        self.control_period = 15.0
        self.frother_deadband = 10.0
        self.max_auto_frother_duty = 80.0
        self.running_frother_duty = 40.0
        self.integral_limit = 20.0
        self.integral_bleed_on_target = 0.7
        self.integral_bleed_above_target = 0.5
        self.dosing_frozen = False
        self.no_response_cycles = 0
        self.no_response_limit = 5
        self.response_threshold = 10.0
        self.min_active_duty = 2.0
        self.last_control_count = None
        self.auto_state = "MANUAL"
        self.air_normal_duty = 75.0
        self.air_min_duty = 60.0
        self.air_reduce_start = 20.0
        self.air_full_reduce = 50.0
        self.air_auto_duty = 75.0

        self._initialize_gpio()
    
    def _initialize_gpio(self) -> bool:
        """Initialize GPIO and configure all pins."""
        if not GPIO_AVAILABLE:
            logger.warning("GPIO not available - simulation mode")
            self.is_initialized = True
            # In simulation mode, set white LED flag to True to indicate power
            self.led_states['white'] = True
            return True
        
        try:
            self.chip = lgpio.gpiochip_open(0)
            
            # Claim outputs for PWM-controlled devices
            for pin in [self.PIN_PERISTALTIC, self.PIN_AGITATOR, self.PIN_AIR_PUMP, self.PIN_FEED_PUMP]:
                lgpio.gpio_claim_output(self.chip, pin, lgpio.SET_PULL_NONE)
                lgpio.tx_pwm(self.chip, pin, self.PWM_FREQUENCY, 0)

            # Claim LED outputs (digital on/off)
            for led_pin in [self.PIN_LED_RED, self.PIN_LED_AMBER, self.PIN_LED_GREEN, self.PIN_LED_WHITE]:
                try:
                    lgpio.gpio_claim_output(self.chip, led_pin, lgpio.SET_PULL_NONE)
                except Exception:
                    # Some systems may not require claim; ignore if claim fails
                    pass
                # default all LEDs off, then enable white to signal power
                try:
                    lgpio.gpio_write(self.chip, led_pin, 0)
                except Exception:
                    pass
            
            if self.estop_enabled:
                lgpio.gpio_claim_input(self.chip, self.PIN_ESTOP, lgpio.SET_PULL_UP)
            
            # Turn on white LED to indicate controller is powered
            self.is_initialized = True
            try:
                self._set_led('white', True)
            except Exception:
                pass
            logger.info("GPIO initialized successfully")
            return True
        except Exception as e:
            logger.error(f"GPIO initialization failed: {e}")
            self.is_initialized = False
            return False
    
    def check_estop(self) -> bool:
        """Check E-Stop status (active when LOW)."""
        if not self.estop_enabled or not GPIO_AVAILABLE or not self.is_initialized:
            return False
        try:
            estop_state = lgpio.gpio_read(self.chip, self.PIN_ESTOP)
            self.estop_triggered = (estop_state == 0)
            if self.estop_triggered:
                logger.critical("🚨 EMERGENCY STOP TRIGGERED - Pin 2 is LOW (0V)")
                self._emergency_shutdown()
            return self.estop_triggered
        except Exception as e:
            logger.error(f"E-Stop check failed: {e}")
            return False
    
    def _emergency_shutdown(self):
        """Stop all devices immediately."""
        logger.critical("Executing emergency shutdown")
        for pin in [self.PIN_PERISTALTIC, self.PIN_AGITATOR, self.PIN_AIR_PUMP, self.PIN_FEED_PUMP]:
            self._set_pwm(pin, 0)
        self.pump_duty = 0.0
        self.motor_states = {k: 0.0 for k in self.motor_states}

        # Force manual mode so the PI controller cannot resume on next tick
        self.pump_mode = 'manual'
        self.auto_state = 'ESTOP'
        self.pi_integral = 0.0  # Clear integral to prevent burst when auto is re-entered
        
        # update green LED (no pumps running)
        try:
            self._set_led('green', False)
        except Exception:
            pass
    
    def _set_pwm(self, pin: int, duty_cycle: float) -> bool:
        """Set PWM duty cycle (0-100%)."""
        duty_cycle = max(0.0, min(100.0, duty_cycle))
        if not GPIO_AVAILABLE:
            logger.warning(f"SIMULATION MODE: Pin {pin} = {duty_cycle}% (lgpio not available)")
            return True
        if not self.is_initialized:
            logger.error(f"GPIO not initialized! Cannot set Pin {pin} to {duty_cycle}%")
            return False
        try:
            lgpio.tx_pwm(self.chip, pin, self.PWM_FREQUENCY, duty_cycle)
            logger.debug(f"GPIO PWM: Pin {pin} = {duty_cycle}% @ {self.PWM_FREQUENCY}Hz")
            # Update green LED state: any pump non-zero -> green ON
            try:
                # pumps configured on PERISTALTIC, AGITATOR, AIR, FEED pins
                any_running = False
                if pin == self.PIN_PERISTALTIC and duty_cycle > 0:
                    any_running = True
                else:
                    # evaluate current motor_states dict for non-zero values
                    any_running = any(v > 0 for v in self.motor_states.values()) or (self.pump_duty > 0)
                self._set_led('green', bool(any_running))
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"PWM write failed for pin {pin}: {e}")
            return False

    def _set_led(self, which: str, on: bool) -> bool:
        """Set an indicator LED by name: 'red','amber','green','white'."""
        if which not in self.led_states:
            raise ValueError(f"Invalid LED name: {which}")

        pin_map = {
            'red': self.PIN_LED_RED,
            'amber': self.PIN_LED_AMBER,
            'green': self.PIN_LED_GREEN,
            'white': self.PIN_LED_WHITE,
        }
        pin = pin_map[which]

        self.led_states[which] = bool(on)

        if not GPIO_AVAILABLE or not self.is_initialized:
            logger.debug(f"SIM: LED {which} (Pin {pin}) -> {'ON' if on else 'OFF'}")
            return True

        try:
            lgpio.gpio_write(self.chip, pin, 1 if on else 0)
            logger.debug(f"LED {which} (Pin {pin}) -> {'ON' if on else 'OFF'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set LED {which} (Pin {pin}): {e}")
            return False

    # Public helpers for external modules to signal conditions
    def set_abnormal(self, abnormal: bool):
        """Turn RED LED on when an abnormal condition (anomaly) is detected."""
        try:
            self._set_led('red', abnormal)
        except Exception:
            pass

    def set_camera_present(self, present: bool):
        """Amber ON when camera is NOT detected; so invert present flag."""
        try:
            self._set_led('amber', not bool(present))
        except Exception:
            pass

    def set_power_on(self, on: bool):
        """White LED indicates controller power/initialized state."""
        try:
            self._set_led('white', bool(on))
        except Exception:
            pass
    
    def set_pump_mode(self, mode: str):
        """Switch pump mode: 'auto' (PI) or 'manual' (direct PWM)."""
        if mode not in ('auto', 'manual'):
            raise ValueError(f"Invalid mode: {mode}")
        old_mode = self.pump_mode
        self.pump_mode = mode
        if mode == 'auto' and old_mode != 'auto':
            # Reset PI controller and no-response protection when entering auto
            self.pi_integral = 0.0
            self.pi_last_error = 0.0
            self.dosing_frozen = False
            self.no_response_cycles = 0
            self.last_control_count = None
            self.auto_state = "AUTO_RESET"

            # Default air duty for auto mode
            self.air_auto_duty = self.air_normal_duty
            self.motor_states['air'] = self.air_auto_duty
            self._set_pwm(self.PIN_AIR_PUMP, self.air_auto_duty)

            logger.info("AUTO mode enabled - PI control reset, air set to normal duty")
        else:
            logger.info(f"{mode.upper()} mode activated")
    
    def set_pump_speed(self, value: float):
        """Control pump in manual mode using direct duty cycle (0-100%)."""
        if self.estop_triggered:
            logger.warning("Cannot control pump - E-Stop active")
            return

        if self.pump_mode != 'manual':
            raise ValueError("Pump speed can only be set directly in manual mode")

        if not 0 <= value <= 100:
            raise ValueError(f"Manual duty cycle must be 0-100%, got {value}")

        duty = min(value, self.max_pump_duty)
        self.pump_duty = duty
        self._set_pwm(self.PIN_PERISTALTIC, duty)

    def _pi_update(self, measured_count: float) -> float:
        """Sampled PI control for frother dosing (auto mode only).

        Uses a deadband and integral bleeding to avoid overdosing.
        """
        setpoint = float(self.target_bubble_count)
        measured = float(measured_count)
        error = setpoint - measured

        # Frozen state: hold frother at 0 until auto is reset
        if self.dosing_frozen:
            self.auto_state = "FROZEN_NO_RESPONSE"
            return 0.0

        # Inside deadband: stop dosing and gently bleed integral
        if abs(error) <= self.frother_deadband:
            self.pi_integral = max(0.0, self.pi_integral * self.integral_bleed_on_target)
            self.auto_state = "ON_TARGET"
            self.no_response_cycles = 0
            return 0.0

        # Above target: stop dosing and bleed integral faster
        if error < -self.frother_deadband:
            self.pi_integral = max(0.0, self.pi_integral * self.integral_bleed_above_target)
            return 0.0

        # Below target: PI dosing
        full_scale_error = max(1.0, setpoint)
        error_ratio = max(0.0, min(1.0, error / full_scale_error))
        proportional_duty = self.pi_kp * self.max_auto_frother_duty * error_ratio

        proposed_integral = self.pi_integral + (self.pi_ki * error * self.control_period)
        proposed_integral = max(0.0, min(self.integral_limit, proposed_integral))

        raw_duty = proportional_duty + proposed_integral
        # Anti-windup: only accept integral growth when not saturated
        if raw_duty <= self.max_auto_frother_duty:
            self.pi_integral = proposed_integral
        else:
            raw_duty = proportional_duty + self.pi_integral

        duty = max(0.0, min(self.max_auto_frother_duty, raw_duty))
        self.auto_state = "FROTHER_PI_DOSING"
        return duty

    def _air_update(self, measured_count: float) -> float:
        """Automatic air correction when bubble count is clearly above setpoint."""
        setpoint = float(self.target_bubble_count)
        overshoot = float(measured_count) - setpoint

        if overshoot <= self.air_reduce_start:
            return self.air_normal_duty
        if overshoot >= self.air_full_reduce:
            return self.air_min_duty

        # Linear reduction between reduce_start and full_reduce
        ratio = (overshoot - self.air_reduce_start) / (self.air_full_reduce - self.air_reduce_start)
        return self.air_normal_duty - (ratio * (self.air_normal_duty - self.air_min_duty))

    def auto_control_from_count(self, measured_count: float) -> Dict:
        """Run sampled auto control from a bubble count measurement.

        Returns a summary dict for API state updates.
        """
        if self.pump_mode != 'auto':
            return {
                'frother_duty': self.pump_duty,
                'air_duty': self.motor_states.get('air', 0.0),
                'state': self.auto_state,
                'dosing_frozen': self.dosing_frozen,
                'no_response_cycles': self.no_response_cycles
            }

        if self.check_estop():
            return {
                'frother_duty': 0.0,
                'air_duty': 0.0,
                'state': 'ESTOP',
                'dosing_frozen': self.dosing_frozen,
                'no_response_cycles': self.no_response_cycles
            }

        previous_running_duty = self.running_frother_duty

        # Compute frother duty (PI) and air duty (auto correction)
        frother_duty = self._pi_update(measured_count)
        air_duty = self._air_update(measured_count)

        # No-response protection only when below target band
        below_band = float(measured_count) < (float(self.target_bubble_count) - self.frother_deadband)
        if below_band and not self.dosing_frozen:
            if self.last_control_count is not None:
                improvement = float(measured_count) - float(self.last_control_count)
                if previous_running_duty >= self.min_active_duty and improvement < self.response_threshold:
                    self.no_response_cycles += 1
                elif improvement >= self.response_threshold:
                    self.no_response_cycles = 0
            self.last_control_count = float(measured_count)

            if self.no_response_cycles >= self.no_response_limit:
                self.dosing_frozen = True
                self.pi_integral = 0.0
                frother_duty = 0.0
                self.auto_state = "FROZEN_NO_RESPONSE"
        elif not below_band:
            # Reset counter when on/above target band
            self.no_response_cycles = 0
            self.last_control_count = float(measured_count)

        # Set air-state labels when count is above target band
        if not self.dosing_frozen and float(measured_count) > (float(self.target_bubble_count) + self.frother_deadband):
            overshoot = float(measured_count) - float(self.target_bubble_count)
            if overshoot <= self.air_reduce_start:
                self.auto_state = "AIR_NORMAL"
            elif overshoot >= self.air_full_reduce:
                self.auto_state = "AIR_MINIMUM"
            else:
                self.auto_state = "AIR_REDUCING"

        # Apply outputs
        self.running_frother_duty = frother_duty
        self.pump_duty = frother_duty
        self.air_auto_duty = air_duty
        self.motor_states['air'] = air_duty

        self._set_pwm(self.PIN_PERISTALTIC, frother_duty)
        self._set_pwm(self.PIN_AIR_PUMP, air_duty)

        return {
            'frother_duty': frother_duty,
            'air_duty': air_duty,
            'state': self.auto_state,
            'dosing_frozen': self.dosing_frozen,
            'no_response_cycles': self.no_response_cycles
        }
    
    def set_auto_setpoint(self, setpoint: int):
        """Update AUTO-mode target bubble count setpoint."""
        if setpoint < 0:
            raise ValueError("Setpoint must be non-negative")

        self.target_bubble_count = setpoint
        logger.info(f"Auto setpoint updated: {self.target_bubble_count}")
    
    def manual_motor_control(self, motor_id: str, pwm_value: float):
        """Control manual motors ('agitator', 'air', 'feed') with PWM (0-100%)."""
        logger.info(f"Motor control request: {motor_id} = {pwm_value}%")
        
        if self.estop_triggered:
            logger.warning("Cannot control motors - E-Stop active")
            return
        
        if motor_id not in self.motor_states:
            raise ValueError(f"Invalid motor_id: {motor_id}")
        
        if not 0 <= pwm_value <= 100:
            raise ValueError(f"PWM value must be 0-100%, got {pwm_value}")
        
        pin_map = {'agitator': self.PIN_AGITATOR, 'air': self.PIN_AIR_PUMP, 'feed': self.PIN_FEED_PUMP}
        pin = pin_map[motor_id]
        self.motor_states[motor_id] = pwm_value
        success = self._set_pwm(pin, pwm_value)
        
        if success:
            logger.info(f"✓ Motor {motor_id} set to {pwm_value}% (Pin {pin})")
        else:
            logger.error(f"✗ Failed to set motor {motor_id} to {pwm_value}%")
    
    def get_status(self) -> Dict:
        """Get current hardware status."""
        return {
            'pump_mode': self.pump_mode,
            'pump_duty': self.pump_duty,
            'motors': self.motor_states.copy(),
            'pi_controller': {
                'setpoint': self.target_bubble_count,
                'kp': self.pi_kp,
                'ki': self.pi_ki,
                'auto_state': self.auto_state,
                'dosing_frozen': self.dosing_frozen,
                'no_response_cycles': self.no_response_cycles,
                'control_period': self.control_period,
                'max_auto_frother_duty': self.max_auto_frother_duty,
                'air_auto_duty': self.air_auto_duty,
                'air_normal_duty': self.air_normal_duty,
                'air_min_duty': self.air_min_duty
            },
            'estop_triggered': self.estop_triggered,
            'initialized': self.is_initialized
        }
    
    def stop_all(self):
        """Stop all motors and pumps (non-emergency)."""
        logger.info("Stopping all devices")
        for pin in [self.PIN_PERISTALTIC, self.PIN_AGITATOR, self.PIN_AIR_PUMP, self.PIN_FEED_PUMP]:
            self._set_pwm(pin, 0)
        self.pump_duty = 0.0
        self.motor_states = {k: 0.0 for k in self.motor_states}
        try:
            self._set_led('green', False)
        except Exception:
            pass
    
    def cleanup(self):
        """Release all GPIO resources."""
        logger.info("Cleaning up GPIO resources")
        self.stop_all()
        
        if GPIO_AVAILABLE and self.chip is not None:
            try:
                lgpio.gpiochip_close(self.chip)
                logger.info("GPIO resources released")
            except Exception as e:
                logger.error(f"GPIO cleanup error: {e}")
        try:
            # turn off white LED when cleaning up
            self._set_led('white', False)
        except Exception:
            pass

        self.is_initialized = False
        self.chip = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def __del__(self):
        if self.is_initialized:
            self.cleanup()
