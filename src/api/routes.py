"""REST API routes: metrics, control, status."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api"])


# Request/response models
class MetricsResponse(BaseModel):
    """Current froth metrics."""
    bubble_count: int
    avg_bubble_size: float
    size_std_dev: float
    froth_coverage: float = Field(ge=0, le=1)
    froth_stability: float = Field(ge=0, le=1)
    pump_duty: float = Field(ge=0, le=100)
    timestamp: str


class PumpModeRequest(BaseModel):
    """Set pump mode."""
    mode: str = Field(pattern="^(auto|manual)$")


class PumpSpeedRequest(BaseModel):
    """Set manual pump speed."""
    duty_cycle: float = Field(ge=0, le=100)


class PIParametersRequest(BaseModel):
    """Update PI controller parameters."""
    kp: float = Field(default=None, ge=0, le=10)
    ki: float = Field(default=None, ge=0, le=1)
    setpoint: int = Field(default=None, ge=0, le=500)


class MotorControlRequest(BaseModel):
    """Control manual motors."""
    motor_id: str = Field(pattern="^(agitator|air|feed)$")
    duty_cycle: float = Field(ge=0, le=100)


def get_state():
    """Get system state from main module."""
    from .main import get_system_state
    return get_system_state()


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get current froth metrics."""
    try:
        return get_state()['current_metrics']
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """Get system status."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        return {
            'running': state['running'],
            'pump_mode': state['pump_mode'],
            'hardware_status': controller.get_status() if controller else {},
            'motor_states': state['motor_states']
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pump/mode")
async def set_pump_mode(request: PumpModeRequest):
    """Switch pump mode between auto/manual."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        controller.set_pump_mode(request.mode)
        state['pump_mode'] = request.mode
        
        return {"status": "ok", "mode": request.mode}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting pump mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pump/speed")
async def set_pump_speed(request: PumpSpeedRequest):
    """Set manual pump speed (manual mode only)."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        if state['pump_mode'] != 'manual':
            raise HTTPException(status_code=400, detail="Pump must be in manual mode")
        
        controller.set_pump_speed(request.duty_cycle)
        
        return {"status": "ok", "duty_cycle": request.duty_cycle}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting pump speed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pi/parameters")
async def update_pi_parameters(request: PIParametersRequest):
    """Update PI controller parameters (auto mode)."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        controller.set_pi_parameters(
            kp=request.kp,
            ki=request.ki,
            setpoint=request.setpoint
        )
        
        return {
            "status": "ok",
            "parameters": {
                "kp": controller.pi_kp,
                "ki": controller.pi_ki,
                "setpoint": controller.pi_setpoint
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating PI parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/motor/control")
async def control_motor(request: MotorControlRequest):
    """Control manual motors (agitator, air, feed)."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        controller.manual_motor_control(request.motor_id, request.duty_cycle)
        state['motor_states'][request.motor_id] = request.duty_cycle
        
        return {
            "status": "ok",
            "motor": request.motor_id,
            "duty_cycle": request.duty_cycle
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error controlling motor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop")
async def emergency_stop():
    """Emergency stop all devices."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        controller.stop_all()
        
        return {"status": "ok", "message": "All devices stopped"}
    except Exception as e:
        logger.error(f"Error in emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))
