from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    label: str
    passed: bool
    evidence: str
    remediation: str


@dataclass(frozen=True)
class ResearchReadinessReport:
    profile: str
    score: float
    passed: int
    total: int
    checks: tuple[ReadinessCheck, ...]
    certification_boundary: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [asdict(item) for item in self.checks]
        return payload


def _check(
    key: str,
    label: str,
    predicate: Callable[[], bool],
    evidence: str,
    remediation: str,
) -> ReadinessCheck:
    try:
        passed = bool(predicate())
    except (KeyError, TypeError, ValueError):
        passed = False
    return ReadinessCheck(key, label, passed, evidence, remediation)


def _report(profile: str, checks: tuple[ReadinessCheck, ...], boundary: str) -> ResearchReadinessReport:
    passed = sum(item.passed for item in checks)
    return ResearchReadinessReport(
        profile=profile,
        score=round(10.0 * passed / max(len(checks), 1), 1),
        passed=passed,
        total=len(checks),
        checks=checks,
        certification_boundary=boundary,
    )


def evaluate_academic_readiness(payload: dict[str, Any]) -> ResearchReadinessReport:
    checks = (
        _check("question", "Research question and hypothesis", lambda: bool(payload.get("research_question")) and bool(payload.get("hypothesis")), "question/hypothesis", "Document the research question and falsifiable hypothesis."),
        _check("protocol", "Protocol or preregistration", lambda: bool(payload.get("protocol_id")) and bool(payload.get("preregistered")), str(payload.get("protocol_id", "missing")), "Register a time-stamped protocol before analysis."),
        _check("ethics", "Ethics and consent statement", lambda: bool(payload.get("ethics_review")) and bool(payload.get("consent_or_exemption")), "ethics review", "Record ethics approval, consent basis or a documented exemption."),
        _check("contributors", "Contributor identities and roles", lambda: len(payload.get("contributors", [])) >= 1 and all(item.get("name") and item.get("role") for item in payload.get("contributors", [])), f"{len(payload.get('contributors', []))} contributors", "Add contributors, roles and persistent identifiers where available."),
        _check("methods", "Complete methods and parameters", lambda: bool(payload.get("methods")) and isinstance(payload.get("parameters"), dict), "methods/parameters", "Record executable parameters and complete analytical methods."),
        _check("data", "Data availability and licensing", lambda: bool(payload.get("data_identifier")) and bool(payload.get("data_license")) and bool(payload.get("data_availability_statement")), str(payload.get("data_identifier", "missing")), "Publish or document controlled access to data with a clear license."),
        _check("software", "Software and environment citation", lambda: bool(payload.get("software_identifier")) and bool(payload.get("environment_lock")), str(payload.get("software_identifier", "missing")), "Cite software/version and provide an environment lock or container digest."),
        _check("repro", "Verified reproducibility bundle", lambda: bool(payload.get("reproducibility_bundle_verified")), "verified bundle" if payload.get("reproducibility_bundle_verified") else "missing", "Provide and verify a reproducibility bundle."),
        _check("statistics", "Statistical analysis plan", lambda: bool(payload.get("statistical_plan")) and bool(payload.get("multiple_testing_policy")), "statistical plan", "Predefine endpoints, power, exclusions and multiple-testing handling."),
        _check("reporting", "Limitations, negative results and reporting checklist", lambda: bool(payload.get("limitations")) and bool(payload.get("reporting_checklist")) and bool(payload.get("negative_results_policy")), "reporting controls", "Record limitations, negative results policy and a field-specific reporting checklist."),
    )
    return _report(
        "academic_research",
        checks,
        "A 10/10 framework report indicates a complete submission package, not peer review acceptance or independent replication.",
    )


def evaluate_pharma_readiness(payload: dict[str, Any]) -> ResearchReadinessReport:
    checks = (
        _check("intended_use", "Intended use and decision context", lambda: bool(payload.get("intended_use")) and bool(payload.get("decision_context")), "intended use", "Define intended use, users, decisions and prohibited uses."),
        _check("protocol", "Approved study protocol", lambda: bool(payload.get("protocol_id")) and payload.get("protocol_status") == "approved", str(payload.get("protocol_id", "missing")), "Approve a controlled protocol before execution."),
        _check("design", "Randomization, blinding and controls", lambda: bool(payload.get("randomization")) and bool(payload.get("blinding")) and bool(payload.get("controls")), "study design controls", "Document randomization, blinding and positive/negative controls."),
        _check("assay", "Assay context and acceptance criteria", lambda: bool(payload.get("assay_ontology_id")) and bool(payload.get("acceptance_criteria")) and bool(payload.get("replicate_plan")), str(payload.get("assay_ontology_id", "missing")), "Use controlled assay context, replicates and predefined acceptance criteria."),
        _check("materials", "Material and sample traceability", lambda: bool(payload.get("sample_chain_of_custody")) and bool(payload.get("compound_identity_controls")), "chain of custody", "Capture sample/material identity, custody and storage conditions."),
        _check("data_integrity", "GxP data-integrity controls", lambda: bool(payload.get("audit_chain_verified")) and bool(payload.get("electronic_signatures_verified")) and bool(payload.get("controlled_records")), "audit/signature controls", "Use controlled records, verified audit trails and bound electronic signatures."),
        _check("validation", "Independent and prospective validation", lambda: bool(payload.get("independent_validation")) and bool(payload.get("prospective_validation")) and bool(payload.get("leakage_audit")), "validation evidence", "Complete independent, prospective and leakage-resistant validation."),
        _check("quality", "Deviation, CAPA and change control", lambda: bool(payload.get("deviation_process")) and bool(payload.get("capa_process")) and bool(payload.get("change_control")), "quality-system processes", "Operate deviations, CAPA and controlled change procedures."),
        _check("review", "Independent QA and scientific review", lambda: bool(payload.get("independent_qa_review")) and bool(payload.get("scientific_review")), "independent review", "Obtain independent quality and scientific approvals."),
        _check("release", "Signed evidence package and release gate", lambda: bool(payload.get("signed_evidence_manifest")) and bool(payload.get("release_gate_passed")) and bool(payload.get("limitations_disclosed")), "release package", "Pass the release gate with signed evidence, limitations and traceability."),
    )
    return _report(
        "pharmaceutical_r_and_d",
        checks,
        "A complete framework package is not regulatory approval, GxP certification, clinical validity or permission for patient-care use.",
    )
