"""
Shiro AI — Scientific Reciprocal Rank Fusion Reranker
Reranks hybrid semantic and keyword search results for precision scientific retrieval.
"""
from __future__ import annotations

import re
from typing import Sequence


class ScientificReranker:
    """Reciprocal Rank Fusion (RRF) reranker with scientific entity boosting."""

    @staticmethod
    def _contains_exact_identifier(text: str, query: str) -> bool:
        query_identifiers = re.findall(r"[A-Za-z0-9_-]+", query)
        text_fold = text.casefold()
        exact_matches = sum(1 for ident in query_identifiers if len(ident) >= 3 and ident.casefold() in text_fold)
        return exact_matches >= 1

    def rerank(self, query: str, results: Sequence[object], top_k: int | None = None) -> list[object]:
        """Reranks retrieval results combining original score with exact scientific identifier boosting."""
        if not results:
            return []

        scored_items = []
        for rank, item in enumerate(results):
            chunk_text = getattr(getattr(item, "chunk", None), "text", "")
            base_score = float(getattr(item, "score", 0.5))
            
            # Reciprocal Rank Score
            rrf_score = 1.0 / (60 + rank + 1)
            
            # Exact Scientific Match Boost
            has_identifier = self._contains_exact_identifier(chunk_text, query)
            boost = 0.25 if has_identifier else 0.0

            final_rank_score = base_score + (rrf_score * 10) + boost
            scored_items.append((final_rank_score, item))

        scored_items.sort(key=lambda x: x[0], reverse=True)
        reranked = [item for _, item in scored_items]
        return reranked[:top_k] if top_k is not None else reranked


class ConservativeLocalReranker(ScientificReranker):
    """Backward compatible alias for ConservativeLocalReranker."""
    pass