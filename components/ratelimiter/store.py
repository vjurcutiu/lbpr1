from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

class StateStore:
    """Port interface for a key-value atomic update store."""

    def get(self, key: str) -> Optional[dict]:
        raise NotImplementedError

    def set(self, key: str, value: dict) -> None:
        raise NotImplementedError

    def update(self, key: str, fn: Callable[[Optional[dict]], dict]) -> dict:
        """Atomically read-modify-write the value for key and return the new value."""
        raise NotImplementedError


class InMemoryStore(StateStore):
    """Thread-safe in-memory store with coarse-grained lock.

    For single-process dev/testing. Multi-process needs a Redis adapter (vNext).
    """

    def __init__(self):
        self._data: Dict[str, dict] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, key: str, fn):
        with self._lock:
            current = self._data.get(key)
            new_value = fn(current)
            self._data[key] = new_value
            return new_value