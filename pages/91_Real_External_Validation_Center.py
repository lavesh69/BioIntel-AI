from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.clinical import (  # noqa: E402
    EXTERNAL_VALIDATION_DOMAINS,
    SOURCE_TYPES,
    VERIFICATION_METHODS,
    ClinicalValidationRegistry,
    build_real_external_validation_framework_readiness,
    evaluate_real_external_validation,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import render_upload_preflight  # noqa: E402

st.set_page_config(
    page_title="Real External Validation · BioIntel AI",
    page_icon="🌍",
    layout="wide",
)
apply_theme()

DB_PATH = ROOT / "data" / "clinical_pharma" / "clinical_validation.sqlite3"
registry = ClinicalValidationRegistry(DB_PATH)
framework = build_real_external_validation_framework_readiness(ROOT)


def _refresh() -> None:
    st.cache_data.clear()
    st.rerun()


def _default_metadata(domain: str) -> dict[str, object]:
    defaults: dict[str, dict[str, object]] = {
        "independent_clinical_evidence": {
            "study_type": "clinical",
            "final_report": True,
            "negative_results_reported": True,
        },
        "prospective_clinical_study": {
            "prospective": True,
            "preregistered": True,
            "primary_endpoint_met": True,
        },
        "pharma_laboratory_validation": {
            "assay_validated": True,
            "replication_complete": True,
            "raw_data_available": True,
        },
        "peer_reviewed_publication": {
            "peer_reviewed": True,
            "publication_status": "published",
            "limitations_reported": True,
        },
        "gxp_operating_history": {
            "duration_months": 12,
            "quality_system": "GCP",
            "audit_complete": True,
        },
        "regulatory_inspection": {
            "authority": "",
            "outcome": "acceptable",
            "critical_findings_open": 0,
        },
        "regulatory_authorization": {
            "authority": "",
            "authorization_number": "",
            "authorization_status": "active",
            "intended_use_match": True,
        },
        "approved_patient_care_use": {
            "institutional_approval": True,
            "deployed_site_count": 1,
            "use_count": 1,
            "authorized_user_count": 1,
            "human_oversight": True,
        },
        "post_market_clinical_evidence": {
            "monitoring_months": 6,
            "cases_or_uses": 1,
            "drift_monitoring": True,
            "safety_reporting": True,
            "periodic_review_approved": True,
            "unresolved_critical_events": 0,
        },
    }
    return defaults[domain]


programs = registry.list_programs()
hero(
    "Real External Validation Center",
    "Import, independently verify and score authentic clinical, pharmaceutical, publication, inspection, authorization, patient-use and post-market evidence. Test fixtures and self-attestation never increase the real score.",
    eyebrow="Step 84 · evidence-driven claims · nine independent domains",
    chips=[
        f"Framework {framework['score']:.1f}/10",
        "Checksum-bound artifacts",
        "Independent reviewer separation",
        "Strict research-only fallback",
    ],
)
scientific_boundary_banner(
    source_kind="external_evidence",
    release_eligible=False,
    message=(
        "A 10/10 software framework does not equal a 10/10 clinical claim. Actual scores rise only "
        "after authentic external documents are uploaded, hash-verified, independently reviewed and "
        "matched to completed real-world milestones."
    ),
)

if not programs:
    st.info(
        "Create a validation program in Clinical & Pharma Validation before registering evidence."
    )
    st.stop()

program_id = st.selectbox(
    "Validation program",
    [item["program_id"] for item in programs],
    format_func=lambda identifier: next(
        f"{item['title']} · {item['status']}"
        for item in programs
        if item["program_id"] == identifier
    ),
)
snapshot = registry.snapshot(program_id)
report = evaluate_real_external_validation(registry, program_id)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Execution framework", f"{framework['score']:.1f}/10")
m2.metric("Authentic score", f"{report.actual_external_validation_score:.1f}/10")
m3.metric("Domains at 10/10", f"{report.domains_at_10}/{report.total_domains}")
m4.metric("Real validated-use gate", "PASS" if report.release_eligible else "BLOCKED")
insight_callout(
    "Permitted claim",
    report.permitted_claim,
    icon="🛡️",
    tone="success" if report.release_eligible else "warning",
)

score_tab, register_tab, review_tab, integrity_tab = st.tabs(
    [
        "Nine-domain ratings",
        "Register authentic evidence",
        "Independent review",
        "Integrity & export",
    ]
)

with score_tab:
    section_title("Real external validation ratings", "📊")
    smart_dataframe(
        [
            {
                "Domain": item.label,
                "Score": item.score,
                "Controls": f"{item.passed_controls}/{item.total_controls}",
                "Status": item.status,
                "Next blocker": item.blockers[0] if item.blockers else "None",
            }
            for item in report.ratings
        ],
        height=480,
        key="real_external_validation_ratings",
    )
    with st.expander("Detailed evidence and blockers"):
        for item in report.ratings:
            st.markdown(f"### {item.label} — {item.score:.1f}/10")
            if item.evidence:
                st.success("\n\n".join(item.evidence))
            if item.blockers:
                st.warning("\n\n".join(item.blockers))
    st.caption(report.boundary)

with register_tab:
    section_title("Register an external evidence artifact", "📥")
    domain = st.selectbox(
        "Validation domain",
        list(EXTERNAL_VALIDATION_DOMAINS),
        format_func=lambda key: EXTERNAL_VALIDATION_DOMAINS[key],
    )
    with st.form("register_external_artifact"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Artifact title")
        organization = c2.text_input("Issuing/source organization")
        c3, c4 = st.columns(2)
        source_type = c3.selectbox("Source type", sorted(SOURCE_TYPES))
        external_identifier = c4.text_input(
            "Official external identifier",
            help="Trial ID, DOI, PubMed ID, inspection reference, authorization number or issuer record ID.",
        )
        c5, c6 = st.columns(2)
        jurisdiction = c5.text_input("Jurisdiction")
        issued_at = c6.text_input("Issued at (ISO 8601)", value="2026-07-08T00:00:00+05:30")
        c7, c8 = st.columns(2)
        source_url = c7.text_input("Official source URL or registry location")
        expires_at = c8.text_input("Expiry (optional ISO 8601)")
        submitter = st.text_input("Submitter identity", value="evidence-custodian")
        independent = st.checkbox("Source is independent from BioIntel/model sponsor", value=True)
        test_fixture = st.checkbox(
            "Software test fixture only",
            value=False,
            help="Test fixtures are always excluded from the authentic score.",
        )
        metadata_text = st.text_area(
            "Domain metadata (JSON)",
            value=json.dumps(_default_metadata(domain), indent=2),
            height=220,
        )
        uploaded = st.file_uploader("Evidence document or controlled record")
        render_upload_preflight(
            uploaded, key="real_external_evidence", soft_limit_mb=100, hard_limit_mb=500
        )
        register_submit = st.form_submit_button("Register checksum-bound evidence", type="primary")
    if register_submit:
        try:
            metadata = json.loads(metadata_text)
            if not isinstance(metadata, dict):
                raise ValueError("Metadata must be a JSON object")
            if uploaded is None:
                raise ValueError("Evidence file is required")
            registry.register_external_validation_artifact(
                program_id=program_id,
                domain=domain,
                title=title,
                source_organization=organization,
                source_type=source_type,
                external_identifier=external_identifier,
                content=uploaded.getvalue(),
                original_filename=uploaded.name,
                mime_type=uploaded.type or "application/octet-stream",
                issued_at=issued_at,
                expires_at=expires_at,
                submitted_by=submitter,
                independent=independent,
                jurisdiction=jurisdiction,
                source_url=source_url,
                metadata=metadata,
                test_fixture=test_fixture,
            )
            st.success(
                "External evidence registered. It will not score until independent approval."
            )
            _refresh()
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            st.error(str(exc))

with review_tab:
    section_title("External evidence register", "🔎")
    artifacts = snapshot.get("external_artifacts", [])
    smart_dataframe(
        [
            {
                "ID": item["artifact_id"],
                "Domain": EXTERNAL_VALIDATION_DOMAINS.get(item["domain"], item["domain"]),
                "Title": item["title"],
                "Organization": item["source_organization"],
                "Identifier": item["external_identifier"],
                "Status": item["status"],
                "Test fixture": item["test_fixture"],
                "Submitted by": item["submitted_by"],
                "Verified by": item["verified_by"],
            }
            for item in artifacts
        ],
        height=400,
        key="external_artifact_register",
    )
    reviewable = [item for item in artifacts if item["status"] == "submitted"]
    if reviewable:
        with st.form("review_external_artifact"):
            artifact_id = st.selectbox(
                "Submitted artifact", [item["artifact_id"] for item in reviewable]
            )
            reviewer = st.text_input("Independent reviewer", value="independent-quality-reviewer")
            status = st.selectbox("Disposition", ["approved", "rejected"])
            method = st.selectbox("Verification method", sorted(VERIFICATION_METHODS))
            notes = st.text_area("Verification notes")
            review_submit = st.form_submit_button("Apply controlled review")
        if review_submit:
            try:
                registry.review_external_validation_artifact(
                    artifact_id,
                    reviewer=reviewer,
                    status=status,
                    verification_method=method,
                    notes=notes,
                )
                st.success("Controlled evidence review recorded.")
                _refresh()
            except (ValueError, KeyError) as exc:
                st.error(str(exc))
    else:
        st.info("No submitted artifacts are awaiting review.")

with integrity_tab:
    section_title("Artifact integrity", "🔐")
    integrity_rows = []
    for item in snapshot.get("external_artifacts", []):
        integrity = registry.verify_external_artifact_integrity(item["artifact_id"])
        integrity_rows.append(
            {
                "Artifact": item["artifact_id"],
                "Valid": integrity["valid"],
                "Expected size": integrity["expected_size"],
                "Actual size": integrity["actual_size"],
                "SHA-256": integrity["actual_sha256"],
            }
        )
    smart_dataframe(integrity_rows, height=360, key="external_artifact_integrity")
    st.download_button(
        "Download current scorecard JSON",
        data=json.dumps(report.to_dict(), indent=2, sort_keys=True),
        file_name=f"{program_id}_real_external_validation_scorecard.json",
        mime="application/json",
        width="stretch",
    )

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
