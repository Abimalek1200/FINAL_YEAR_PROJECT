"""
Froth Anomaly Detector

Uses Isolation Forest to detect unusual froth patterns.
Simple, lightweight machine learning for Raspberry Pi.
"""

import logging
import numpy as np
from typing import List, Optional
from sklearn.ensemble import IsolationForest
import pickle
import os

logger = logging.getLogger(__name__)


class FrothAnomalyDetector:
    """Detect abnormal froth behavior using machine learning.
    
    Uses Isolation Forest - a fast algorithm that finds "outliers"
    (data points that don't fit the normal pattern).
    """
    
    def __init__(self, contamination: float = 0.1):
        """Initialize anomaly detector.
        
        Args:
            contamination: Expected fraction of anomalies (0.1 = 10%)
                          Lower = stricter (fewer alerts)
                          Higher = more sensitive (more alerts)
        
        Example:
            >>> detector = FrothAnomalyDetector(contamination=0.1)
            >>> detector.train(normal_operation_data)
        """
        self.contamination = contamination
        self.is_trained = False
        
        # Create Isolation Forest model (optimized for Raspberry Pi)
        self.model = IsolationForest(
            contamination=contamination,  # Expected anomaly rate
            max_samples=256,  # Small for RPi memory
            n_estimators=50,  # Balance accuracy vs speed
            random_state=42,  # Reproducible results
            n_jobs=1  # Single core (RPi friendly)
        )
        
        logger.info(f"Anomaly detector created (contamination={contamination})")
    
    def train(self, normal_data: np.ndarray):
        """Train detector on normal operating conditions.
        
        Collect 1-2 hours of good flotation data, then call this.
        
        Args:
            normal_data: Array of shape (n_samples, n_features)
                        Features: [bubble_count, avg_size, std_dev, coverage]
        
        Example:
            >>> # Collect data during good operation
            >>> data = []
            >>> for i in range(1000):  # 1000 frames
            ...     metrics = get_froth_metrics()
            ...     data.append([
            ...         metrics['bubble_count'],
            ...         metrics['avg_bubble_size'],
            ...         metrics['size_std_dev'],
            ...         metrics['coverage_ratio']
            ...     ])
            >>> detector.train(np.array(data))
        """
        if len(normal_data) < 100:
            logger.warning(f"Only {len(normal_data)} samples - need 100+ for good training")
        
        logger.info(f"Training on {len(normal_data)} samples...")
        
        # Fit the model
        self.model.fit(normal_data)
        self.is_trained = True
        
        logger.info("✓ Training complete - detector ready")
    
    def predict(self, features: List[float]) -> int:
        """Check if current froth is normal or anomalous.
        
        Args:
            features: [bubble_count, avg_size, std_dev, coverage]
        
        Returns:
            1 if normal, -1 if anomaly detected
        
        Example:
            >>> features = [bubble_count, avg_size, std_dev, coverage]
            >>> result = detector.predict(features)
            >>> if result == -1:
            ...     print("⚠ Anomaly detected!")
        """
        if not self.is_trained:
            logger.warning("Detector not trained - returning normal")
            return 1
        
        # Reshape for sklearn (expects 2D array)
        features_array = np.array(features).reshape(1, -1)
        
        # Predict: 1 = normal, -1 = anomaly
        prediction = self.model.predict(features_array)[0]
        
        if prediction == -1:
            logger.warning(f"Anomaly detected! Features: {features}")
        
        return int(prediction)
    
    def get_anomaly_score(self, features: List[float]) -> float:
        """Get anomaly score (how unusual this data is).
        
        More negative = more anomalous
        
        Args:
            features: [bubble_count, avg_size, std_dev, coverage]
        
        Returns:
            Anomaly score (typically between -0.5 and 0.5)
        
        Example:
            >>> score = detector.get_anomaly_score(features)
            >>> print(f"Anomaly score: {score:.3f}")
        """
        if not self.is_trained:
            return 0.0
        
        features_array = np.array(features).reshape(1, -1)
        score = self.model.score_samples(features_array)[0]
        
        return float(score)
    
    def save(self, filepath: str = "models/anomaly_detector.pkl"):
        """Save trained model to file.
        
        Args:
            filepath: Where to save the model
        
        Example:
            >>> detector.save("models/anomaly_detector.pkl")
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump(self.model, f)
        
        logger.info(f"Model saved to {filepath}")
    
    def load(self, filepath: str = "models/anomaly_detector.pkl"):
        """Load previously trained model.
        
        Args:
            filepath: Path to saved model
        
        Example:
            >>> detector.load("models/anomaly_detector.pkl")
        """
        if not os.path.exists(filepath):
            logger.error(f"Model file not found: {filepath}")
            return False
        
        with open(filepath, 'rb') as f:
            self.model = pickle.load(f)
        
        self.is_trained = True
        logger.info(f"Model loaded from {filepath}")
        return True


def collect_training_data(metrics_history: List[dict]) -> np.ndarray:
    """Convert metrics history to training data format.
    
    Helper function to prepare data for training.
    
    Args:
        metrics_history: List of metrics dictionaries
    
    Returns:
        Numpy array ready for training
    
    Example:
        >>> # After collecting metrics for a while:
        >>> history = [
        ...     {'bubble_count': 120, 'avg_bubble_size': 250, ...},
        ...     {'bubble_count': 118, 'avg_bubble_size': 248, ...},
        ... ]
        >>> training_data = collect_training_data(history)
        >>> detector.train(training_data)
    """
    features = []
    
    for metrics in metrics_history:
        features.append([
            metrics.get('bubble_count', 0),
            metrics.get('avg_bubble_size', 0),
            metrics.get('size_std_dev', 0),
            metrics.get('coverage_ratio', 0)
        ])
    
    return np.array(features)


if __name__ == "__main__":
    # Test anomaly detector
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== Anomaly Detector Test ===\n")
    
    # Create detector
    detector = FrothAnomalyDetector(contamination=0.1)
    
    # Generate synthetic "normal" data
    print("Generating normal operating data...")
    np.random.seed(42)
    normal_data = []
    
    for i in range(500):
        # Normal: bubble_count ~120, avg_size ~250
        bubble_count = np.random.normal(120, 10)
        avg_size = np.random.normal(250, 20)
        std_dev = np.random.normal(50, 10)
        coverage = np.random.normal(0.6, 0.1)
        
        normal_data.append([bubble_count, avg_size, std_dev, coverage])
    
    normal_data = np.array(normal_data)
    
    # Train detector
    detector.train(normal_data)
    
    # Test on normal data
    print("\nTesting on normal data:")
    test_normal = [120, 250, 50, 0.6]
    result = detector.predict(test_normal)
    score = detector.get_anomaly_score(test_normal)
    print(f"  Features: {test_normal}")
    print(f"  Result: {'Normal ✓' if result == 1 else 'Anomaly ✗'}")
    print(f"  Score: {score:.3f}")
    
    # Test on anomalous data
    print("\nTesting on anomalous data:")
    test_anomaly = [200, 400, 100, 0.9]  # Very different!
    result = detector.predict(test_anomaly)
    score = detector.get_anomaly_score(test_anomaly)
    print(f"  Features: {test_anomaly}")
    print(f"  Result: {'Normal ✓' if result == 1 else 'Anomaly ✗'}")
    print(f"  Score: {score:.3f}")
    
    # Save and load test
    print("\nTesting save/load...")
    detector.save("test_model.pkl")
    
    new_detector = FrothAnomalyDetector()
    new_detector.load("test_model.pkl")
    
    result = new_detector.predict(test_normal)
    print(f"  Loaded model works: {'✓' if result == 1 else '✗'}")
    
    # Cleanup
    os.remove("test_model.pkl")
    
    print("\n✓ All tests passed")
