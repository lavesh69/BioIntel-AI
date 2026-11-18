from __future__ import annotations

import json
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass(frozen=True)
class CacheStats:
    name: str
    entries: int
    estimated_bytes: int
    hits: int
    misses: int
    evictions: int
    expirations: int
    max_entries: int
    max_bytes: int
    ttl_seconds: float


@dataclass
class _Entry(Generic[V]):
    value: V
    created_monotonic: float
    estimated_bytes: int


_REGISTRY_LOCK = threading.RLock()
_REGISTRY: dict[str, "BoundedTTLCache[Hashable, object]"] = {}


def _estimate_bytes(value: object) -> int:
    try:
        return len(json.dumps(value, default=str, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        try:
            return int(sys.getsizeof(value))
        except Exception:
            return 1


class BoundedTTLCache(Generic[K, V]):
    """Small thread-safe process cache with hard count, byte and TTL bounds.

    It deliberately returns the stored object. Callers that expose mutable frames
    to different sessions should store immutable values or make defensive copies.
    """

    def __init__(
        self,
        *,
        name: str,
        max_entries: int = 128,
        max_bytes: int = 64 * 1024 * 1024,
        ttl_seconds: float = 300.0,
    ) -> None:
        if not name.strip():
            raise ValueError("cache name is required")
        if max_entries < 1 or max_bytes < 1 or ttl_seconds <= 0:
            raise ValueError("cache limits must be positive")
        self.name = name.strip()
        self.max_entries = int(max_entries)
        self.max_bytes = int(max_bytes)
        self.ttl_seconds = float(ttl_seconds)
        self._items: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._bytes = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0
        self._lock = threading.RLock()
        with _REGISTRY_LOCK:
            _REGISTRY[self.name] = self  # type: ignore[assignment]

    def _expired(self, entry: _Entry[V], now: float) -> bool:
        return now - entry.created_monotonic >= self.ttl_seconds

    def _remove(self, key: K, *, expired: bool = False, evicted: bool = False) -> None:
        entry = self._items.pop(key, None)
        if entry is None:
            return
        self._bytes = max(0, self._bytes - entry.estimated_bytes)
        if expired:
            self._expirations += 1
        if evicted:
            self._evictions += 1

    def _prune_expired(self, now: float) -> None:
        for key, entry in list(self._items.items()):
            if self._expired(entry, now):
                self._remove(key, expired=True)

    def get(self, key: K, default: V | None = None) -> V | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                self._misses += 1
                return default
            if self._expired(entry, now):
                self._remove(key, expired=True)
                self._misses += 1
                return default
            self._items.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: K, value: V, *, estimated_bytes: int | None = None) -> bool:
        size = max(1, int(estimated_bytes if estimated_bytes is not None else _estimate_bytes(value)))
        if size > self.max_bytes:
            return False
        now = time.monotonic()
        with self._lock:
            self._prune_expired(now)
            self._remove(key)
            self._items[key] = _Entry(value=value, created_monotonic=now, estimated_bytes=size)
            self._bytes += size
            while len(self._items) > self.max_entries or self._bytes > self.max_bytes:
                oldest = next(iter(self._items))
                self._remove(oldest, evicted=True)
            return True

    def get_or_compute(self, key: K, factory: Callable[[], V]) -> V:
        sentinel = object()
        current = self.get(key, sentinel)  # type: ignore[arg-type]
        if current is not sentinel:
            return current  # type: ignore[return-value]
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._bytes = 0

    def stats(self) -> CacheStats:
        with self._lock:
            self._prune_expired(time.monotonic())
            return CacheStats(
                name=self.name,
                entries=len(self._items),
                estimated_bytes=self._bytes,
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                expirations=self._expirations,
                max_entries=self.max_entries,
                max_bytes=self.max_bytes,
                ttl_seconds=self.ttl_seconds,
            )


def cache_registry_snapshot() -> list[dict[str, int | float | str]]:
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    return [cache.stats().__dict__.copy() for cache in caches]


def clear_registered_caches() -> int:
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    for cache in caches:
        cache.clear()
    return len(caches)
