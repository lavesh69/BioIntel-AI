from __future__ import annotations

import time
from dataclasses import asdict
from typing import Iterable

from biointel.internet.downloader import InternetDownloadError, fetch_public_bytes
from biointel.internet.network_policy import InternetPolicy, internet_policy_from_environment

from .catalog import ScientificResource


def _probe_policy() -> InternetPolicy:
    current = internet_policy_from_environment()
    return InternetPolicy(
        enabled=current.enabled,
        allow_public_https=current.allow_public_https,
        official_hosts_only=True,
        resolve_dns=current.resolve_dns,
        max_download_bytes=min(current.max_download_bytes, 512 * 1024),
        timeout_seconds=min(current.timeout_seconds, 6.0),
        retries=0,
    )


def probe_resources(resources: Iterable[ScientificResource]) -> dict[str, object]:
    policy = _probe_policy()
    rows: list[dict[str, object]] = []
    for resource in resources:
        started = time.perf_counter()
        try:
            _body, metadata = fetch_public_bytes(
                resource.homepage,
                policy=policy,
                allowed_hosts={resource.host},
                max_bytes=512 * 1024,
                accept="text/html,application/json,text/plain,*/*;q=0.5",
            )
        except InternetDownloadError as exc:
            text = str(exc)
            # Some large home pages ignore byte-range/size hints. Reaching the
            # server and receiving an oversized response still proves network
            # availability, while avoiding a large download.
            available = "exceeds the" in text and "limit" in text
            rows.append(
                {
                    "resource": resource.name,
                    "host": resource.host,
                    "available": available,
                    "state": "reachable; response intentionally truncated" if available else "optional service unavailable",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": "" if available else text,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "resource": resource.name,
                    "host": resource.host,
                    "available": False,
                    "state": "optional service unavailable",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        else:
            rows.append(
                {
                    "resource": resource.name,
                    "host": resource.host,
                    "available": True,
                    "state": "available",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "status": metadata.get("status"),
                    "content_type": metadata.get("content_type"),
                    "error": "",
                }
            )
    return {
        "schema": "biointel.scientific-resources.v209.availability.v1",
        "policy": asdict(policy),
        "resources": rows,
        "available_count": sum(bool(row.get("available")) for row in rows),
        "checked_count": len(rows),
        "scientific_boundary": "Connectivity confirms only website reachability; it does not validate evidence quality or database completeness.",
    }


__all__ = ["probe_resources"]
