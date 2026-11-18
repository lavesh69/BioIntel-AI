from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .registry import ClinicalValidationRegistry

CLAIM_PROFILES: dict[str, dict[str, Any]] = {
    "research_demo": {
        "label": "Research/demo use",
        "minimum_sites": 0,
        "minimum_outcomes": 0,
        "minimum_training_records": 0,
        "required_evidence_categories": (),
    },
    "pharma_r_and_d": {
        "label": "Pharmaceutical R&D decision support",
        "minimum_sites": 2,
        "minimum_outcomes": 2,
        "minimum_training_records": 2,
        "required_evidence_categories": (
            "assay_validation",
            "independent_external_validation",
            "prospective_validation",
            "quality_assurance",
            "data_integrity",
            "model_validation",
            "supplier_qualification",
        ),
    },
    "clinical_decision_support": {
        "label": "Clinical decision-support candidate",
        "minimum_sites": 3,
        "minimum_outcomes": 3,
        "minimum_training_records": 3,
        "required_evidence_categories": (
            "ethics_regulatory",
            "clinical_evaluation",
            "assay_validation",
            "independent_external_validation",
            "prospective_validation",
            "quality_assurance",
            "data_integrity",
            "model_validation",
            "privacy_security",
            "human_factors",
            "post_market_surveillance",
            "supplier_qualification",
        ),
    },
}


@dataclass(frozen=True)
class ReadinessGate:
    gate_id: str
    domain: str
    label: str
    passed: bool
    evidence: str
    remediation: str
    external: bool
    critical: bool = True


@dataclass(frozen=True)
class ClinicalPharmaReadinessReport:
    program_id: str
    claim_profile: str
    control_readiness_score: float
    external_evidence_score: float
    total_score: float
    release_eligible: bool
    permitted_claim: str
    gates: tuple[ReadinessGate, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gate(
    gate_id: str,
    domain: str,
    label: str,
    passed: bool,
    evidence: str,
    remediation: str,
    *,
    external: bool = False,
    critical: bool = True,
) -> ReadinessGate:
    return ReadinessGate(
        gate_id, domain, label, bool(passed), evidence, remediation, external, critical
    )


def evaluate_clinical_pharma_readiness(
    registry: ClinicalValidationRegistry, program_id: str
) -> ClinicalPharmaReadinessReport:
    snapshot = registry.snapshot(program_id)
    program = snapshot["program"]
    profile_key = str(program["claim_profile"])
    profile = CLAIM_PROFILES.get(profile_key, CLAIM_PROFILES["clinical_decision_support"])
    research = profile_key == "research_demo"

    sites = snapshot["sites"]
    qualified = [item for item in sites if item["status"] == "qualified"]
    independent_sites = [item for item in qualified if item["independent"]]
    independent_site_ids = {item["site_id"] for item in independent_sites}
    protocols = snapshot["protocols"]
    approved_protocols = [item for item in protocols if item["status"] == "approved"]
    planned_sample_size = max((int(item["sample_size"]) for item in approved_protocols), default=0)
    protocol_with_ethics = any(item.get("ethics_reference") for item in approved_protocols)
    preregistered = any(item.get("preregistration_reference") for item in approved_protocols)
    freezes = [item for item in snapshot["model_freezes"] if item["status"] == "locked"]
    predictions = [item for item in snapshot["prediction_batches"] if item["status"] == "locked"]
    outcomes = snapshot["outcome_batches"]
    outcome_prediction_ids = {item["prediction_batch_id"] for item in outcomes}
    matched_batches = sum(item["batch_id"] in outcome_prediction_ids for item in predictions)
    locked_samples = sum(int(item["sample_count"]) for item in predictions)
    outcome_samples = sum(int(item["sample_count"]) for item in outcomes)
    all_blinded = bool(predictions) and all(item["blinded"] for item in predictions)
    all_adjudicated = bool(outcomes) and all(item["adjudicated"] for item in outcomes)

    results = snapshot["analysis_results"]
    approved_results = [item for item in results if item["status"] == "approved"]
    approved_primary = [item for item in approved_results if item["result_scope"] == "primary"]
    passed_primary = [item for item in approved_primary if item["passed"]]
    approved_site_result_ids = {
        item["site_id"]
        for item in approved_results
        if item["result_scope"] == "site" and item["passed"] and item.get("site_id")
    }
    approved_subgroup = [
        item for item in approved_results if item["result_scope"] == "subgroup" and item["passed"]
    ]

    evidence = snapshot["evidence_items"]
    approved_evidence = [item for item in evidence if item["status"] == "approved"]
    approved_categories = {item["category"] for item in approved_evidence}
    required_categories = set(profile["required_evidence_categories"])
    missing_categories = sorted(required_categories - approved_categories)
    independent_approved = [item for item in approved_evidence if item["independent"]]

    quality_events = snapshot["quality_events"]
    open_major = [
        item
        for item in quality_events
        if item["status"] != "closed" and item["severity"].lower() in {"major", "critical"}
    ]
    ineffective_closed = [
        item
        for item in quality_events
        if item["status"] == "closed" and not item["effectiveness_verified"]
    ]
    training = [item for item in snapshot["training_records"] if item["result"] == "passed"]
    summary_signatures = [
        item
        for item in snapshot["signatures"]
        if item["object_type"] == "validation_summary_report"
        and item["meaning"].lower() in {"approval", "approved", "authorization"}
    ]

    gates = (
        _gate(
            "CPV-001",
            "Scope",
            "Documented intended use",
            bool(program["intended_use"] and program["decision_context"]),
            program["intended_use"] or "Missing",
            "Define the exact intended use and decision context.",
        ),
        _gate(
            "CPV-002",
            "Scope",
            "Prohibited uses and claim boundary",
            bool(program["prohibited_uses"]),
            f"{len(program['prohibited_uses'])} prohibited use(s)",
            "Document autonomous clinical and unsupported regulated uses as prohibited.",
        ),
        _gate(
            "CPV-003",
            "Protocol",
            "Approved controlled protocol",
            bool(approved_protocols),
            f"{len(approved_protocols)} approved protocol version(s)",
            "Approve a controlled protocol before model freeze.",
        ),
        _gate(
            "CPV-004",
            "Protocol",
            "Predefined endpoint and success criterion",
            bool(approved_protocols)
            and all(
                item["primary_endpoint"]
                and item["success_criterion"]
                and item["statistical_plan"]
                and int(item["sample_size"]) > 0
                for item in approved_protocols
            ),
            f"Planned sample size={planned_sample_size}",
            "Predefine endpoint, criterion, sample size and analysis plan.",
        ),
        _gate(
            "CPV-005",
            "Ethics",
            "Ethics/regulatory determination",
            research or protocol_with_ethics or "ethics_regulatory" in approved_categories,
            "Reference captured" if protocol_with_ethics else "Missing",
            "Obtain IRB/IEC approval, exemption or regulatory determination as applicable.",
            external=True,
        ),
        _gate(
            "CPV-006",
            "Transparency",
            "Prospective preregistration",
            research or preregistered,
            "Reference captured" if preregistered else "Missing",
            "Preregister before outcomes are accessible.",
            external=True,
        ),
        _gate(
            "CPV-007",
            "Sites",
            "Qualified independent sites",
            research or len(independent_sites) >= int(profile["minimum_sites"]),
            f"{len(independent_sites)}/{profile['minimum_sites']} independent qualified sites",
            "Qualify the required independent laboratories or clinical sites.",
            external=True,
        ),
        _gate(
            "CPV-008",
            "Model control",
            "Immutable model and input freeze",
            research or bool(freezes),
            f"{len(freezes)} locked freeze(s)",
            "Freeze model, data, code, environment and feature specification hashes.",
        ),
        _gate(
            "CPV-009",
            "Prospective execution",
            "Predictions locked before outcomes",
            research or (bool(predictions) and matched_batches == len(predictions)),
            f"{len(predictions)} predictions; {matched_batches} linked outcomes",
            "Lock blinded predictions before site outcomes arrive.",
            external=True,
        ),
        _gate(
            "CPV-010",
            "Prospective execution",
            "Blinding and adjudication",
            research or (all_blinded and all_adjudicated),
            f"blinded={all_blinded}; adjudicated={all_adjudicated}",
            "Use blinded sample codes and independent endpoint adjudication.",
            external=True,
        ),
        _gate(
            "CPV-011",
            "Prospective execution",
            "Outcome-batch coverage",
            research or len(outcomes) >= int(profile["minimum_outcomes"]),
            f"{len(outcomes)}/{profile['minimum_outcomes']} batches; {outcome_samples} samples",
            "Complete the required prospective outcome batches.",
            external=True,
        ),
        _gate(
            "CPV-012",
            "Statistics",
            "Sample-size reconciliation",
            research
            or (
                planned_sample_size > 0
                and locked_samples >= planned_sample_size
                and outcome_samples >= planned_sample_size
            ),
            f"planned={planned_sample_size}; locked={locked_samples}; outcomes={outcome_samples}",
            "Meet the prospectively defined sample size or approve an amendment.",
        ),
        _gate(
            "CPV-013",
            "Statistics",
            "Approved primary endpoint result",
            research or bool(passed_primary),
            f"{len(passed_primary)} passed / {len(approved_primary)} approved primary result(s)",
            "Calculate the predefined endpoint with confidence intervals and independent review.",
            external=True,
        ),
        _gate(
            "CPV-014",
            "Statistics",
            "Per-site performance analysis",
            research or independent_site_ids.issubset(approved_site_result_ids),
            f"{len(approved_site_result_ids)}/{len(independent_site_ids)} sites with passing results",
            "Report and independently review every qualified site's performance.",
            external=True,
        ),
        _gate(
            "CPV-015",
            "Statistics",
            "Predefined subgroup analysis",
            profile_key != "clinical_decision_support" or bool(approved_subgroup),
            f"{len(approved_subgroup)} approved subgroup result(s)",
            "Complete predefined clinically relevant subgroup analyses.",
            external=True,
        ),
        _gate(
            "CPV-016",
            "Evidence",
            "Required evidence categories",
            research or not missing_categories,
            "Complete" if not missing_categories else f"Missing: {', '.join(missing_categories)}",
            "Import and independently approve every required evidence category.",
            external=True,
        ),
        _gate(
            "CPV-017",
            "Evidence",
            "Independent evidence provenance",
            research or len(independent_approved) >= max(2, int(profile["minimum_sites"])),
            f"{len(independent_approved)} independent approved evidence items",
            "Obtain evidence from organizations separate from the model sponsor.",
            external=True,
        ),
        _gate(
            "CPV-018",
            "Quality system",
            "No open major/critical events",
            not open_major,
            f"{len(open_major)} open major/critical event(s)",
            "Resolve major/critical deviations, incidents and CAPAs.",
        ),
        _gate(
            "CPV-019",
            "Quality system",
            "CAPA effectiveness verified",
            not ineffective_closed,
            f"{len(ineffective_closed)} ineffective closed event(s)",
            "Record and verify CAPA effectiveness.",
        ),
        _gate(
            "CPV-020",
            "People",
            "Role-based training evidence",
            research or len(training) >= int(profile["minimum_training_records"]),
            f"{len(training)}/{profile['minimum_training_records']} passed records",
            "Train operators, investigators and quality reviewers.",
            external=True,
        ),
        _gate(
            "CPV-021",
            "Data integrity",
            "Tamper-evident audit chain",
            bool(snapshot["audit"]["valid"]),
            f"{snapshot['audit']['event_count']} events; final hash={snapshot['audit']['final_hash'][:12]}…",
            "Investigate any audit-chain break.",
        ),
        _gate(
            "CPV-022",
            "Approval",
            "Signed validation summary",
            research or bool(summary_signatures),
            f"{len(summary_signatures)} approval signature(s)",
            "Independently review and electronically sign the validation summary.",
            external=True,
        ),
        _gate(
            "CPV-023",
            "Release",
            "Program status supports release",
            program["status"] == "completed" if not research else True,
            f"status={program['status']}",
            "Complete the validation program and obtain quality release authorization.",
        ),
    )

    controls = [item for item in gates if not item.external]
    external = [item for item in gates if item.external]
    control_score = round(10 * sum(item.passed for item in controls) / len(controls), 1)
    evidence_score = round(10 * sum(item.passed for item in external) / len(external), 1)
    total_score = round(0.45 * control_score + 0.55 * evidence_score, 1)
    blockers = tuple(item.label for item in gates if item.critical and not item.passed)
    warnings = tuple(item.label for item in gates if not item.critical and not item.passed)
    release_eligible = not blockers and not research
    if release_eligible and profile_key == "pharma_r_and_d":
        claim = "Pharmaceutical R&D validation package complete for the documented intended use."
    elif release_eligible:
        claim = (
            "Clinical decision-support validation package complete; regulatory authorization "
            "remains jurisdiction-specific."
        )
    else:
        claim = (
            "Research/demo use only; clinical and validated pharmaceutical claims remain blocked."
        )
    return ClinicalPharmaReadinessReport(
        program_id=program_id,
        claim_profile=profile_key,
        control_readiness_score=control_score,
        external_evidence_score=evidence_score,
        total_score=total_score,
        release_eligible=release_eligible,
        permitted_claim=claim,
        gates=gates,
        blockers=blockers,
        warnings=warnings,
        boundary=(
            "This report measures evidence completeness against a strict validation workflow. "
            "It does not replace sponsor quality approval, competent-authority authorization, "
            "independent clinical judgment, laboratory accreditation or regulatory inspection."
        ),
    )


FRAMEWORK_ASSETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Clinical validation registry",
        "src/biointel/clinical/registry.py",
        ("create_program", "freeze_model", "lock_prediction_batch", "verify_audit_chain"),
    ),
    (
        "Controlled registry schema",
        "src/biointel/clinical/schema.py",
        ("validation_programs", "analysis_results", "audit_events"),
    ),
    (
        "Quality and signature controls",
        "src/biointel/clinical/quality.py",
        ("add_evidence", "close_quality_event", "sign_object"),
    ),
    (
        "Strict readiness gates",
        "src/biointel/clinical/readiness.py",
        ("CPV-001", "CPV-023", "release_eligible"),
    ),
    (
        "Checksum-bound dossier",
        "src/biointel/clinical/dossier.py",
        ("manifest.json", "verify_validation_dossier"),
    ),
    (
        "Execution user interface",
        "pages/90_Clinical_Pharma_Validation_Center.py",
        ("Clinical & Pharmaceutical Validation Center", "Lock prediction batch"),
    ),
    (
        "Validation policy",
        "config/clinical_pharma_validation_policy.yaml",
        ("pharma_r_and_d", "clinical_decision_support", "release_blockers"),
    ),
    (
        "Validation execution guide",
        "docs/CLINICAL_PHARMA_VALIDATION_EXECUTION_GUIDE.md",
        ("certification boundary", "prospective execution"),
    ),
    (
        "Blank controlled templates",
        "data/clinical_pharma/templates/01_VALIDATION_MASTER_PLAN.md",
        ("Validation Master Plan", "Intended use"),
    ),
    (
        "Deterministic qualification tests",
        "tests/test_step83_clinical_pharma_validation.py",
        ("complete_pharma_execution_package", "incomplete_program_remains_research_only"),
    ),
)


def build_clinical_pharma_framework_readiness(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    checks: list[dict[str, Any]] = []
    for label, relative, tokens in FRAMEWORK_ASSETS:
        path = base / relative
        passed = path.is_file()
        if passed:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            passed = all(token.lower() in text for token in tokens)
        checks.append(
            {
                "label": label,
                "path": relative,
                "passed": passed,
                "evidence": "implemented and inspectable" if passed else "missing or incomplete",
            }
        )
    passed_count = sum(item["passed"] for item in checks)
    score = round(10 * passed_count / len(checks), 1)
    return {
        "schema": "biointel.clinical-pharma-framework-readiness.v1",
        "score": score,
        "passed": passed_count,
        "total": len(checks),
        "complete": passed_count == len(checks),
        "checks": checks,
        "external_validation_status": "authentic independent and prospective evidence required",
        "boundary": (
            "A complete framework score confirms software controls and executable templates only; "
            "it does not certify clinical validity, GxP status or regulatory approval."
        ),
    }
