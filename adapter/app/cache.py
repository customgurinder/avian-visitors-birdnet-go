"""Tiny thread-safe in-memory TTL cache.

BirdNET-Go responses change slowly (new detections arrive every few seconds
at most), and the AV frontend polls several endpoints together. Caching
upstream GETs for a few seconds keeps load off BirdNET-Go and mirrors the
original PHP facade's `Cache-Control: max-age=30`.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = max(0, ttl_seconds)
        self._store: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        if self._ttl == 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Hashable, value: Any) -> None:
        if self._ttl == 0:
            return
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
