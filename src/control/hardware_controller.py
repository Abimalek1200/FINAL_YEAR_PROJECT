"""Unified hardware control: dual-mode pump (PI/manual), motors, E-Stop (GPIO 12-15,22)."""

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
    """Unified control: dual-mode pump + manual motors."""
    
    PIN_PERISTALTIC, PIN_AGITATOR, PIN_AIR_PUMP, PIN_FEED_PUMP, PIN_ESTOP = 12, 13, 14, 15, 22
    PWM_FREQUENCY = 1000
    
    def __init__(self, pi_kp: float = 0.5, pi_ki: float = 0.05, pi_setpoint: int = 120,
                 max_pump_duty: float = 80.0, estop_enabled: bool = True):
        """Initialize controller with PI params and safety limits."""
        self.pi_kp, self.pi_ki, self.pi_setpoint = pi_kp, pi_ki, pi_setpoint
        self.max_pump_duty, self.estop_enabled = max_pump_duty, estop_enabled
        self.pi_integral, self.pi_last_error = 0.0, 0.0
        
        self.pump_mode, self.pump_duty = 'manual', 0.0
        self.motor_states = {'agitator': 0.0, 'air': 0.0, 'feed': 0.0}
        self.chip, self.is_initialized, self.estop_triggered = None, False, False
        
        self._initialize_gpio()
    
    def _initialize_gpio(self) -> bool:
        """Initialize GPIO and configure all pins."""
        if not GPIO_AVAILABLE:
            logger.warning("GPIO not available - simulation mode")
            self.is_initialized = True
            return True
        
        try:
            self.chip = lgpio.gpiochip_open(0)
            
            for pin in [self.PIN_PERISTALTIC, self.PIN_AGITATOR, self.PIN_AIR_PUMP, self.PIN_FEED_PUMP]:
                lgpio.tx_pwm(self.chip, pin, self.PWM_FREQUENCY, 0)
            
            if self.estop_enabled:
                lgpio.gpio_claim_input(self.chip, self.PIN_ESTOP, lgpio.SET_PULL_UP)
            
            self.is_initialized = True
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
        self.pi_integral = 0.0
    
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
            return True
        except Exception as e:
            logger.error(f"PWM write failed for pin {pin}: {e}")
            return False
    
    def set_pump_mode(self, mode: str):
        """Switch pump mode: 'auto' (PI) or 'manual' (direct PWM)."""
        if mode not in ('auto', 'manual'):
            raise ValueError(f"Invalid mode: {mode}")
        old_mode = self.pump_mode
        self.pump_mode = mode
        if mode == 'auto' and old_mode != 'auto':
            self.pi_integral, self.pi_last_error = 0.0, 0.0
            logger.info("AUTO mode - PI reset")
        else:
            logger.info(f"{mode.upper()} mode activated")
    
    def set_pump_speed(self, value: float):
        """Control pump: manual=duty cycle (0-100%), auto=bubble count for PI."""
        if self.estop_triggered:
            logger.warning("Cannot control pump - E-Stop active")
            return
        
        if self.pump_mode == 'manual':
            if not 0 <= value <= 100:
                raise ValueError(f"Manual duty cycle must be 0-100%, got {value}")
            duty = min(value, self.max_pump_duty)
            self.pump_duty = duty
            self._set_pwm(self.PIN_PERISTALTIC, duty)
        else:
            duty = self._pi_update(value)
            self.pump_duty = duty
            self._set_pwm(self.PIN_PERISTALTIC, duty)
    
    def _pi_update(self, measured_value: float) -> float:
        """PI controller update for auto mode."""
        error = self.pi_setpoint - measured_value
        self.pi_integral += error
        self.pi_integral = max(-50, min(50, self.pi_integral))
        
        p_term = self.pi_kp * error
        i_term = self.pi_ki * self.pi_integral
        output = p_term + i_term
        
        duty = max(0.0, min(self.max_pump_duty, output))
        self.pi_last_error = error
        return duty
    
    def set_pi_parameters(self, kp: Optional[float] = None, ki: Optional[float] = None, 
                         setpoint: Optional[int] = None):
        """Update PI controller parameters."""
        if kp is not None:
            if kp < 0:
                raise ValueError("Kp must be non-negative")
            self.pi_kp = kp
        
        if ki is not None:
            if ki < 0:
                raise ValueError("Ki must be non-negative")
            self.pi_ki = ki
        
        if setpoint is not None:
            if setpoint < 0:
                raise ValueError("Setpoint must be non-negative")
            self.pi_setpoint = setpoint
            self.pi_integral = 0.0
        
        logger.info(f"PI updated: Kp={self.pi_kp}, Ki={self.pi_ki}, Setpoint={self.pi_setpoint}")
    
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
                'kp': self.pi_kp,
                'ki': self.pi_ki,
                'setpoint': self.pi_setpoint,
                'integral': self.pi_integral,
                'last_error': self.pi_last_error
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
        
        self.is_initialized = False
        self.chip = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def __del__(self):
        if self.is_initialized:
            self.cleanup()
