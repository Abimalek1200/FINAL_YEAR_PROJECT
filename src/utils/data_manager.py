"""
Data Manager - ML Training Data Only

Minimal database interface for anomaly detection training.
Optimized for performance on Raspberry Pi.
"""

import sqlite3
from typing import List
from pathlib import Path


class DataManager:
    """Lightweight database for ML training data collection."""
    
    def __init__(self, db_path: str = "data/flotation.db"):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()
    
    def _create_table(self):
        """Create metrics table if not exists."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bubble_count INTEGER,
                avg_bubble_size REAL,
                size_std_dev REAL,
                coverage_ratio REAL
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)")
        self.conn.commit()
    
    def save_metrics(self, metrics: dict):
        """Save metrics to database.
        
        Args:
            metrics: Dictionary with bubble_count, avg_bubble_size, size_std_dev, coverage_ratio
        """
        self.conn.execute("""
            INSERT INTO metrics (bubble_count, avg_bubble_size, size_std_dev, coverage_ratio)
            VALUES (?, ?, ?, ?)
        """, (
            metrics.get('bubble_count', 0),
            metrics.get('avg_bubble_size', 0.0),
            metrics.get('size_std_dev', 0.0),
            metrics.get('froth_coverage', 0.0)
        ))
        self.conn.commit()
    
    def get_training_data(self, limit: int = 300) -> List[List[float]]:
        """Get recent data for ML training.
        
        Args:
            limit: Number of samples to retrieve
        
        Returns:
            List of feature vectors: [[bubble_count, avg_size, std_dev, coverage], ...]
        """
        cursor = self.conn.execute("""
            SELECT bubble_count, avg_bubble_size, size_std_dev, coverage_ratio
            FROM metrics
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        return [list(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection."""
        self.conn.close()

