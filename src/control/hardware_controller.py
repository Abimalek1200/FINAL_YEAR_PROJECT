"""Unified hardware control: SIMO auto/manual control + E-Stop (GPIO 12-15,22)."""

import logging
import time
from typing import Dict, Optional

try:
    import lgpio
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("lgpio not available - simulation mode")

logger = logging.getLogger(__name__)


class HardwareController:
    """Unified control: SIMO auto loop + manual overrides."""
    
    PIN_PERISTALTIC, PIN_AGITATOR, PIN_AIR_PUMP, PIN_FEED_PUMP, PIN_ESTOP = 12, 13, 14, 15, 22
    # Indicator outputs requested by operator
    # Assign LEDs per user request:
    # GPIO 23 - RED: ON when abnormal condition detected
    # GPIO 24 - AMBER: ON when camera is NOT detected
    # GPIO 25 - GREEN: ON when any of the pumps are operational
    # GPIO 8  - WHITE: ON when the Pi/controller is powered/initialized
    PIN_LED_RED, PIN_LED_AMBER, PIN_LED_GREEN, PIN_LED_WHITE = 23, 24, 25, 8
    PWM_FREQUENCY = 3000

    # SIMO auto-control defaults (easy to tune)
    DEADBAND = 5
    DOSING_DURATION = 5.0
    STABILIZATION_WAIT = 15.0

    DOSING_MIN_PWM = 50.0
    DOSING_MAX_PWM = 100.0
    DOSING_ERROR_MIN = 10.0
    DOSING_ERROR_MAX = 60.0

    AIR_MAX_PWM = 60.0
    AIR_MIN_PWM = 50.0
    AIR_ERROR_MIN = 10.0
    AIR_ERROR_MAX = 45.0
    
    def __init__(self, target_bubble_count: int = 85,
                 max_pump_duty: float = 80.0, estop_enabled: bool = True):
        """Initialize controller with SIMO setpoint, limits, and safety settings."""
        self.target_bubble_count = target_bubble_count
        self.max_pump_duty, self.estop_enabled = max_pump_duty, estop_enabled
        
        self.pump_mode, self.pump_duty = 'manual', 0.0
        self.motor_states = {'agitator': 0.0, 'air': 0.0, 'feed': 0.0}
        self.chip, self.is_initialized, self.estop_triggered = None, False, False
        # LED state flags
        self.led_states = {'red': False, 'amber': False, 'green': False, 'white': False}

        # SIMO auto-control state
        self.auto_dosing_active = False
        self.auto_dose_end_time = 0.0
        self.auto_next_dose_allowed_time = 0.0
        self.auto_last_dosing_pwm = 0.0
        
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
                logger.critical("EMERGENCY STOP TRIGGERED")
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
        """Switch pump mode: 'auto' (SIMO) or 'manual' (direct PWM)."""
        if mode not in ('auto', 'manual'):
            raise ValueError(f"Invalid mode: {mode}")
        old_mode = self.pump_mode
        self.pump_mode = mode
        if mode == 'auto' and old_mode != 'auto':
            self.auto_dosing_active = False
            self.auto_dose_end_time = 0.0
            self.auto_next_dose_allowed_time = 0.0
            self.auto_last_dosing_pwm = 0.0

            # Auto mode default: air at maximum allowed auto value
            self.motor_states['air'] = self.AIR_MAX_PWM
            self._set_pwm(self.PIN_AIR_PUMP, self.AIR_MAX_PWM)

            logger.info("AUTO mode enabled - SIMO control reset, air set to 45%")
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

    @staticmethod
    def _map_linear(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        """Linearly map value from one range to another, with input clamped."""
        if in_max <= in_min:
            return out_min
        clamped = max(in_min, min(in_max, value))
        ratio = (clamped - in_min) / (in_max - in_min)
        return out_min + ratio * (out_max - out_min)

    def map_dosing_rate(self, error_bubbles: float) -> float:
        """Map low-count error (10-60) to dosing PWM (10-80%), then clamp by safety max."""
        duty = self._map_linear(
            error_bubbles,
            self.DOSING_ERROR_MIN,
            self.DOSING_ERROR_MAX,
            self.DOSING_MIN_PWM,
            self.DOSING_MAX_PWM
        )
        return max(self.DOSING_MIN_PWM, min(self.max_pump_duty, duty))

    def map_air_rate(self, error_bubbles: float) -> float:
        """Map high-count error (10-45) to air PWM (45 down to 35%) with strict bounds."""
        duty = self._map_linear(
            error_bubbles,
            self.AIR_ERROR_MIN,
            self.AIR_ERROR_MAX,
            self.AIR_MAX_PWM,
            self.AIR_MIN_PWM
        )
        return max(self.AIR_MIN_PWM, min(self.AIR_MAX_PWM, duty))

    def auto_control_step(self, bubble_count: float, now: Optional[float] = None):
        """Run one non-blocking SIMO control step in auto mode.

        Rules:
        - Deadband ±5 around setpoint: hold current states.
        - Below setpoint: dose for 5s at mapped PWM (10-80), then wait 15s before next dose.
        - Above setpoint: reduce air duty from 45% toward 35% immediately.
        - In auto mode, air defaults to 45% when not reduced.
        """
        if self.pump_mode != 'auto' or self.estop_triggered:
            return

        t_now = time.monotonic() if now is None else now
        error = float(self.target_bubble_count) - float(bubble_count)

        # Complete active dosing window
        if self.auto_dosing_active:
            if t_now < self.auto_dose_end_time:
                self.pump_duty = self.auto_last_dosing_pwm
                self._set_pwm(self.PIN_PERISTALTIC, self.auto_last_dosing_pwm)
            else:
                self.auto_dosing_active = False
                self.pump_duty = 0.0
                self._set_pwm(self.PIN_PERISTALTIC, 0.0)
                self.auto_next_dose_allowed_time = t_now + self.STABILIZATION_WAIT
                logger.info(
                    f"Auto dosing complete. Stabilization wait: {self.STABILIZATION_WAIT:.1f}s"
                )

        # Deadband: no corrective action, keep current state
        if abs(error) <= self.DEADBAND:
            return

        # Below setpoint: dosing logic + default air max
        if error > 0:
            self.motor_states['air'] = self.AIR_MAX_PWM
            self._set_pwm(self.PIN_AIR_PUMP, self.AIR_MAX_PWM)

            can_start_dose = (not self.auto_dosing_active) and (t_now >= self.auto_next_dose_allowed_time)
            if can_start_dose:
                dosing_pwm = self.map_dosing_rate(error)
                self.auto_last_dosing_pwm = dosing_pwm
                self.auto_dosing_active = True
                self.auto_dose_end_time = t_now + self.DOSING_DURATION

                self.pump_duty = dosing_pwm
                self._set_pwm(self.PIN_PERISTALTIC, dosing_pwm)
                logger.info(
                    f"Auto dosing started: bubble_count={bubble_count:.1f}, "
                    f"error={error:.1f}, duty={dosing_pwm:.1f}%, duration={self.DOSING_DURATION:.1f}s"
                )
            return

        # Above setpoint: immediate air reduction, no extra wait
        high_error = abs(error)
        new_air_pwm = self.map_air_rate(high_error)
        self.motor_states['air'] = new_air_pwm
        self._set_pwm(self.PIN_AIR_PUMP, new_air_pwm)

        # Ensure dosing pump is off when count is high and no active dosing window
        if not self.auto_dosing_active:
            self.pump_duty = 0.0
            self._set_pwm(self.PIN_PERISTALTIC, 0.0)
    
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
            'auto_control': {
                'setpoint': self.target_bubble_count,
                'deadband': self.DEADBAND,
                'dosing_duration_s': self.DOSING_DURATION,
                'stabilization_wait_s': self.STABILIZATION_WAIT,
                'auto_dosing_active': self.auto_dosing_active,
                'next_dose_allowed_in_s': max(0.0, self.auto_next_dose_allowed_time - time.monotonic())
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
