# VisionProcessor - Quick Reference

## Overview
`vision_processor.py` consolidates all vision functionality into a single 275-line module:
- Camera interface (from `camera.py`)
- Preprocessing pipeline (from `preprocessor.py`)
- Bubble detection (from `bubble_detector.py`)
- Froth analysis (from `froth_analyzer.py`)

## Essential Metrics Extracted
1. **bubble_count** - Number of detected bubbles
2. **avg_bubble_size** - Average bubble area in pixels²
3. **size_std_dev** - Size distribution variance
4. **froth_coverage** - Percentage of frame covered by bubbles (0-1)
5. **froth_stability** - Stability score based on uniformity, consistency, density (0-1)

## Basic Usage

```python
from vision.vision_processor import VisionProcessor

# Initialize with default parameters
processor = VisionProcessor()

# Initialize camera
if processor.initialize_camera():
    # Get metrics (captures frame + full analysis)
    metrics = processor.get_metrics()
    
    if metrics['success']:
        print(f"Bubbles: {metrics['bubble_count']}")
        print(f"Coverage: {metrics['froth_coverage']:.2%}")
        print(f"Stability: {metrics['froth_stability']:.3f}")

# Clean up
processor.release()
```

## Recommended Usage (Context Manager)

```python
with VisionProcessor() as processor:
    metrics = processor.get_metrics()
    # Camera auto-released on exit
```

## Custom Parameters

All parameters from copilot-instructions.md are configurable:

```python
processor = VisionProcessor(
    # Camera settings
    camera_id=0,
    frame_width=640,
    frame_height=480,
    camera_fps=30,
    camera_retries=5,
    
    # Preprocessing (tested optimal values)
    blur_kernel=(1, 1),
    morph_kernel=(1, 1),
    opening_iterations=2,
    closing_iterations=4,
    
    # Detection (tested optimal values)
    min_bubble_area=80,
    distance_threshold=0.125,
    circularity_threshold=0.45,
    watershed_dilations=3,
    
    # Temporal analysis
    history_size=10
)
```

## Error Handling

The VisionProcessor includes robust error handling:

### Camera Failures
- Automatic retry logic (default: 5 attempts with 2s delays)
- Graceful degradation: returns default metrics on failure

### Processing Failures
- Try-catch blocks around all critical operations
- Continues with default values rather than crashing

### Invalid Parameters
- All parameters validated in constructor
- Sensible defaults provided

## Return Value Structure

```python
{
    'bubble_count': int,           # Number of detected bubbles
    'avg_bubble_size': float,      # Average area in pixels²
    'size_std_dev': float,         # Size distribution std dev
    'froth_coverage': float,       # Coverage ratio (0-1)
    'froth_stability': float,      # Stability score (0-1)
    'timestamp': str,              # ISO format timestamp
    'success': bool                # True if processing succeeded
}
```

## Integration with Control System

```python
# In your control loop
processor = VisionProcessor()
processor.initialize_camera()

while running:
    # Get metrics every control cycle
    metrics = processor.get_metrics()
    
    if metrics['success']:
        # Pass to PI controller
        bubble_count = metrics['bubble_count']
        stability = metrics['froth_stability']
        
        # Use for control decisions
        controller.update(bubble_count)
        
        # Check for anomalies
        if stability < 0.3:
            trigger_alert("Low froth stability")
    
    time.sleep(1)  # Control loop timing

processor.release()
```

## Testing

Run the test script to validate functionality:

```bash
python scripts/test_vision_processor.py
```

This will:
1. Initialize camera with retry logic
2. Capture 5 frames and extract metrics
3. Test context manager usage
4. Display all metrics and success/failure

## Performance Notes

**Raspberry Pi 5 Optimization:**
- Default 640x480 resolution for speed
- Processing time: <100ms per frame (target)
- Memory usage: <50MB
- CPU usage: <60% average

**For Higher Quality:**
- Increase resolution to 1920x1080 (will reduce FPS)
- Adjust `frame_width` and `frame_height` parameters

## Troubleshooting

**"Camera init failed after N attempts"**
- Check USB connection
- Verify camera permissions: `ls -l /dev/video0`
- Test with: `v4l2-ctl --list-devices`

**"No bubbles detected"**
- Verify lighting conditions (LED ring light should be on)
- Check froth presence in flotation cell
- Adjust `min_bubble_area` or `circularity_threshold` if needed

**Low FPS (<5 FPS)**
- Reduce resolution
- Check CPU usage: `htop`
- Verify no other processes using camera

## Migration from Old Code

**Old (multiple files):**
```python
from vision.camera import Camera
from vision.preprocessor import ImagePreprocessor
from vision.bubble_detector import BubbleDetector
from vision.froth_analyzer import FrothAnalyzer

camera = Camera()
preprocessor = ImagePreprocessor()
detector = BubbleDetector()
analyzer = FrothAnalyzer(preprocessor, detector)

camera.open()
ret, frame = camera.read()
metrics = analyzer.analyze(frame)
```

**New (single file):**
```python
from vision.vision_processor import VisionProcessor

processor = VisionProcessor()
processor.initialize_camera()
metrics = processor.get_metrics()
```

## File Size Comparison

| File | Lines | Purpose |
|------|-------|---------|
| `camera.py` | 262 | Camera interface |
| `preprocessor.py` | 236 | Image preprocessing |
| `bubble_detector.py` | 350 | Bubble detection |
| `froth_analyzer.py` | 401 | Froth analysis |
| **Total (old)** | **1,249** | **4 files** |
| **vision_processor.py** | **275** | **1 file** |
| **Reduction** | **78% smaller** | **75% fewer files** |

## What Was Removed

✂️ **Removed (non-essential):**
- Verbose debug logging
- Intermediate visualization methods
- Redundant parameter validation
- Extended documentation in docstrings
- Helper methods for statistics display
- Experimental features not used in production

✅ **Preserved (essential):**
- All critical error handling
- Camera retry logic
- Complete preprocessing pipeline
- Watershed segmentation algorithm
- Contour filtering and analysis
- Stability calculation
- All production parameters
- Context manager support
