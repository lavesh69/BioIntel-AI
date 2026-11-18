from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Iterable

import numpy as np
import pandas as pd

from biointel.discovery.workflow import TARGET_WEIGHT_TEMPLATES, score_target_priority

DIMENSIONS = tuple(TARGET_WEIGHT_TEMPLATES["balanced"])
SOURCE_QUALITY_DEFAULTS = {
    "human_genetics": 1.00,
    "clinical": 0.95,
    "primary_experiment": 0.90,
    "curated_database": 0.85,
    "peer_reviewed_literature": 0.80,
    "preprint": 0.60,
    "computational_prediction": 0.45,
    "expert_opinion": 0.40,
    "demo_reference": 0.20,
}


@dataclass(frozen=True)
class TargetEvidenceProfile:
    target_id: str
    indication: str
    template: str
    dimension_scores: dict[str, float]
    dimension_confidence: dict[str, float]
    total_score: float
    confidence_adjusted_score: float
    evidence_confidence: float
    priority_tier: str
    evidence_count: int
    source_count: int
    conflicts: list[str]
    gaps: list[str]
    gate_failures: list[str]
    evidence_register: list[dict[str, object]]
    methodology: dict[str, object]


def _parse_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _recency_weight(value: object, half_life_years: float) -> float:
    date = _parse_date(value)
    if date is None:
        return 0.85
    age_years = max(0.0, (datetime.now(UTC) - date).days / 365.25)
    return float(0.5 ** (age_years / max(half_life_years, 0.5)))


def build_target_evidence_profile(
    target_id: str,
    evidence_rows: Iterable[dict[str, object]] | pd.DataFrame,
    *,
    indication: str = "",
    template: str = "balanced",
    custom_weights: dict[str, float] | None = None,
    hard_gates: dict[str, float] | None = None,
    recency_half_life_years: float = 8.0,
) -> TargetEvidenceProfile:
    records = (
        evidence_rows.to_dict("records")
        if isinstance(evidence_rows, pd.DataFrame)
        else list(evidence_rows)
    )
    cleaned: list[dict[str, object]] = []
    for index, row in enumerate(records):
        dimension = str(row.get("dimension", "")).strip().lower().replace(" ", "_")
        if dimension not in DIMENSIONS:
            raise ValueError(
                f"Evidence row {index + 1} has unsupported dimension: {dimension or '<blank>'}"
            )
        score = float(row.get("score", row.get("strength", 0)))
        if not 0 <= score <= 100:
            raise ValueError(f"Evidence row {index + 1} score must be 0–100")
        confidence = float(row.get("confidence", 0.7))
        if confidence > 1:
            confidence /= 100
        if not 0 <= confidence <= 1:
            raise ValueError(f"Evidence row {index + 1} confidence must be 0–1 or 0–100")
        source_type = str(row.get("source_type", "expert_opinion")).strip().lower()
        source_quality = float(
            row.get("source_quality", SOURCE_QUALITY_DEFAULTS.get(source_type, 0.5))
        )
        if source_quality > 1:
            source_quality /= 100
        source_quality = min(max(source_quality, 0.0), 1.0)
        recency = _recency_weight(row.get("evidence_date"), recency_half_life_years)
        effective_weight = confidence * source_quality * recency
        cleaned.append(
            {
                **row,
                "dimension": dimension,
                "score": score,
                "confidence": confidence,
                "source_type": source_type,
                "source_quality": source_quality,
                "recency_weight": round(recency, 6),
                "effective_weight": round(effective_weight, 6),
            }
        )

    dimension_scores: dict[str, float] = {}
    dimension_confidence: dict[str, float] = {}
    conflicts: list[str] = []
    gaps: list[str] = []
    for dimension in DIMENSIONS:
        rows = [row for row in cleaned if row["dimension"] == dimension]
        if not rows:
            dimension_scores[dimension] = 0.0
            dimension_confidence[dimension] = 0.0
            gaps.append(dimension.replace("_", " ").title())
            continue
        values = np.array([float(row["score"]) for row in rows], dtype=float)
        weights = np.array([float(row["effective_weight"]) for row in rows], dtype=float)
        if weights.sum() <= 0:
            score = float(values.mean())
        else:
            score = float(np.average(values, weights=weights))
        dimension_scores[dimension] = round(score, 2)
        confidence = min(1.0, float(weights.sum()) / max(len(rows), 1))
        dimension_confidence[dimension] = round(confidence * 100, 2)
        if len(values) >= 2 and float(values.max() - values.min()) >= 40:
            conflicts.append(
                f"{dimension.replace('_', ' ').title()} evidence spans {values.min():.0f}–{values.max():.0f}."
            )

    evidence_confidence = round(
        float(np.mean(list(dimension_confidence.values()))) if dimension_confidence else 0.0,
        2,
    )
    scored = score_target_priority(
        target_id,
        **dimension_scores,
        template=template,
        weights=custom_weights,
        evidence_confidence=evidence_confidence,
        hard_gates=hard_gates,
    )
    sources = {
        (str(row.get("source", "")), str(row.get("source_id", "")))
        for row in cleaned
        if row.get("source") or row.get("source_id")
    }
    return TargetEvidenceProfile(
        target_id=scored.target_id,
        indication=indication.strip(),
        template=template if custom_weights is None else "custom",
        dimension_scores=dimension_scores,
        dimension_confidence=dimension_confidence,
        total_score=scored.total_score,
        confidence_adjusted_score=scored.confidence_adjusted_score,
        evidence_confidence=evidence_confidence,
        priority_tier=scored.priority_tier,
        evidence_count=len(cleaned),
        source_count=len(sources),
        conflicts=conflicts,
        gaps=gaps,
        gate_failures=scored.gate_failures,
        evidence_register=cleaned,
        methodology={
            **scored.methodology,
            "aggregation": "source-quality × confidence × recency weighted evidence",
            "recency_half_life_years": recency_half_life_years,
            "source_quality_defaults": SOURCE_QUALITY_DEFAULTS,
            "warning": "Imported evidence must be independently reviewed; this profile does not create biological truth.",
        },
    )



TARGET_EVIDENCE_PROVIDER_PLAN = (
    {"provider": "Open Targets", "dimensions": ["disease_relevance", "genetic_evidence"], "query": "target + disease associations", "required_fields": ["association score", "evidence type", "source release"]},
    {"provider": "GWAS Catalog / ClinVar", "dimensions": ["genetic_evidence"], "query": "gene/variant + phenotype", "required_fields": ["variant", "effect", "p-value or clinical significance", "study/release"]},
    {"provider": "GTEx / Human Protein Atlas", "dimensions": ["safety_window", "disease_relevance"], "query": "target tissue expression", "required_fields": ["tissue", "expression", "specificity", "release"]},
    {"provider": "ChEMBL / BindingDB", "dimensions": ["tractability", "experimental_validation"], "query": "target bioactivity and known ligands", "required_fields": ["assay", "activity", "units", "target confidence", "release"]},
    {"provider": "UniProt / InterPro / RCSB", "dimensions": ["tractability", "experimental_validation"], "query": "target sequence domains structures", "required_fields": ["accession", "review status", "domain/structure", "release"]},
    {"provider": "Reactome / STRING", "dimensions": ["pathway_evidence"], "query": "target pathways and network", "required_fields": ["pathway/network evidence", "organism", "release"]},
    {"provider": "ClinicalTrials.gov / drug labels", "dimensions": ["experimental_validation", "safety_window"], "query": "target-modulating interventions", "required_fields": ["intervention", "phase", "status", "safety context", "retrieval date"]},
)


def target_evidence_query_plan(target_id: str, indication: str = "") -> list[dict[str, object]]:
    target = target_id.strip()
    if not target:
        raise ValueError("Target identifier is required.")
    disease = indication.strip() or "<indication required>"
    return [
        {
            **row,
            "target_id": target,
            "indication": disease,
            "query_text": f"{target} {disease} {row['query']}",
            "status": "planned / not retrieved",
            "scientific_boundary": "Provider evidence must be retrieved, checksum-bound and reviewed before scoring.",
        }
        for row in TARGET_EVIDENCE_PROVIDER_PLAN
    ]

def profile_dict(result: TargetEvidenceProfile) -> dict[str, object]:
    return asdict(result)
