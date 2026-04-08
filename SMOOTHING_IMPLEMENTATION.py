#!/usr/bin/env python3
"""
Quick reference: 2-second moving average implementation for bubble_count

HOW IT WORKS:
=============

1. TimeWindowMovingAverage class maintains a sliding window of samples
   - Window size: 2 seconds (configurable)
   - Automatically discards samples older than window
   - Returns integer (rounded) average

2. Integration points:
   ✓ main.py: Initialize in lifespan, apply in vision_loop
   ✓ vision_loop: Apply smoothing BEFORE storing in current_metrics
   ✓ control_loop: Uses smoothed bubble_count for PI controller
   ✓ /api/metrics endpoint: Returns smoothed bubble_count
   ✓ /ws WebSocket: Broadcasts smoothed bubble_count
   ✓ dashboard: Displays smoothed bubble_count

3. Raw value preserved:
   - bubble_count_raw stored in metrics for debugging
   - Available via /api/metrics and WebSocket (optional)


DATA FLOW:
==========

VisionProcessor.get_metrics()
    ↓
    raw bubble_count (e.g., 145)
    ↓
vision_loop()
    ↓
    ma.update(145)  ← Moving average filter (2s window)
    ↓
    smoothed_count = 142  ← e.g., average of last 2s samples
    ↓
    current_metrics['bubble_count'] = 142
    current_metrics['bubble_count_raw'] = 145
    ↓
    ├─→ /api/metrics endpoint
    ├─→ /ws WebSocket broadcast
    └─→ control_loop() uses smoothed value


BENEFITS:
=========

1. Noise reduction: Filters out sudden spikes/drops in bubble detection
2. Stable control: PI controller input is smoothed, prevents oscillation
3. Accurate setpoint tracking: Less reactive to momentary detection errors
4. Hardware efficiency: Pump doesn't react to transient bubbles


USAGE IN CONTROL LOOP:
======================

# Before (raw):
bubble_count = 145 → large fluctuations → pump oscillates

# After (smoothed):
bubble_count = 142 (avg of last 2s) → stable input → steady control


TESTING:
========

Run: python tests/test_metrics_smoothing.py

Tests cover:
- Basic averaging (100, 110, 90 → smooth progression)
- Time window expiration (samples removed after 2s)
- Noise smoothing (variance reduction)
- Reset functionality


CONFIGURATION:
==============

To change window size, modify in main.py:
    system_state['bubble_count_ma'] = TimeWindowMovingAverage(window_seconds=X.X)

Recommended values:
- 1.0s: Very responsive, less smoothing (use for fast responses)
- 2.0s: Good balance (DEFAULT)
- 3.0s: More smoothing, slower response


DEBUGGING:
==========

To compare raw vs smoothed:
- Check WebSocket/API response includes bubble_count_raw
- Log: f"Raw: {raw}, Smoothed: {smoothed}"
- Compare in dashboard console


FILES MODIFIED:
===============

1. src/api/metrics_smoothing.py
   - NEW: TimeWindowMovingAverage class
   
2. src/api/main.py
   - Import metrics_smoothing module
   - Initialize moving average in lifespan()
   - Apply smoothing in vision_loop()
   
3. dashboard/js/app.js
   - Documentation: bubble_count is now 2s smoothed average
   
4. tests/test_metrics_smoothing.py
   - NEW: Comprehensive test suite


STATUS: ✓ COMPLETE
"""

if __name__ == '__main__':
    print(__doc__)
