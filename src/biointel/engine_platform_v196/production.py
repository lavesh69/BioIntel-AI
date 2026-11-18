from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pandas as pd


@dataclass(frozen=True)
class ProductionConfiguration:
    database_url: str = ""
    redis_url: str = ""
    object_storage_endpoint: str = ""
    object_storage_bucket: str = ""
    oidc_issuer: str = ""
    otel_endpoint: str = ""
    crdt_enabled: bool = False


def _url_check(value: str, schemes: set[str], *, require_host: bool = True) -> tuple[bool, str]:
    if not value:
        return False, "not configured"
    parsed = urlparse(value)
    if parsed.scheme.lower() not in schemes:
        return False, "unsupported URL scheme"
    if require_host and not parsed.hostname:
        return False, "host missing"
    if parsed.password:
        return True, "configured; secret is redacted"
    return True, "configured"


def validate_production_configuration(configuration: ProductionConfiguration) -> pd.DataFrame:
    database_ok, database_note = _url_check(configuration.database_url, {"postgresql", "postgres"})
    redis_ok, redis_note = _url_check(configuration.redis_url, {"redis", "rediss"})
    object_ok, object_note = _url_check(configuration.object_storage_endpoint, {"https", "http"})
    if object_ok and not configuration.object_storage_bucket.strip():
        object_ok, object_note = False, "bucket missing"
    oidc_ok, oidc_note = _url_check(configuration.oidc_issuer, {"https"})
    otel_ok, otel_note = _url_check(configuration.otel_endpoint, {"https", "http", "grpc"})
    rows = [
        {"service": "postgresql", "configured": database_ok, "note": database_note, "required_for_personal_mode": False},
        {"service": "redis", "configured": redis_ok, "note": redis_note, "required_for_personal_mode": False},
        {"service": "object_storage", "configured": object_ok, "note": object_note, "required_for_personal_mode": False},
        {"service": "oidc", "configured": oidc_ok, "note": oidc_note, "required_for_personal_mode": False},
        {"service": "observability", "configured": otel_ok, "note": otel_note, "required_for_personal_mode": False},
        {"service": "crdt", "configured": bool(configuration.crdt_enabled), "note": "built-in deterministic RGA enabled" if configuration.crdt_enabled else "disabled", "required_for_personal_mode": False},
    ]
    return pd.DataFrame(rows)


def deployment_plan(configuration: ProductionConfiguration) -> dict[str, Any]:
    checks = validate_production_configuration(configuration)
    configured = int(checks["configured"].sum())
    return {
        "schema": "biointel.production-deployment-plan.v1",
        "mode": "lab-distributed" if configured else "personal-local",
        "configured_services": configured,
        "service_count": len(checks),
        "checks": checks.to_dict(orient="records"),
        "secrets_included": False,
        "claim_boundary": "Configuration validation does not start external servers or prove their availability. Credentials and network probes remain operator-controlled.",
    }
