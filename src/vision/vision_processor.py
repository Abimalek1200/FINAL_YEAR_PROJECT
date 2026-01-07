"""
Unified Vision Processor for Froth Flotation Control System
Combines camera, preprocessing, detection, and analysis in <300 lines.
"""

import cv2 as cv
import numpy as np
import logging
import time
from typing import Dict, Any, Optional, Tuple
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class VisionProcessor:
    """Unified vision processing with robust error handling for production."""
    
    def __init__(
        self,
        camera_id: int = 0,
        frame_width: int = 640,
        frame_height: int = 480,
        camera_fps: int = 30,
        camera_retries: int = 5,
        blur_kernel: Tuple[int, int] = (1, 1),
        morph_kernel: Tuple[int, int] = (1, 1),
        opening_iterations: int = 2,
        closing_iterations: int = 4,
        min_bubble_area: int = 80,
        distance_threshold: float = 0.125,
        circularity_threshold: float = 0.45,
        watershed_dilations: int = 3,
        history_size: int = 10
    ):
        """Initialize with all vision parameters from copilot-instructions.md config."""
        self.camera_id, self.frame_width, self.frame_height = camera_id, frame_width, frame_height
        self.camera_fps, self.camera_retries = camera_fps, camera_retries
        self.blur_kernel, self.morph_kernel = blur_kernel, morph_kernel
        self.opening_iterations, self.closing_iterations = opening_iterations, closing_iterations
        self.min_bubble_area, self.distance_threshold = min_bubble_area, distance_threshold
        self.circularity_threshold, self.watershed_dilations = circularity_threshold, watershed_dilations
        
        self.cap: Optional[cv.VideoCapture] = None
        self.is_camera_open = False
        self.morph_kernel_elem = cv.getStructuringElement(cv.MORPH_ELLIPSE, morph_kernel)
        self.watershed_kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (1, 1))
        self.bubble_count_history = deque(maxlen=history_size)
        self.avg_size_history = deque(maxlen=history_size)
        
        logger.info("VisionProcessor initialized")
    
    def initialize_camera(self) -> bool:
        """Initialize camera with retry logic."""
        for attempt in range(self.camera_retries):
            try:
                self.cap = cv.VideoCapture(self.camera_id)
                if not self.cap.isOpened():
                    time.sleep(2)
                    continue
                
                self.cap.set(cv.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, self.frame_height)
                self.cap.set(cv.CAP_PROP_FPS, self.camera_fps)
                
                ret, test_frame = self.cap.read()
                if not ret or test_frame is None:
                    self.cap.release()
                    time.sleep(2)
                    continue
                
                self.is_camera_open = True
                logger.info("Camera initialized successfully")
                return True
                
            except Exception as e:
                logger.error(f"Camera init error: {e}")
                if self.cap:
                    self.cap.release()
                time.sleep(2)
        
        logger.error(f"Camera init failed after {self.camera_retries} attempts")
        return False
    
    def capture_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Capture frame with error handling."""
        if not self.is_camera_open or self.cap is None:
            if not self.initialize_camera():
                return False, None
        
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.error("Failed to capture frame")
                self.is_camera_open = False
                return False, None
            return True, frame
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            self.is_camera_open = False
            return False, None
    
    def process_bubbles(self, frame: np.ndarray) -> Dict[str, Any]:
        """Complete preprocessing and bubble detection pipeline."""
        if frame is None or frame.size == 0:
            return {'count': 0, 'diameters': [], 'areas': [], 'avg_diameter': 0.0, 'mask': None}
        
        try:
            # Preprocessing: grayscale → blur → threshold → morphology
            gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            blur = cv.GaussianBlur(gray, self.blur_kernel, 0)
            _, binary = cv.threshold(blur, 0, 255, cv.THRESH_BINARY_INV + cv.THRESH_OTSU)
            opening = cv.morphologyEx(binary, cv.MORPH_OPEN, self.morph_kernel_elem,
                                     iterations=self.opening_iterations)
            closing = cv.morphologyEx(opening, cv.MORPH_CLOSE, self.morph_kernel_elem,
                                     iterations=self.closing_iterations)
            
            # Watershed segmentation
            dist = cv.distanceTransform(closing, cv.DIST_L2, 5)
            _, sure_fg = cv.threshold(dist, self.distance_threshold * dist.max(), 255, 0)
            sure_fg = np.uint8(sure_fg)
            sure_bg = cv.dilate(closing, self.watershed_kernel, iterations=self.watershed_dilations)
            unknown = cv.subtract(sure_bg, sure_fg)
            
            ret, markers = cv.connectedComponents(sure_fg)
            markers = markers + 1
            markers[unknown == 255] = 0
            markers_ws = markers.copy()
            cv.watershed(cv.cvtColor(frame, cv.COLOR_BGR2RGB), markers_ws)
            
            # Extract bubble mask
            mask = np.zeros_like(closing, dtype=np.uint8)
            mask[markers_ws > 1] = 255
            
            # Contour analysis
            contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            bubbles = self._analyze_contours(contours)
            
            return {
                'count': bubbles['count'],
                'diameters': bubbles['diameters'],
                'areas': bubbles['areas'],
                'avg_diameter': bubbles['avg_diameter'],
                'mask': mask
            }
        except Exception as e:
            logger.error(f"Bubble processing error: {e}")
            return {'count': 0, 'diameters': [], 'areas': [], 'avg_diameter': 0.0, 'mask': None}
    
    def _analyze_contours(self, contours) -> Dict[str, Any]:
        """Filter and extract metrics from contours."""
        diameters, areas = [], []
        
        for cnt in contours:
            area = cv.contourArea(cnt)
            if area < self.min_bubble_area:
                continue
            
            peri = cv.arcLength(cnt, True)
            if peri <= 0:
                continue
            
            circularity = 4 * np.pi * area / (peri * peri)
            if circularity < self.circularity_threshold:
                continue
            
            diameter = 2.0 * np.sqrt(area / np.pi)
            diameters.append(diameter)
            areas.append(area)
        
        return {
            'count': len(diameters),
            'diameters': diameters,
            'areas': areas,
            'avg_diameter': float(np.mean(diameters)) if diameters else 0.0
        }
    
    def analyze_froth(self, frame: np.ndarray, bubble_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate froth metrics from bubble data."""
        try:
            count = bubble_data['count']
            diameters = bubble_data['diameters']
            areas = bubble_data['areas']
            mask = bubble_data.get('mask')
            
            # Coverage ratio
            coverage = 0.0
            if mask is not None:
                total_pixels = frame.shape[0] * frame.shape[1]
                bubble_pixels = np.count_nonzero(mask)
                coverage = float(bubble_pixels) / total_pixels if total_pixels > 0 else 0.0
            
            # Size metrics
            avg_size = float(np.mean(areas)) if areas else 0.0
            size_std = float(np.std(diameters)) if diameters else 0.0
            
            # Update history and calculate stability
            self.bubble_count_history.append(count)
            self.avg_size_history.append(avg_size)
            stability = self._calculate_stability(bubble_data['avg_diameter'], size_std, count)
            
            return {
                'bubble_count': count,
                'avg_bubble_size': avg_size,
                'size_std_dev': size_std,
                'froth_coverage': coverage,
                'froth_stability': stability
            }
        except Exception as e:
            logger.error(f"Froth analysis error: {e}")
            return {
                'bubble_count': 0,
                'avg_bubble_size': 0.0,
                'size_std_dev': 0.0,
                'froth_coverage': 0.0,
                'froth_stability': 0.0
            }
    
    def _calculate_stability(self, avg_diameter: float, size_std: float, count: int) -> float:
        """Calculate stability score (0-1) from size uniformity, temporal consistency, density."""
        # Size uniformity
        size_uniformity = 1.0 / (1.0 + size_std / avg_diameter) if avg_diameter > 0 else 0.0
        
        # Temporal consistency
        if len(self.bubble_count_history) >= 3:
            count_std = float(np.std(list(self.bubble_count_history)))
            count_mean = float(np.mean(list(self.bubble_count_history)))
            count_consistency = 1.0 / (1.0 + count_std / count_mean) if count_mean > 0 else 0.0
        else:
            count_consistency = 0.5
        
        # Density score (optimal: 50-200 bubbles)
        if count < 50:
            density_score = count / 50.0
        elif count > 200:
            density_score = max(0.5, 1.0 - (count - 200) / 200.0)
        else:
            density_score = 1.0
        
        stability = 0.4 * size_uniformity + 0.4 * count_consistency + 0.2 * density_score
        return np.clip(stability, 0.0, 1.0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Main entry point: capture frame and extract all metrics.
        
        Returns dict with bubble_count, avg_bubble_size, size_std_dev,
        froth_coverage, froth_stability, timestamp, and success flag.
        """
        timestamp = datetime.now().isoformat()
        
        # Capture frame
        success, frame = self.capture_frame()
        if not success or frame is None:
            logger.error("Frame capture failed, returning defaults")
            return {
                'bubble_count': 0, 'avg_bubble_size': 0.0, 'size_std_dev': 0.0,
                'froth_coverage': 0.0, 'froth_stability': 0.0,
                'timestamp': timestamp, 'success': False
            }
        
        # Process bubbles
        bubble_data = self.process_bubbles(frame)
        if bubble_data['count'] == 0:
            logger.debug("No bubbles detected")  # Changed to debug to reduce log spam
        
        # Analyze froth
        froth_metrics = self.analyze_froth(frame, bubble_data)
        froth_metrics['timestamp'] = timestamp
        froth_metrics['success'] = True
        
        return froth_metrics
    
    def release(self):
        """Release camera resources."""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_camera_open = False
    
    def __enter__(self):
        self.initialize_camera()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    
    def __del__(self):
        self.release()
