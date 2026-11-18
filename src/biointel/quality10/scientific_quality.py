from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class QualityDimension:
    key: str
    label: str
    score: float
    weight: float
    evidence: str
    blocker: bool = False


@dataclass(slots=True)
class QualityAssessment:
    implementation_readiness: float
    scientific_evidence_score: float
    release_eligible: bool
    dimensions: list[dict[str, Any]]
    blockers: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bounded(value: float) -> float:
    return max(0.0, min(10.0, float(value)))


def assess_quality(
    *,
    input_integrity: float = 10,
    reproducibility: float = 10,
    execution_completion: float = 10,
    error_handling: float = 10,
    test_coverage: float = 10,
    provenance: float = 10,
    external_validation: float = 0,
    prospective_validation: float = 0,
    peer_review: float = 0,
    clinical_or_regulatory: float = 0,
    source_kind: str = "user_supplied",
    synthetic: bool = False,
) -> QualityAssessment:
    implementation = [
        QualityDimension("input_integrity", "Input integrity", _bounded(input_integrity), 0.18, "Checksums, schema and parse validation"),
        QualityDimension("reproducibility", "Reproducibility", _bounded(reproducibility), 0.19, "Versioned workflow and environment manifest"),
        QualityDimension("execution_completion", "Execution completion", _bounded(execution_completion), 0.20, "Dependency-aware step completion"),
        QualityDimension("error_handling", "Error handling", _bounded(error_handling), 0.15, "Retries, timeout, logs and recovery"),
        QualityDimension("test_coverage", "Automated verification", _bounded(test_coverage), 0.13, "Unit, integration and package verification"),
        QualityDimension("provenance", "Provenance", _bounded(provenance), 0.15, "Input/output hashes and immutable audit records"),
    ]
    evidence = [
        QualityDimension("external_validation", "Independent external validation", _bounded(external_validation), 0.35, "Independent dataset/laboratory result", external_validation < 7),
        QualityDimension("prospective_validation", "Prospective validation", _bounded(prospective_validation), 0.30, "Pre-registered blinded or prospective outcome", prospective_validation < 7),
        QualityDimension("peer_review", "Peer-reviewed evidence", _bounded(peer_review), 0.20, "External scientific review", peer_review < 5),
        QualityDimension("clinical_or_regulatory", "Clinical/regulatory evidence", _bounded(clinical_or_regulatory), 0.15, "Authority, accredited laboratory or clinical operating evidence", clinical_or_regulatory < 5),
    ]
    implementation_score = sum(item.score * item.weight for item in implementation)
    evidence_score = sum(item.score * item.weight for item in evidence)
    blockers: list[str] = []
    warnings: list[str] = []
    if synthetic:
        blockers.append("Synthetic or demonstration data cannot support scientific release.")
    if source_kind in {"demo", "demo_reference", "synthetic"}:
        blockers.append("Demonstration/reference input is not release evidence.")
    for item in evidence:
        if item.blocker:
            blockers.append(f"{item.label} is below the release threshold.")
    if implementation_score < 9:
        warnings.append("Implementation readiness is below the internal excellence target.")
    release_eligible = implementation_score >= 9 and evidence_score >= 7.5 and not blockers
    return QualityAssessment(
        implementation_readiness=round(implementation_score, 2),
        scientific_evidence_score=round(evidence_score, 2),
        release_eligible=release_eligible,
        dimensions=[asdict(item) for item in implementation + evidence],
        blockers=blockers,
        warnings=warnings,
    )


def summarize_quality_dimensions(dimensions: Iterable[dict[str, Any]]) -> dict[str, float]:
    return {str(item["key"]): float(item["score"]) for item in dimensions}
