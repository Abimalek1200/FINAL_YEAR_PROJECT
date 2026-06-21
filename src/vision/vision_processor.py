"""
Unified Vision Processor for Froth Flotation Control System
Combines camera, preprocessing, detection, and analysis with optional U-Net segmentation.
"""

import cv2 as cv
import numpy as np
import logging
import time
from typing import Dict, Any, Optional, Tuple
from collections import deque
from datetime import datetime
from .unet_segmenter import UNetSegmenter

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
        blur_kernel_size: int = 5,
        morph_kernel_size: int = 3,
        min_bubble_area: int = 150,
        max_bubble_area: int = 11000,
        circularity_threshold: float = 0.2,
        history_size: int = 10,
        use_unet: bool = True,
        unet_model_path: str = "models/froth_unet.onnx",
        unet_input_size: int = 256,
        unet_threshold: float = 0.45,
        min_unet_coverage: float = 0.02,
        max_unet_coverage: float = 0.90
    ):
        """Initialize with contour detection and optional U-Net segmentation.
        
        Args:
            camera_id: USB camera device ID
            frame_width: Camera frame width (pixels)
            frame_height: Camera frame height (pixels)
            camera_fps: Target camera frame rate
            camera_retries: Max retry attempts for camera init
            blur_kernel_size: Gaussian blur kernel size
            morph_kernel_size: Morphological kernel size
            min_bubble_area: Minimum bubble area filter (pixels²)
            max_bubble_area: Maximum bubble area filter (pixels²)
            circularity_threshold: Minimum circularity (0-1)
            history_size: Size of metrics history buffer
            use_unet: Enable U-Net ONNX segmentation
            unet_model_path: Path to ONNX model file
            unet_input_size: U-Net input size (256x256)
            unet_threshold: Probability threshold for U-Net mask
            min_unet_coverage: Minimum valid mask coverage (0-1)
            max_unet_coverage: Maximum valid mask coverage (0-1)
        """
        self.camera_id, self.frame_width, self.frame_height = camera_id, frame_width, frame_height
        self.camera_fps, self.camera_retries = camera_fps, camera_retries
        
        # Contour detection parameters
        self.blur_kernel_size = blur_kernel_size
        self.morph_kernel_size = morph_kernel_size
        self.min_bubble_area = min_bubble_area
        self.max_bubble_area = max_bubble_area
        self.circularity_threshold = circularity_threshold

        # U-Net parameters
        self.use_unet = use_unet
        self.min_unet_coverage = min_unet_coverage
        self.max_unet_coverage = max_unet_coverage
        self.detection_source = "classical"  # Track which segmentation was used
        
        self.cap: Optional[cv.VideoCapture] = None
        self.is_camera_open = False
        self.bubble_count_history = deque(maxlen=history_size)
        self.avg_size_history = deque(maxlen=history_size)
        
        # Storage for annotation
        self.last_frame: Optional[np.ndarray] = None
        self.last_annotated_frame: Optional[np.ndarray] = None
        self.bubble_centroids: list = []  # [(cx, cy, radius), ...]

        # Initialize U-Net segmenter (optional)
        self.unet = None
        if self.use_unet:
            try:
                self.unet = UNetSegmenter(
                    model_path=unet_model_path,
                    input_size=unet_input_size,
                    threshold=unet_threshold
                )
                if self.unet.available():
                    logger.info("U-Net segmentation enabled")
                else:
                    logger.warning("U-Net ONNX model unavailable, will use classical OpenCV pipeline")
                    self.unet = None
            except Exception as e:
                logger.warning(f"U-Net initialization failed: {e}, using classical pipeline")
                self.unet = None
        else:
            logger.info("U-Net segmentation disabled by user")

        logger.info("VisionProcessor initialized with optional U-Net segmentation")
    
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

    def _get_classical_mask(self, frame: np.ndarray) -> np.ndarray:
        """Generate binary mask using classical OpenCV preprocessing.
        
        Pipeline:
        - Grayscale conversion
        - CLAHE contrast enhancement
        - Median blur (noise reduction)
        - Gaussian blur (smoothing)
        - Adaptive threshold (binary segmentation)
        - Morphological opening (remove small noise)
        - Morphological closing (fill holes)
        
        Args:
            frame: BGR input frame
        
        Returns:
            Binary mask (uint8, 255=foreground, 0=background)
        """
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

        # CLAHE for contrast enhancement
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Median blur to reduce noise
        median = cv.medianBlur(enhanced, 5)

        # Gaussian blur for smoothing
        blur = cv.GaussianBlur(median, (self.blur_kernel_size, self.blur_kernel_size), 0)

        # Adaptive thresholding for better bubble separation
        binary = cv.adaptiveThreshold(
            blur, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv.THRESH_BINARY_INV, 11, 2
        )

        # Morphological operations to clean up
        kernel = cv.getStructuringElement(
            cv.MORPH_ELLIPSE,
            (self.morph_kernel_size, self.morph_kernel_size)
        )
        opening = cv.morphologyEx(binary, cv.MORPH_OPEN, kernel, iterations=2)
        closing = cv.morphologyEx(opening, cv.MORPH_CLOSE, kernel, iterations=2)

        return closing

    def _get_unet_mask(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Generate binary mask using U-Net ONNX with validity checks.
        
        Validates mask coverage is within acceptable range before accepting.
        
        Args:
            frame: BGR input frame
        
        Returns:
            Binary mask if valid (255=foreground, 0=background), None if invalid or unavailable
        """
        if self.unet is None or not self.unet.available():
            return None

        try:
            mask = self.unet.predict_mask(frame)
            if mask is None:
                return None

            # Check coverage is within acceptable range
            mask_size = mask.size
            nonzero_pixels = np.count_nonzero(mask)
            coverage = float(nonzero_pixels) / mask_size if mask_size > 0 else 0.0

            if coverage < self.min_unet_coverage or coverage > self.max_unet_coverage:
                logger.debug(
                    f"U-Net mask rejected: coverage={coverage:.3f} outside "
                    f"[{self.min_unet_coverage:.3f}, {self.max_unet_coverage:.3f}]"
                )
                return None

            return mask

        except Exception as e:
            logger.error(f"U-Net mask generation failed: {e}")
            return None

    def _get_binary_mask(self, frame: np.ndarray) -> np.ndarray:
        """Get binary mask with fallback strategy.
        
        Try U-Net first if enabled, fall back to classical OpenCV.
        Updates self.detection_source tracking which method was used.
        
        Args:
            frame: BGR input frame
        
        Returns:
            Binary mask (255=foreground, 0=background)
        """
        if self.use_unet and self.unet is not None and self.unet.available():
            mask = self._get_unet_mask(frame)
            if mask is not None:
                self.detection_source = "unet"
                logger.debug("Using U-Net segmentation")
                return mask
            logger.debug("U-Net mask invalid, falling back to classical OpenCV")

        self.detection_source = "classical"
        logger.debug("Using classical OpenCV segmentation")
        return self._get_classical_mask(frame)
    
    def process_bubbles(self, frame: np.ndarray) -> Dict[str, Any]:
        """Contour-based bubble detection with optional U-Net preprocessing.
        
        Pipeline:
        1. Get binary mask (U-Net optional, classical fallback)
        2. Find contours in binary mask
        3. Analyze contours with area and circularity filtering
        4. Create output mask from valid bubble centroids
        """
        if frame is None or frame.size == 0:
            return {'count': 0, 'diameters': [], 'areas': [], 'avg_diameter': 0.0, 'mask': None}
        
        try:
            # Get binary mask with U-Net/classical fallback
            binary = self._get_binary_mask(frame)

            # Find contours
            contours, _ = cv.findContours(binary, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            
            # Analyze contours
            bubbles = self._analyze_contours(contours)
            
            # Create mask from valid contours
            gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            mask = np.zeros_like(gray, dtype=np.uint8)
            for cx, cy, radius in self.bubble_centroids:
                cv.circle(mask, (cx, cy), radius, 255, -1)
            
            return {
                'count': bubbles['count'],
                'diameters': bubbles['diameters'],
                'areas': bubbles['areas'],
                'avg_diameter': bubbles['avg_diameter'],
                'mask': mask,
                'segmentation_mask': binary  # ? add: the raw U-Net/classical mask for coverage
            }
        except Exception as e:
            logger.error(f"Bubble processing error: {e}")
            return {'count': 0, 'diameters': [], 'areas': [], 'avg_diameter': 0.0, 'mask': None}
    
    def _analyze_contours(self, contours) -> Dict[str, Any]:
        """Analyze contours with area and circularity filtering."""
        diameters, areas = [], []
        centroids = []  # Store (cx, cy, radius) for annotation
        
        for cnt in contours:
            # Calculate area
            area = cv.contourArea(cnt)
            
            # Filter by area range
            if area < self.min_bubble_area or area > self.max_bubble_area:
                continue
            
            # Calculate perimeter and circularity
            perimeter = cv.arcLength(cnt, True)
            if perimeter == 0:
                continue
            
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            
            # Filter by circularity (how round it is)
            if circularity < self.circularity_threshold:
                continue
            
            # Calculate equivalent circle diameter and radius
            diameter = np.sqrt(4 * area / np.pi)
            radius = int(diameter / 2)
            
            # Get centroid using moments
            M = cv.moments(cnt)
            if M['m00'] != 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                centroids.append((cx, cy, radius))
                
                diameters.append(diameter)
                areas.append(area)
        
        # Store centroids for annotation
        self.bubble_centroids = centroids
        
        return {
            'count': len(diameters),
            'diameters': diameters,
            'areas': areas,
            'avg_diameter': float(np.mean(diameters)) if diameters else 0.0
        }
    
    def annotate_frame(self, frame: np.ndarray, count: int, avg_size: float, coverage: float = 0.0) -> np.ndarray:
        """Draw circular boundaries on bubbles."""
        if frame is None or frame.size == 0:
            return frame
        
        output = frame.copy()
        GREEN = (0, 255, 0)
        
        # Draw circular outline for each bubble
        for cx, cy, radius in self.bubble_centroids:
            cv.circle(output, (cx, cy), radius, GREEN, 2)
        
        return output
    
    def analyze_froth(self, frame: np.ndarray, bubble_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate froth metrics from bubble data."""
        try:
            count = bubble_data['count']
            diameters = bubble_data['diameters']
            areas = bubble_data['areas']
            mask = bubble_data.get('mask')
            coverage_mask = bubble_data.get('segmentation_mask')
            if coverage_mask is None:
                coverage_mask = bubble_data.get('mask')

            # Coverage ratio
            coverage = 0.0
            if coverage_mask is not None:
                total_pixels = frame.shape[0] * frame.shape[1]
                bubble_pixels = np.count_nonzero(coverage_mask)
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
        """Calculate stability score (0-1) from size uniformity, temporal consistency, density.
        
        Uses exp(-k*cv) sensitivity so small changes in variation are visible
        across the full 0-1 range rather than compressing near 1.0.
        """
        # Size uniformity � penalises variation relative to mean diameter
        # k=4: cv of 0.10 ? 0.67, cv of 0.25 ? 0.37, cv of 0.50 ? 0.14
        cv_size = size_std / avg_diameter if avg_diameter > 0 else 1.0
        size_uniformity = float(np.exp(-4.0 * cv_size))

        # Temporal consistency � requires full history window before contributing
        # k=6: cv of 0.05 ? 0.74, cv of 0.15 ? 0.41, cv of 0.30 ? 0.17
        history_len = len(self.bubble_count_history)
        if history_len >= self.bubble_count_history.maxlen:
            count_std = float(np.std(list(self.bubble_count_history)))
            count_mean = float(np.mean(list(self.bubble_count_history)))
            cv_count = count_std / count_mean if count_mean > 0 else 1.0
            count_consistency = float(np.exp(-6.0 * cv_count))
        else:
            # Not enough history yet � hold at 0.0 so it doesn't inflate score
            count_consistency = 0.0

        # Density score (optimal: 50-200 bubbles) � unchanged
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
        
        # Store original frame
        self.last_frame = frame.copy()
        
        # Process bubbles
        bubble_data = self.process_bubbles(frame)
        if bubble_data['count'] == 0:
            logger.debug("No bubbles detected")  # Changed to debug to reduce log spam
        
        # Analyze froth
        froth_metrics = self.analyze_froth(frame, bubble_data)
        froth_metrics['timestamp'] = timestamp
        froth_metrics['success'] = True
        
        # Create annotated frame (with circular boundaries)
        # Pass coverage to show in legend
        self.last_annotated_frame = self.annotate_frame(
            frame, 
            froth_metrics['bubble_count'],
            froth_metrics['avg_bubble_size'],
            froth_metrics['froth_coverage']
        )
        
        return froth_metrics
    
    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Get last annotated frame with circular bubble boundaries.
        
        Returns:
            Annotated frame or None if no frame available
        """
        return self.last_annotated_frame

    def get_raw_frame(self) -> Optional[np.ndarray]:
        """Get the last captured unannotated camera frame.

        Returns:
            Raw frame or None if no frame available
        """
        return self.last_frame
    
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
