from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .external_evidence import EXTERNAL_VALIDATION_DOMAINS
from .registry import ClinicalValidationRegistry


@dataclass(frozen=True)
class ExternalDomainRating:
    domain: str
    label: str
    score: float
    passed_controls: int
    total_controls: int
    status: str
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class RealExternalValidationReport:
    program_id: str
    actual_external_validation_score: float
    domains_at_10: int
    total_domains: int
    authentic_artifact_count: int
    excluded_artifact_count: int
    release_eligible: bool
    permitted_claim: str
    ratings: tuple[ExternalDomainRating, ...]
    blockers: tuple[str, ...]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "yes", "approved", "pass", "passed", "active"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _control(
    label: str, passed: bool, evidence: str, remediation: str
) -> tuple[str, bool, str, str]:
    return label, bool(passed), evidence, remediation


def _rating(domain: str, controls: list[tuple[str, bool, str, str]]) -> ExternalDomainRating:
    passed = sum(item[1] for item in controls)
    score = round(10 * passed / len(controls), 1)
    evidence = tuple(f"{label}: {detail}" for label, ok, detail, _ in controls if ok)
    blockers = tuple(remediation for _, ok, _, remediation in controls if not ok)
    return ExternalDomainRating(
        domain=domain,
        label=EXTERNAL_VALIDATION_DOMAINS[domain],
        score=score,
        passed_controls=passed,
        total_controls=len(controls),
        status="10/10 verified" if passed == len(controls) else "evidence incomplete",
        evidence=evidence,
        blockers=blockers,
    )


def _valid_artifacts(
    registry: ClinicalValidationRegistry, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.now(UTC)
    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        issued = _iso(row.get("issued_at"))
        expires = _iso(row.get("expires_at"))
        integrity = registry.verify_external_artifact_integrity(row["artifact_id"])
        accepted = (
            row.get("status") == "approved"
            and not row.get("test_fixture")
            and bool(row.get("independent"))
            and bool(row.get("external_identifier"))
            and bool(row.get("verified_by"))
            and row.get("verified_by") != row.get("submitted_by")
            and issued is not None
            and issued <= now
            and (expires is None or expires > now)
            and integrity["valid"]
        )
        item = {**row, "integrity": integrity}
        (valid if accepted else excluded).append(item)
    return valid, excluded


def evaluate_real_external_validation(
    registry: ClinicalValidationRegistry, program_id: str
) -> RealExternalValidationReport:
    snapshot = registry.snapshot(program_id)
    program = snapshot["program"]
    valid, excluded = _valid_artifacts(registry, snapshot.get("external_artifacts", []))
    by_domain = {
        domain: [item for item in valid if item["domain"] == domain]
        for domain in EXTERNAL_VALIDATION_DOMAINS
    }
    qualified_sites = [
        item for item in snapshot["sites"] if item["status"] == "qualified" and item["independent"]
    ]
    accredited_sites = [item for item in qualified_sites if item.get("laboratory_accreditation")]
    approved_protocols = [item for item in snapshot["protocols"] if item["status"] == "approved"]
    predictions = [item for item in snapshot["prediction_batches"] if item["status"] == "locked"]
    outcomes = snapshot["outcome_batches"]
    outcome_ids = {item["prediction_batch_id"] for item in outcomes}
    matched = bool(predictions) and all(item["batch_id"] in outcome_ids for item in predictions)
    prospective_integrity = (
        matched
        and all(item["blinded"] for item in predictions)
        and bool(outcomes)
        and all(item["adjudicated"] for item in outcomes)
    )
    planned = max((int(item["sample_size"]) for item in approved_protocols), default=0)
    actual_samples = sum(int(item["sample_count"]) for item in outcomes)
    approved_results = [
        item for item in snapshot["analysis_results"] if item["status"] == "approved"
    ]
    primary_pass = any(
        item["result_scope"] == "primary" and item["passed"] for item in approved_results
    )
    passed_site_ids = {
        item["site_id"]
        for item in approved_results
        if item["result_scope"] == "site" and item["passed"] and item.get("site_id")
    }
    qualified_site_ids = {item["site_id"] for item in qualified_sites}
    no_open_major = not any(
        item["status"] != "closed" and item["severity"].lower() in {"major", "critical"}
        for item in snapshot["quality_events"]
    )
    training_count = sum(item["result"] == "passed" for item in snapshot["training_records"])

    independent = by_domain["independent_clinical_evidence"]
    independent_orgs = {item["source_organization"] for item in independent}
    r1 = _rating(
        "independent_clinical_evidence",
        [
            _control(
                "Evidence volume",
                len(independent) >= 2,
                f"{len(independent)} approved artifacts",
                "Add at least two authentic approved clinical evidence artifacts.",
            ),
            _control(
                "Independent organizations",
                len(independent_orgs) >= 2,
                f"{len(independent_orgs)} organizations",
                "Obtain evidence from at least two independent organizations.",
            ),
            _control(
                "Clinical report types",
                all(
                    item["source_type"] in {"clinical_study_report", "official_registry_record"}
                    for item in independent
                )
                and bool(independent),
                "Controlled clinical or registry records",
                "Use controlled clinical study reports or official registry records.",
            ),
            _control(
                "Traceable identifiers",
                all(bool(item["external_identifier"]) for item in independent)
                and bool(independent),
                "External identifiers captured",
                "Record trial, registry or issuer identifiers.",
            ),
            _control(
                "Independent review and integrity",
                all(
                    item["integrity"]["valid"] and item["verified_by"] != item["submitted_by"]
                    for item in independent
                )
                and bool(independent),
                "Hash and reviewer separation verified",
                "Complete independent review and artifact integrity verification.",
            ),
        ],
    )

    prospective = by_domain["prospective_clinical_study"]
    protocol_ready = bool(approved_protocols) and all(
        item.get("preregistration_reference") and item.get("ethics_reference")
        for item in approved_protocols
    )
    per_site_ready = bool(qualified_site_ids) and qualified_site_ids.issubset(passed_site_ids)
    r2 = _rating(
        "prospective_clinical_study",
        [
            _control(
                "Prospective report",
                bool(prospective),
                f"{len(prospective)} approved report(s)",
                "Add an authentic final prospective study report.",
            ),
            _control(
                "Approved preregistered protocol",
                protocol_ready,
                f"{len(approved_protocols)} approved protocol(s)",
                "Approve and preregister the protocol with ethics/regulatory determination.",
            ),
            _control(
                "Independent multisite execution",
                len(qualified_sites) >= 2,
                f"{len(qualified_sites)} qualified independent sites",
                "Complete execution at two or more qualified independent sites.",
            ),
            _control(
                "Prediction/outcome sequencing",
                prospective_integrity,
                f"matched={matched}; outcomes={len(outcomes)}",
                "Lock blinded predictions before independently adjudicated outcomes.",
            ),
            _control(
                "Predefined endpoint success",
                planned > 0 and actual_samples >= planned and primary_pass and per_site_ready,
                f"planned={planned}; outcomes={actual_samples}; primary_pass={primary_pass}",
                "Meet sample size and pass independently reviewed primary and per-site endpoints.",
            ),
        ],
    )

    lab = by_domain["pharma_laboratory_validation"]
    lab_orgs = {item["source_organization"] for item in lab}
    r3 = _rating(
        "pharma_laboratory_validation",
        [
            _control(
                "Independent laboratory reports",
                len(lab) >= 2 and len(lab_orgs) >= 2,
                f"{len(lab)} reports from {len(lab_orgs)} labs",
                "Add reports from at least two independent pharmaceutical laboratories.",
            ),
            _control(
                "Qualified accredited sites",
                len(accredited_sites) >= 2,
                f"{len(accredited_sites)} accredited independent sites",
                "Qualify at least two laboratories with accreditation or documented scope.",
            ),
            _control(
                "Assay validation",
                bool(lab) and all(_truthy(item["metadata"].get("assay_validated")) for item in lab),
                "Assay validation declared",
                "Provide approved assay validation evidence.",
            ),
            _control(
                "Independent replication",
                bool(lab)
                and all(_truthy(item["metadata"].get("replication_complete")) for item in lab),
                "Replication complete",
                "Complete independent replication across sites/lots/operators.",
            ),
            _control(
                "Raw-data traceability",
                bool(lab)
                and all(_truthy(item["metadata"].get("raw_data_available")) for item in lab),
                "Raw data traceable",
                "Link controlled raw data, methods and acceptance results.",
            ),
        ],
    )

    publications = by_domain["peer_reviewed_publication"]
    r4 = _rating(
        "peer_reviewed_publication",
        [
            _control(
                "Published validation article",
                bool(publications),
                f"{len(publications)} approved publication(s)",
                "Publish at least one validation study in a peer-reviewed journal.",
            ),
            _control(
                "Journal source type",
                bool(publications)
                and all(item["source_type"] == "journal_article" for item in publications),
                "Journal article records",
                "Register the final journal article rather than a manuscript or poster.",
            ),
            _control(
                "DOI/PubMed traceability",
                bool(publications)
                and all(
                    item["external_identifier"].lower().startswith(("doi:", "pmid:"))
                    for item in publications
                ),
                "DOI/PubMed identifiers captured",
                "Add a DOI or PubMed identifier.",
            ),
            _control(
                "Peer-review status",
                bool(publications)
                and all(
                    _truthy(item["metadata"].get("peer_reviewed"))
                    and str(item["metadata"].get("publication_status", "")).lower() == "published"
                    for item in publications
                ),
                "Published and peer reviewed",
                "Verify final peer-review and publication status.",
            ),
            _control(
                "Study limitations disclosed",
                bool(publications)
                and all(
                    _truthy(item["metadata"].get("limitations_reported")) for item in publications
                ),
                "Limitations reported",
                "Document limitations, negative results and conflicts of interest.",
            ),
        ],
    )

    gxp = by_domain["gxp_operating_history"]
    accepted_qms = {"glp", "gcp", "gmp", "gclp", "iso 13485", "21 cfr part 11"}
    r5 = _rating(
        "gxp_operating_history",
        [
            _control(
                "Controlled operating history",
                bool(gxp),
                f"{len(gxp)} approved operating record(s)",
                "Import authentic controlled operating-history evidence.",
            ),
            _control(
                "Sustained duration",
                bool(gxp)
                and all(_num(item["metadata"].get("duration_months")) >= 12 for item in gxp),
                "At least 12 months",
                "Document at least 12 months of controlled operation.",
            ),
            _control(
                "Applicable quality system",
                bool(gxp)
                and all(
                    str(item["metadata"].get("quality_system", "")).strip().lower() in accepted_qms
                    for item in gxp
                ),
                "Recognized quality system recorded",
                "Identify the applicable GLP/GCP/GMP/GCLP/ISO/Part 11 quality system.",
            ),
            _control(
                "Audit and CAPA state",
                bool(gxp)
                and all(_truthy(item["metadata"].get("audit_complete")) for item in gxp)
                and no_open_major,
                f"audit_complete; open_major={not no_open_major}",
                "Complete audits and close major/critical CAPAs.",
            ),
            _control(
                "Qualified personnel",
                training_count >= 2,
                f"{training_count} passed training records",
                "Record role-based qualification and training evidence.",
            ),
        ],
    )

    inspections = by_domain["regulatory_inspection"]
    r6 = _rating(
        "regulatory_inspection",
        [
            _control(
                "Official inspection evidence",
                bool(inspections),
                f"{len(inspections)} approved inspection record(s)",
                "Import an authentic regulatory inspection report or official outcome.",
            ),
            _control(
                "Inspection-report source",
                bool(inspections)
                and all(
                    item["source_type"] == "regulatory_inspection_report" for item in inspections
                ),
                "Regulatory inspection reports",
                "Use official regulatory inspection outcome documents.",
            ),
            _control(
                "Authority traceability",
                bool(inspections)
                and all(bool(item["metadata"].get("authority")) for item in inspections),
                "Authority recorded",
                "Record the inspecting authority and official reference.",
            ),
            _control(
                "Acceptable outcome",
                bool(inspections)
                and all(
                    str(item["metadata"].get("outcome", "")).lower()
                    in {"pass", "acceptable", "no action indicated", "closed"}
                    for item in inspections
                ),
                "Acceptable/closed outcome",
                "Resolve the inspection outcome and any required response.",
            ),
            _control(
                "No open critical findings",
                bool(inspections)
                and all(
                    _num(item["metadata"].get("critical_findings_open")) == 0
                    for item in inspections
                ),
                "No open critical findings",
                "Close all critical inspection findings.",
            ),
        ],
    )

    authorizations = by_domain["regulatory_authorization"]
    r7 = _rating(
        "regulatory_authorization",
        [
            _control(
                "Official authorization evidence",
                bool(authorizations),
                f"{len(authorizations)} approved authorization record(s)",
                "Import an authentic regulator-issued authorization.",
            ),
            _control(
                "Authorization source type",
                bool(authorizations)
                and all(
                    item["source_type"] == "regulatory_authorization" for item in authorizations
                ),
                "Regulatory authorization records",
                "Use official authorization or clearance documents.",
            ),
            _control(
                "Authority and number",
                bool(authorizations)
                and all(
                    item["metadata"].get("authority")
                    and item["metadata"].get("authorization_number")
                    for item in authorizations
                ),
                "Authority and authorization number recorded",
                "Record the authority and authorization/clearance number.",
            ),
            _control(
                "Active and intended-use matched",
                bool(authorizations)
                and all(
                    str(item["metadata"].get("authorization_status", "")).lower() == "active"
                    and _truthy(item["metadata"].get("intended_use_match"))
                    for item in authorizations
                ),
                "Active intended-use match",
                "Verify active status and exact intended-use alignment.",
            ),
            _control(
                "Jurisdiction coverage",
                bool(authorizations)
                and all(bool(item.get("jurisdiction")) for item in authorizations),
                "Jurisdiction recorded",
                "Record each authorization jurisdiction.",
            ),
        ],
    )

    patient = by_domain["approved_patient_care_use"]
    r8 = _rating(
        "approved_patient_care_use",
        [
            _control(
                "Institutional deployment evidence",
                bool(patient),
                f"{len(patient)} approved deployment record(s)",
                "Import authorized institutional deployment evidence.",
            ),
            _control(
                "Institutional approval",
                bool(patient)
                and all(
                    _truthy(item["metadata"].get("institutional_approval")) for item in patient
                ),
                "Institutional approval recorded",
                "Obtain institutional governance/clinical approval.",
            ),
            _control(
                "Documented real use",
                bool(patient)
                and all(
                    _num(item["metadata"].get("deployed_site_count")) >= 1
                    and _num(item["metadata"].get("use_count")) > 0
                    for item in patient
                ),
                "Sites and use counts recorded",
                "Document authorized real-world use at one or more sites.",
            ),
            _control(
                "Human oversight and trained users",
                bool(patient)
                and all(
                    _truthy(item["metadata"].get("human_oversight"))
                    and _num(item["metadata"].get("authorized_user_count")) > 0
                    for item in patient
                ),
                "Human oversight and users recorded",
                "Ensure trained authorized users and documented human oversight.",
            ),
            _control(
                "Authorization dependency",
                r7.score == 10.0 and no_open_major,
                f"authorization={r7.score:.1f}/10; quality_clear={no_open_major}",
                "Complete regulatory authorization and resolve major/critical quality events.",
            ),
        ],
    )

    post_market = by_domain["post_market_clinical_evidence"]
    r9 = _rating(
        "post_market_clinical_evidence",
        [
            _control(
                "Post-market report",
                bool(post_market),
                f"{len(post_market)} approved report(s)",
                "Import an approved post-market or real-world performance report.",
            ),
            _control(
                "Monitoring duration",
                bool(post_market)
                and all(
                    _num(item["metadata"].get("monitoring_months")) >= 6 for item in post_market
                ),
                "At least 6 months",
                "Complete a meaningful post-market monitoring period.",
            ),
            _control(
                "Real-use denominator",
                bool(post_market)
                and all(_num(item["metadata"].get("cases_or_uses")) > 0 for item in post_market),
                "Case/use denominator recorded",
                "Record the monitored case or use denominator.",
            ),
            _control(
                "Drift and safety surveillance",
                bool(post_market)
                and all(
                    _truthy(item["metadata"].get("drift_monitoring"))
                    and _truthy(item["metadata"].get("safety_reporting"))
                    for item in post_market
                ),
                "Drift and safety monitoring active",
                "Operate model drift, complaint and safety-event surveillance.",
            ),
            _control(
                "Periodic review and event closure",
                bool(post_market)
                and all(
                    _truthy(item["metadata"].get("periodic_review_approved"))
                    and _num(item["metadata"].get("unresolved_critical_events")) == 0
                    for item in post_market
                ),
                "Periodic review approved; no unresolved critical events",
                "Approve periodic review and close critical events.",
            ),
        ],
    )

    ratings = (r1, r2, r3, r4, r5, r6, r7, r8, r9)
    score = round(sum(item.score for item in ratings) / len(ratings), 1)
    domains_at_10 = sum(item.score == 10.0 for item in ratings)
    blockers = tuple(f"{item.label}: {blocker}" for item in ratings for blocker in item.blockers)
    release_eligible = domains_at_10 == len(ratings) and program["status"] == "completed"
    permitted_claim = (
        "Real external validation evidence is complete for the documented intended use; "
        "jurisdiction-specific legal and regulatory scope still governs use."
        if release_eligible
        else "Research/demo use only; real clinical, pharma, regulatory and patient-care claims remain blocked."
    )
    return RealExternalValidationReport(
        program_id=program_id,
        actual_external_validation_score=score,
        domains_at_10=domains_at_10,
        total_domains=len(ratings),
        authentic_artifact_count=len(valid),
        excluded_artifact_count=len(excluded),
        release_eligible=release_eligible,
        permitted_claim=permitted_claim,
        ratings=ratings,
        blockers=blockers,
        boundary=(
            "A 10/10 domain requires authentic, independently verified, checksum-valid evidence. "
            "Software controls, blank templates, test fixtures, synthetic datasets and self-attestation "
            "never increase the real external-validation score."
        ),
    )


FRAMEWORK_ASSETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "External evidence registry",
        "src/biointel/clinical/external_evidence.py",
        (
            "register_external_validation_artifact",
            "review_external_validation_artifact",
            "test_fixture",
        ),
    ),
    (
        "Nine-domain authentic scorecard",
        "src/biointel/clinical/external_readiness.py",
        (
            "independent_clinical_evidence",
            "regulatory_authorization",
            "post_market_clinical_evidence",
        ),
    ),
    (
        "Controlled database schema",
        "src/biointel/clinical/schema.py",
        ("external_validation_artifacts", "verification_method"),
    ),
    (
        "External validation center",
        "pages/91_Real_External_Validation_Center.py",
        ("Real External Validation Center", "Authentic score"),
    ),
    (
        "Policy and claim blockers",
        "config/real_external_validation_policy.yaml",
        ("test_fixtures_never_score", "patient_care_claim"),
    ),
    (
        "Execution guide",
        "docs/REAL_EXTERNAL_VALIDATION_EXECUTION_GUIDE.md",
        ("independent organizations", "regulatory authorization"),
    ),
    (
        "Controlled template pack",
        "data/external_validation/templates/01_INDEPENDENT_CLINICAL_EVIDENCE_CHECKLIST.md",
        ("Independent Clinical Evidence", "External identifier"),
    ),
    (
        "Qualification tests",
        "tests/test_step84_real_external_validation.py",
        ("test_blank_program_scores_zero", "test_complete_authentic_fixture_scores_ten"),
    ),
    (
        "Qualification command",
        "scripts/qualify_step84_real_external_validation.py",
        ("build_real_external_validation_framework_readiness", "actual_external_validation_score"),
    ),
    (
        "Checksum dossier integration",
        "src/biointel/clinical/dossier.py",
        ("external_artifacts", "verify_external_artifact_integrity"),
    ),
)


def build_real_external_validation_framework_readiness(root: str | Path) -> dict[str, Any]:
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
    passed = sum(item["passed"] for item in checks)
    return {
        "schema": "biointel.real-external-validation-framework-readiness.v1",
        "score": round(10 * passed / len(checks), 1),
        "passed": passed,
        "total": len(checks),
        "complete": passed == len(checks),
        "checks": checks,
        "actual_external_validation_status": "evidence-driven; no bundled real-world claim",
        "boundary": (
            "Framework readiness can be 10/10 without real external validation. Actual domain scores "
            "remain zero until authentic independently verified evidence is imported and approved."
        ),
    }
