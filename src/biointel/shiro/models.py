from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LanguageInfo:
    code: str
    label: str
    script: str
    confidence: float
    normalized_query: str
    preserved_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    retrieval_required: bool
    citations_required: bool
    allowed_sources: tuple[str, ...]
    external_requested: bool = False
    external_allowed: bool = False
    clinical_safety: bool = False


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    project_id: str
    filename: str
    source_type: str
    mime_type: str
    byte_size: int
    sha256: str
    uploaded_at: str
    author: str = ""
    internal: bool = True
    external: bool = False
    synthetic: bool = False
    confidential: bool = True
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    source_id: str
    project_id: str
    ordinal: int
    text: str
    location: str
    section: str
    embedding: tuple[float, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: ChunkRecord
    source: SourceRecord
    score: float
    semantic_score: float
    keyword_score: float
    matched_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "source_id": self.source.source_id,
            "project_id": self.source.project_id,
            "text": self.chunk.text,
            "location": self.chunk.location,
            "section": self.chunk.section,
            "source_title": self.source.filename,
            "source_type": self.source.source_type,
            "score": self.score,
            "semantic_score": self.semantic_score,
            "keyword_score": self.keyword_score,
            "matched_terms": list(self.matched_terms),
            "internal": self.source.internal,
            "external": self.source.external,
            "synthetic": self.source.synthetic,
        }


@dataclass(frozen=True)
class Citation:
    citation_id: str
    chunk_id: str
    source_id: str
    source_title: str
    filename: str
    location: str
    section: str
    project_id: str
    project_name: str
    source_type: str
    internal: bool
    external: bool
    synthetic: bool
    source_sha256: str
    relevance_score: float
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IngestionResult:
    job_id: str
    source: SourceRecord
    chunks_indexed: int
    state: str
    duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source": self.source.to_dict(),
            "chunks_indexed": self.chunks_indexed,
            "state": self.state,
            "duplicate": self.duplicate,
        }


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    project_id: str
    conversation_id: str
    citations: tuple[Citation, ...]
    language: LanguageInfo
    plan: QueryPlan
    provider: str
    model: str
    evidence_status: str
    request_id: str
    actions: tuple[dict[str, Any], ...] = ()
    provider_route: tuple[str, ...] = ()
    general_knowledge: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "citations": [item.to_dict() for item in self.citations],
            "language": asdict(self.language),
            "plan": asdict(self.plan),
            "provider": self.provider,
            "model": self.model,
            "evidence_status": self.evidence_status,
            "request_id": self.request_id,
            "actions": list(self.actions),
            "provider_route": list(self.provider_route),
            "general_knowledge": self.general_knowledge,
        }
