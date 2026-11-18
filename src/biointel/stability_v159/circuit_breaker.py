from __future__ import annotations

from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class CircuitDecision:
    allowed: bool
    failure_count: int
    retry_after_seconds: float
    reason: str


_LOCK = threading.RLock()
_FAILURES: dict[str, tuple[int, float]] = {}
_MAX_FAILURES = 2
_COOLDOWN_SECONDS = 30.0


def circuit_decision(fingerprint: str, *, now: float | None = None) -> CircuitDecision:
    timestamp = time.monotonic() if now is None else float(now)
    with _LOCK:
        count, last_failure = _FAILURES.get(fingerprint, (0, 0.0))
        elapsed = timestamp - last_failure
        if count >= _MAX_FAILURES and elapsed < _COOLDOWN_SECONDS:
            retry_after = max(0.0, _COOLDOWN_SECONDS - elapsed)
            return CircuitDecision(
                allowed=False,
                failure_count=count,
                retry_after_seconds=retry_after,
                reason="Repeated identical failures were temporarily blocked to prevent a crash loop.",
            )
        if elapsed >= _COOLDOWN_SECONDS and count:
            _FAILURES.pop(fingerprint, None)
            count = 0
        return CircuitDecision(True, count, 0.0, "Execution admitted.")


def record_failure(fingerprint: str, *, now: float | None = None) -> int:
    timestamp = time.monotonic() if now is None else float(now)
    with _LOCK:
        count, _ = _FAILURES.get(fingerprint, (0, 0.0))
        count += 1
        _FAILURES[fingerprint] = (count, timestamp)
        return count


def clear_failure(fingerprint: str) -> None:
    with _LOCK:
        _FAILURES.pop(fingerprint, None)
