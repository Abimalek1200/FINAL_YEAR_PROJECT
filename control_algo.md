I need to replace the existing auto mode control algorithm in my froth flotation control system with a new single-input-multiple-output (SIMO) control loop. The system runs on a Raspberry Pi 5 with Python.

## Current Context:
- I have a working `HardwareController` class that controls pumps via PWM (0-100% duty cycle)
- I have a vision system that provides `current_metrics['bubble_count']`
- The existing auto mode uses a PI controller on the dosing pump only
- I want to replace this with a SIMO approach controlling BOTH dosing pump AND air pump

## New Control Algorithm Requirements:

### Control Variables:
- **Process Variable (PV)**: bubble_count from vision metrics
- **Setpoint**: target_bubble_count (e.g., 120)
- **Actuator 1**: Dosing pump (frother addition)
- **Actuator 2**: Air pump (air flow rate)

### Control Logic:

#### Dosing Pump Control (when count < setpoint):
- IF bubble_count < setpoint:
  - Calculate error = setpoint - bubble_count (range: 10 to 60 bubbles low)
  - Map error to dosing rate (PWM duty cycle) from 10% to 80%
  - Error 10 → 10% duty, Error 60 → 80% duty (linear mapping)
  - Open dosing pump at calculated rate for exactly 5 seconds
  - After dosing, wait 15 seconds for system to stabilize before next action

#### Air Pump Control (when count > setpoint):
- IF bubble_count > setpoint:
  - Calculate error = bubble_count - setpoint (range: 10 to 45 bubbles high)
  - Map error to air pump duty cycle from 45% DOWN to 35%
  - Error 10 → 45% duty, Error 45 → 35% duty (linear mapping)
  - Air pump duty cycle MUST stay strictly within 35-45% range (never below 35%, never above 45%)
  - Apply air adjustment immediately (no wait period needed)

#### Air Pump Default State:
- When in AUTO mode, air pump starts at 45% duty cycle (maximum)
- Only reduce air duty when bubble_count > setpoint
- If bubble_count < setpoint, air duty returns to 45%
- Air duty never goes above 45% (max) or below 35% (min)

### Control Cycle Structure:
1. Check bubble_count from vision metrics
2. Compare to setpoint
3. IF count < setpoint: 
   - Calculate dosing rate (10-80% PWM based on error)
   - Run dosing pump at that rate for 5 seconds
   - Wait 15 seconds (system stabilization)
4. IF count > setpoint:
   - Calculate reduced air duty (45-35% based on error)
   - Set air pump to new duty (immediately)
   - No wait period (air effect is faster)
5. IF count == setpoint (within deadband of ±5 bubbles):
   - No action, maintain current state

### Parameters (easy to change):
- TARGET_SETPOINT = 120 (bubbles)
- DEADBAND = 5 (bubbles)
- DOSING_DURATION = 5 (seconds)
- STABILIZATION_WAIT = 15 (seconds)
- DOSING_MIN_PWM = 10 (%)
- DOSING_MAX_PWM = 80 (%)
- DOSING_ERROR_MIN = 10 (bubbles low)
- DOSING_ERROR_MAX = 60 (bubbles low)
- AIR_MAX_PWM = 45 (%)
- AIR_MIN_PWM = 35 (%)
- AIR_ERROR_MIN = 10 (bubbles high)
- AIR_ERROR_MAX = 45 (bubbles high)

### Error Mapping Functions:
```python
def map_dosing_rate(error_bubbles):
    """Map error (10-60) to PWM (10-80%) linearly"""
    # error_bubbles is how many bubbles below setpoint
    pass

def map_air_rate(error_bubbles):
    """Map error (10-45) to PWM (45% down to 35%) linearly"""
    # error_bubbles is how many bubbles above setpoint
    pass