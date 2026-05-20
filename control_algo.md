# PI Control Algorithm for Auto Mode

This document outlines the current control algorithm used in the flotation system's "auto" mode. It uses a standard Proportional-Integral (PI) controller to regulate the frother dosing pump based on real-time bubble count data from the vision system.

## Current Context:
- The `HardwareController` class manages all hardware, including the frother pump via PWM.
- The vision system provides a `bubble_count` metric.
- The auto mode uses a PI controller to adjust the frother dosing pump duty cycle.

## Control Algorithm Principle:

### Control Variables:
- **Process Variable (PV)**: `bubble_count` from the vision system.
- **Setpoint (SP)**: The desired `bubble_count`, configured in `config/control_config.json`.
- **Manipulated Variable (MV)**: The PWM duty cycle of the frother dosing pump.

### PI Control Logic:

The core of the control logic resides in the `_pi_update` method within the `HardwareController`.

1.  **Error Calculation**: The controller continuously calculates the error:
    `error = setpoint - measured_value`
    Where `measured_value` is the current `bubble_count`.

2.  **Proportional (P) Term**: This term provides an immediate response proportional to the current error. A larger error results in a larger and more immediate adjustment to the pump speed.
    `p_term = Kp * error`

3.  **Integral (I) Term**: This term accumulates the error over time. It is responsible for eliminating steady-state error, ensuring the system reaches the setpoint even with small, persistent deviations.
    `self.pi_integral += error`
    `i_term = Ki * self.pi_integral`

4.  **Anti-Windup**: To prevent the integral term from growing too large (which can cause significant overshooting), it is clamped within a predefined range (e.g., -50 to 50).

5.  **Output Calculation**: The final output is the sum of the P and I terms. This value is then clamped to ensure it stays within the safe operating limits of the pump (e.g., 0% to 80% duty cycle).
    `output = p_term + i_term`
    `duty_cycle = max(0.0, min(max_pump_duty, output))`

### Control Cycle Structure:
1.  The `control_loop` in `api/main.py` runs periodically (e.g., every 1 second).
2.  It retrieves the latest `bubble_count` from the shared system state.
3.  If the system is in 'auto' mode, it calls the `set_pump_speed` method of the `HardwareController`, passing the `bubble_count`.
4.  The `HardwareController` internally calls its `_pi_update` method to get the new calculated duty cycle.
5.  The controller applies this new duty cycle to the frother pump GPIO pin.
6.  This loop repeats, continuously adjusting the frother dosage to maintain the bubble count at the setpoint.

### Key Parameters (from `config/control_config.json`):
- **kp**: Proportional gain.
- **ki**: Integral gain.
- **setpoint**: The target bubble count.
- **max_duty_cycle**: The maximum allowable PWM duty cycle for the pump.