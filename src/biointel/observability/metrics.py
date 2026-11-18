from __future__ import annotations

import re
import time
from collections import defaultdict
from threading import Lock
from typing import Any

_DYNAMIC_SEGMENT = re.compile(r"^(?:\d+|[0-9a-f]{16,}|[A-Fa-f0-9-]{24,})$")


def normalize_path(path: str) -> str:
    parts = []
    for part in path.strip().split("/"):
        if not part:
            continue
        parts.append(":id" if _DYNAMIC_SEGMENT.match(part) else part)
    return "/" + "/".join(parts)


class MetricsRegistry:
    """Dependency-light process metrics with Prometheus text export."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = Lock()
        self._request_count: dict[tuple[str, str, int], int] = defaultdict(int)
        self._request_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._request_duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._exceptions: dict[tuple[str, str], int] = defaultdict(int)
        self._jobs: dict[str, int] = defaultdict(int)

    def observe_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        route = normalize_path(path)
        method = method.upper()
        with self._lock:
            self._request_count[(method, route, int(status_code))] += 1
            self._request_duration_sum[(method, route)] += max(float(duration_seconds), 0.0)
            self._request_duration_count[(method, route)] += 1

    def observe_exception(self, path: str, exception_name: str) -> None:
        with self._lock:
            self._exceptions[(normalize_path(path), exception_name[:120])] += 1

    def observe_job(self, status: str) -> None:
        with self._lock:
            self._jobs[status.lower().strip() or "unknown"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            request_count = sum(self._request_count.values())
            error_count = sum(
                count
                for (_, _, status), count in self._request_count.items()
                if status >= 400
            )
            duration_count = sum(self._request_duration_count.values())
            duration_sum = sum(self._request_duration_sum.values())
            return {
                "uptime_seconds": round(time.time() - self.started_at, 3),
                "request_count": request_count,
                "error_count": error_count,
                "mean_request_duration_ms": round(
                    1000.0 * duration_sum / max(duration_count, 1), 3
                ),
                "exception_count": sum(self._exceptions.values()),
                "job_events": dict(self._jobs),
            }

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def prometheus_text(self) -> str:
        lines = [
            "# HELP biointel_process_uptime_seconds Process uptime in seconds.",
            "# TYPE biointel_process_uptime_seconds gauge",
            f"biointel_process_uptime_seconds {time.time() - self.started_at:.6f}",
            "# HELP biointel_http_requests_total Total HTTP requests.",
            "# TYPE biointel_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), count in sorted(self._request_count.items()):
                lines.append(
                    'biointel_http_requests_total{method="%s",route="%s",status="%s"} %d'
                    % (self._escape(method), self._escape(route), status, count)
                )
            lines.extend(
                [
                    "# HELP biointel_http_request_duration_seconds_sum Sum of HTTP request durations.",
                    "# TYPE biointel_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, route), total in sorted(self._request_duration_sum.items()):
                lines.append(
                    'biointel_http_request_duration_seconds_sum{method="%s",route="%s"} %.9f'
                    % (self._escape(method), self._escape(route), total)
                )
            lines.extend(
                [
                    "# HELP biointel_http_request_duration_seconds_count Count of observed HTTP request durations.",
                    "# TYPE biointel_http_request_duration_seconds_count counter",
                ]
            )
            for (method, route), count in sorted(self._request_duration_count.items()):
                lines.append(
                    'biointel_http_request_duration_seconds_count{method="%s",route="%s"} %d'
                    % (self._escape(method), self._escape(route), count)
                )
            lines.extend(
                [
                    "# HELP biointel_unhandled_exceptions_total Unhandled exceptions by route and class.",
                    "# TYPE biointel_unhandled_exceptions_total counter",
                ]
            )
            for (route, exception_name), count in sorted(self._exceptions.items()):
                lines.append(
                    'biointel_unhandled_exceptions_total{route="%s",exception="%s"} %d'
                    % (self._escape(route), self._escape(exception_name), count)
                )
            lines.extend(
                [
                    "# HELP biointel_job_events_total Observed job lifecycle events.",
                    "# TYPE biointel_job_events_total counter",
                ]
            )
            for status, count in sorted(self._jobs.items()):
                lines.append(
                    'biointel_job_events_total{status="%s"} %d'
                    % (self._escape(status), count)
                )
        return "\n".join(lines) + "\n"


METRICS = MetricsRegistry()
