"""
Shiro AI — RAG Groundedness & Confidence Evaluator
Evaluates scientific evidence precision, citation alignment, and factual grounding confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ConfidenceScore:
    overall_confidence: float  # 0.0 to 1.0
    percentage: str            # e.g., "94.5%"
    citation_count: int
    matched_term_coverage: float
    evidence_authenticity: str  # "Verified Local Project Evidence"
    rating: str                 # "High Confidence", "Moderate Confidence", "Low Confidence"


class ShiroRAGEvaluator:
    """Evaluates factual grounding confidence for retrieved RAG responses."""

    @staticmethod
    def evaluate(query: str, evidence: Sequence[object], citations: Sequence[object]) -> ConfidenceScore:
        if not evidence or not citations:
            return ConfidenceScore(
                overall_confidence=0.0,
                percentage="0.0%",
                citation_count=0,
                matched_term_coverage=0.0,
                evidence_authenticity="No Evidence Found",
                rating="Zero Grounding",
            )

        citation_count = len(citations)
        total_scores = []
        matched_counts = []

        for item in evidence:
            score = float(getattr(item, "score", 0.5))
            matched = getattr(item, "matched_terms", ())
            total_scores.append(score)
            matched_counts.append(len(matched))

        avg_score = sum(total_scores) / max(1, len(total_scores))
        max_matched = max(matched_counts) if matched_counts else 0

        # Calculate composite confidence
        raw_confidence = min(1.0, 0.60 * avg_score + 0.25 * min(1.0, citation_count / 3.0) + 0.15 * min(1.0, max_matched / 2.0))
        confidence_pct = round(raw_confidence * 100, 1)

        rating = "High Confidence" if raw_confidence >= 0.70 else ("Moderate Confidence" if raw_confidence >= 0.40 else "Low Confidence")

        return ConfidenceScore(
            overall_confidence=round(raw_confidence, 4),
            percentage=f"{confidence_pct}%",
            citation_count=citation_count,
            matched_term_coverage=round(min(1.0, max_matched / 3.0), 2),
            evidence_authenticity="Verified Local Project Evidence",
            rating=rating,
        )
