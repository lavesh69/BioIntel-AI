from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.clinical import (  # noqa: E402
    CLAIM_PROFILES,
    ClinicalValidationRegistry,
    build_validation_dossier,
    evaluate_clinical_pharma_readiness,
    verify_validation_dossier,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import (  # noqa: E402
    MAX_UPLOAD_BYTES,
    profile_streamlit_upload,
    stage_streamlit_upload,
)

st.set_page_config(
    page_title="Clinical & Pharma Validation · BioIntel AI",
    page_icon="🏥",
    layout="wide",
)
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('clinical_pharma_validation', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'clinical_pharma_validation', expanded=False)
# STEP178_19_MODULE_CLINICAL_OPERATIONAL_PRIVACY_ML_ASSURANCE
from biointel.target_modules_v178.ui import render_step178_module_upgrade
render_step178_module_upgrade('clinical_pharma_validation', expanded=False)


DB_PATH = ROOT / "data" / "clinical_pharma" / "clinical_validation.sqlite3"
DOSSIER_DIR = ROOT / "reports" / "generated" / "clinical_pharma"
registry = ClinicalValidationRegistry(DB_PATH)


def _safe_artifact_name(value: str, prefix: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value or f"{prefix}.bin").name)
    name = name.strip("._")[:120]
    return name or f"{prefix}.bin"


def _save_upload(uploaded: object, prefix: str) -> Path:
    """Stream an artifact to the local dossier without a full-memory copy."""

    profile = profile_streamlit_upload(
        uploaded, soft_limit_mb=100, hard_limit_mb=1024
    )
    if not profile.allowed:
        raise ValueError("The uploaded artifact has an invalid file signature.")
    if not profile.within_hard_limit:
        raise ValueError("Each validation artifact must be 1 GB or smaller.")
    if profile.size_bytes <= 0:
        raise ValueError(f"{prefix} upload is empty.")
    digest_prefix = profile.sha256[:16] or "pending_hash"
    name = _safe_artifact_name(str(getattr(uploaded, "name", "")), prefix)
    target = DOSSIER_DIR / "uploads" / f"{prefix}_{digest_prefix}_{name}"
    staged = stage_streamlit_upload(uploaded, target, max_bytes=MAX_UPLOAD_BYTES)
    if profile.sha256 and staged["sha256"] != profile.sha256:
        raise ValueError("Artifact changed during staged upload; please upload it again.")
    return target


def _refresh() -> None:
    st.cache_data.clear()
    st.rerun()


programs = registry.list_programs()
hero(
    "Clinical & Pharmaceutical Validation Center",
    "Execute a controlled validation program from intended-use definition through independent sites, immutable model freeze, prospective prediction locking, evidence review, CAPA and checksum-bound dossier release.",
    eyebrow="Validation execution system · strict claim blocking · authentic evidence required",
    chips=[
        f"{len(programs)} validation program(s)",
        "Tamper-evident audit chain",
        "Prospective prediction lock",
        "Signed evidence dossier",
    ],
)
scientific_boundary_banner(
    source_kind="mixed_evidence",
    release_eligible=False,
    message=(
        "The software framework is validation-ready, but BioIntel AI is not automatically clinically or pharmaceutically validated. "
        "Validated-use claims remain blocked until authentic independent, prospective, quality-reviewed evidence satisfies every gate."
    ),
)

with st.expander("Create a controlled validation program", expanded=not programs):
    with st.form("create_validation_program"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Program title", value="BioIntel prospective validation program")
        profile = c2.selectbox(
            "Claim profile",
            options=list(CLAIM_PROFILES),
            format_func=lambda key: CLAIM_PROFILES[key]["label"],
        )
        intended_use = st.text_area(
            "Intended use",
            value="Research prioritization and pharmaceutical R&D decision support under qualified human review.",
        )
        decision_context = st.text_input(
            "Decision context", value="Preclinical evidence prioritization"
        )
        target_population = st.text_input(
            "Target population / sample domain", value="Define assay/sample population"
        )
        c3, c4 = st.columns(2)
        jurisdictions = c3.text_input(
            "Jurisdictions (comma separated)", value="India, United States, European Union"
        )
        risk = c4.text_input("Risk classification", value="gxp_relevant_r_and_d")
        prohibited = st.text_area(
            "Prohibited uses (one per line)",
            value="Autonomous diagnosis\nAutonomous treatment selection\nUnsupported clinical release",
        )
        c5, c6 = st.columns(2)
        owner = c5.text_input("Program owner", value="program-owner")
        quality_owner = c6.text_input("Independent quality owner", value="quality-owner")
        create_submit = st.form_submit_button("Create controlled program", type="primary")
    if create_submit:
        registry.create_program(
            title=title,
            claim_profile=profile,
            intended_use=intended_use,
            decision_context=decision_context,
            target_population=target_population,
            jurisdictions=[item.strip() for item in jurisdictions.split(",") if item.strip()],
            risk_classification=risk,
            prohibited_uses=[item.strip() for item in prohibited.splitlines() if item.strip()],
            owner=owner,
            quality_owner=quality_owner,
            actor=owner,
        )
        _refresh()

if not programs:
    render_phase108_visual_suite("clinical_validation", ROOT, context=locals())
    st.info("Create a controlled validation program to begin.")
    st.stop()

selected_program_id = st.selectbox(
    "Active validation program",
    options=[item["program_id"] for item in programs],
    format_func=lambda identifier: next(
        f"{item['title']} · {item['status']} · {item['claim_profile']}"
        for item in programs
        if item["program_id"] == identifier
    ),
)
snapshot = registry.snapshot(selected_program_id)
report = evaluate_clinical_pharma_readiness(registry, selected_program_id)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Control readiness", f"{report.control_readiness_score:.1f}/10")
m2.metric("External evidence", f"{report.external_evidence_score:.1f}/10")
m3.metric("Combined readiness", f"{report.total_score:.1f}/10")
m4.metric("Validated-use gate", "PASS" if report.release_eligible else "BLOCKED")
insight_callout(
    "Permitted claim",
    report.permitted_claim,
    icon="🛡️",
    tone="success" if report.release_eligible else "warning",
)

(
    overview_tab,
    site_tab,
    protocol_tab,
    prospective_tab,
    evidence_tab,
    dossier_tab,
) = st.tabs(
    [
        "Readiness gates",
        "Program & sites",
        "Protocol & freeze",
        "Prospective execution",
        "Evidence & quality",
        "Dossier & approval",
    ]
)

with overview_tab:
    section_title("Claim-specific validation gates", "🚦")
    smart_dataframe(
        [
            {
                "Gate": gate.gate_id,
                "Domain": gate.domain,
                "Requirement": gate.label,
                "Status": "Pass" if gate.passed else "Blocked",
                "Evidence": gate.evidence,
                "External": gate.external,
                "Remediation": gate.remediation,
            }
            for gate in report.gates
        ],
        height=620,
        key="clinical_pharma_gate_overview",
    )
    st.caption(report.boundary)

with site_tab:
    section_title("Program lifecycle", "🗂️")
    with st.form("program_status"):
        status = st.selectbox(
            "Program status",
            sorted(ClinicalValidationRegistry.PROGRAM_STATUSES),
            index=sorted(ClinicalValidationRegistry.PROGRAM_STATUSES).index(
                snapshot["program"]["status"]
            ),
        )
        reason = st.text_input("Controlled reason", value="Approved lifecycle transition")
        status_submit = st.form_submit_button("Update program status")
    if status_submit:
        registry.set_program_status(
            selected_program_id, status, actor="validation-admin", reason=reason
        )
        _refresh()

    section_title("Independent validation sites", "🏢")
    smart_dataframe(snapshot["sites"], height=260, key="clinical_sites")
    with st.form("register_site"):
        s1, s2, s3 = st.columns(3)
        site_name = s1.text_input("Site name")
        organization = s2.text_input("Organization")
        country = s3.text_input("Country", value="India")
        s4, s5, s6 = st.columns(3)
        independent = s4.checkbox("Independent from sponsor", value=True)
        investigator = s5.text_input("Principal investigator")
        qa_contact = s6.text_input("QA contact")
        accreditation = st.text_input("Laboratory accreditation / qualification reference")
        site_submit = st.form_submit_button("Register site")
    if site_submit:
        registry.register_site(
            program_id=selected_program_id,
            site_name=site_name,
            organization=organization,
            country=country,
            independent=independent,
            principal_investigator=investigator,
            qa_contact=qa_contact,
            laboratory_accreditation=accreditation,
            actor="site-manager",
        )
        _refresh()
    registered_sites = [item for item in snapshot["sites"] if item["status"] != "qualified"]
    if registered_sites:
        site_to_qualify = st.selectbox(
            "Site awaiting qualification",
            [item["site_id"] for item in registered_sites],
            format_func=lambda identifier: next(
                item["site_name"] for item in registered_sites if item["site_id"] == identifier
            ),
        )
        if st.button("Qualify selected site"):
            registry.qualify_site(
                site_to_qualify,
                actor="independent-quality-owner",
                reason="Documented site qualification approved",
            )
            _refresh()

with protocol_tab:
    section_title("Controlled validation protocol", "📋")
    smart_dataframe(snapshot["protocols"], height=260, key="clinical_protocols")
    with st.form("create_protocol"):
        p1, p2 = st.columns(2)
        protocol_id = p1.text_input("Protocol ID", value="PROT-001")
        protocol_title = p2.text_input("Protocol title", value="Independent prospective validation")
        primary_endpoint = st.text_input("Primary endpoint", value="Balanced accuracy")
        success_criterion = st.text_input(
            "Success criterion", value=">=0.70 with lower 95% CI >=0.65"
        )
        p3, p4 = st.columns(2)
        sample_size = p3.number_input("Planned sample size", min_value=1, value=100)
        preregistration = p4.text_input("Preregistration reference")
        ethics = st.text_input("Ethics / regulatory determination reference")
        statistical_plan = st.text_area(
            "Statistical analysis plan",
            value="95% confidence intervals, calibration, per-site and subgroup analysis",
        )
        dmp = st.text_area(
            "Data management plan", value="Blinded sample codes and controlled reconciliation"
        )
        protocol_submit = st.form_submit_button("Create protocol")
    if protocol_submit:
        registry.create_protocol(
            program_id=selected_program_id,
            protocol_id=protocol_id,
            title=protocol_title,
            primary_endpoint=primary_endpoint,
            success_criterion=success_criterion,
            sample_size=int(sample_size),
            statistical_plan=statistical_plan,
            preregistration_reference=preregistration,
            ethics_reference=ethics,
            data_management_plan=dmp,
            payload={"negative_results_reported": True},
            actor="protocol-author",
        )
        _refresh()
    draft_protocols = [item for item in snapshot["protocols"] if item["status"] == "draft"]
    if draft_protocols:
        protocol_to_approve = st.selectbox(
            "Protocol awaiting approval",
            [item["protocol_version_id"] for item in draft_protocols],
        )
        if st.button("Approve selected protocol"):
            registry.approve_protocol(
                protocol_to_approve,
                approver="independent-quality-owner",
                reason="Approved before model/data freeze",
            )
            _refresh()

    section_title("Immutable model configuration freeze", "🧊")
    st.caption(
        "Each validation artifact supports up to 1 GB. Files are streamed into the local controlled dossier, not copied into the browser page's working memory."
    )
    approved_protocols = [item for item in snapshot["protocols"] if item["status"] == "approved"]
    with st.form("freeze_model"):
        freeze_protocol = st.selectbox(
            "Approved protocol version",
            [item["protocol_version_id"] for item in approved_protocols],
            disabled=not approved_protocols,
        )
        model_id = st.text_input("Model ID", value="BIOINTEL-MODEL-001")
        model_file = st.file_uploader("Model artifact", key="freeze_model_file")
        dataset_file = st.file_uploader("Frozen dataset manifest", key="freeze_dataset_file")
        code_file = st.file_uploader("Code/release manifest", key="freeze_code_file")
        environment_file = st.file_uploader("Environment lock", key="freeze_env_file")
        feature_file = st.file_uploader("Feature specification", key="freeze_feature_file")
        freeze_submit = st.form_submit_button("Freeze model configuration")
    if freeze_submit:
        uploads = [model_file, dataset_file, code_file, environment_file, feature_file]
        if not approved_protocols or not all(uploads):
            st.error("Approved protocol and all five frozen artifacts are required.")
        else:
            try:
                with st.spinner("Streaming frozen artifacts into the controlled local dossier…"):
                    paths = [_save_upload(item, f"freeze_{index}") for index, item in enumerate(uploads)]
                registry.freeze_model(
                    program_id=selected_program_id,
                    protocol_version_id=freeze_protocol,
                    model_id=model_id,
                    model_path=paths[0],
                    dataset_path=paths[1],
                    code_path=paths[2],
                    environment_path=paths[3],
                    feature_spec_path=paths[4],
                    intended_use=snapshot["program"]["intended_use"],
                    actor="model-custodian",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Model freeze was not recorded: {exc}")
            else:
                _refresh()

with prospective_tab:
    section_title("Prospective predictions before outcomes", "🔒")
    st.caption("Artifact files are accepted up to 1 GB and streamed to local controlled storage before their checksum is registered.")
    smart_dataframe(snapshot["prediction_batches"], height=240, key="prediction_batches")
    qualified_sites = [item for item in snapshot["sites"] if item["status"] == "qualified"]
    freezes = [item for item in snapshot["model_freezes"] if item["status"] == "locked"]
    with st.form("lock_prediction_batch"):
        pr1, pr2 = st.columns(2)
        freeze_id = pr1.selectbox(
            "Locked model freeze",
            [item["freeze_id"] for item in freezes],
            disabled=not freezes,
        )
        prediction_site = pr2.selectbox(
            "Qualified site",
            [item["site_id"] for item in qualified_sites],
            disabled=not qualified_sites,
        )
        batch_label = st.text_input("Batch label", value="PROSPECTIVE-BATCH-001")
        prediction_count = st.number_input("Sample count", min_value=1, value=50)
        prediction_upload = st.file_uploader("Blinded predictions", key="prediction_upload")
        prediction_submit = st.form_submit_button("Lock prediction batch")
    if prediction_submit:
        if not freezes or not qualified_sites or prediction_upload is None:
            st.error("A locked freeze, qualified site and prediction file are required.")
        else:
            try:
                registry.lock_prediction_batch(
                    program_id=selected_program_id,
                    freeze_id=freeze_id,
                    site_id=prediction_site,
                    batch_label=batch_label,
                    predictions_path=_save_upload(prediction_upload, "predictions"),
                    sample_count=int(prediction_count),
                    blinded=True,
                    sample_code_scheme="Opaque site-generated identifiers",
                    actor="prediction-custodian",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Prediction batch was not locked: {exc}")
            else:
                _refresh()

    section_title("Outcome reconciliation", "🧾")
    unmatched = [
        item
        for item in snapshot["prediction_batches"]
        if item["batch_id"]
        not in {outcome["prediction_batch_id"] for outcome in snapshot["outcome_batches"]}
    ]
    with st.form("register_outcomes"):
        outcome_prediction = st.selectbox(
            "Locked prediction batch",
            [item["batch_id"] for item in unmatched],
            disabled=not unmatched,
        )
        outcome_upload = st.file_uploader("Adjudicated outcomes", key="outcome_upload")
        endpoint = st.text_input("Endpoint name", value="Balanced accuracy")
        outcome_submit = st.form_submit_button("Register outcome batch")
    if outcome_submit:
        if not unmatched or outcome_upload is None:
            st.error("An unmatched prediction batch and outcome file are required.")
        else:
            try:
                selected = next(item for item in unmatched if item["batch_id"] == outcome_prediction)
                registry.register_outcome_batch(
                    program_id=selected_program_id,
                    prediction_batch_id=outcome_prediction,
                    outcomes_path=_save_upload(outcome_upload, "outcomes"),
                    sample_count=int(selected["sample_count"]),
                    endpoint_name=endpoint,
                    adjudicated=True,
                    actor="outcome-custodian",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Outcome batch was not registered: {exc}")
            else:
                _refresh()

    section_title("Predefined statistical result", "📈")
    with st.form("analysis_result"):
        ar1, ar2, ar3 = st.columns(3)
        result_scope = ar1.selectbox("Scope", ["primary", "site", "subgroup", "sensitivity"])
        result_protocol = ar2.selectbox(
            "Protocol",
            [item["protocol_version_id"] for item in approved_protocols],
            disabled=not approved_protocols,
        )
        result_site = ar3.selectbox(
            "Site (for site result)",
            [""] + [item["site_id"] for item in qualified_sites],
        )
        metric_name = st.text_input("Metric", value="balanced_accuracy")
        a1, a2, a3 = st.columns(3)
        metric_value = a1.number_input("Value", value=0.75, format="%.4f")
        lower_ci = a2.number_input("Lower CI", value=0.66, format="%.4f")
        upper_ci = a3.number_input("Upper CI", value=0.84, format="%.4f")
        criterion = st.text_input("Success criterion", value=">=0.70")
        passed = st.checkbox("Predefined criterion passed", value=True)
        analysis_file = st.file_uploader("Statistical analysis output", key="analysis_file")
        analysis_submit = st.form_submit_button("Submit analysis result")
    if analysis_submit:
        if not approved_protocols or analysis_file is None:
            st.error("Approved protocol and analysis output are required.")
        else:
            try:
                registry.record_analysis_result(
                    program_id=selected_program_id,
                    protocol_version_id=result_protocol,
                    result_scope=result_scope,
                    site_id=result_site or None,
                    metric_name=metric_name,
                    metric_value=float(metric_value),
                    lower_ci=float(lower_ci),
                    upper_ci=float(upper_ci),
                    success_criterion=criterion,
                    passed=passed,
                    analysis_content=None,
                    analysis_path=_save_upload(analysis_file, "analysis"),
                    analyst="independent-statistician",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Analysis result was not recorded: {exc}")
            else:
                _refresh()
    pending_results = [
        item for item in snapshot["analysis_results"] if item["status"] == "submitted"
    ]
    if pending_results:
        result_to_review = st.selectbox(
            "Analysis result awaiting independent review",
            [item["analysis_result_id"] for item in pending_results],
        )
        if st.button("Approve selected statistical result"):
            registry.review_analysis_result(
                result_to_review,
                reviewer="independent-quality-reviewer",
                status="approved",
                reason="Predefined result and confidence interval independently reviewed",
            )
            _refresh()

with evidence_tab:
    section_title("Authentic evidence registry", "🔬")
    st.caption("Evidence and training artifacts use the same 1 GB streamed local-dossier boundary; their hashes are recorded, never treated as proof of external validation by themselves.")
    smart_dataframe(snapshot["evidence_items"], height=260, key="clinical_evidence")
    required_categories = CLAIM_PROFILES[snapshot["program"]["claim_profile"]][
        "required_evidence_categories"
    ]
    with st.form("add_evidence"):
        category = st.selectbox(
            "Evidence category",
            list(required_categories)
            or ["assay_validation", "model_validation", "quality_assurance"],
        )
        e1, e2 = st.columns(2)
        evidence_type = e1.text_input("Evidence type", value="reviewed_report")
        reference = e2.text_input("Reference / study ID")
        source = st.text_input("Source organization")
        independent_evidence = st.checkbox("Independent from sponsor", value=True)
        evidence_file = st.file_uploader("Evidence file", key="evidence_file")
        evidence_submit = st.form_submit_button("Add evidence")
    if evidence_submit:
        if evidence_file is None:
            st.error("Evidence file is required.")
        else:
            try:
                registry.add_evidence(
                    program_id=selected_program_id,
                    category=category,
                    evidence_type=evidence_type,
                    reference=reference,
                    source_organization=source,
                    independent=independent_evidence,
                    content=None,
                    content_path=_save_upload(evidence_file, "evidence"),
                    owner="evidence-owner",
                    actor="evidence-owner",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Evidence was not registered: {exc}")
            else:
                _refresh()
    submitted_evidence = [
        item for item in snapshot["evidence_items"] if item["status"] == "submitted"
    ]
    if submitted_evidence:
        evidence_to_review = st.selectbox(
            "Evidence awaiting review", [item["evidence_id"] for item in submitted_evidence]
        )
        if st.button("Approve selected evidence"):
            registry.review_evidence(
                evidence_to_review,
                reviewer="independent-quality-reviewer",
                status="approved",
                reason="Authenticity, provenance and applicability reviewed",
            )
            _refresh()

    section_title("Deviation, CAPA and change control", "🛠️")
    smart_dataframe(snapshot["quality_events"], height=220, key="clinical_quality_events")
    with st.form("open_quality_event"):
        q1, q2 = st.columns(2)
        event_type = q1.selectbox(
            "Event type", sorted(ClinicalValidationRegistry.QUALITY_EVENT_TYPES)
        )
        severity = q2.selectbox("Severity", ["minor", "major", "critical"])
        event_title = st.text_input("Title")
        event_description = st.text_area("Description")
        quality_submit = st.form_submit_button("Open quality event")
    if quality_submit:
        registry.open_quality_event(
            program_id=selected_program_id,
            event_type=event_type,
            severity=severity,
            title=event_title,
            description=event_description,
            owner="quality-owner",
            actor="quality-owner",
        )
        _refresh()
    open_events = [item for item in snapshot["quality_events"] if item["status"] != "closed"]
    if open_events:
        with st.form("close_quality_event"):
            event_to_close = st.selectbox(
                "Open event", [item["quality_event_id"] for item in open_events]
            )
            root_cause = st.text_area("Root cause")
            action_plan = st.text_area("Corrective/preventive action")
            effectiveness = st.checkbox("Effectiveness verified")
            close_submit = st.form_submit_button("Close quality event")
        if close_submit:
            registry.close_quality_event(
                event_to_close,
                root_cause=root_cause,
                action_plan=action_plan,
                effectiveness_verified=effectiveness,
                actor="independent-quality-owner",
                reason="Quality disposition completed",
            )
            _refresh()

    section_title("Role-based training", "🎓")
    with st.form("record_training"):
        t1, t2, t3 = st.columns(3)
        person_id = t1.text_input("Person ID")
        role = t2.text_input("Role")
        curriculum = t3.text_input("Curriculum/SOP ID")
        completed = st.text_input("Completed at (ISO 8601)", value="2026-07-08T00:00:00+05:30")
        training_file = st.file_uploader("Training evidence", key="training_file")
        training_submit = st.form_submit_button("Record passed training")
    if training_submit:
        if training_file is None:
            st.error("Training evidence is required.")
        else:
            try:
                registry.record_training(
                    program_id=selected_program_id,
                    person_id=person_id,
                    role_name=role,
                    curriculum_id=curriculum,
                    completed_at=completed,
                    result="passed",
                    evidence=None,
                    evidence_path=_save_upload(training_file, "training"),
                    actor="training-admin",
                )
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                st.error(f"Training record was not saved: {exc}")
            else:
                _refresh()

with dossier_tab:
    section_title("Validation dossier and release authorization", "📦")
    smart_dataframe(
        [
            {
                "Gate": gate.gate_id,
                "Domain": gate.domain,
                "Requirement": gate.label,
                "Status": "Pass" if gate.passed else "Blocked",
                "Evidence": gate.evidence,
            }
            for gate in report.gates
        ],
        height=500,
        key="clinical_pharma_dossier_gates",
    )
    dossier_path = DOSSIER_DIR / f"{selected_program_id}_validation_dossier.zip"
    if st.button("Build checksum-bound validation dossier", type="primary", width="stretch"):
        build_validation_dossier(registry, selected_program_id, dossier_path)
        st.success("Validation dossier generated and verified.")
    if dossier_path.is_file():
        verification = verify_validation_dossier(dossier_path)
        v1, v2, v3 = st.columns(3)
        v1.metric("Dossier integrity", "PASS" if verification["valid"] else "FAIL")
        v2.metric("Verified files", verification["checked_files"])
        v3.metric("Archive size", f"{verification['size_bytes'] / 1024:.1f} KB")
        st.download_button(
            "Download validation dossier",
            data=dossier_path.read_bytes(),
            file_name=dossier_path.name,
            mime="application/zip",
            width="stretch",
        )

    section_title("Electronic release signature", "✍️")
    with st.form("sign_release"):
        signer = st.text_input("Signer identity", value="independent-quality-owner")
        meaning = st.selectbox("Signature meaning", ["Approval", "Authorization", "Review"])
        signature_reason = st.text_area("Reason", value="Validation summary independently reviewed")
        signing_secret = st.text_input("Signing secret (minimum 12 characters)", type="password")
        sign_submit = st.form_submit_button("Sign validation summary")
    if sign_submit:
        summary_digest = hashlib.sha256(str(report.to_dict()).encode()).hexdigest()
        registry.sign_object(
            program_id=selected_program_id,
            object_type="validation_summary_report",
            object_id=f"VSR-{selected_program_id}",
            object_sha256=summary_digest,
            signer=signer,
            meaning=meaning,
            reason=signature_reason,
            signing_secret=signing_secret,
        )
        _refresh()

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("clinical_validation", ROOT, context=locals())

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("clinical_pharma_core", None, key_prefix="step114_clinical_pharma_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("clinical_pharma_validation", expanded=False)


# Step 185 operational assurance panel (synthetic/demo boundary preserved)
try:
    from biointel.operational_assurance_v185.ui import render_step185_operational_assurance as _render_step185_operational_assurance
    _render_step185_operational_assurance("clinical_pharma_validation")
except Exception as _step185_exc:
    try:
        import streamlit as st
        st.info(f"Step 185 assurance panel unavailable: {_step185_exc}")
    except Exception:
        pass

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('clinical_pharma_validation', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('clinical_pharma_validation', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('clinical_pharma_validation', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('clinical_pharma_validation', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('clinical_pharma_validation', expanded=False)
