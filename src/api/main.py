"""FastAPI app: vision processing, hardware control, WebSocket streaming."""

import logging
import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import routes, websocket
from .metrics_smoothing import TimeWindowMovingAverage
from time import monotonic

logger = logging.getLogger(__name__)

DEFAULT_TARGET_SETPOINT = 100
DEFAULT_MAX_PUMP_DUTY = 80.0


def _load_control_defaults() -> tuple[int, float]:
    """Load setpoint and pump limits from config/control_config.json with safe fallbacks."""
    try:
        project_root = Path(__file__).resolve().parents[2]
        control_config_path = project_root / "config" / "control_config.json"

        with control_config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)

        pi_cfg = cfg.get("pi_controller", {})
        pump_cfg = cfg.get("frother_pump", {})

        setpoint = int(pi_cfg.get("setpoint", DEFAULT_TARGET_SETPOINT))
        max_duty = float(pump_cfg.get("max_duty_cycle", DEFAULT_MAX_PUMP_DUTY))

        return setpoint, max_duty
    except Exception as e:
        logger.warning(f"Could not load control config defaults: {e}. Using built-in defaults.")
        return DEFAULT_TARGET_SETPOINT, DEFAULT_MAX_PUMP_DUTY

# Global system state
system_state = {
    'vision_processor': None,
    'hardware_controller': None,
    'anomaly_detector': None,
    'data_manager': None,
    'running': False,
    'camera_present': None,
    'current_metrics': {
        'bubble_count': 0,
        'avg_bubble_size': 0.0,
        'size_std_dev': 0.0,
        'froth_coverage': 0.0,
        'froth_stability': 0.0,
        'pump_duty': 0.0,
        'timestamp': ''
    },
    'bubble_count_ma': TimeWindowMovingAverage(window_seconds=4.0),
    'pump_mode': 'manual',  # 'auto' or 'manual'
    'motor_states': {'agitator': 0.0, 'air': 0.0, 'feed': 0.0}
    ,
    'anomaly_status': {
        'status': 'normal',
        'prediction': 1,
        'score': 0.0,
        'trained': False,
        'message': 'Detector not trained',
        'timestamp': '',
        'sequence': 0
    }
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("=" * 60)
    logger.info("FLOTATION CONTROL SYSTEM - STARTING")
    logger.info("=" * 60)
    
    try:
        target_setpoint, max_pump_duty = _load_control_defaults()

        # Initialize vision processor
        logger.info("Initializing vision processor...")
        from ..vision.vision_processor import VisionProcessor
        system_state['vision_processor'] = VisionProcessor(frame_width=640, frame_height=480, camera_fps=10)
        logger.info("✓ Vision processor initialized")
        
        # Initialize hardware controller
        logger.info("Initializing hardware controller...")
        from ..control.hardware_controller import HardwareController
        system_state['hardware_controller'] = HardwareController(
            target_bubble_count=target_setpoint, max_pump_duty=max_pump_duty
        )
        logger.info("✓ Hardware controller initialized")

        # Initialize ML components (for operator-triggered training)
        logger.info("Initializing ML components...")
        from ..ml.anomaly_detector import FrothAnomalyDetector
        from ..utils.data_manager import DataManager
        system_state['anomaly_detector'] = FrothAnomalyDetector(contamination=0.1)
        system_state['data_manager'] = DataManager(db_path="data/flotation.db")

        # Load existing trained model if available
        project_root = Path(__file__).resolve().parents[2]
        model_path = project_root / "models" / "anomaly_detector.pkl"
        loaded = system_state['anomaly_detector'].load(str(model_path))
        if loaded:
            logger.info(f"✓ Loaded trained anomaly model from {model_path}")
            system_state['anomaly_status']['trained'] = True
            system_state['anomaly_status']['message'] = 'Trained model loaded'
        else:
            logger.info(
                "No trained anomaly model loaded; detector will run untrained until training is triggered"
            )

        logger.info("✓ ML components initialized")
        
        # Start background tasks
        system_state['running'] = True
        asyncio.create_task(vision_loop())
        asyncio.create_task(control_loop())
        
        logger.info("✓ System startup complete")
        
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    
    yield  # Application running
    
    # Shutdown
    logger.info("Shutting down...")
    system_state['running'] = False
    
    if system_state['hardware_controller']:
        system_state['hardware_controller'].cleanup()
    
    if system_state['vision_processor']:
        system_state['vision_processor'].release()

    if system_state['data_manager']:
        system_state['data_manager'].close()
    
    logger.info("✓ Shutdown complete")


async def vision_loop():
    """Continuous vision processing loop with smoothed bubble count publishing."""
    vision = system_state['vision_processor']
    bubble_count_ma = system_state['bubble_count_ma']

    last_training_save_time = 0.0
    training_sample_interval = 5.0
    
    while system_state['running']:
        try:
            metrics = vision.get_metrics()
            controller = system_state.get('hardware_controller')

            if controller:
                controller.set_camera_present(bool(metrics.get('success', False)))

            if metrics['success']:
                # Smooth bubble_count over time window before publishing
                raw_count = metrics.get('bubble_count', 0)
                metrics['bubble_count'] = bubble_count_ma.update(raw_count)

                # Update current metrics (exclude 'success' flag)
                system_state['current_metrics'] = {
                    k: v for k, v in metrics.items() if k != 'success'
                }
                system_state['current_metrics']['pump_duty'] = system_state['hardware_controller'].pump_duty

                # Save metrics for anomaly-model training dataset
                data_manager = system_state.get('data_manager')
                now = monotonic()

                if data_manager is not None and now - last_training_save_time >= training_sample_interval:
                    data_manager.save_metrics(system_state['current_metrics'])
                    last_training_save_time = now
            
            await asyncio.sleep(0.2)  # 5 FPS processing rate
        except Exception as e:
            logger.error(f"Vision loop error: {e}")
            
            controller = system_state.get('hardware_controller')
            if controller:
                controller.set_camera_present(False)

            await asyncio.sleep(1)


async def control_loop():
    """Continuous control loop for auto mode and anomaly inference."""
    controller = system_state['hardware_controller']
    
    while system_state['running']:
        try:
            # Check E-Stop (returns True if triggered)
            if controller.check_estop():
                logger.critical("Control loop halted: E-STOP is active")
                # Stop control loop and wait 1 second before checking again
                await asyncio.sleep(1.0)
                continue

            # Update pump in auto mode (sampled control)
            if system_state['pump_mode'] == 'auto':
                bubble_count = system_state['current_metrics']['bubble_count']
                result = controller.auto_control_from_count(bubble_count)

                # Update shared state for dashboard/API
                system_state['current_metrics']['pump_duty'] = float(result.get('frother_duty', 0.0))
                system_state['motor_states']['air'] = float(result.get('air_duty', 0.0))

            # Run anomaly inference every control cycle
            detector = system_state.get('anomaly_detector')
            metrics = system_state.get('current_metrics', {})
            if detector is not None:
                features = [
                    float(metrics.get('bubble_count', 0.0)),
                    float(metrics.get('avg_bubble_size', 0.0)),
                    float(metrics.get('size_std_dev', 0.0)),
                    float(metrics.get('froth_coverage', 0.0))
                ]

                prediction = int(detector.predict(features))
                score = float(detector.get_anomaly_score(features))
                trained = bool(detector.is_trained)

                if not trained:
                    status = 'normal'
                    message = 'Detector not trained'
                elif prediction == -1:
                    status = 'critical' if score <= -0.20 else 'warning'
                    message = f"Anomaly detected (score={score:.3f})"
                else:
                    status = 'normal'
                    message = 'Normal operation'

                previous = system_state.get('anomaly_status', {})
                changed = (
                    status != previous.get('status')
                    or prediction != previous.get('prediction')
                    or trained != previous.get('trained')
                    or abs(score - float(previous.get('score', 0.0))) >= 0.01
                )

                sequence = int(previous.get('sequence', 0)) + (1 if changed else 0)
                system_state['anomaly_status'] = {
                    'status': status,
                    'prediction': prediction,
                    'score': score,
                    'trained': trained,
                    'message': message,
                    'timestamp': metrics.get('timestamp', ''),
                    'sequence': sequence
                }

                abnormal_led = trained and status == 'critical'
                controller.set_abnormal(abnormal_led)

            # In auto mode, hold the last decision for the control period
            if system_state['pump_mode'] == 'auto':
                wait_time = 0.0
                while wait_time < controller.control_period and system_state['running']:
                    await asyncio.sleep(0.5)
                    wait_time += 0.5
                    controller.check_estop()

                    # Stop auto timing loop if mode changes
                    if system_state['pump_mode'] != 'auto':
                        break
            else:
                await asyncio.sleep(1.0)  # 1 Hz control rate in manual mode
        except Exception as e:
            logger.error(f"Control loop error: {e}")
            await asyncio.sleep(1)


# Create FastAPI app
app = FastAPI(
    title="Flotation Control System",
    description="Real-time froth flotation control with vision processing",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (allow dashboard access from any origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routers
app.include_router(routes.router, prefix="/api")
app.include_router(websocket.router)

# Mount static files BEFORE the root route
dashboard_path = "dashboard"
try:
    # Serve CSS and JS files
    app.mount("/css", StaticFiles(directory=f"{dashboard_path}/css"), name="css")
    app.mount("/js", StaticFiles(directory=f"{dashboard_path}/js"), name="js")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")


@app.get("/")
async def root():
    """Serve dashboard HTML."""
    try:
        return FileResponse(f"{dashboard_path}/index.html")
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return {"error": "Dashboard not found", "details": str(e)}


def get_system_state():
    """Export system state for routes and websocket modules."""
    return system_state
