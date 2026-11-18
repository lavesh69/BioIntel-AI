from __future__ import annotations

from typing import Sequence

from biointel.shiro.models import Citation, RetrievalResult


def build_citations(results: Sequence[RetrievalResult], project_name: str) -> tuple[Citation, ...]:
    citations: list[Citation] = []
    for index, result in enumerate(results, start=1):
        source = result.source
        citations.append(Citation(
            citation_id=f"CIT-{index:02d}", chunk_id=result.chunk.chunk_id,
            source_id=source.source_id, source_title=source.filename, filename=source.filename,
            location=result.chunk.location, section=result.chunk.section,
            project_id=source.project_id, project_name=project_name, source_type=source.source_type,
            internal=source.internal, external=source.external, synthetic=source.synthetic,
            source_sha256=source.sha256, relevance_score=result.score,
            excerpt=result.chunk.text[:500],
        ))
    return tuple(citations)
