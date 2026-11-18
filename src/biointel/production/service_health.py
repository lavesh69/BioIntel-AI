from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    endpoint: str
    available: bool
    latency_ms: float | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _safe_endpoint(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse((parsed.scheme, host + port, parsed.path, "", "", ""))


def tcp_health(name: str, host: str, port: int, *, timeout: float = 2.0) -> ServiceStatus:
    started = time.perf_counter()
    endpoint = f"{host}:{port}"
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            latency = (time.perf_counter() - started) * 1000
            return ServiceStatus(name, endpoint, True, round(latency, 2), "TCP connection accepted")
    except OSError as exc:
        return ServiceStatus(name, endpoint, False, None, f"{type(exc).__name__}: connection failed")


def http_health(name: str, url: str, *, timeout: float = 3.0) -> ServiceStatus:
    started = time.perf_counter()
    safe = _safe_endpoint(url)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "BioIntel-AI/9.6"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            latency = (time.perf_counter() - started) * 1000
            code = int(getattr(response, "status", 200))
            return ServiceStatus(name, safe, 200 <= code < 500, round(latency, 2), f"HTTP {code}")
    except (OSError, urllib.error.URLError) as exc:
        return ServiceStatus(name, safe, False, None, f"{type(exc).__name__}: request failed")


def health_from_url(name: str, url: str) -> ServiceStatus:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return http_health(name, url)
    defaults = {"postgres": 5432, "postgresql": 5432, "redis": 6379}
    try:
        port = parsed.port or defaults.get(parsed.scheme)
    except ValueError:
        port = None
    if parsed.hostname and port:
        return tcp_health(name, parsed.hostname, port)
    return ServiceStatus(name, _safe_endpoint(url), False, None, "Unsupported or incomplete endpoint")
