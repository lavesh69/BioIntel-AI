from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .evidence_lake import ScientificEvidenceLake


@dataclass(frozen=True)
class ScientificCapability:
    key: str
    label: str
    implementation_score: float
    implementation_status: str
    evidence_score: float
    evidence_status: str
    controls: tuple[str, ...]
    missing: tuple[str, ...]
    certification_boundary: str


DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"key":"scientific_data_authenticity","label":"Scientific Data Authenticity","paths":["src/biointel/scientific/provider_hub.py","src/biointel/scientific/evidence_lake.py","config/scientific_provider_policy.yaml","scripts/sync_scientific_evidence.py","tests/scientific/test_step38_scientific_excellence.py"]},
    {"key":"dataset_diversity","label":"Dataset Diversity","paths":["config/scientific_coverage_targets.yaml","data/real_evidence/official_snapshots/provider_seed_catalog.json","src/biointel/scientific/excellence.py"]},
    {"key":"unique_dataset_quality","label":"Unique Dataset Quality","paths":["src/biointel/scientific/evidence_lake.py","config/scientific_release_policy.yaml","scripts/qualify_scientific_release.py"]},
    {"key":"assay_data_quality","label":"Assay Data Quality","paths":["src/biointel/scientific/assay_quality.py","config/assay_quality_policy.yaml","tests/scientific/test_step38_scientific_excellence.py"]},
    {"key":"biological_diversity","label":"Biological Diversity","paths":["config/scientific_coverage_targets.yaml","data/real_evidence/official_snapshots/organism_coverage_seed.csv"]},
    {"key":"multi_organism_coverage","label":"Multi-Organism Coverage","paths":["config/scientific_coverage_targets.yaml","data/real_evidence/official_snapshots/organism_coverage_seed.csv"]},
    {"key":"clinical_data_coverage","label":"Clinical Data Coverage","paths":["src/biointel/scientific/provider_hub.py","data/real_evidence/official_snapshots/clinicaltrials_verified_seed.json","config/clinical_evidence_policy.yaml"]},
    {"key":"real_scientific_validation","label":"Real Scientific Validation","paths":["src/biointel/scientific/benchmark.py","src/biointel/scientific/prospective.py","config/scientific_validation_policy.yaml"]},
    {"key":"prospective_validation","label":"Prospective Validation","paths":["src/biointel/scientific/prospective.py","scripts/register_prospective_study.py","config/prospective_validation_policy.yaml"]},
    {"key":"external_validation","label":"External Validation","paths":["src/biointel/scientific/benchmark.py","scripts/qualify_scientific_release.py","config/scientific_validation_policy.yaml"]},
    {"key":"ml_model_quality","label":"ML Model Quality","paths":["src/biointel/scientific/benchmark.py","src/biointel/training/release_gate.py","config/scientific_release_policy.yaml"]},
    {"key":"dti_prediction_capability","label":"DTI Prediction Capability","paths":["src/biointel/dti/validation_suite.py","src/biointel/scientific/benchmark.py","config/dti_scientific_benchmark.yaml"]},
    {"key":"overall_scientific_credibility","label":"Overall Scientific Credibility","paths":["src/biointel/scientific/excellence.py","docs/SCIENTIFIC_EVIDENCE_AND_VALIDATION.md","reports/step38_scientific_qualification.json"]},
    {"key":"database_scientific_depth","label":"Database Real Scientific Depth","paths":["src/biointel/scientific/evidence_lake.py","reports/scientific_evidence.sqlite3","config/scientific_coverage_targets.yaml"]},
    {"key":"evidence_registry","label":"Evidence Registry","paths":["src/biointel/scientific/evidence_lake.py","src/biointel/data/evidence_registry.py","scripts/seed_step38_scientific_evidence.py"]},
    {"key":"internet_provider_integration","label":"Internet/Provider Integration","paths":["src/biointel/scientific/provider_hub.py","config/scientific_provider_policy.yaml","scripts/sync_scientific_evidence.py"]},
)


def _evidence_scores(summary: dict[str, int]) -> dict[str, float]:
    provider = min(summary["providers"] / 8.0, 1.0)
    records = min(summary["records"] / 10000.0, 1.0)
    organisms = min(summary["organisms"] / 12.0, 1.0)
    assays = min(summary["assay_types"] / 8.0, 1.0)
    clinical = min(summary["clinical_records"] / 1000.0, 1.0)
    approved = min(summary.get("approved_records", 0) / max(summary["records"], 1), 1.0)
    release = min(summary["release_eligible_records"] / 5000.0, 1.0)
    benchmark = min(summary.get("reviewed_benchmarks", 0) / 2.0, 1.0)
    external = min(summary.get("external_completed_studies", 0) / 3.0, 1.0)
    prospective = min(summary.get("prospective_completed_studies", 0) / 2.0, 1.0)
    dti_external = min(summary.get("dti_external_completed_studies", 0) / 2.0, 1.0)
    dti_prospective = min(summary.get("dti_prospective_completed_studies", 0) / 2.0, 1.0)
    snapshots = min(summary["snapshots"] / 25.0, 1.0)
    return {
        "scientific_data_authenticity": round(2 + 4*provider + 2*records + 2*release, 1),
        "dataset_diversity": round(3 + 2*provider + 2*organisms + 1.5*assays + 1.5*clinical, 1),
        "unique_dataset_quality": round(3 + 2*records + 3*approved + 2*release, 1),
        "assay_data_quality": round(3 + 3*assays + 2*records + 2*release, 1),
        "biological_diversity": round(2 + 5*organisms + 1.5*assays + 1.5*clinical, 1),
        "multi_organism_coverage": round(2 + 8*organisms, 1),
        "clinical_data_coverage": round(2 + 8*clinical, 1),
        "real_scientific_validation": round(2 + 3*benchmark + 3*external + 2*prospective, 1),
        "prospective_validation": round(1 + 9*prospective, 1),
        "external_validation": round(2 + 8*external, 1),
        "ml_model_quality": round(3 + 3*benchmark + 4*external, 1),
        "dti_prediction_capability": round(3 + 4*dti_external + 3*dti_prospective, 1),
        "database_scientific_depth": round(2 + 2*provider + 2*records + 2*organisms + 2*clinical, 1),
        "evidence_registry": round(3 + 2*provider + 2*records + 1.5*organisms + 1.5*assays, 1),
        "internet_provider_integration": round(3 + 4*provider + 3*snapshots, 1),
    }


def build_scientific_excellence_readiness(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    lake_path = runtime_database_path(project_root, "scientific_evidence.sqlite3")
    summary = ScientificEvidenceLake(lake_path).summary()
    evidence = _evidence_scores(summary)
    capabilities: list[ScientificCapability] = []
    for definition in DEFINITIONS:
        missing = tuple(path for path in definition["paths"] if not (project_root / path).exists())
        controls = tuple(path for path in definition["paths"] if (project_root / path).exists())
        implementation_score = round(10.0 * len(controls) / len(definition["paths"]), 1)
        key = definition["key"]
        current = evidence.get(key, 0.0)
        capabilities.append(ScientificCapability(
            key=key,
            label=definition["label"],
            implementation_score=implementation_score,
            implementation_status="complete" if not missing else "incomplete",
            evidence_score=current,
            evidence_status="qualified" if current >= 8.5 else "developing" if current >= 5 else "insufficient",
            controls=controls,
            missing=missing,
            certification_boundary=(
                "10/10 implementation readiness means the provider, provenance, QC, benchmark and release controls exist. "
                "Actual 10/10 evidence requires large licensed provider snapshots, independent external studies and completed blinded prospective validation."
            ),
        ))
    non_overall = [item.evidence_score for item in capabilities if item.key != "overall_scientific_credibility"]
    overall_evidence = round(sum(non_overall) / max(len(non_overall), 1), 1)
    overall_status = "qualified" if overall_evidence >= 8.5 else "developing" if overall_evidence >= 5 else "insufficient"
    capabilities = [
        ScientificCapability(**{**asdict(item), "evidence_score": overall_evidence, "evidence_status": overall_status})
        if item.key == "overall_scientific_credibility" else item
        for item in capabilities
    ]
    return {
        "implementation_average": round(sum(item.implementation_score for item in capabilities) / len(capabilities), 1),
        "evidence_average": round(sum(item.evidence_score for item in capabilities) / len(capabilities), 1),
        "capability_count": len(capabilities),
        "summary": summary,
        "capabilities": [asdict(item) for item in capabilities],
        "boundary": "Repository capability readiness is distinct from scientific truth, clinical utility, wet-lab confirmation or regulatory acceptance.",
    }
