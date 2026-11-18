from __future__ import annotations

from threading import Event, RLock


class CancellationRegistry:
    def __init__(self) -> None:
        self._events: dict[str, Event] = {}
        self._lock = RLock()

    def register(self, request_id: str) -> Event:
        with self._lock:
            event = self._events.setdefault(request_id, Event())
        return event

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            event = self._events.get(request_id)
        if event is None:
            return False
        event.set()
        return True

    def release(self, request_id: str) -> None:
        with self._lock:
            self._events.pop(request_id, None)


CANCELLATIONS = CancellationRegistry()