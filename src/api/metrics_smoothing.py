"""Time-window moving average for bubble count smoothing."""

from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Deque, Tuple


@dataclass
class TimeWindowMovingAverage:
    """Time-window moving average for bubble count smoothing.
    
    Maintains a sliding window of samples over a specified time period
    and returns the average. Old samples are automatically discarded.
    
    Args:
        window_seconds: Time window in seconds (default: 4.0)
    
    Example:
        >>> ma = TimeWindowMovingAverage(window_seconds=4.0)
        >>> ma.update(100)
        100
        >>> ma.update(110)
        105
        >>> ma.update(90)
        100
    """
    window_seconds: float = 4.0

    def __post_init__(self) -> None:
        """Initialize internal state."""
        self._samples: Deque[Tuple[float, float]] = deque()
        self._sum: float = 0.0

    def update(self, value: float, now: float | None = None) -> int:
        """Update moving average with new sample.
        
        Args:
            value: New bubble count sample
            now: Current timestamp (default: monotonic time)
        
        Returns:
            Smoothed count as integer (rounded)
        """
        t = monotonic() if now is None else now
        v = float(value)

        # Add new sample
        self._samples.append((t, v))
        self._sum += v

        # Remove samples outside window
        cutoff = t - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            _, old = self._samples.popleft()
            self._sum -= old

        # Return average (handle empty case)
        if not self._samples:
            return int(round(v))

        return int(round(self._sum / len(self._samples)))

    def reset(self) -> None:
        """Clear all samples."""
        self._samples.clear()
        self._sum = 0.0
