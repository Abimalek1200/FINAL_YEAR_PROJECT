"""
Logging Configuration

Simple, student-friendly logging setup.
Logs to both file and console with automatic rotation.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
):
    """Configure logging for the flotation system.
    
    Creates logs in 'logs/' directory with automatic rotation.
    Logs appear in both the file and on screen.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        max_bytes: Max size of each log file before rotation
        backup_count: Number of old log files to keep
    
    Example:
        >>> setup_logging(log_level="DEBUG")
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("System started!")
    """
    # Create logs directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Format: timestamp - name - level - message
    # Example: 2025-12-21 14:30:15 - vision.camera - INFO - Camera opened
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler 1: Rotating file (main log)
    file_handler = RotatingFileHandler(
        filename=f"{log_dir}/flotation.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Capture everything to file
    root_logger.addHandler(file_handler)
    
    # Handler 2: Error file (only errors and critical)
    error_handler = RotatingFileHandler(
        filename=f"{log_dir}/flotation-error.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)  # Only errors
    root_logger.addHandler(error_handler)
    
    # Handler 3: Console output (for monitoring)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)
    
    # Log the configuration
    logging.info("="*60)
    logging.info(f"Logging initialized: level={log_level}, dir={log_dir}")
    logging.info("="*60)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.
    
    Args:
        name: Usually __name__ of the module
    
    Returns:
        Configured logger instance
    
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
    """
    return logging.getLogger(name)


if __name__ == "__main__":
    # Test logging setup
    print("\\n=== Logging Test ===\\n")
    
    setup_logging(log_level="DEBUG")
    
    logger = get_logger("test")
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    print("\\nCheck logs/ directory for output files:")
    print("  - flotation.log (all messages)")
    print("  - flotation-error.log (errors only)")
    print("\\n✓ Logging test complete")
