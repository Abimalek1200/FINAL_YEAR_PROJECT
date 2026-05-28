"""REST API routes: metrics, control, status."""

import logging
from pathlib import Path

import numpy as np
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


class ControlParametersRequest(BaseModel):
    """Update SIMO auto-control parameters."""
    setpoint: int = Field(default=None, ge=0, le=500)


class MotorControlRequest(BaseModel):
    """Control manual motors."""
    motor_id: str = Field(pattern="^(agitator|air|feed)$")
    duty_cycle: float = Field(ge=0, le=100)


class TrainModelRequest(BaseModel):
    """Trigger anomaly model training from collected metrics."""
    sample_limit: int = Field(default=1000, ge=100, le=10000)
    save_model: bool = Field(default=True)


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
        
        # Read from controller (single source of truth), not state dict
        return {
            'running': state['running'],
            'pump_mode': controller.pump_mode if controller else 'manual',
            'hardware_status': controller.get_status() if controller else {},
            'motor_states': controller.motor_states.copy() if controller else {}
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
        state['pump_mode'] = controller.pump_mode  # Sync from controller (single source of truth)
        # On mode switch, sync motor states from controller to state
        state['motor_states'] = controller.motor_states.copy()
        
        return {"status": "ok", "mode": controller.pump_mode}
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


@router.post("/simo/parameters")
async def update_simo_parameters(request: ControlParametersRequest):
    """Update SIMO auto-control parameters."""
    try:
        state = get_state()
        controller = state['hardware_controller']
        
        if not controller:
            raise HTTPException(status_code=503, detail="Controller not initialized")
        
        if request.setpoint is not None:
            controller.set_auto_setpoint(request.setpoint)
        
        return {
            "status": "ok",
            "parameters": {
                "setpoint": controller.target_bubble_count
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


@router.post("/ml/train")
async def train_anomaly_model(request: TrainModelRequest):
    """Train anomaly detector from recently collected metrics."""
    try:
        state = get_state()
        detector = state.get('anomaly_detector')
        data_manager = state.get('data_manager')

        if detector is None or data_manager is None:
            raise HTTPException(status_code=503, detail="ML components not initialized")

        training_rows = data_manager.get_training_data(limit=request.sample_limit)
        sample_count = len(training_rows)

        if sample_count < 100:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough training data. Need at least 100 samples, have {sample_count}."
            )

        # DataManager returns [bubble_count, avg_size, std_dev, coverage_ratio]
        training_data = np.array(training_rows, dtype=float)
        detector.train(training_data)

        project_root = Path(__file__).resolve().parents[2]
        model_path = project_root / "models" / "anomaly_detector.pkl"
        if request.save_model:
            detector.save(str(model_path))

        return {
            "status": "ok",
            "message": "Anomaly model trained successfully",
            "sample_count": sample_count,
            "saved": bool(request.save_model),
            "model_path": str(model_path) if request.save_model else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error training anomaly model: {e}")
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
