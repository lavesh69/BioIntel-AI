from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigurationFinding:
    key: str
    severity: str
    message: str
    remediation: str


def runtime_environment() -> str:
    return os.getenv("BIOINTEL_ENV", "local").strip().lower() or "local"


def is_production() -> bool:
    return runtime_environment() in {"production", "prod"}


def configured_api_clients() -> list[dict[str, Any]]:
    raw = os.getenv("BIOINTEL_API_CLIENTS_JSON", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    clients = payload if isinstance(payload, list) else payload.get("clients", [])
    return [item for item in clients if isinstance(item, dict)]


def _secret_strength(value: str) -> bool:
    if len(value) < 24:
        return False
    classes = sum(
        bool(re.search(pattern, value))
        for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]")
    )
    return classes >= 3


def validate_runtime_configuration() -> dict[str, Any]:
    environment = runtime_environment()
    production = is_production()
    findings: list[ConfigurationFinding] = []
    clients = configured_api_clients()
    legacy_key = os.getenv("BIOINTEL_API_KEY", "").strip()

    if production and not clients and not legacy_key:
        findings.append(
            ConfigurationFinding(
                "authentication_required",
                "critical",
                "Production mode has no configured API identity.",
                "Set BIOINTEL_API_CLIENTS_JSON with at least one high-entropy operator/admin key.",
            )
        )

    weak_clients = [
        str(item.get("client_id") or item.get("name") or "unnamed")
        for item in clients
        if not _secret_strength(str(item.get("key") or ""))
    ]
    if weak_clients:
        findings.append(
            ConfigurationFinding(
                "weak_api_keys",
                "critical" if production else "warning",
                "Weak or short API keys: " + ", ".join(weak_clients),
                "Use unique random keys of at least 24 characters with mixed character classes.",
            )
        )
    if legacy_key and not _secret_strength(legacy_key):
        findings.append(
            ConfigurationFinding(
                "weak_legacy_key",
                "critical" if production else "warning",
                "BIOINTEL_API_KEY does not meet the production entropy policy.",
                "Rotate it to a random high-entropy key or use BIOINTEL_API_CLIENTS_JSON.",
            )
        )

    trusted_hosts = [
        value.strip()
        for value in os.getenv(
            "BIOINTEL_TRUSTED_HOSTS", "127.0.0.1,localhost,testserver"
        ).split(",")
        if value.strip()
    ]
    if production and ("*" in trusted_hosts or not trusted_hosts):
        findings.append(
            ConfigurationFinding(
                "trusted_hosts",
                "critical",
                "Production trusted-host policy is empty or contains a wildcard.",
                "Set BIOINTEL_TRUSTED_HOSTS to explicit service and public hostnames.",
            )
        )

    required_service_variables = {
        "database": "BIOINTEL_DATABASE_URL",
        "redis": "BIOINTEL_REDIS_URL",
        "object_storage": "BIOINTEL_OBJECT_STORAGE_ENDPOINT",
    }
    for service, variable in required_service_variables.items():
        if production and not os.getenv(variable, "").strip():
            findings.append(
                ConfigurationFinding(
                    f"missing_{service}",
                    "critical",
                    f"{variable} is not configured in production mode.",
                    f"Configure {variable} and validate connectivity before serving traffic.",
                )
            )

    if production and os.getenv("BIOINTEL_OFFICIAL_HOSTS_ONLY", "1").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        findings.append(
            ConfigurationFinding(
                "internet_allowlist",
                "warning",
                "Production outbound downloads are not restricted to official hosts.",
                "Set BIOINTEL_OFFICIAL_HOSTS_ONLY=1 and maintain an explicit provider allowlist.",
            )
        )

    critical = sum(item.severity == "critical" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    return {
        "environment": environment,
        "production": production,
        "valid": critical == 0,
        "critical_count": critical,
        "warning_count": warnings,
        "configured_clients": len(clients) + int(bool(legacy_key)),
        "findings": [asdict(item) for item in findings],
    }


def enforce_runtime_configuration() -> None:
    report = validate_runtime_configuration()
    if report["production"] and not report["valid"]:
        messages = "; ".join(
            item["message"] for item in report["findings"] if item["severity"] == "critical"
        )
        raise RuntimeError("Invalid BioIntel production configuration: " + messages)
