from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import asdict
from pathlib import Path
from typing import Any

from biointel.scientific.validation_depth import (
    CAPABILITY_DEFINITIONS,
    ValidationCapability,
    ValidationEvidenceRegistry,
)


def build_validation_readiness(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    registry = ValidationEvidenceRegistry(runtime_database_path(project_root, "validation_evidence.sqlite3"))
    summary = registry.summary()
    analytical_external = min(summary["completed_external_dti"] / 2.0, 1.0)
    prospective = min(summary["completed_blinded_prospective"] / 2.0, 1.0)
    provider = min(summary["verified_provider_releases"] / 5.0, 1.0)
    wetlab = min(summary["completed_wetlab"] / 2.0, 1.0)
    independent_wetlab = min(summary["completed_independent_wetlab"] / 2.0, 1.0)
    multisite = min(summary["completed_multisite"] / 1.0, 1.0)
    actual_scores = {
        "prospective_validation": round(3 + 7 * prospective, 1),
        "external_dti_validation": round(3.5 + 6.5 * analytical_external, 1),
        "independent_dti_benchmarking": round(4 + 6 * analytical_external, 1),
        "ml_model_quality": round(4.5 + 5.5 * analytical_external, 1),
        "dti_prediction_capability": round(4.5 + 5.5 * analytical_external, 1),
        "model_generalization": round(4 + 6 * analytical_external, 1),
        "cold_drug_validation": round(5 + 5 * analytical_external, 1),
        "cold_target_validation": round(4.5 + 5.5 * analytical_external, 1),
        "cold_both_validation": round(4 + 6 * analytical_external, 1),
        "scaffold_generalization": round(4.5 + 5.5 * analytical_external, 1),
        "temporal_generalization": round(4 + 6 * analytical_external, 1),
        "independent_calibration": round(4 + 6 * analytical_external, 1),
        "independent_uncertainty": round(4 + 6 * analytical_external, 1),
        "database_depth": round(6 + 4 * provider, 1),
        "evidence_registry": round(6.5 + 3.5 * provider, 1),
        "provider_integration": round(6.5 + 3.5 * provider, 1),
        "provider_release_coverage": round(5.5 + 4.5 * provider, 1),
        "wet_lab_evidence": round(2.5 + 7.5 * wetlab, 1),
        "prospective_wetlab_reproducibility": round(2.5 + 7.5 * independent_wetlab, 1),
        "independent_lab_replication": round(2 + 8 * independent_wetlab, 1),
        "multi_site_validation": round(2 + 8 * multisite, 1),
    }
    credibility_inputs = [
        actual_scores["prospective_validation"],
        actual_scores["external_dti_validation"],
        actual_scores["ml_model_quality"],
        actual_scores["dti_prediction_capability"],
        actual_scores["wet_lab_evidence"],
        actual_scores["independent_lab_replication"],
        actual_scores["multi_site_validation"],
    ]
    actual_scores["scientific_credibility"] = round(
        sum(credibility_inputs) / len(credibility_inputs), 1
    )

    capabilities: list[ValidationCapability] = []
    for definition in CAPABILITY_DEFINITIONS:
        controls = tuple(path for path in definition["paths"] if (project_root / path).exists())
        missing = tuple(path for path in definition["paths"] if not (project_root / path).exists())
        implementation_score = round(10 * len(controls) / len(definition["paths"]), 1)
        evidence_score = actual_scores[definition["key"]]
        capabilities.append(
            ValidationCapability(
                key=definition["key"],
                label=definition["label"],
                implementation_score=implementation_score,
                evidence_score=evidence_score,
                status=(
                    "evidence-qualified"
                    if evidence_score == 10
                    else "framework-ready/evidence-pending"
                    if implementation_score == 10
                    else "implementation-incomplete"
                ),
                controls=controls,
                blockers=missing,
                boundary=(
                    "10/10 implementation means enforceable schemas, hashes, chronology, split policies, calibration, review and release gates exist. "
                    "Actual evidence reaches 10/10 only after qualifying independent datasets or genuine laboratory/site results are imported."
                ),
            )
        )
    return {
        "implementation_average": round(
            sum(row.implementation_score for row in capabilities) / len(capabilities), 1
        ),
        "evidence_average": round(
            sum(row.evidence_score for row in capabilities) / len(capabilities), 1
        ),
        "capability_count": len(capabilities),
        "summary": summary,
        "integrity": registry.verify_integrity(),
        "capabilities": [asdict(row) for row in capabilities],
        "boundary": "The repository cannot manufacture wet-lab, independent laboratory or multi-site evidence. Those scores are evidence-gated by design.",
    }
