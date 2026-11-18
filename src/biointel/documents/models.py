from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractedTable:
    name: str
    source: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.columns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "row_count": self.row_count,
            "column_count": self.column_count,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExtractedTable":
        return cls(
            name=str(payload.get("name", "Table")),
            source=str(payload.get("source", "document")),
            columns=tuple(map(str, payload.get("columns", []))),
            rows=tuple(tuple(row) for row in payload.get("rows", [])),
            confidence=(
                float(payload["confidence"])
                if payload.get("confidence") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ExtractedSection:
    name: str
    text: str
    source: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExtractedSection":
        return cls(
            name=str(payload.get("name", "Section")),
            text=str(payload.get("text", "")),
            source=str(payload.get("source", "document")),
            confidence=(
                float(payload["confidence"])
                if payload.get("confidence") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ExtractedRegion:
    region_id: str
    source: str
    kind: str
    text: str
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = list(self.bbox) if self.bbox is not None else None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExtractedRegion":
        bbox = payload.get("bbox")
        return cls(
            region_id=str(payload.get("region_id", "")),
            source=str(payload.get("source", "document")),
            kind=str(payload.get("kind", "text")),
            text=str(payload.get("text", "")),
            page_number=(
                int(payload["page_number"])
                if payload.get("page_number") is not None
                else None
            ),
            bbox=tuple(map(float, bbox)) if bbox else None,
            confidence=(
                float(payload["confidence"])
                if payload.get("confidence") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ScientificEntity:
    text: str
    entity_type: str
    normalized: str
    source: str
    start: int | None = None
    end: int | None = None
    confidence: float = 0.7
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScientificEntity":
        return cls(
            text=str(payload.get("text", "")),
            entity_type=str(payload.get("entity_type", "other")),
            normalized=str(payload.get("normalized", payload.get("text", ""))),
            source=str(payload.get("source", "document")),
            start=int(payload["start"]) if payload.get("start") is not None else None,
            end=int(payload["end"]) if payload.get("end") is not None else None,
            confidence=float(payload.get("confidence", 0.7)),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class DocumentExtraction:
    source_name: str
    file_type: str
    mime_type: str
    source_sha256: str
    source_size_bytes: int
    text: str
    sections: tuple[ExtractedSection, ...] = field(default_factory=tuple)
    tables: tuple[ExtractedTable, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    regions: tuple[ExtractedRegion, ...] = field(default_factory=tuple)
    entities: tuple[ScientificEntity, ...] = field(default_factory=tuple)
    structured_fields: dict[str, Any] = field(default_factory=dict)
    page_count: int = 0
    sheet_count: int = 0
    paragraph_count: int = 0
    image_count: int = 0

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def row_count(self) -> int:
        return sum(table.row_count for table in self.tables)

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def region_count(self) -> int:
        return len(self.regions)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def summary(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "source_sha256": self.source_sha256,
            "source_size_bytes": self.source_size_bytes,
            "page_count": self.page_count,
            "sheet_count": self.sheet_count,
            "paragraph_count": self.paragraph_count,
            "image_count": self.image_count,
            "table_count": self.table_count,
            "row_count": self.row_count,
            "character_count": self.character_count,
            "region_count": self.region_count,
            "entity_count": self.entity_count,
            "warning_count": len(self.warnings),
        }

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self.summary(),
            "text": self.text,
            "sections": [section.to_dict() for section in self.sections],
            "metadata": self.metadata,
            "warnings": list(self.warnings),
            "regions": [region.to_dict() for region in self.regions],
            "entities": [entity.to_dict() for entity in self.entities],
            "structured_fields": self.structured_fields,
        }
        payload["tables"] = [
            table.to_dict()
            if include_rows
            else {
                "name": table.name,
                "source": table.source,
                "columns": list(table.columns),
                "row_count": table.row_count,
                "column_count": table.column_count,
                "confidence": table.confidence,
                "metadata": table.metadata,
            }
            for table in self.tables
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentExtraction":
        return cls(
            source_name=str(payload.get("source_name", "document")),
            file_type=str(payload.get("file_type", "unknown")),
            mime_type=str(payload.get("mime_type", "application/octet-stream")),
            source_sha256=str(payload.get("source_sha256", "")),
            source_size_bytes=int(payload.get("source_size_bytes", 0)),
            text=str(payload.get("text", "")),
            sections=tuple(
                ExtractedSection.from_dict(item) for item in payload.get("sections", [])
            ),
            tables=tuple(ExtractedTable.from_dict(item) for item in payload.get("tables", [])),
            metadata=dict(payload.get("metadata") or {}),
            warnings=tuple(map(str, payload.get("warnings", []))),
            regions=tuple(
                ExtractedRegion.from_dict(item) for item in payload.get("regions", [])
            ),
            entities=tuple(
                ScientificEntity.from_dict(item) for item in payload.get("entities", [])
            ),
            structured_fields=dict(payload.get("structured_fields") or {}),
            page_count=int(payload.get("page_count", 0)),
            sheet_count=int(payload.get("sheet_count", 0)),
            paragraph_count=int(payload.get("paragraph_count", 0)),
            image_count=int(payload.get("image_count", 0)),
        )
