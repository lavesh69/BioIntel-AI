from __future__ import annotations

import importlib.util
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from biointel.production.config import is_production, validate_runtime_configuration


@dataclass(frozen=True)
class ProductionCheck:
    key: str
    label: str
    status: str
    required: bool
    message: str


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _tcp_reachable(url: str, *, default_port: int, timeout: float = 0.35) -> bool:
    if not url:
        return False
    parsed = urlparse(url if "://" in url else f"tcp://{url}")
    host = parsed.hostname
    port = parsed.port or default_port
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def production_readiness() -> dict[str, object]:
    production = is_production()
    project_root = Path(__file__).resolve().parents[3]
    database_url = os.getenv("BIOINTEL_DATABASE_URL", "")
    redis_url = os.getenv("BIOINTEL_REDIS_URL", "")
    object_url = os.getenv("BIOINTEL_OBJECT_STORAGE_ENDPOINT", "")
    oidc_issuer = os.getenv("BIOINTEL_OIDC_ISSUER", "")
    persistence_backend = os.getenv("BIOINTEL_PERSISTENCE_BACKEND", "sqlite").strip().lower()
    queue_backend = os.getenv("BIOINTEL_QUEUE_BACKEND", "local").strip().lower()
    artifact_backend = os.getenv("BIOINTEL_ARTIFACT_BACKEND", "local").strip().lower()
    config = validate_runtime_configuration()

    checks = [
        ProductionCheck(
            "runtime_config",
            "Production configuration policy",
            "ready" if config["valid"] else "blocked",
            production,
            "Secrets, hosts, authentication and required service variables must pass policy.",
        ),
        ProductionCheck(
            "postgres_driver",
            "PostgreSQL driver",
            "ready" if _module_available("psycopg") else "missing",
            production,
            "Install requirements-production.txt to enable PostgreSQL.",
        ),
        ProductionCheck(
            "postgres_service",
            "PostgreSQL service",
            "ready" if _tcp_reachable(database_url, default_port=5432) else "not_reachable",
            production,
            "Set BIOINTEL_DATABASE_URL and verify service reachability.",
        ),
        ProductionCheck(
            "persistence_integration",
            "Application persistence backend",
            "integrated" if persistence_backend == "postgres" else "local_only",
            production,
            "Core registries still use SQLite unless a PostgreSQL repository backend is explicitly implemented and selected.",
        ),
        ProductionCheck(
            "redis_driver",
            "Redis driver",
            "ready" if _module_available("redis") else "missing",
            production,
            "Redis enables shared rate limits, queues and distributed caches.",
        ),
        ProductionCheck(
            "redis_service",
            "Redis service",
            "ready" if _tcp_reachable(redis_url, default_port=6379) else "not_reachable",
            production,
            "Set BIOINTEL_REDIS_URL and verify service reachability.",
        ),
        ProductionCheck(
            "queue_integration",
            "Distributed queue backend",
            "integrated" if queue_backend in {"redis", "celery"} else "local_only",
            production,
            "The bundled worker remains a local SQLite queue unless Redis/Celery execution is implemented and selected.",
        ),
        ProductionCheck(
            "object_storage_service",
            "S3/MinIO object storage",
            "ready"
            if (_module_available("boto3") and _tcp_reachable(object_url, default_port=9000))
            else "not_reachable",
            production,
            "Set object-storage endpoint and credentials for managed artifacts.",
        ),
        ProductionCheck(
            "artifact_integration",
            "Artifact storage backend",
            "integrated" if artifact_backend in {"s3", "minio"} else "local_only",
            production,
            "Reports, models and documents remain filesystem-backed unless an object-store repository is selected.",
        ),
        ProductionCheck(
            "oidc",
            "OIDC identity verification",
            "configured" if oidc_issuer else "not_configured",
            False,
            "Issuer configuration alone is not authentication; token verification and claims mapping are required.",
        ),
        ProductionCheck(
            "telemetry",
            "Prometheus/OpenTelemetry dependencies",
            "ready"
            if _module_available("prometheus_client") and _module_available("opentelemetry")
            else "optional_missing",
            False,
            "The built-in metrics endpoint works without these packages; install them for external export and traces.",
        ),
        ProductionCheck(
            "multi_tenant_architecture",
            "Tenant isolation architecture",
            "ready" if (project_root / "src/biointel/multitenancy/middleware.py").is_file()
            and (project_root / "src/biointel/multitenancy/store.py").is_file() else "missing",
            production,
            "Tenant context, memberships and tenant-filtered resource repositories are required.",
        ),
        ProductionCheck(
            "kubernetes_chart",
            "Kubernetes Helm deployment",
            "ready" if (project_root / "deploy/helm/biointel/Chart.yaml").is_file()
            and (project_root / "deploy/helm/biointel/templates/hpa.yaml").is_file()
            and (project_root / "deploy/helm/biointel/templates/networkpolicy.yaml").is_file() else "missing",
            production,
            "A versioned Helm chart with probes, autoscaling, disruption budgets and network policy is required.",
        ),
        ProductionCheck(
            "visual_regression",
            "Visual regression CI",
            "ready" if len(list((project_root / "visual/baselines").glob("*.png"))) >= 4
            and (project_root / ".github/workflows/visual-regression.yml").is_file() else "missing",
            False,
            "Reviewed desktop/mobile baselines and a browser CI gate protect the primary interface.",
        ),
    ]
    ready_statuses = {"ready", "configured", "integrated"}
    ready = sum(item.status in ready_statuses for item in checks)
    required_checks = [item for item in checks if item.required]
    required_ready = sum(item.status in ready_statuses for item in required_checks)
    blockers = [asdict(item) for item in required_checks if item.status not in ready_statuses]
    if production and not blockers:
        mode = "production_ready"
    elif production:
        mode = "production_blocked"
    else:
        mode = "local_professional"
    return {
        "mode": mode,
        "ready_checks": ready,
        "total_checks": len(checks),
        "required_ready_checks": required_ready,
        "required_check_count": len(required_checks),
        "checks": [asdict(item) for item in checks],
        "blockers": blockers,
        "local_sqlite_supported": True,
        "production_services_optional": not production,
        "runtime_configuration": config,
    }
