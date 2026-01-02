"""
Vision processing module for froth flotation control system.

Provides unified vision processing with camera interface, preprocessing,
bubble detection, and froth analysis in a single minimal class.
"""

# New unified processor (recommended)
from .vision_processor import VisionProcessor

__all__ = [
    # Recommended - unified processor
    'VisionProcessor',  
]

__version__ = '2.0.0'
