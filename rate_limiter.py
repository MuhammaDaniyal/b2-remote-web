from __future__ import annotations

import collections
import threading
import time
from typing import Deque, Dict, Tuple


class CommandRateLimiter:
    def __init__(
        self,
        min_interval_seconds: float,
        max_commands_per_window: int,
        window_seconds: float,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.max_commands_per_window = max_commands_per_window
        self.window_seconds = window_seconds
        self._history: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> Tuple[bool, float]:
        now = time.monotonic()

        with self._lock:
            history = self._history.setdefault(key, collections.deque())

            while history and now - history[0] >= self.window_seconds:
                history.popleft()

            if history:
                elapsed = now - history[-1]
                if elapsed < self.min_interval_seconds:
                    return False, self.min_interval_seconds - elapsed

            if len(history) >= self.max_commands_per_window:
                retry_after = self.window_seconds - (now - history[0])
                return False, max(retry_after, 0.0)

            history.append(now)
            return True, 0.0
