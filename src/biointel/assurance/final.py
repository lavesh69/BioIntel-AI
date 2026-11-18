from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.clinical import (
    ClinicalValidationRegistry,
    build_clinical_pharma_framework_readiness,
    build_independent_validation_accelerator_readiness,
    build_real_external_validation_framework_readiness,
    evaluate_real_external_validation,
)
from biointel.data.relationship_integrity import relationship_summary
from biointel.engineering.quality_gates import run_engineering_gates
from biointel.engineering.repository_audit import run_repository_audit
from biointel.intelligence.data_intelligence import all_database_health
from biointel.production.config import validate_runtime_configuration
from biointel.production.readiness import production_readiness
from biointel.realworld.verified_evidence import build_step42_maximum_evidence
from biointel.scientific.public_evidence import public_external_evidence_readiness


def _status(passed: bool) -> str:
    return "ready" if passed else "review"


def build_final_assurance(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    databases = all_database_health(base)
    relationships = relationship_summary(base)
    engineering = run_engineering_gates(base)
    repository = run_repository_audit(base)
    runtime_config = validate_runtime_configuration()
    production = production_readiness()
    evidence = build_step42_maximum_evidence(base)
    public_evidence = public_external_evidence_readiness(base)
    clinical_pharma = build_clinical_pharma_framework_readiness(base)
    real_external_framework = build_real_external_validation_framework_readiness(base)
    validation_accelerator = build_independent_validation_accelerator_readiness(base)
    external_registry_path = base / "data" / "clinical_pharma" / "clinical_validation.sqlite3"
    real_external_reports = []
    if external_registry_path.is_file():
        external_registry = ClinicalValidationRegistry(external_registry_path)
        real_external_reports = [
            evaluate_real_external_validation(external_registry, item["program_id"])
            for item in external_registry.list_programs()
        ]
    real_external_score = max(
        (item.actual_external_validation_score for item in real_external_reports), default=0.0
    )
    real_external_release = any(item.release_eligible for item in real_external_reports)

    db_ready = (
        databases["healthy_count"] == databases["database_count"]
        and databases["database_count"] > 0
    )
    relationship_ready = int(relationships.get("broken_edges", 0)) == 0
    checks = [
        {
            "key": "database_integrity",
            "label": "Database integrity and discoverability",
            "status": _status(db_ready),
            "score": 10.0 if db_ready else 5.0,
            "evidence": f"{databases['healthy_count']}/{databases['database_count']} databases healthy",
        },
        {
            "key": "relationship_integrity",
            "label": "Cross-registry relationship integrity",
            "status": _status(relationship_ready),
            "score": 10.0 if relationship_ready else 5.0,
            "evidence": f"{relationships.get('valid_edges', 0)} valid edges; {relationships.get('broken_edges', 0)} broken",
        },
        {
            "key": "engineering_gates",
            "label": "Engineering release gates",
            "status": _status(bool(engineering["passed"])),
            "score": 10.0 if engineering["passed"] else 6.0,
            "evidence": f"{sum(item['passed'] for item in engineering['results'])}/{len(engineering['results'])} gates passed",
        },
        {
            "key": "repository_hygiene",
            "label": "Repository security, hygiene and documentation",
            "status": _status(bool(repository["passed"])),
            "score": 10.0 if repository["passed"] else 6.0,
            "evidence": f"{sum(bool(item.get('passed')) for item in repository['checks'].values())}/{len(repository['checks'])} audit checks passed",
        },
        {
            "key": "runtime_configuration",
            "label": "Runtime configuration policy",
            "status": _status(bool(runtime_config["valid"])),
            "score": 10.0 if runtime_config["valid"] else 5.0,
            "evidence": f"critical={runtime_config['critical_count']} warnings={runtime_config['warning_count']}",
        },
        {
            "key": "production_controls",
            "label": "Production control implementation",
            "status": "ready" if production["mode"] != "production_blocked" else "review",
            "score": 10.0 if production["mode"] != "production_blocked" else 5.0,
            "evidence": (
                f"Implementation available; {production['ready_checks']}/{production['total_checks']} runtime checks currently active in {production['mode']} mode"
            ),
        },
        {
            "key": "clinical_pharma_validation_framework",
            "label": "Clinical/pharmaceutical validation execution framework",
            "status": _status(bool(clinical_pharma["complete"])),
            "score": float(clinical_pharma["score"]),
            "evidence": (
                f"{clinical_pharma['passed']}/{clinical_pharma['total']} implementation controls present; "
                "authentic independent evidence remains separate"
            ),
        },
        {
            "key": "real_external_validation_framework",
            "label": "Real external-validation execution framework",
            "status": _status(bool(real_external_framework["complete"])),
            "score": float(real_external_framework["score"]),
            "evidence": (
                f"{real_external_framework['passed']}/{real_external_framework['total']} authenticity, "
                "review, integrity and nine-domain scoring controls present"
            ),
        },
        {
            "key": "independent_validation_accelerator",
            "label": "Independent validation execution accelerator",
            "status": _status(validation_accelerator.score == 10.0),
            "score": float(validation_accelerator.score),
            "evidence": (
                f"{validation_accelerator.passed_controls}/{validation_accelerator.total_controls} "
                "action-plan, partner-pack and claim-boundary controls present"
            ),
        },
        {
            "key": "bundled_public_external_evidence",
            "label": "Bundled public external scientific evidence",
            "status": _status(bool(public_evidence["complete"])),
            "score": float(public_evidence["score"]),
            "evidence": (
                f"{public_evidence['passed']}/{public_evidence['total']} public-evidence controls; "
                f"{public_evidence['summary']['verified_files']} checksum-verified artifacts"
            ),
        },
        {
            "key": "real_external_validation_evidence",
            "label": "Real external clinical/pharma evidence",
            "status": "ready" if real_external_release else "external_required",
            "score": float(real_external_score),
            "evidence": (
                f"{len(real_external_reports)} controlled program(s); authentic evidence only; "
                "test fixtures and synthetic records excluded"
            ),
        },
        {
            "key": "verifiable_evidence",
            "label": "Measured and checksum-bound evidence",
            "status": "ready" if evidence["artifact_integrity"]["ok"] else "review",
            "score": float(evidence["verifiable_average"]),
            "evidence": f"{evidence['artifact_integrity']['verified_count']}/{evidence['artifact_integrity']['artifact_count']} artifacts verified",
        },
        {
            "key": "external_evidence",
            "label": "Authentic third-party evidence",
            "status": (
                "external_required" if evidence["authentic_external_average"] < 10 else "ready"
            ),
            "score": float(evidence["authentic_external_average"]),
            "evidence": "Customers, regulators, journals, laboratories and production history must be independently supplied.",
        },
    ]
    internal = [
        item
        for item in checks
        if item["key"]
        not in {"external_evidence", "verifiable_evidence", "real_external_validation_evidence", "bundled_public_external_evidence"}
    ]
    return {
        "schema": "biointel.final-assurance.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "version": (base / "VERSION").read_text(encoding="utf-8").strip(),
        "implementation_score": round(
            sum(float(item["score"]) for item in internal) / len(internal), 1
        ),
        "verifiable_evidence_score": float(evidence["verifiable_average"]),
        "bundled_public_external_evidence_score": float(public_evidence["score"]),
        "authentic_external_evidence_score": float(evidence["authentic_external_average"]),
        "real_external_validation_score": float(real_external_score),
        "real_external_validation_release_eligible": real_external_release,
        "checks": checks,
        "database_health": databases,
        "relationship_health": relationships,
        "engineering": engineering,
        "repository_audit": repository,
        "runtime_configuration": runtime_config,
        "production_readiness": production,
        "evidence": evidence,
        "public_external_evidence": public_evidence,
        "clinical_pharma_framework": clinical_pharma,
        "real_external_validation_framework": real_external_framework,
        "independent_validation_accelerator": validation_accelerator.to_dict(),
        "real_external_validation_programs": [item.to_dict() for item in real_external_reports],
        "boundary": "Implementation and controlled-environment evidence are reported separately from authentic external approvals, customers, publications, laboratory outcomes and operating history.",
    }
