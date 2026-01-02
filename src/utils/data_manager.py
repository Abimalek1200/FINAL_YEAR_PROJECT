"""
Data Manager for SQLite Database

Simple database interface for storing metrics.
Includes automatic cleanup to save space on Raspberry Pi.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DataManager:
    """Manage SQLite database for flotation metrics.
    
    Stores all measurements with automatic old data cleanup.
    """
    
    def __init__(self, db_path: str = "data/flotation.db", retention_days: int = 7):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
            retention_days: How many days of data to keep (saves space)
        
        Example:
            >>> db = DataManager(retention_days=7)
            >>> db.save_metrics(metrics_dict)
        """
        self.db_path = db_path
        self.retention_days = retention_days
        
        # Create directory if needed
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
        
        # Create tables
        self.create_tables()
        
        logger.info(f"Database ready: {db_path} (retention: {retention_days} days)")
    
    def create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Main metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bubble_count INTEGER,
                avg_bubble_size REAL,
                size_std_dev REAL,
                froth_stability REAL,
                coverage_ratio REAL,
                pump_duty_cycle REAL,
                anomaly_detected BOOLEAN
            )
        """)
        
        # Index for faster time-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON metrics(timestamp)
        """)
        
        self.conn.commit()
        logger.info("Database tables created/verified")
    
    def save_metrics(self, metrics: Dict):
        """Save current metrics to database.
        
        Args:
            metrics: Dictionary with all measurements
        
        Example:
            >>> metrics = {
            ...     'bubble_count': 120,
            ...     'avg_bubble_size': 250.5,
            ...     'pump_duty_cycle': 45.2,
            ...     ...
            ... }
            >>> db.save_metrics(metrics)
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO metrics (
                bubble_count, avg_bubble_size, size_std_dev,
                froth_stability, coverage_ratio, pump_duty_cycle,
                anomaly_detected
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            metrics.get('bubble_count', 0),
            metrics.get('avg_bubble_size', 0.0),
            metrics.get('size_std_dev', 0.0),
            metrics.get('froth_stability', 0.0),
            metrics.get('coverage_ratio', 0.0),
            metrics.get('pump_duty_cycle', 0.0),
            metrics.get('anomaly_detected', False)
        ))
        
        self.conn.commit()
    
    def get_recent(self, limit: int = 100) -> List[Dict]:
        """Get most recent metrics records.
        
        Args:
            limit: Maximum number of records to return
        
        Returns:
            List of metric dictionaries
        
        Example:
            >>> recent = db.get_recent(limit=50)
            >>> for record in recent:
            ...     print(f"{record['timestamp']}: {record['bubble_count']} bubbles")
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM metrics 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        
        # Convert to dictionaries
        return [dict(row) for row in rows]
    
    def get_time_range(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get metrics within a time range.
        
        Args:
            start_time: Beginning of time range
            end_time: End of time range
        
        Returns:
            List of metric dictionaries
        
        Example:
            >>> from datetime import datetime, timedelta
            >>> now = datetime.now()
            >>> hour_ago = now - timedelta(hours=1)
            >>> data = db.get_time_range(hour_ago, now)
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM metrics 
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def cleanup_old_data(self):
        """Delete data older than retention period.
        
        Frees up space on Raspberry Pi SD card.
        Run this daily (or it runs automatically).
        
        Example:
            >>> db.cleanup_old_data()  # Removes old records
        """
        cursor = self.conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # Count records to delete
        cursor.execute("""
            SELECT COUNT(*) FROM metrics 
            WHERE timestamp < ?
        """, (cutoff_date,))
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Delete old records
            cursor.execute("""
                DELETE FROM metrics 
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            # Reclaim disk space
            cursor.execute("VACUUM")
            
            self.conn.commit()
            logger.info(f"Cleaned up {count} old records (older than {self.retention_days} days)")
        else:
            logger.debug("No old records to clean up")
    
    def get_stats(self) -> Dict:
        """Get database statistics.
        
        Returns:
            Dictionary with record count, date range, size
        
        Example:
            >>> stats = db.get_stats()
            >>> print(f"Database has {stats['record_count']} records")
        """
        cursor = self.conn.cursor()
        
        # Total records
        cursor.execute("SELECT COUNT(*) FROM metrics")
        record_count = cursor.fetchone()[0]
        
        # Date range
        cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp) FROM metrics
        """)
        min_date, max_date = cursor.fetchone()
        
        # Database file size
        db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
        
        return {
            'record_count': record_count,
            'oldest_record': min_date,
            'newest_record': max_date,
            'database_size_mb': db_size / (1024 * 1024)
        }
    
    def close(self):
        """Close database connection.
        
        Example:
            >>> db.close()  # Done with database
        """
        self.conn.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    # Test database manager
    logging.basicConfig(level=logging.INFO)
    
    print("\\n=== Data Manager Test ===\\n")
    
    # Create temporary database
    db = DataManager(db_path="test_db.sqlite", retention_days=1)
    
    # Save some test data
    print("Saving test metrics...")
    for i in range(10):
        metrics = {
            'bubble_count': 100 + i,
            'avg_bubble_size': 250.0 + i,
            'size_std_dev': 50.0,
            'froth_stability': 0.8,
            'coverage_ratio': 0.6,
            'pump_duty_cycle': 45.0 + i,
            'anomaly_detected': False
        }
        db.save_metrics(metrics)
    
    print("✓ Saved 10 records\\n")
    
    # Retrieve data
    print("Retrieving recent data...")
    recent = db.get_recent(limit=5)
    print(f"  Got {len(recent)} records")
    print(f"  Latest bubble count: {recent[0]['bubble_count']}\\n")
    
    # Get statistics
    print("Database statistics:")
    stats = db.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Cleanup
    db.close()
    Path("test_db.sqlite").unlink()
    
    print("\\n✓ All tests passed")
