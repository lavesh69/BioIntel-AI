from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ScalingProfile:
    stateless_api: bool = True
    external_database: bool = True
    external_cache: bool = True
    external_object_storage: bool = True
    idempotent_jobs: bool = True
    tenant_partition_key: str = "tenant_id"
    api_min_replicas: int = 2
    api_max_replicas: int = 20
    worker_min_replicas: int = 2
    worker_max_replicas: int = 50


def validate_horizontal_scaling(profile: ScalingProfile | None = None) -> dict[str, Any]:
    selected = profile or ScalingProfile()
    checks = {
        "stateless_api": selected.stateless_api,
        "external_database": selected.external_database,
        "external_cache": selected.external_cache,
        "external_object_storage": selected.external_object_storage,
        "idempotent_jobs": selected.idempotent_jobs,
        "tenant_partition_key": bool(selected.tenant_partition_key),
        "api_replica_range": selected.api_min_replicas >= 2 and selected.api_max_replicas >= selected.api_min_replicas,
        "worker_replica_range": selected.worker_min_replicas >= 2 and selected.worker_max_replicas >= selected.worker_min_replicas,
    }
    return {"ready": all(checks.values()), "checks": checks, "profile": asdict(selected)}
