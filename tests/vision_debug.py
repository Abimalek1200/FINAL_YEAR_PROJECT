"""
Live preview to visually verify VisionProcessor bubble detection.

Press 'q' or ESC to exit.
"""

import sys
from pathlib import Path

import cv2

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vision.vision_processor import VisionProcessor  # type: ignore


def main() -> None:
    # Minimal production-like config; adjust if needed
    processor = VisionProcessor(
        camera_id=1,
        frame_width=640,
        frame_height=480,
        camera_fps=30,
        camera_retries=3,
        min_bubble_area=15,
        distance_threshold=0.125,
        circularity_threshold=0.45,
        watershed_dilations=3,
    )

    if not processor.initialize_camera():
        print("ERROR: Coul d not initialize camera.")
        return

    try:
        while True:
            raw_frame = processor.capture_frame()
            if raw_frame is None:
                print("WARNING: Empty frame, skipping.")
                continue

            # Handle both possible return types: frame or (ret, frame)
            if isinstance(raw_frame, tuple):
                ok, frame = raw_frame
                if not ok or frame is None:
                    print("WARNING: Capture failed, skipping.")
                    continue
            else:
                frame = raw_frame

            # Run bubble detection
            try:
                bubble_data = processor.process_bubbles(frame)
            except Exception as e:
                print(f"ERROR: Bubble processing failed: {e}")
                continue

            # Copy frame for drawing
            annotated = frame.copy()

            # Draw detected bubbles if contours are available
            contours = None
            if isinstance(bubble_data, dict):
                contours = bubble_data.get("contours")
            elif bubble_data is not None:
                contours = bubble_data

            if contours is not None:
                cv2.drawContours(annotated, contours, -1, (0, 255, 0), 1)

            # Get metrics for overlay text
            try:
                metrics = processor.get_metrics()
            except Exception as e:
                print(f"ERROR: Metrics extraction failed: {e}")
                metrics = {
                    "bubble_count": 0,
                    "avg_bubble_size": 0.0,
                    "size_std_dev": 0.0,
                    "froth_coverage": 0.0,
                    "froth_stability": 0.0,
                    "success": False,
                }

            text = (
                f"Count: {metrics.get('bubble_count', 0)}  "
                f"AvgSize: {metrics.get('avg_bubble_size', 0.0):.1f}  "
                f"Cov: {metrics.get('froth_coverage', 0.0)*100:5.1f}%  "
                f"Stab: {metrics.get('froth_stability', 0.0):.2f}"
            )
            cv2.putText(
                annotated,
                text,
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("Vision Debug - Annotated Froth", annotated)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' or ESC
                break

    finally:
        processor.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

#How to run (from project root):

#```bash
#python scripts/vision_debug_preview.py