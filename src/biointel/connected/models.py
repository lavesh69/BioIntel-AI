from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    base_url: str
    host: str
    domains: tuple[str, ...]
    description: str
    requires_key: bool = False
    optional_key_env: str = ""
    documentation_url: str = ""
    requests_per_second: float = 3.0
    supports_free_text: bool = True
    version_note: str = "Live official API"


@dataclass(frozen=True)
class ConnectedRecord:
    provider: str
    record_id: str
    record_type: str
    title: str
    summary: str
    source_url: str
    payload: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryResult:
    provider: str
    query: str
    entity_type: str
    records: tuple[ConnectedRecord, ...]
    retrieved_at_utc: str
    source_url: str
    sha256: str
    cache_status: str
    warnings: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    request_id: str = ""
    provider_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "query": self.query,
            "entity_type": self.entity_type,
            "records": [record.to_dict() for record in self.records],
            "retrieved_at_utc": self.retrieved_at_utc,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "cache_status": self.cache_status,
            "warnings": list(self.warnings),
            "elapsed_ms": self.elapsed_ms,
            "request_id": self.request_id,
            "provider_version": self.provider_version,
        }


@dataclass(frozen=True)
class ConnectionDiagnostic:
    provider: str
    available: bool
    stage: str
    status: str
    latency_ms: float
    records: int = 0
    cache_status: str = "none"
    http_status: int | None = None
    request_id: str = ""
    error_type: str = ""
    error: str = ""
    checked_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
