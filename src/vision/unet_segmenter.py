"""
U-Net ONNX Segmentation Module for Froth Flotation Vision System

Optional binary mask generator using deep learning segmentation.
Falls back gracefully to classical OpenCV if model unavailable.
"""

import cv2 as cv
import numpy as np
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class UNetSegmenter:
    """Lightweight ONNX U-Net segmentation for froth mask generation."""

    def __init__(
        self,
        model_path: str = "models/froth_unet.onnx",
        input_size: int = 256,
        threshold: float = 0.45
    ):
        """Initialize U-Net ONNX model.

        Args:
            model_path: Path to ONNX model file
            input_size: Input image size (256x256)
            threshold: Probability threshold for binary mask (default 0.45)
        """
        self.model_path = model_path
        self.input_size = input_size
        self.threshold = threshold
        self.net = None
        self.available_flag = False

        self._load_model()

    def _load_model(self) -> None:
        """Load ONNX model with error handling."""
        try:
            if not os.path.exists(self.model_path):
                logger.warning(f"U-Net model file not found: {self.model_path}")
                return

            self.net = cv.dnn.readNetFromONNX(self.model_path)
            self.available_flag = True
            logger.info(f"U-Net ONNX model loaded successfully from {self.model_path}")

        except Exception as e:
            logger.warning(f"Failed to load U-Net ONNX model: {e}")
            self.net = None
            self.available_flag = False

    def available(self) -> bool:
        """Check if U-Net model is available and ready.

        Returns:
            True if model loaded successfully, False otherwise
        """
        return self.available_flag

    def predict_mask(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Generate binary segmentation mask using U-Net ONNX.

        Args:
            frame: BGR input frame from camera

        Returns:
            Binary mask (uint8, 255=foreground, 0=background) or None if inference fails

        Preprocessing pipeline:
        - BGR → RGB conversion
        - Resize to 256x256
        - Normalize to [0, 1]
        - Convert to NCHW format (1 x 3 x 256 x 256)

        Postprocessing pipeline:
        - Apply sigmoid to logits
        - Threshold at 0.45
        - Resize back to original frame size
        - Morphological cleanup (3x3 elliptical kernel)
        - Return uint8 mask (255 or 0)
        """
        if not self.available_flag or self.net is None:
            return None

        if frame is None or frame.size == 0:
            return None

        try:
            original_height, original_width = frame.shape[:2]

            # Preprocess frame
            rgb_frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
            resized = cv.resize(rgb_frame, (self.input_size, self.input_size))
            normalized = resized.astype(np.float32) / 255.0

            # Convert to NCHW format (1 x 3 x 256 x 256)
            blob = cv.dnn.blobFromImage(
                normalized,
                scalefactor=1.0,
                size=(self.input_size, self.input_size),
                mean=[0, 0, 0],
                swapRB=False,
                crop=False
            )

            # Run inference
            self.net.setInput(blob)
            output = self.net.forward()

            # output shape: (1, 1, 256, 256)
            pred = output.squeeze()

            # Apply sigmoid to convert logits to probability
            prob_mask = 1.0 / (1.0 + np.exp(-pred))

            # Threshold to binary
            binary_mask = (prob_mask > self.threshold).astype(np.uint8) * 255

            # Resize back to original frame size
            binary_mask = cv.resize(binary_mask, (original_width, original_height))

            # Morphological cleanup
            kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3, 3))
            binary_mask = cv.morphologyEx(binary_mask, cv.MORPH_OPEN, kernel, iterations=1)
            binary_mask = cv.morphologyEx(binary_mask, cv.MORPH_CLOSE, kernel, iterations=1)

            return binary_mask

        except Exception as e:
            logger.error(f"U-Net inference failed: {e}")
            return None
