from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Sequence

from biointel.shiro.core.language import detect_language, meaningful_terms
from biointel.shiro.models import RetrievalResult
from biointel.shiro.retrieval.reranker import ConservativeLocalReranker
from biointel.shiro.retrieval.vector_store import EmbeddingProvider, cosine
from biointel.shiro.storage.repositories import ShiroRepository


class RetrievalService:
    def __init__(
        self,
        repository: ShiroRepository,
        embeddings: EmbeddingProvider,
        reranker: ConservativeLocalReranker | None = None,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.reranker = reranker

    @staticmethod
    def _document_terms(text: str) -> Counter[str]:
        return Counter(meaningful_terms(text))

    @staticmethod
    def _metadata_match(
        source: object,
        *,
        module_id: str | None,
        report_id: str | None,
        internal_only: bool,
        external_only: bool,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        if internal_only and not source.internal:
            return False
        if external_only and not source.external:
            return False
        if module_id and str(source.metadata.get("module_id", "")) != module_id:
            return False
        if report_id and str(source.metadata.get("report_id", "")) != report_id:
            return False
        uploaded = str(source.uploaded_at)[:10]
        if date_from and uploaded < date_from:
            return False
        if date_to and uploaded > date_to:
            return False
        return True

    def search(
        self,
        project_id: str,
        query: str,
        *,
        top_k: int = 6,
        source_ids: Sequence[str] | None = None,
        source_types: Sequence[str] | None = None,
        module_id: str | None = None,
        report_id: str | None = None,
        internal_only: bool = False,
        external_only: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
        rerank: bool = False,
    ) -> tuple[RetrievalResult, ...]:
        clean = " ".join(query.strip().split())
        if not clean:
            return ()
        for value in (date_from, date_to):
            if value:
                datetime.strptime(value, "%Y-%m-%d")
        language = detect_language(clean)
        query_terms = meaningful_terms(language.normalized_query)
        if not query_terms:
            return ()
        pairs = [
            pair for pair in self.repository.list_chunks(project_id, source_ids=source_ids, source_types=source_types)
            if self._metadata_match(
                pair[1], module_id=module_id, report_id=report_id,
                internal_only=internal_only, external_only=external_only,
                date_from=date_from, date_to=date_to,
            )
        ]
        if not pairs:
            return ()
        document_counters = [self._document_terms(chunk.text) for chunk, _source in pairs]
        document_frequency = Counter()
        for counter in document_counters:
            document_frequency.update(counter.keys())
        count = len(pairs)
        average_length = sum(sum(counter.values()) for counter in document_counters) / max(1, count)
        query_vector = self.embeddings.embed([language.normalized_query])[0]
        scored: list[RetrievalResult] = []
        for (chunk, source), counter in zip(pairs, document_counters):
            matched = tuple(term for term in query_terms if counter.get(term, 0))
            semantic = max(0.0, cosine(query_vector, chunk.embedding))
            if not matched and semantic < 0.35:
                continue
            length = max(1, sum(counter.values()))
            bm25 = 0.0
            for term in matched:
                frequency = counter[term]
                inverse = math.log(1 + (count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                bm25 += inverse * (frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * length / max(1.0, average_length)))
            keyword = bm25 / (bm25 + 2.0) if bm25 > 0 else 0.0
            coverage = len(matched) / len(set(query_terms)) if query_terms else 0.0
            score = min(1.0, 0.48 * semantic + 0.37 * keyword + 0.15 * coverage)
            scored.append(RetrievalResult(chunk, source, round(score, 6), round(semantic, 6), round(keyword, 6), matched))
        scored.sort(key=lambda item: (item.score, len(item.matched_terms), item.source.uploaded_at), reverse=True)
        selected: list[RetrievalResult] = []
        seen: set[tuple[str, str]] = set()
        candidate_limit = min(50, max(top_k * 4, top_k)) if rerank and self.reranker else top_k
        for item in scored:
            key = (item.source.source_id, item.chunk.location)
            if key in seen or item.score < 0.08:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= max(1, min(int(candidate_limit), 50)):
                break
        if rerank and self.reranker:
            return self.reranker.rerank(language.normalized_query, selected, top_k)
        return tuple(selected[: max(1, min(int(top_k), 30))])