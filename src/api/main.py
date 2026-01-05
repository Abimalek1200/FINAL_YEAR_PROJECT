"""FastAPI app: vision processing, hardware control, WebSocket streaming."""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import routes, websocket

logger = logging.getLogger(__name__)

# Global system state
system_state = {
    'vision_processor': None,
    'hardware_controller': None,
    'running': False,
    'current_metrics': {
        'bubble_count': 0,
        'avg_bubble_size': 0.0,
        'size_std_dev': 0.0,
        'froth_coverage': 0.0,
        'froth_stability': 0.0,
        'pump_duty': 0.0,
        'timestamp': ''
    },
    'pump_mode': 'manual',  # 'auto' or 'manual'
    'motor_states': {'agitator': 0.0, 'air': 0.0, 'feed': 0.0}
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("=" * 60)
    logger.info("FLOTATION CONTROL SYSTEM - STARTING")
    logger.info("=" * 60)
    
    try:
        # Initialize vision processor
        logger.info("Initializing vision processor...")
        from ..vision.vision_processor import VisionProcessor
        system_state['vision_processor'] = VisionProcessor(frame_width=640, frame_height=480, camera_fps=10)
        logger.info("✓ Vision processor initialized")
        
        # Initialize hardware controller
        logger.info("Initializing hardware controller...")
        from ..control.hardware_controller import HardwareController
        system_state['hardware_controller'] = HardwareController(
            pi_kp=0.5, pi_ki=0.05, pi_setpoint=120, max_pump_duty=80.0
        )
        logger.info("✓ Hardware controller initialized")
        
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
    
    logger.info("✓ Shutdown complete")


async def vision_loop():
    """Continuous vision processing loop."""
    vision = system_state['vision_processor']
    
    while system_state['running']:
        try:
            metrics = vision.get_metrics()
            if metrics['success']:
                # Update current metrics (exclude 'success' flag)
                system_state['current_metrics'] = {
                    k: v for k, v in metrics.items() if k != 'success'
                }
                system_state['current_metrics']['pump_duty'] = system_state['hardware_controller'].pump_duty
            
            await asyncio.sleep(0.5)  # 2 Hz update rate
        except Exception as e:
            logger.error(f"Vision loop error: {e}")
            await asyncio.sleep(1)


async def control_loop():
    """Continuous control loop for auto mode."""
    controller = system_state['hardware_controller']
    
    while system_state['running']:
        try:
            # Check E-Stop
            controller.check_estop()
            
            # Update pump in auto mode
            if system_state['pump_mode'] == 'auto':
                bubble_count = system_state['current_metrics']['bubble_count']
                controller.set_pump_speed(bubble_count)
            
            await asyncio.sleep(1.0)  # 1 Hz control rate
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
