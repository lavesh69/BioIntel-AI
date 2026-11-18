from __future__ import annotations

from typing import Sequence

from biointel.shiro.exceptions import CitationValidationError
from biointel.shiro.models import Citation, RetrievalResult


def validate_citations(project_id: str, citations: Sequence[Citation], context: Sequence[RetrievalResult]) -> None:
    allowed = {(item.source.source_id, item.chunk.chunk_id) for item in context}
    seen: set[str] = set()
    for citation in citations:
        if citation.citation_id in seen:
            raise CitationValidationError(f"Duplicate citation ID: {citation.citation_id}")
        seen.add(citation.citation_id)
        if citation.project_id != project_id:
            raise CitationValidationError("A citation crossed the active project boundary.")
        if (citation.source_id, citation.chunk_id) not in allowed:
            raise CitationValidationError("A citation was not present in the retrieved model context.")
        if citation.internal == citation.external:
            raise CitationValidationError("A citation must be classified as internal or external, not both/neither.")
