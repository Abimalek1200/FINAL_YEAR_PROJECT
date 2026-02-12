#!/usr/bin/env python3
"""
Flotation Control System - Main Entry Point
Raspberry Pi 5 Application Launcher
"""

import sys
import os
import logging
import signal
import asyncio
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'flotation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def check_prerequisites():
    """Check if all prerequisites are met before starting"""
    logger.info("Checking system prerequisites...")
    
    # Check Python version
    if sys.version_info < (3, 11):
        logger.error(f"Python 3.11+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        return False
    
    # Check required modules
    required_modules = [
        'cv2', 'numpy', 'sklearn', 'fastapi', 
        'uvicorn', 'lgpio', 'psutil', 'websockets'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        logger.error(f"Missing required modules: {', '.join(missing_modules)}")
        logger.error("Run setup script or install manually: sudo apt install python3-lgpio")
        return False
    
    # Check if running on Raspberry Pi
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            if 'Raspberry Pi' not in cpuinfo:
                logger.warning("Not running on Raspberry Pi - some features may not work")
    except FileNotFoundError:
        logger.warning("Could not detect Raspberry Pi")
    
    # Check lgpio (Raspberry Pi 5)
    try:
        import lgpio
        chip = lgpio.gpiochip_open(0)
        logger.info("✓ lgpio GPIO access verified")
        lgpio.gpiochip_close(chip)
    except Exception as e:
        logger.error(f"lgpio check failed: {e}")
        logger.error("Install with: sudo apt install python3-lgpio")
        return False
    
    # Check camera availability
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.warning("Camera not detected - will continue but vision features disabled")
        else:
            logger.info("Camera detected successfully")
            cap.release()
    except Exception as e:
        logger.warning(f"Camera check failed: {e}")
    
    # Check configuration files
    config_dir = PROJECT_ROOT / "config"
    required_configs = [
        'camera_config.json',
        'control_config.json', 
        'system_config.json'
    ]
    
    for config_file in required_configs:
        config_path = config_dir / config_file
        if not config_path.exists():
            logger.error(f"Missing configuration file: {config_path}")
            logger.error("Run setup.sh to generate default configurations")
            return False
    
    logger.info("All prerequisites met ✓")
    return True


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


async def main():
    """Main application entry point"""
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("Flotation Control System Starting")
    logger.info("=" * 60)
    
    # Check prerequisites
    if not check_prerequisites():
        logger.error("Prerequisites check failed - exiting")
        sys.exit(1)
    
    try:
        # Import FastAPI application
        from src.api.main import app
        import uvicorn
        
        # Load system configuration
        import json
        config_path = PROJECT_ROOT / "config" / "system_config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Get API settings
        api_config = config.get('api', {})
        host = api_config.get('host', '0.0.0.0')
        port = api_config.get('port', 8000)
        
        logger.info(f"Starting web server on {host}:{port}")
        logger.info(f"Dashboard URL: http://localhost:{port}")
        logger.info("Press Ctrl+C to stop")
        
        # Start uvicorn server
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(uvicorn_config)
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Flotation Control System stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
