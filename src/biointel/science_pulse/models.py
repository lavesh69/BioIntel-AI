from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


MIGRATION_VERSION = "science_pulse_news_first_v2"
DEFAULT_TENANT = "local"


class ContentType(StrEnum):
    PUBLICATION = "publication"
    PREPRINT = "preprint"
    CLINICAL_TRIAL = "clinical_trial"
    DATASET = "dataset"
    NEWS = "news"
    RETRACTION = "retraction"
    CORRECTION = "correction"
    EVENT = "event"


class ProviderState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    EXTERNAL_VALIDATION_REQUIRED = "EXTERNAL_VALIDATION_REQUIRED"


class LiveState(StrEnum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    LOCAL = "LOCAL"
    DEMO = "DEMO"


class TrustState(StrEnum):
    NORMAL = "normal"
    CORRECTED = "corrected"
    RETRACTED = "retracted"
    EXPRESSION_OF_CONCERN = "expression_of_concern"
    UNVERIFIED = "unverified"


class DeliveryState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    CONFIGURATION_REQUIRED = "configuration_required"
    APPROVAL_REQUIRED = "approval_required"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *values: object) -> str:
    material = "\x1f".join(str(value or "").strip().lower() for value in values)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part for part in re.split(r"[,;|]", value) if part.strip()]
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        marker = text.casefold()
        if text and marker not in seen:
            result.append(text[:500])
            seen.add(marker)
    return result


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    key: str
    name: str
    kind: str
    base_url: str
    content_types: tuple[str, ...]
    schedule_seconds: int
    high_priority: bool = False
    approved: bool = True
    enabled: bool = True
    ownership: str = ""
    license_note: str = ""
    status: str = ProviderState.EXTERNAL_VALIDATION_REQUIRED


@dataclass(slots=True)
class PulseRecord:
    provider_key: str
    external_id: str
    title: str
    canonical_url: str
    content_type: str = ContentType.PUBLICATION
    source_name: str = ""
    original_source: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    publisher: str = ""
    published_at: str = ""
    updated_at: str = ""
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    organisms: list[str] = field(default_factory=list)
    genes: list[str] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    language: str = "en"
    license_note: str = ""
    trust_state: str = TrustState.NORMAL
    provenance: dict[str, Any] = field(default_factory=dict)
    live_state: str = LiveState.LIVE
    relevance: float = 0.5
    confidence: float = 0.5
    quality: float = 0.5

    def normalized(self) -> "PulseRecord":
        self.provider_key = self.provider_key.strip().lower().replace(" ", "_")[:80]
        self.external_id = re.sub(r"\s+", " ", self.external_id).strip()[:500]
        self.title = re.sub(r"\s+", " ", self.title).strip()[:2000]
        self.canonical_url = self.canonical_url.strip()[:4000]
        self.doi = self.doi.strip().lower().removeprefix("https://doi.org/")[:300]
        self.pmid = self.pmid.strip()[:100]
        self.pmcid = self.pmcid.strip()[:100]
        self.abstract = re.sub(r"\s+", " ", self.abstract).strip()[:20000]
        self.authors = list_value(self.authors)
        self.categories = list_value(self.categories)
        self.keywords = list_value(self.keywords)
        self.entities = list_value(self.entities)
        self.organisms = list_value(self.organisms)
        self.genes = list_value(self.genes)
        self.diseases = list_value(self.diseases)
        self.technologies = list_value(self.technologies)
        self.relevance = max(0.0, min(1.0, float(self.relevance)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.quality = max(0.0, min(1.0, float(self.quality)))
        return self

    @property
    def item_id(self) -> str:
        durable = self.doi or self.pmid or self.external_id or self.canonical_url or self.title
        return stable_id("spi", self.provider_key, durable)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
