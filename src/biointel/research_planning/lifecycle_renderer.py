from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
from typing import Any
import zipfile

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import hero, section_title
from biointel.ui.workflow import render_upload_preflight

from .lifecycle_engines import (
    LIFECYCLE_ENGINE_CATALOG,
    LifecycleOutput,
    ethics_consent_workbench,
    fair_data_management_workbench,
    interim_monitoring_safety_workbench,
    publication_dissemination_workbench,
)
from .review_store import PlanningReviewStore
from .digital_thread import ResearchDigitalThreadStore, ThreadLink, ThreadNode

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORE_PATH = PROJECT_ROOT / "UserData" / "research_planning" / "research_planning.sqlite"
THREAD_PATH = PROJECT_ROOT / "UserData" / "research_planning" / "research_digital_thread.sqlite"


MODULE_META: dict[str, dict[str, Any]] = {
    "research_ethics_consent": {
        "title": "Research Ethics, Consent & Participant Protection Studio",
        "summary": "Plan participant protection, consent, privacy, vulnerable-population safeguards and review evidence in one traceable workspace.",
        "icon": "shield",
        "chips": ["Ethics readiness", "Consent coverage", "Privacy", "Vulnerable populations", "Review evidence"],
        "boundary": "This workspace supports planning and gap detection. It does not grant ethics approval, determine legal compliance or replace an ethics committee, institutional review board or qualified privacy review.",
    },
    "research_data_fair_planning": {
        "title": "Research Data Management & FAIR Planning Studio",
        "summary": "Design a durable research data-management plan covering identifiers, metadata, access, formats, retention, repositories, licences and backups.",
        "icon": "database",
        "chips": ["FAIR readiness", "Data stewardship", "Retention", "Repository planning", "Backup controls"],
        "boundary": "FAIR and data-management scores are planning indicators. Repository acceptance, legal access conditions and organisation-specific retention requirements remain external decisions.",
    },
    "research_interim_monitoring_safety": {
        "title": "Data Monitoring, Interim Review & Safety Studio",
        "summary": "Prepare interim review packages, monitor event rates, surface imbalance signals and track prespecified safety-review triggers.",
        "icon": "activity",
        "chips": ["Interim review", "Safety signals", "Arm comparison", "Thresholds", "Escalation"],
        "boundary": "This module is a planning and review aid. It does not make medical decisions, replace a qualified monitoring committee or independently determine whether a study should continue, pause or stop.",
    },
    "research_publication_dissemination": {
        "title": "Publication, Dissemination & Knowledge Translation Studio",
        "summary": "Plan publications, public summaries, data/code statements, stakeholder communication and accessible research dissemination.",
        "icon": "book-open",
        "chips": ["Publication plan", "Open science", "Audience coverage", "Accessibility", "Knowledge translation"],
        "boundary": "Readiness scores do not guarantee journal acceptance, public impact, policy uptake or intellectual-property clearance. All external submissions require appropriate review.",
    },
}


def starter_frame(module_key: str) -> pd.DataFrame:
    if module_key == "research_ethics_consent":
        return pd.DataFrame([
            {"item_id": "ETH-001", "domain": "Consent", "requirement": "Explain study purpose, procedures, risks, benefits and withdrawal choices in participant-friendly language.", "status": "In review", "risk_level": "High", "vulnerable_group": "All participants", "consent_required": True, "privacy_sensitive": True, "owner": "Ethics lead", "evidence_reference": "Draft consent form v1.2", "consent_version": "1.2", "consent_language": "English", "effective_date": "2026-08-01", "approval_expiry": "2027-07-31", "participant_id": "P001", "consent_option": "Primary study", "consent_decision": "Signed", "signed_date": "2026-08-02", "withdrawal_date": "", "reconsent_due_date": "2027-06-30", "submission_id": "SUB-001", "submission_status": "In review", "submission_date": "2026-07-20", "approval_date": "", "query_id": "Q-001", "query_status": "Open", "query_due_date": "2026-08-10", "withdrawal_scope": "Stop future collection; retain already analysed data", "data_category": "Participant identifiers and outcomes", "data_destination": "Controlled research repository"},
            {"item_id": "ETH-002", "domain": "Privacy", "requirement": "Define data minimisation, pseudonymisation, access roles, transfer safeguards and incident response.", "status": "Draft", "risk_level": "High", "vulnerable_group": "All participants", "consent_required": False, "privacy_sensitive": True, "owner": "Data protection lead", "evidence_reference": "Data flow diagram v0.4", "consent_version": "", "consent_language": "", "effective_date": "", "approval_expiry": "", "participant_id": "", "consent_option": "", "consent_decision": "", "signed_date": "", "withdrawal_date": "", "reconsent_due_date": "", "submission_id": "SUB-001", "submission_status": "In review", "submission_date": "2026-07-20", "approval_date": "", "query_id": "Q-002", "query_status": "Resolved", "query_due_date": "2026-08-05", "withdrawal_scope": "", "data_category": "Pseudonymised research data", "data_destination": "Secure analysis workspace"},
            {"item_id": "ETH-003", "domain": "Safeguards", "requirement": "Document assent, guardian permission, capacity assessment and additional monitoring for vulnerable participants.", "status": "Not started", "risk_level": "Critical", "vulnerable_group": "Vulnerable participants", "consent_required": True, "privacy_sensitive": True, "owner": "", "evidence_reference": "", "consent_version": "1.2", "consent_language": "English", "effective_date": "", "approval_expiry": "", "participant_id": "P002", "consent_option": "Future research use", "consent_decision": "Declined", "signed_date": "2026-08-03", "withdrawal_date": "", "reconsent_due_date": "2026-08-15", "submission_id": "SUB-001", "submission_status": "In review", "submission_date": "2026-07-20", "approval_date": "", "query_id": "Q-003", "query_status": "Open", "query_due_date": "2026-08-01", "withdrawal_scope": "Destroy remaining specimens", "data_category": "Genomic data", "data_destination": "Restricted genomic archive"},
            {"item_id": "ETH-004", "domain": "Compensation", "requirement": "Confirm that reimbursement and compensation are proportionate and do not create undue influence.", "status": "Ready", "risk_level": "Moderate", "vulnerable_group": "All participants", "consent_required": False, "privacy_sensitive": False, "owner": "Operations", "evidence_reference": "Budget section 8", "consent_version": "", "consent_language": "", "effective_date": "", "approval_expiry": "", "participant_id": "", "consent_option": "", "consent_decision": "", "signed_date": "", "withdrawal_date": "", "reconsent_due_date": "", "submission_id": "SUB-001", "submission_status": "In review", "submission_date": "2026-07-20", "approval_date": "", "query_id": "", "query_status": "", "query_due_date": "", "withdrawal_scope": "", "data_category": "", "data_destination": ""},
        ])
    if module_key == "research_data_fair_planning":
        return pd.DataFrame([
            {"asset_id": "DATA-001", "data_type": "Clinical research table", "format": "CSV", "metadata_standard": "Study data dictionary", "persistent_id": "local:study/data-001", "access_level": "Controlled", "retention_years": 10, "repository": "Institutional repository", "licence": "Controlled research use", "owner": "Data steward", "backup_copies": 3, "encryption": "AES-256", "checksum": "sha256:clinical-demo", "checksum_algorithm": "SHA-256", "checksum_verified": True, "format_validated": True, "schema_name": "ClinicalTable-v1", "schema_required_fields": 25, "schema_present_fields": 25, "file_size_mb": 120, "monthly_growth_mb": 20, "deposit_status": "Ready", "access_request_status": "Committee review", "legal_hold": "No", "destruction_date": "2036-07-31", "embargo_until": "2027-01-01", "last_restore_test": "2026-06-01", "data_dictionary_complete": True, "provenance_complete": True, "consent_restriction": "Disease research only", "repository_policy": "Controlled access", "storage_location": "Encrypted primary storage", "backup_location": "Encrypted offsite archive"},
            {"asset_id": "DATA-002", "data_type": "Genomic variants", "format": "VCF", "metadata_standard": "VCF metadata + sample manifest", "persistent_id": "local:study/data-002", "access_level": "Restricted", "retention_years": 10, "repository": "Secure genomic archive", "licence": "Consent-limited use", "owner": "Genomics lead", "backup_copies": 2, "encryption": "AES-256", "checksum": "sha256:variants-demo", "checksum_algorithm": "SHA-256", "checksum_verified": True, "format_validated": True, "schema_name": "VCF-4.3", "schema_required_fields": 12, "schema_present_fields": 11, "file_size_mb": 850, "monthly_growth_mb": 60, "deposit_status": "In preparation", "access_request_status": "Restricted", "legal_hold": "No", "destruction_date": "2036-07-31", "embargo_until": "", "last_restore_test": "2025-01-01", "data_dictionary_complete": False, "provenance_complete": True, "consent_restriction": "No commercial use", "repository_policy": "Managed access", "storage_location": "Genomics vault", "backup_location": "Offsite archive"},
            {"asset_id": "DATA-003", "data_type": "Analysis code", "format": "TXT", "metadata_standard": "README + environment lock", "persistent_id": "", "access_level": "Internal", "retention_years": 7, "repository": "Version-control archive", "licence": "", "owner": "Statistical programmer", "backup_copies": 1, "encryption": "At rest", "checksum": "", "checksum_algorithm": "SHA-256", "checksum_verified": False, "format_validated": False, "schema_name": "", "schema_required_fields": 0, "schema_present_fields": 0, "file_size_mb": 35, "monthly_growth_mb": 5, "deposit_status": "Not started", "access_request_status": "Not applicable", "legal_hold": "No", "destruction_date": "2033-07-31", "embargo_until": "", "last_restore_test": "", "data_dictionary_complete": False, "provenance_complete": False, "consent_restriction": "", "repository_policy": "", "storage_location": "Local repository", "backup_location": ""},
        ])
    if module_key == "research_interim_monitoring_safety":
        return pd.DataFrame([
            {"participant_id": "P001", "arm": "Control", "arm_population": 50, "event_id": "EV-001", "event_type": "Headache", "severity": "Mild", "serious": False, "relatedness": "Unlikely", "event_day": 8, "resolved": True, "reportable": False, "site_id": "SITE-A", "system_organ_class": "Nervous system", "preferred_term": "Headache", "expectedness": "Expected", "treatment_emergent": True, "adverse_event_of_special_interest": False, "action_taken": "None", "outcome": "Recovered", "awareness_date": "2026-07-01", "report_due_date": "2026-07-31", "submitted_date": "2026-07-03", "dose_level": "0", "person_time_days": 60, "followup_days": 60, "information_fraction": 0.5, "efficacy_z": 0.4, "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.45, "lab_test": "", "baseline_grade": "", "worst_grade": "", "monitoring_committee_action": "Continue", "data_access_state": "Blinded"},
            {"participant_id": "P002", "arm": "Treatment", "arm_population": 50, "event_id": "EV-002", "event_type": "Laboratory abnormality", "severity": "Moderate", "serious": False, "relatedness": "Possible", "event_day": 12, "resolved": True, "reportable": False, "site_id": "SITE-A", "system_organ_class": "Investigations", "preferred_term": "ALT increased", "expectedness": "Unexpected", "treatment_emergent": True, "adverse_event_of_special_interest": True, "action_taken": "Dose interrupted", "outcome": "Recovered", "awareness_date": "2026-07-02", "report_due_date": "2026-08-01", "submitted_date": "2026-07-04", "dose_level": "20 mg", "person_time_days": 55, "followup_days": 55, "information_fraction": 0.5, "efficacy_z": 1.1, "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.62, "lab_test": "ALT", "baseline_grade": "Normal", "worst_grade": "Grade 2", "monitoring_committee_action": "Review liver events", "data_access_state": "Unblinded committee"},
            {"participant_id": "P003", "arm": "Treatment", "arm_population": 50, "event_id": "EV-003", "event_type": "Hospitalisation", "severity": "Severe", "serious": True, "relatedness": "Possible", "event_day": 19, "resolved": False, "reportable": True, "site_id": "SITE-B", "system_organ_class": "General disorders", "preferred_term": "Hospitalisation", "expectedness": "Unexpected", "treatment_emergent": True, "adverse_event_of_special_interest": True, "action_taken": "Treatment stopped", "outcome": "Recovering", "awareness_date": "2026-06-01", "report_due_date": "2026-06-08", "submitted_date": "", "dose_level": "20 mg", "person_time_days": 40, "followup_days": 40, "information_fraction": 0.5, "efficacy_z": 1.1, "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.62, "lab_test": "Haemoglobin", "baseline_grade": "Normal", "worst_grade": "Grade 3", "monitoring_committee_action": "Immediate review", "data_access_state": "Unblinded committee"},
            {"participant_id": "P003", "arm": "Treatment", "arm_population": 50, "event_id": "EV-004", "event_type": "Rash", "severity": "Moderate", "serious": False, "relatedness": "Probable", "event_day": 27, "resolved": False, "reportable": False, "site_id": "SITE-B", "system_organ_class": "Skin disorders", "preferred_term": "Rash", "expectedness": "Expected", "treatment_emergent": True, "adverse_event_of_special_interest": False, "action_taken": "Dose reduced", "outcome": "Ongoing", "awareness_date": "2026-07-10", "report_due_date": "2026-08-09", "submitted_date": "", "dose_level": "10 mg", "person_time_days": 40, "followup_days": 40, "information_fraction": 0.5, "efficacy_z": 1.1, "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.62, "lab_test": "", "baseline_grade": "", "worst_grade": "", "monitoring_committee_action": "Review", "data_access_state": "Blinded"},
        ])
    if module_key == "research_publication_dissemination":
        today = pd.Timestamp.utcnow().normalize()
        return pd.DataFrame([
            {"output_id": "OUT-001", "title": "Primary research manuscript", "audience": "Scientific community", "channel": "Peer-reviewed journal", "owner": "Publication lead", "target_date": (today + pd.Timedelta(days=90)).date().isoformat(), "status": "Draft", "open_access": True, "lay_summary": False, "data_statement": True, "code_available": True, "accessibility_review": False, "priority": "Critical", "manuscript_section": "Methods", "section_status": "In progress", "section_word_count": 1800, "target_word_count": 2500, "claim_id": "CLM-001", "source_analysis_id": "AN-PRIMARY", "figure_table_id": "FIG-001", "evidence_status": "Internally verified", "guideline": "Study-type reporting checklist", "reporting_item": "Primary outcome definition", "reporting_item_status": "Addressed", "author": "Lead investigator", "contribution_role": "Conceptualization", "author_approved": True, "conflict_declared": True, "journal": "Target Journal A", "journal_scope_fit": 82, "open_access_fee": 2500, "review_comment_id": "REV-001", "review_status": "Open", "manuscript_version": "v0.4", "planned_endpoint": "Primary outcome at week 12", "reported_endpoint": "Primary outcome at week 12", "submission_status": "Not submitted", "preprint_status": "Planned", "embargo_date": "", "figure_accessibility_complete": False},
            {"output_id": "OUT-002", "title": "Participant results summary", "audience": "Participants", "channel": "Plain-language summary", "owner": "Engagement lead", "target_date": (today + pd.Timedelta(days=120)).date().isoformat(), "status": "Planned", "open_access": True, "lay_summary": True, "data_statement": True, "code_available": False, "accessibility_review": True, "priority": "High", "manuscript_section": "Lay summary", "section_status": "Draft", "section_word_count": 350, "target_word_count": 600, "claim_id": "CLM-002", "source_analysis_id": "", "figure_table_id": "FIG-002", "evidence_status": "", "guideline": "Plain-language standard", "reporting_item": "Benefits and harms explained", "reporting_item_status": "In progress", "author": "Patient engagement partner", "contribution_role": "Review and editing", "author_approved": False, "conflict_declared": True, "journal": "", "journal_scope_fit": 0, "open_access_fee": 0, "review_comment_id": "REV-002", "review_status": "Resolved", "manuscript_version": "v0.2", "planned_endpoint": "Primary outcome at week 12", "reported_endpoint": "Responder outcome at week 12", "submission_status": "Not applicable", "preprint_status": "Not applicable", "embargo_date": "", "figure_accessibility_complete": True},
            {"output_id": "OUT-003", "title": "Data and code release", "audience": "Research reuse community", "channel": "Repository", "owner": "Data steward", "target_date": (today + pd.Timedelta(days=140)).date().isoformat(), "status": "In progress", "open_access": False, "lay_summary": False, "data_statement": True, "code_available": True, "accessibility_review": True, "priority": "High", "manuscript_section": "Data availability", "section_status": "In progress", "section_word_count": 180, "target_word_count": 250, "claim_id": "", "source_analysis_id": "", "figure_table_id": "", "evidence_status": "", "guideline": "Open science checklist", "reporting_item": "Repository and access conditions", "reporting_item_status": "Addressed", "author": "Data steward", "contribution_role": "Data curation", "author_approved": True, "conflict_declared": True, "journal": "Target Journal A", "journal_scope_fit": 82, "open_access_fee": 2500, "review_comment_id": "", "review_status": "", "manuscript_version": "v0.4", "planned_endpoint": "", "reported_endpoint": "", "submission_status": "Not submitted", "preprint_status": "Planned", "embargo_date": (today + pd.Timedelta(days=180)).date().isoformat(), "figure_accessibility_complete": True},
        ])
    raise KeyError(module_key)


def _run_engine(module_key: str, frame: pd.DataFrame, threshold: float) -> LifecycleOutput:
    if module_key == "research_ethics_consent":
        return ethics_consent_workbench(frame)
    if module_key == "research_data_fair_planning":
        return fair_data_management_workbench(frame)
    if module_key == "research_interim_monitoring_safety":
        return interim_monitoring_safety_workbench(frame, serious_rate_threshold=threshold)
    if module_key == "research_publication_dissemination":
        return publication_dissemination_workbench(frame)
    raise KeyError(module_key)


@st.cache_data(ttl=900, max_entries=16, show_spinner=False)
def _run_engine_cached(module_key: str, frame: pd.DataFrame, threshold: float) -> LifecycleOutput:
    return _run_engine(module_key, frame, threshold)


def _record_column(module_key: str) -> str:
    return str(LIFECYCLE_ENGINE_CATALOG[module_key]["record_id"])


def _add_figure(
    figures: list[tuple[str, go.Figure, pd.DataFrame]],
    title: str,
    figure: go.Figure,
    data: pd.DataFrame,
) -> None:
    if isinstance(data, pd.DataFrame) and not data.empty:
        figure.update_layout(margin={"l": 40, "r": 30, "t": 70, "b": 45})
        figures.append((title, figure, data))


def _sankey_from_pairs(frame: pd.DataFrame, source: str, target: str, value: str, title: str) -> go.Figure:
    data = frame[[source, target, value]].copy()
    data[source] = data[source].fillna("Unspecified").astype(str)
    data[target] = data[target].fillna("Unspecified").astype(str)
    labels = list(dict.fromkeys(data[source].tolist() + data[target].tolist()))
    index = {label: idx for idx, label in enumerate(labels)}
    figure = go.Figure(go.Sankey(
        node={"label": labels, "pad": 15, "thickness": 18},
        link={
            "source": [index[item] for item in data[source]],
            "target": [index[item] for item in data[target]],
            "value": data[value].astype(float).clip(lower=0).tolist(),
        },
    ))
    figure.update_layout(title=title)
    return figure


def _build_figures(module_key: str, result: LifecycleOutput) -> list[tuple[str, go.Figure, pd.DataFrame]]:
    tables = result.all_tables()
    figures: list[tuple[str, go.Figure, pd.DataFrame]] = []
    if module_key == "research_ethics_consent":
        domain = tables["domain_summary"]
        subgroup = tables["subgroup_summary"]
        _add_figure(figures, "Readiness by protection domain", px.bar(domain, x="domain", y="mean_readiness", color="blockers", range_y=[0, 100], title="Readiness by protection domain"), domain)
        _add_figure(figures, "Vulnerable-population safeguard matrix", px.scatter(subgroup, x="requirements", y="readiness", size="consent_items", color="unresolved_high_risk", hover_name="vulnerable_group", range_y=[0, 100], title="Safeguard readiness by population"), subgroup)
        _add_figure(figures, "Weighted ethics gaps", px.bar(result.primary.sort_values("weighted_gap", ascending=False), x="item_id", y="weighted_gap", color="risk_level", hover_data=["requirement", "status"], title="Risk-weighted unresolved requirements"), result.primary)
        registry = tables.get("consent_version_registry", pd.DataFrame())
        _add_figure(figures, "Consent version lineage", px.bar(registry, x="consent_version", y="requirements", color="version_complete", facet_col="consent_language", title="Consent versions, language coverage and completeness"), registry)
        matrix = tables.get("participant_consent_matrix", pd.DataFrame())
        if not matrix.empty:
            pivot = matrix.pivot_table(index="participant_id", columns="consent_option", values="active_consent", aggfunc="max", fill_value=False).astype(int)
            _add_figure(figures, "Participant consent option matrix", px.imshow(pivot, aspect="auto", labels={"color": "Active consent"}, title="Participant-level consent choices"), pivot.reset_index())
        schedule = tables.get("reconsent_schedule", pd.DataFrame())
        _add_figure(figures, "Re-consent due calendar", px.scatter(schedule, x="reconsent_due_parsed", y="item_id", color="urgency", hover_data=["owner", "consent_version", "vulnerable_group"], title="Re-consent deadlines and urgency"), schedule)
        queries = tables.get("committee_query_tracker", pd.DataFrame())
        if not queries.empty:
            query_data = queries.copy()
            query_data["days_to_due"] = (query_data["query_due_parsed"] - pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tzinfo is None else query_data["query_due_parsed"] - pd.Timestamp.utcnow()).dt.days
            _add_figure(figures, "Committee query aging", px.bar(query_data, x="query_id", y="days_to_due", color="query_overdue", hover_data=["submission_id", "query_status", "owner"], title="Ethics committee query deadlines"), query_data)
        privacy = tables.get("privacy_data_flow", pd.DataFrame())
        if not privacy.empty:
            flow = privacy.groupby(["data_category", "data_destination"], dropna=False).size().reset_index(name="items")
            _add_figure(figures, "Privacy data-flow map", _sankey_from_pairs(flow, "data_category", "data_destination", "items", "Privacy-sensitive data flow"), flow)
        withdrawal = tables.get("withdrawal_impact", pd.DataFrame())
        _add_figure(figures, "Withdrawal impact coverage", px.histogram(withdrawal, y="withdrawal_scope", color="status", title="Participant withdrawal rules and readiness"), withdrawal)
        readability = tables.get("readability_summary", pd.DataFrame())
        _add_figure(figures, "Participant material readability", px.bar(readability, x="domain", y="mean_readability", color="long_sentence_items", range_y=[0, 100], title="Readability of participant-facing requirements"), readability)
        submissions = tables.get("ethics_submission_summary", pd.DataFrame())
        _add_figure(figures, "Ethics submission readiness", px.scatter(submissions, x="items", y="readiness", size="open_queries", color="submission_status", hover_name="submission_id", range_y=[0, 100], title="Submission package readiness and open queries"), submissions)
    elif module_key == "research_data_fair_planning":
        dimensions = tables["fair_dimensions"]
        type_summary = tables["data_type_summary"]
        radar = go.Figure(go.Scatterpolar(r=dimensions["score"].tolist() + [dimensions["score"].iloc[0]], theta=dimensions["dimension"].tolist() + [dimensions["dimension"].iloc[0]], fill="toself"))
        radar.update_layout(title="FAIR readiness profile", polar={"radialaxis": {"range": [0, 100], "visible": True}}, showlegend=False)
        _add_figure(figures, "FAIR readiness profile", radar, dimensions)
        _add_figure(figures, "Asset-level FAIR score", px.bar(result.primary.sort_values("fair_score"), x="fair_score", y="asset_id", orientation="h", color="backup_risk", range_x=[0, 100], hover_data=["data_type", "format", "repository"], title="Asset-level FAIR and resilience readiness"), result.primary)
        _add_figure(figures, "Data type readiness", px.scatter(type_summary, x="retention_years", y="mean_fair_score", size="assets", color="backup_copies", hover_name="data_type", range_y=[0, 100], title="Retention, backup and FAIR readiness"), type_summary)
        operational = tables.get("operational_dimensions", pd.DataFrame())
        if not operational.empty:
            op_radar = go.Figure(go.Scatterpolar(r=operational["score"].tolist() + [operational["score"].iloc[0]], theta=operational["dimension"].tolist() + [operational["dimension"].iloc[0]], fill="toself"))
            op_radar.update_layout(title="Operational data lifecycle readiness", polar={"radialaxis": {"range": [0, 100], "visible": True}}, showlegend=False)
            _add_figure(figures, "Operational lifecycle readiness", op_radar, operational)
        integrity = tables.get("file_integrity", pd.DataFrame())
        _add_figure(figures, "File integrity status board", px.bar(integrity, x="asset_id", y="operational_data_score", color="integrity_state", range_y=[0, 100], hover_data=["data_type", "format", "checksum_verified"], title="File integrity and operational data score"), integrity)
        repository = tables.get("repository_readiness", pd.DataFrame())
        _add_figure(figures, "Repository deposit readiness", px.bar(repository, x="repository", y="readiness_percent", color="deposit_status", range_y=[0, 100], hover_data=["assets", "total_size_mb"], title="Repository package readiness"), repository)
        storage = tables.get("storage_summary", pd.DataFrame())
        if not storage.empty:
            melted = storage.melt(id_vars=["month"], value_vars=["projected_size_mb", "replicated_storage_mb"], var_name="storage_type", value_name="megabytes")
            _add_figure(figures, "Storage growth forecast", px.line(melted, x="month", y="megabytes", color="storage_type", markers=True, title="Twelve-month storage and replication forecast"), melted)
        access = tables.get("access_governance_matrix", pd.DataFrame())
        if not access.empty:
            access_counts = access.groupby(["access_level", "access_request_status"], dropna=False).size().reset_index(name="assets")
            _add_figure(figures, "Access governance matrix", px.density_heatmap(access_counts, x="access_level", y="access_request_status", z="assets", histfunc="sum", title="Data access states and request workflows"), access_counts)
        licence = tables.get("licence_compatibility", pd.DataFrame())
        _add_figure(figures, "Licence compatibility review", px.histogram(licence, x="compatibility_state", color="access_level", title="Licence, consent and access compatibility"), licence)
        retention = tables.get("retention_calendar", pd.DataFrame())
        _add_figure(figures, "Retention and destruction calendar", px.scatter(retention, x="destruction_date_parsed", y="asset_id", color="action_state", hover_data=["owner", "retention_years", "legal_hold"], title="Retention, legal hold and destruction actions"), retention)
        metadata = result.primary[["asset_id", "metadata_completeness", "technical_integrity", "access_governance", "preservation_readiness", "reproducibility_readiness"]].set_index("asset_id")
        _add_figure(figures, "Data lifecycle quality heatmap", px.imshow(metadata, aspect="auto", zmin=0, zmax=100, labels={"color": "Score"}, title="Asset-level lifecycle quality dimensions"), metadata.reset_index())
    elif module_key == "research_interim_monitoring_safety":
        arm = tables["arm_summary"]
        timeline = tables["timeline"]
        severity = tables["severity_summary"]
        _add_figure(figures, "Serious-event rate by arm", px.bar(arm, x="arm", y="serious_event_rate", color="threshold_exceeded", hover_data=["participants", "serious_events", "unresolved_events"], title="Serious-event rate by arm"), arm)
        _add_figure(figures, "Cumulative event timeline", px.line(timeline, x="event_day", y="cumulative_events", color="arm", markers=True, title="Cumulative monitored events"), timeline)
        _add_figure(figures, "Severity distribution", px.bar(severity, x="arm", y="events", color="severity", barmode="stack", title="Event severity by arm"), severity)
        exposure = tables.get("exposure_adjusted_rates", pd.DataFrame())
        if not exposure.empty:
            exposure_melted = exposure.melt(id_vars=["arm"], value_vars=["events_per_100_person_years", "serious_events_per_100_person_years"], var_name="rate_type", value_name="rate")
            _add_figure(figures, "Exposure-adjusted incidence", px.bar(exposure_melted, x="arm", y="rate", color="rate_type", barmode="group", title="Exposure-adjusted event rates per 100 person-years"), exposure_melted)
        first = tables.get("time_to_first_event", pd.DataFrame())
        _add_figure(figures, "Time to first event", px.line(first, x="first_event_day", y="cumulative_event_fraction", color="arm", line_shape="hv", markers=True, title="Cumulative fraction with a first monitored event"), first)
        organ = tables.get("organ_system_severity", pd.DataFrame())
        if not organ.empty:
            organ_pivot = organ.pivot_table(index="system_organ_class", columns="severity", values="events", aggfunc="sum", fill_value=0)
            _add_figure(figures, "Organ-system severity heatmap", px.imshow(organ_pivot, aspect="auto", labels={"color": "Events"}, title="Event burden by organ system and severity"), organ_pivot.reset_index())
        participant = tables.get("participant_safety_timeline", pd.DataFrame())
        _add_figure(figures, "Participant safety timeline", px.scatter(participant, x="event_day", y="participant_id", color="severity", symbol="serious", hover_data=["preferred_term", "action_taken", "outcome", "dose_level"], title="Participant-level event chronology"), participant)
        deadlines = tables.get("reporting_deadlines", pd.DataFrame())
        _add_figure(figures, "Safety reporting deadlines", px.scatter(deadlines, x="effective_report_due", y="event_id", color="report_late", symbol="serious", hover_data=["site_id", "submitted_date_parsed", "report_delay_days"], title="Safety report due dates and late submissions"), deadlines)
        recurrent = tables.get("recurrent_event_summary", pd.DataFrame())
        _add_figure(figures, "Recurrent-event burden", px.bar(recurrent, x="participant_id", y="events", color="recurrent_event_burden", facet_col="arm", hover_data=["serious_events", "followup_days"], title="Repeated event burden by participant"), recurrent)
        sites = tables.get("site_signal_summary", pd.DataFrame())
        _add_figure(figures, "Site safety signal review", px.scatter(sites, x="participants", y="events_per_participant", size="serious_events", color="signal_state", hover_name="site_id", title="Site-level reporting patterns"), sites)
        labs = tables.get("laboratory_shift_summary", pd.DataFrame())
        if not labs.empty:
            lab_pivot = labs.pivot_table(index=["lab_test", "baseline_grade"], columns="worst_grade", values="participants", aggfunc="sum", fill_value=0)
            _add_figure(figures, "Laboratory grade shifts", px.imshow(lab_pivot, aspect="auto", labels={"color": "Participants"}, title="Baseline-to-worst laboratory grade shifts"), lab_pivot.reset_index())
        interim = tables.get("interim_boundary_review", pd.DataFrame())
        if not interim.empty:
            boundary_long = interim.melt(id_vars=["arm", "information_fraction"], value_vars=["efficacy_z", "efficacy_boundary", "futility_boundary"], var_name="series", value_name="z_value")
            _add_figure(figures, "Interim stopping boundaries", px.line(boundary_long, x="information_fraction", y="z_value", color="series", facet_col="arm", markers=True, title="Interim efficacy and futility boundary review"), boundary_long)
            _add_figure(figures, "Conditional power trajectory", px.scatter(interim, x="information_fraction", y="conditional_power", color="interim_decision_signal", hover_name="arm", range_y=[0, 1], title="Conditional power and prespecified review signals"), interim)
        benefit = tables.get("benefit_risk_summary", pd.DataFrame())
        _add_figure(figures, "Benefit-risk planning view", px.scatter(benefit, x="serious_events_per_100_person_years", y="efficacy_signal", size="participants", color="arm", hover_data=["benefit_risk_index", "events_per_100_person_years"], title="Planning view of efficacy signal versus serious-event burden"), benefit)
        dose = result.primary.loc[result.primary["dose_level"].ne("")].copy()
        if not dose.empty:
            _add_figure(figures, "Dose and adverse-event profile", px.scatter(dose, x="dose_level", y="safety_signal_score", size="severity_weight", color="system_organ_class", hover_name="preferred_term", title="Dose level and event signal score"), dose)
    elif module_key == "research_publication_dissemination":
        audience = tables["audience_summary"]
        channel = tables["channel_summary"]
        timeline = tables["timeline"]
        _add_figure(figures, "Audience coverage and readiness", px.scatter(audience, x="outputs", y="mean_readiness", size="mean_open_science", color="overdue", hover_name="audience", range_y=[0, 100], title="Audience coverage, readiness and open-science planning"), audience)
        _add_figure(figures, "Channel readiness", px.bar(channel, x="channel", y="readiness", color="overdue", range_y=[0, 100], title="Dissemination channel readiness"), channel)
        _add_figure(figures, "Dissemination timeline", px.scatter(timeline, x="target_date_parsed", y="channel", color="overdue", symbol="status", hover_name="title", title="Planned publication and dissemination timeline"), timeline)
        manuscript = tables.get("manuscript_progress", pd.DataFrame())
        _add_figure(figures, "Manuscript section completion", px.bar(manuscript, x="manuscript_section", y="completion_percent", color="completed_items", range_y=[0, 100], hover_data=["word_count", "target_word_count"], title="Manuscript section production progress"), manuscript)
        claims = tables.get("claim_evidence_traceability", pd.DataFrame())
        if not claims.empty:
            claim_flow = claims.copy()
            claim_flow["source_analysis_id"] = claim_flow["source_analysis_id"].replace("", "Unlinked analysis")
            claim_flow["figure_table_id"] = claim_flow["figure_table_id"].replace("", "Unlinked output")
            first_flow = claim_flow.groupby(["claim_id", "source_analysis_id"], dropna=False).size().reset_index(name="links")
            second_flow = claim_flow.groupby(["source_analysis_id", "figure_table_id"], dropna=False).size().reset_index(name="links")
            labels = list(dict.fromkeys(first_flow["claim_id"].tolist() + first_flow["source_analysis_id"].tolist() + second_flow["figure_table_id"].tolist()))
            index = {label: i for i, label in enumerate(labels)}
            sankey = go.Figure(go.Sankey(node={"label": labels}, link={"source": [index[x] for x in first_flow["claim_id"]] + [index[x] for x in second_flow["source_analysis_id"]], "target": [index[x] for x in first_flow["source_analysis_id"]] + [index[x] for x in second_flow["figure_table_id"]], "value": first_flow["links"].tolist() + second_flow["links"].tolist()}))
            sankey.update_layout(title="Claim → analysis → figure/table traceability")
            _add_figure(figures, "Claim-evidence traceability graph", sankey, claims)
        guideline = tables.get("reporting_guideline_summary", pd.DataFrame())
        _add_figure(figures, "Reporting guideline completion", px.bar(guideline, x="guideline", y="completion_percent", color="complete_items", range_y=[0, 100], title="Reporting checklist completion"), guideline)
        authors = tables.get("authorship_contributions", pd.DataFrame())
        if not authors.empty:
            author_matrix = authors.pivot_table(index="author", columns="contribution_role", values="outputs", aggfunc="sum", fill_value=0)
            _add_figure(figures, "Author contribution matrix", px.imshow(author_matrix, aspect="auto", labels={"color": "Outputs"}, title="Contributor roles and publication outputs"), author_matrix.reset_index())
        journals = tables.get("journal_selection", pd.DataFrame())
        _add_figure(figures, "Journal fit and access planning", px.scatter(journals, x="scope_fit", y="open_access_fee", size="outputs", color="selection_state", hover_name="journal", range_x=[0, 100], title="Journal scope fit and open-access cost"), journals)
        figures_table = tables.get("figure_table_inventory", pd.DataFrame())
        _add_figure(figures, "Figure and table readiness", px.histogram(figures_table, x="status", color="figure_accessibility_complete", title="Figure/table production and accessibility status"), figures_table)
        review = tables.get("peer_review_burndown", pd.DataFrame())
        _add_figure(figures, "Peer review issue burn-down", px.bar(review, x="review_status", y="comments", color="review_status", title="Peer review comment status"), review)
        versions = tables.get("publication_version_lineage", pd.DataFrame())
        _add_figure(figures, "Publication version lineage", px.scatter(versions, x="target_date_parsed", y="manuscript_version", color="status", symbol="submission_status", hover_data=["output_id", "preprint_status"], title="Manuscript, preprint and submission versions"), versions)
        deviations = tables.get("protocol_publication_deviations", pd.DataFrame())
        _add_figure(figures, "Protocol-to-publication deviations", px.bar(deviations.assign(deviation_count=1), x="claim_id", y="deviation_count", color="deviation_state", hover_data=["planned_endpoint", "reported_endpoint", "source_analysis_id"], title="Endpoint and claim deviations requiring justification"), deviations)
        matrix = tables.get("audience_channel_matrix", pd.DataFrame())
        if not matrix.empty:
            _add_figure(figures, "Audience-channel dissemination map", _sankey_from_pairs(matrix, "audience", "channel", "outputs", "Audience to dissemination channel map"), matrix)
        open_science = result.primary[["output_id", "open_access", "lay_summary", "data_statement", "code_available", "accessibility_review"]].set_index("output_id").astype(int)
        _add_figure(figures, "Open-science dependency matrix", px.imshow(open_science, aspect="auto", zmin=0, zmax=1, labels={"color": "Ready"}, title="Open science and accessibility components"), open_science.reset_index())
    return figures


def _operational_document(module_key: str, result: LifecycleOutput) -> tuple[str, str]:
    summary_lines = [f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in result.summary.items()]
    warning_lines = [f"- {item}" for item in result.warnings] or ["- No engine warning was generated for this planning run."]
    table_lines = [f"- `{name}.csv`: {len(frame):,} records" for name, frame in result.all_tables().items()]
    title_map = {
        "research_ethics_consent": ("ETHICS_SUBMISSION_AND_CONSENT_OPERATIONS.md", "Ethics Submission and Consent Operations Package"),
        "research_data_fair_planning": ("DATA_MANAGEMENT_AND_REPOSITORY_DEPOSIT_PLAN.md", "Data Management and Repository Deposit Plan"),
        "research_interim_monitoring_safety": ("INTERIM_MONITORING_AND_SAFETY_REVIEW_PACKAGE.md", "Interim Monitoring and Safety Review Package"),
        "research_publication_dissemination": ("MANUSCRIPT_AND_DISSEMINATION_PACKAGE.md", "Manuscript and Dissemination Operations Package"),
    }
    filename, title = title_map[module_key]
    text = "\n".join([
        f"# {title}",
        "",
        "Generated by BioIntel AI as a structured research-planning aid. This package requires qualified human review and does not constitute ethics, legal, medical, regulatory or journal approval.",
        "",
        "## Operational summary",
        *summary_lines,
        "",
        "## Review warnings",
        *warning_lines,
        "",
        "## Included machine-readable tables",
        *table_lines,
        "",
        "## Traceability",
        f"- Module: `{module_key}`",
        f"- Manifest SHA-256: `{result.manifest()['manifest_sha256']}`",
        "- Every CSV table is independently checksum-bound in `manifest.json`.",
        "- Review decisions are included in `reviews.csv`.",
        "",
        "## Required external review",
        "- Confirm local institutional, legal and regulatory requirements.",
        "- Review unresolved issues and cross-module impacts.",
        "- Lock an approved version only after accountable reviewers sign off.",
        "",
    ])
    return filename, text


def _bundle(module_key: str, result: LifecycleOutput, reviews: pd.DataFrame) -> tuple[bytes, dict[str, Any]]:
    manifest = result.manifest()
    manifest["review_records"] = int(len(reviews))
    manifest["operational_tables"] = int(len(result.all_tables()))
    document_name, document_text = _operational_document(module_key, result)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, frame in result.all_tables().items():
            archive.writestr(f"tables/{name}.csv", frame.to_csv(index=False, lineterminator="\n"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        archive.writestr("summary.json", json.dumps(dict(result.summary), indent=2, default=str))
        archive.writestr("reviews.csv", reviews.to_csv(index=False, lineterminator="\n"))
        archive.writestr(document_name, document_text)
        archive.writestr("README.txt", "BioIntel AI Research Lifecycle operational package. Results are planning and review aids and require qualified external approval.\n")
    payload = buffer.getvalue()
    manifest["bundle_sha256"] = sha256(payload).hexdigest()
    manifest["operational_document"] = document_name
    return payload, manifest


def render_lifecycle_module(module_key: str) -> None:
    if module_key not in MODULE_META:
        raise KeyError(module_key)
    meta = MODULE_META[module_key]
    key = f"rpl_{module_key}"
    hero(meta["title"], meta["summary"], eyebrow="BioIntel Research Planning · Full Research Lifecycle", chips=meta["chips"])
    scientific_boundary_banner(source_kind="reference", release_eligible=False, message=meta["boundary"])

    tabs = st.tabs(["1 · Inputs", "2 · Analysis & visuals", "3 · Review & versions", "4 · Reproducible export", "5 · Lifecycle handoffs", "6 · Guide"])
    with tabs[0]:
        section_title("Prepare lifecycle planning data", "input")
        source = st.radio("Data source", ["Starter dataset", "Upload CSV/TSV/Excel/JSON"], horizontal=True, key=f"{key}_source")
        template = starter_frame(module_key)
        st.download_button("Download module template", template.to_csv(index=False).encode("utf-8"), f"{module_key}_template.csv", "text/csv", key=f"{key}_template")
        frame = template.copy()
        if source != "Starter dataset":
            uploaded = st.file_uploader("Upload planning data", type=["csv", "tsv", "xlsx", "xls", "json"], key=f"{key}_upload")
            if uploaded is None:
                st.info("Upload a file or use the starter dataset.")
                frame = template.head(0)
            else:
                try:
                    render_upload_preflight(
                        uploaded,
                        key=f"{key}_upload_preflight",
                        allowed_extensions=["csv", "tsv", "xlsx", "xls", "json"],
                        soft_limit_mb=100,
                        hard_limit_mb=1024,
                        module_key=module_key,
                    )
                    suffix = Path(uploaded.name).suffix.lower()
                    raw = uploaded.getvalue()
                    if suffix == ".csv":
                        frame = pd.read_csv(io.BytesIO(raw))
                    elif suffix == ".tsv":
                        frame = pd.read_csv(io.BytesIO(raw), sep="\t")
                    elif suffix in {".xlsx", ".xls"}:
                        frame = pd.read_excel(io.BytesIO(raw))
                    elif suffix == ".json":
                        payload = json.loads(raw.decode("utf-8"))
                        frame = pd.DataFrame(payload if isinstance(payload, list) else payload.get("records", []))
                    else:
                        raise ValueError("Unsupported file type.")
                except Exception as exc:
                    st.error(f"Input failed safely: {exc}")
                    frame = template.head(0)
        if not frame.empty:
            if len(frame) <= 2_000:
                edit_rows = st.toggle("Edit lifecycle planning rows", value=False, key=f"{key}_edit_toggle")
                if edit_rows:
                    frame = pd.DataFrame(st.data_editor(frame, num_rows="dynamic", width="stretch", key=f"{key}_editor"))
            else:
                st.info("Large planning tables remain read-only in the browser. Analysis uses the full bounded dataset without rendering every row.")
        st.session_state[f"{key}_frame"] = frame
        metric_cards([
            ("Records", len(frame), None),
            ("Columns", len(frame.columns), None),
            ("Missing cells", int(frame.isna().sum().sum()) if not frame.empty else 0, None),
            ("Input SHA-256", sha256(frame.to_csv(index=False).encode()).hexdigest()[:16] + "…" if not frame.empty else "—", None),
        ])
        if not frame.empty:
            smart_dataframe(frame.head(500), height=360, key=f"{key}_preview")
        with st.form(f"{key}_run_form"):
            threshold = 0.10
            if module_key == "research_interim_monitoring_safety":
                threshold = st.slider("Planning serious-event review threshold", 0.0, 1.0, 0.10, 0.01)
            reviewer = st.text_input("Scientific owner / reviewer", value="Local research reviewer")
            submitted = st.form_submit_button("Run lifecycle analysis", type="primary", width="stretch")
        if submitted:
            try:
                if frame.empty:
                    raise ValueError("No records are available for analysis.")
                result = _run_engine_cached(module_key, frame, threshold)
                st.session_state[f"{key}_result"] = result
                st.session_state[f"{key}_reviewer"] = reviewer
                try:
                    thread_store = ResearchDigitalThreadStore(THREAD_PATH)
                    node_type = {
                        "research_ethics_consent": "ethics_plan",
                        "research_data_fair_planning": "data_management_plan",
                        "research_interim_monitoring_safety": "monitoring_plan",
                        "research_publication_dissemination": "publication_plan",
                    }[module_key]
                    node_id = thread_store.upsert_node(ThreadNode(
                        node_id="",
                        node_type=node_type,
                        title=meta["title"],
                        module_key=module_key,
                        status="Needs review" if result.warnings else "Reviewed",
                        payload={"summary": dict(result.summary), "manifest_sha256": result.manifest()["manifest_sha256"]},
                    ))
                    protocol_nodes = thread_store.nodes()
                    if not protocol_nodes.empty:
                        protocol_rows = protocol_nodes.loc[protocol_nodes["node_type"].eq("protocol")]
                        if not protocol_rows.empty and protocol_rows.iloc[0]["node_id"] != node_id:
                            thread_store.link(ThreadLink(str(protocol_rows.iloc[0]["node_id"]), node_id, "governs_lifecycle", True))
                    st.session_state[f"{key}_thread_node_id"] = node_id
                except Exception as thread_exc:
                    st.session_state[f"{key}_thread_warning"] = str(thread_exc)
                st.success("Lifecycle analysis completed with bounded validation.")
            except Exception as exc:
                recovery = sha256(f"{module_key}|{type(exc).__name__}|{exc}".encode()).hexdigest()[:12].upper()
                st.session_state.pop(f"{key}_result", None)
                st.error(f"Analysis stopped safely · RPL-{recovery}\n\n{exc}")

    result = st.session_state.get(f"{key}_result")
    with tabs[1]:
        section_title("Lifecycle readiness, gaps and decisions", "analysis")
        if not isinstance(result, LifecycleOutput):
            st.info("Run the analysis in the first tab.")
        else:
            cards = [(name.replace("_", " ").title(), value, None) for name, value in result.summary.items()]
            metric_cards(cards[:6])
            for warning in result.warnings:
                st.warning(warning)
            figures = _build_figures(module_key, result)
            if figures:
                selected = st.selectbox("Scientific visual", [item[0] for item in figures], key=f"{key}_visual")
                title, figure, visual_data = next(item for item in figures if item[0] == selected)
                st.plotly_chart(figure, width="stretch", key=f"{key}_plot")
                st.download_button("Download visual data", visual_data.to_csv(index=False).encode(), f"{module_key}_{title.lower().replace(' ', '_')}.csv", "text/csv", key=f"{key}_visual_download")
            table_name = st.selectbox("Result table", list(result.all_tables()), key=f"{key}_table")
            smart_dataframe(result.all_tables()[table_name].head(5000), height=430, key=f"{key}_table_view")

    with tabs[2]:
        section_title("Scientific review and immutable plan versions", "review")
        if not isinstance(result, LifecycleOutput):
            st.info("Run the analysis before saving review decisions or versions.")
        else:
            store = PlanningReviewStore(STORE_PATH)
            record_col = _record_column(module_key)
            ids = result.primary[record_col].astype(str).drop_duplicates().tolist()[:5000]
            c1, c2 = st.columns(2)
            record_id = c1.selectbox("Record", ids, key=f"{key}_record")
            decision = c2.selectbox("Decision", ["Needs review", "Accepted", "Rejected", "Needs confirmation", "Escalated"], key=f"{key}_decision")
            reviewer = st.text_input("Reviewer", value=str(st.session_state.get(f"{key}_reviewer", "Local research reviewer")), key=f"{key}_reviewer_input")
            note = st.text_area("Decision rationale", key=f"{key}_note")
            if st.button("Save review decision", type="primary", key=f"{key}_save_review"):
                store.upsert_review(module_key, record_id, decision, reviewer, note)
                st.success("Review decision saved.")
            smart_dataframe(store.reviews(module_key), height=280, key=f"{key}_reviews")
            c3, c4 = st.columns(2)
            version_status = c3.selectbox("Version status", ["Draft", "Reviewed", "Locked", "Superseded", "Retracted"], key=f"{key}_version_status")
            reason = c4.text_input("Version reason", value="Lifecycle planning review", key=f"{key}_version_reason")
            if st.button("Save version", key=f"{key}_save_version"):
                payload = result.manifest()
                version_id = store.save_version(module_key, version_status, payload["manifest_sha256"], payload, reviewer, reason)
                st.success(f"Saved version {version_id}.")
            smart_dataframe(store.versions(module_key), height=280, key=f"{key}_versions")

    with tabs[3]:
        section_title("Reproducibility and audit package", "export")
        if not isinstance(result, LifecycleOutput):
            st.info("Run the analysis before exporting.")
        else:
            store = PlanningReviewStore(STORE_PATH)
            reviews = store.reviews(module_key)
            package, manifest = _bundle(module_key, result, reviews)
            metric_cards([
                ("Bundle size", f"{len(package)/1024:.1f} KB", None),
                ("Tables", len(result.all_tables()), None),
                ("Reviews", len(reviews), None),
                ("Bundle SHA-256", manifest["bundle_sha256"][:16] + "…", None),
            ])
            st.download_button("Download complete lifecycle package", package, f"{module_key}_bundle.zip", "application/zip", type="primary", width="stretch", key=f"{key}_bundle")
            smart_json(manifest, title="Lifecycle manifest", download_name=f"{module_key}_manifest.json", key=f"{key}_manifest")

    with tabs[4]:
        section_title("Research lifecycle handoffs", "network")
        thread_node_id = st.session_state.get(f"{key}_thread_node_id")
        if thread_node_id:
            st.caption(f"Digital-thread node: {thread_node_id}")
        elif st.session_state.get(f"{key}_thread_warning"):
            st.warning("The analysis completed, but the digital-thread update was isolated: " + str(st.session_state.get(f"{key}_thread_warning")))
        links = [
            ("Research Planning Command Center", "pages/221_Research_Planning_Command_Center.py"),
            ("Study Protocol Designer", "pages/205_Study_Protocol_Designer.py"),
            ("Data Collection & CRF Designer", "pages/214_Data_Collection_CRF_Designer.py"),
            ("Statistical Analysis Plan Studio", "pages/215_Statistical_Analysis_Plan_Studio.py"),
            ("Pre-Registration & Reproducibility Studio", "pages/220_PreRegistration_Reproducibility_Studio.py"),
            ("Research Ethics, Consent & Participant Protection Studio", "pages/223_Research_Ethics_Consent_Participant_Protection_Studio.py"),
            ("Research Data Management & FAIR Planning Studio", "pages/224_Research_Data_Management_FAIR_Planning_Studio.py"),
            ("Data Monitoring, Interim Review & Safety Studio", "pages/225_Data_Monitoring_Interim_Review_Safety_Studio.py"),
            ("Publication, Dissemination & Knowledge Translation Studio", "pages/226_Publication_Dissemination_Knowledge_Translation_Studio.py"),
        ]
        st.markdown("Current result context can be carried into the connected research-lifecycle modules.")
        if isinstance(result, LifecycleOutput) and st.button("Prepare lifecycle handoff", key=f"{key}_handoff"):
            st.session_state["biointel_research_lifecycle_context"] = {
                "source_module": module_key,
                "summary": dict(result.summary),
                "manifest_sha256": result.manifest()["manifest_sha256"],
            }
            st.success("Lifecycle handoff context prepared.")
        for label, path in links:
            st.page_link(path, label=label)

    with tabs[5]:
        section_title("Purpose and operating boundary", "guide")
        st.markdown(f"**Purpose:** {meta['summary']}")
        st.markdown("**Workflow**")
        st.markdown("1. Import or edit a structured planning table.\n2. Run bounded validation and readiness analysis.\n3. Review issues and supporting evidence.\n4. Save review decisions and an immutable version.\n5. Export the complete reproducibility package.\n6. Hand off context to connected planning modules.")
        st.warning(meta["boundary"])


def lifecycle_readiness(module_key: str, context: dict[str, Any] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build a deterministic cross-lifecycle readiness view for existing modules."""
    context = dict(context or {})
    phase_weights = {
        "Scientific question": 1.0,
        "Protocol and design": 1.2,
        "Participant protection": 1.3,
        "Data management": 1.0,
        "Statistical analysis": 1.2,
        "Operational feasibility": 1.0,
        "Interim monitoring": 1.1,
        "Reproducibility": 1.1,
        "Dissemination": 0.9,
    }
    defaults = {
        "Scientific question": 80.0,
        "Protocol and design": 78.0,
        "Participant protection": float(context.get("participant_protection_score", 70.0)),
        "Data management": float(context.get("data_readiness_score", 70.0)),
        "Statistical analysis": float(context.get("statistical_readiness_score", 75.0)),
        "Operational feasibility": float(context.get("operational_readiness_score", 70.0)),
        "Interim monitoring": float(context.get("monitoring_readiness_score", 60.0)),
        "Reproducibility": float(context.get("reproducibility_score", 70.0)),
        "Dissemination": float(context.get("dissemination_readiness_score", 55.0)),
    }
    # Modules receive a modest boost in their core lifecycle area, never beyond 100.
    boosts = {
        "study_protocol_designer": "Protocol and design",
        "data_collection_crf_designer": "Data management",
        "statistical_analysis_plan": "Statistical analysis",
        "research_feasibility_recruitment": "Operational feasibility",
        "preregistration_reproducibility": "Reproducibility",
        "research_ethics_consent": "Participant protection",
        "research_data_fair_planning": "Data management",
        "research_interim_monitoring_safety": "Interim monitoring",
        "research_publication_dissemination": "Dissemination",
    }
    if module_key in boosts:
        phase = boosts[module_key]
        defaults[phase] = max(defaults[phase], 85.0)
    readiness = pd.DataFrame([
        {"phase": phase, "score": round(float(np.clip(score, 0, 100)), 1), "weight": weight}
        for phase, weight in phase_weights.items()
        for score in [defaults[phase]]
    ])
    readiness["weighted_score"] = readiness["score"] * readiness["weight"]
    gaps = readiness.loc[readiness["score"] < 75, ["phase", "score"]].copy()
    if not gaps.empty:
        gaps["severity"] = np.where(gaps["score"] < 50, "Critical", "Major")
        gaps["recommended_action"] = "Open the related lifecycle module and resolve missing controls."
    else:
        gaps = pd.DataFrame(columns=["phase", "score", "severity", "recommended_action"])
    overall = float(readiness["weighted_score"].sum() / readiness["weight"].sum())
    summary = {"overall_lifecycle_readiness": round(overall, 1), "open_lifecycle_gaps": int(len(gaps)), "module_key": module_key}
    return readiness.drop(columns="weighted_score"), gaps, summary


def render_lifecycle_readiness_panel(module_key: str, *, context: dict[str, Any] | None = None, key_prefix: str = "rpl_shared") -> None:
    readiness, gaps, summary = lifecycle_readiness(module_key, context)
    metric_cards([
        ("Lifecycle readiness", f"{summary['overall_lifecycle_readiness']:.1f}%", None),
        ("Open lifecycle gaps", summary["open_lifecycle_gaps"], None),
        ("Lifecycle phases", len(readiness), None),
        ("Traceability mode", "Connected", None),
    ])
    fig = go.Figure(go.Scatterpolar(r=readiness["score"].tolist() + [readiness["score"].iloc[0]], theta=readiness["phase"].tolist() + [readiness["phase"].iloc[0]], fill="toself"))
    fig.update_layout(title="End-to-end research lifecycle readiness", polar={"radialaxis": {"range": [0, 100], "visible": True}}, showlegend=False)
    st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_radar")
    if gaps.empty:
        st.success("No lifecycle phase is below the 75% planning threshold.")
    else:
        smart_dataframe(gaps, height=240, key=f"{key_prefix}_gaps")
    c1, c2, c3, c4 = st.columns(4)
    c1.page_link("pages/223_Research_Ethics_Consent_Participant_Protection_Studio.py", label="Ethics & consent")
    c2.page_link("pages/224_Research_Data_Management_FAIR_Planning_Studio.py", label="FAIR data planning")
    c3.page_link("pages/225_Data_Monitoring_Interim_Review_Safety_Studio.py", label="Interim monitoring")
    c4.page_link("pages/226_Publication_Dissemination_Knowledge_Translation_Studio.py", label="Publication & dissemination")
