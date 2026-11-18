from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from biointel.research_planning.lifecycle_engines import (
    ethics_consent_workbench,
    fair_data_management_workbench,
    interim_monitoring_safety_workbench,
    publication_dissemination_workbench,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step147_ethics_operational_lifecycle_tables_and_impacts():
    frame = pd.DataFrame([
        {
            "item_id": "E1", "domain": "Consent", "requirement": "Explain the study purpose and participant choices clearly.",
            "status": "In review", "risk_level": "High", "vulnerable_group": "All", "consent_required": True,
            "privacy_sensitive": True, "owner": "Ethics", "evidence_reference": "consent-v1",
            "consent_version": "1.0", "consent_language": "English", "effective_date": "2026-01-01",
            "approval_expiry": "2027-01-01", "participant_id": "P1", "consent_option": "Primary",
            "consent_decision": "Signed", "signed_date": "2026-01-02", "withdrawal_date": "",
            "reconsent_due_date": "2026-08-01", "submission_id": "S1", "submission_status": "In review",
            "submission_date": "2026-01-01", "approval_date": "", "query_id": "Q1", "query_status": "Open",
            "query_due_date": "2026-07-01", "withdrawal_scope": "Stop future collection",
            "data_category": "Identifiers", "data_destination": "Secure archive",
        }
    ])
    output = ethics_consent_workbench(frame)
    expected = {
        "consent_version_registry", "participant_consent_matrix", "reconsent_schedule",
        "ethics_submission_summary", "committee_query_tracker", "privacy_data_flow",
        "withdrawal_impact", "readability_summary", "cross_module_impacts",
    }
    assert expected.issubset(output.tables)
    assert output.summary["consent_versions"] == 1
    assert output.summary["participant_consent_records"] == 1
    assert output.summary["open_committee_queries"] == 1
    assert output.summary["operational_coverage_percent"] == 100.0
    assert output.primary["readability_score"].between(0, 100).all()


def test_step147_ethics_flags_privacy_flow_and_overdue_query():
    frame = pd.DataFrame([
        {
            "item_id": "E1", "domain": "Consent", "requirement": "Consent", "status": "Draft", "risk_level": "High",
            "vulnerable_group": "All", "consent_required": True, "privacy_sensitive": True, "owner": "Lead",
            "evidence_reference": "draft", "query_id": "Q1", "query_status": "Open", "query_due_date": "2020-01-01",
            "data_category": "", "data_destination": "",
        }
    ])
    output = ethics_consent_workbench(frame)
    issues = output.tables["issues"]["issue"].tolist()
    assert any("overdue" in value.lower() for value in issues)
    assert any("data flow" in value.lower() for value in issues)


def test_step147_fair_operational_quality_and_storage_forecast():
    frame = pd.DataFrame([
        {
            "asset_id": "A1", "data_type": "Table", "format": "CSV", "metadata_standard": "Dictionary",
            "persistent_id": "pid:a1", "access_level": "Controlled", "retention_years": 10,
            "repository": "Archive", "licence": "Research use", "owner": "Steward", "backup_copies": 3,
            "encryption": "AES-256", "checksum": "abc", "checksum_verified": True, "format_validated": True,
            "schema_required_fields": 10, "schema_present_fields": 9, "file_size_mb": 100,
            "monthly_growth_mb": 5, "data_dictionary_complete": True, "provenance_complete": True,
            "last_restore_test": "2026-01-01", "consent_restriction": "Research only",
            "repository_policy": "Controlled",
        }
    ])
    output = fair_data_management_workbench(frame)
    assert output.summary["checksum_verified_percent"] == 100.0
    assert output.summary["projected_12_month_storage_mb"] == 480.0
    assert len(output.tables["operational_dimensions"]) == 7
    assert output.tables["storage_summary"]["month"].tolist() == list(range(13))
    assert output.primary["operational_data_score"].between(0, 100).all()


def test_step147_fair_rejects_impossible_schema_counts():
    frame = pd.DataFrame([
        {
            "asset_id": "A1", "data_type": "Table", "format": "CSV", "metadata_standard": "Dictionary",
            "persistent_id": "pid:a1", "access_level": "Controlled", "retention_years": 10,
            "repository": "Archive", "licence": "Research use", "owner": "Steward", "backup_copies": 2,
            "encryption": "AES-256", "schema_required_fields": 2, "schema_present_fields": 3,
        }
    ])
    with pytest.raises(ValueError, match="cannot exceed"):
        fair_data_management_workbench(frame)


def test_step147_safety_exposure_deadlines_interim_and_site_signals():
    frame = pd.DataFrame([
        {
            "participant_id": "P1", "arm": "Control", "arm_population": 20, "event_id": "EV1",
            "event_type": "Headache", "severity": "Mild", "serious": False, "relatedness": "Unlikely",
            "event_day": 5, "resolved": True, "reportable": False, "site_id": "S1",
            "system_organ_class": "Nervous system", "preferred_term": "Headache", "expectedness": "Expected",
            "awareness_date": "2026-07-01", "report_due_date": "2026-07-31", "submitted_date": "2026-07-02",
            "person_time_days": 60, "followup_days": 60, "information_fraction": 0.5, "efficacy_z": 0.4,
            "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.5,
        },
        {
            "participant_id": "P2", "arm": "Treatment", "arm_population": 20, "event_id": "EV2",
            "event_type": "Hospitalisation", "severity": "Severe", "serious": True, "relatedness": "Possible",
            "event_day": 10, "resolved": False, "reportable": True, "site_id": "S2",
            "system_organ_class": "General disorders", "preferred_term": "Hospitalisation", "expectedness": "Unexpected",
            "awareness_date": "2026-01-01", "report_due_date": "2026-01-08", "submitted_date": "",
            "person_time_days": 30, "followup_days": 30, "information_fraction": 0.5, "efficacy_z": 3.0,
            "efficacy_boundary": 2.8, "futility_boundary": -0.5, "conditional_power": 0.9,
            "lab_test": "ALT", "baseline_grade": "Normal", "worst_grade": "Grade 3",
        },
        {
            "participant_id": "P2", "arm": "Treatment", "arm_population": 20, "event_id": "EV3",
            "event_type": "Rash", "severity": "Moderate", "serious": False, "relatedness": "Probable",
            "event_day": 15, "resolved": False, "reportable": False, "site_id": "S2",
            "system_organ_class": "Skin disorders", "preferred_term": "Rash", "expectedness": "Expected",
            "person_time_days": 30, "followup_days": 30,
        },
    ])
    output = interim_monitoring_safety_workbench(frame, serious_rate_threshold=0.2)
    expected = {
        "exposure_adjusted_rates", "time_to_first_event", "recurrent_event_summary",
        "organ_system_severity", "participant_safety_timeline", "reporting_deadlines",
        "site_signal_summary", "laboratory_shift_summary", "interim_boundary_review",
        "benefit_risk_summary", "cross_module_impacts",
    }
    assert expected.issubset(output.tables)
    assert output.summary["late_safety_reports"] == 1
    assert output.summary["recurrent_event_participants"] == 1
    assert output.summary["interim_reviews_configured"] >= 1
    assert "Efficacy boundary crossed" in output.tables["interim_boundary_review"]["interim_decision_signal"].tolist()


def test_step147_safety_rejects_negative_person_time():
    frame = pd.DataFrame([
        {
            "participant_id": "P1", "arm": "A", "event_id": "E1", "event_type": "AE", "severity": "Mild",
            "serious": False, "relatedness": "Unrelated", "event_day": 1, "resolved": True, "reportable": False,
            "person_time_days": -1,
        }
    ])
    with pytest.raises(ValueError, match="Person-time"):
        interim_monitoring_safety_workbench(frame)


def test_step147_publication_manuscript_claim_authorship_and_deviation_workflows():
    frame = pd.DataFrame([
        {
            "output_id": "O1", "title": "Paper", "audience": "Researchers", "channel": "Journal", "owner": "Lead",
            "target_date": "2026-12-01", "status": "Draft", "open_access": True, "lay_summary": False,
            "data_statement": True, "code_available": True, "accessibility_review": False, "priority": "High",
            "manuscript_section": "Methods", "section_status": "Draft", "section_word_count": 500,
            "target_word_count": 1000, "claim_id": "C1", "source_analysis_id": "AN1", "figure_table_id": "F1",
            "evidence_status": "Verified", "guideline": "Checklist", "reporting_item": "Outcome definition",
            "reporting_item_status": "Addressed", "author": "Author A", "contribution_role": "Writing",
            "author_approved": True, "conflict_declared": True, "journal": "Journal A", "journal_scope_fit": 85,
            "open_access_fee": 1000, "review_comment_id": "R1", "review_status": "Open",
            "manuscript_version": "v1", "planned_endpoint": "Endpoint A", "reported_endpoint": "Endpoint B",
            "figure_accessibility_complete": False,
        }
    ])
    output = publication_dissemination_workbench(frame, today="2026-07-13")
    expected = {
        "manuscript_progress", "claim_evidence_traceability", "reporting_checklist",
        "reporting_guideline_summary", "authorship_contributions", "journal_selection",
        "figure_table_inventory", "peer_review_workspace", "peer_review_burndown",
        "publication_version_lineage", "protocol_publication_deviations",
        "audience_channel_matrix", "cross_module_impacts",
    }
    assert expected.issubset(output.tables)
    assert output.summary["claims"] == 1
    assert output.summary["traceable_claim_percent"] == 100.0
    assert output.summary["open_peer_review_comments"] == 1
    assert output.summary["protocol_publication_deviations"] == 1


def test_step147_publication_validates_journal_fit_range():
    frame = pd.DataFrame([
        {
            "output_id": "O1", "title": "Paper", "audience": "Researchers", "channel": "Journal", "owner": "Lead",
            "target_date": "2026-12-01", "status": "Draft", "open_access": True, "lay_summary": False,
            "data_statement": True, "code_available": True, "accessibility_review": False, "priority": "High",
            "journal_scope_fit": 101,
        }
    ])
    with pytest.raises(ValueError, match="between 0 and 100"):
        publication_dissemination_workbench(frame, today="2026-07-13")


def test_step147_renderer_declares_operational_visual_depth_and_documents():
    text = (ROOT / "src/biointel/research_planning/lifecycle_renderer.py").read_text(encoding="utf-8")
    visual_titles = [
        "Consent version lineage", "Participant consent option matrix", "Privacy data-flow map",
        "Operational lifecycle readiness", "Storage growth forecast", "Data lifecycle quality heatmap",
        "Exposure-adjusted incidence", "Interim stopping boundaries", "Benefit-risk planning view",
        "Manuscript section completion", "Claim-evidence traceability graph", "Open-science dependency matrix",
    ]
    for title in visual_titles:
        assert title in text
    for document in [
        "ETHICS_SUBMISSION_AND_CONSENT_OPERATIONS.md",
        "DATA_MANAGEMENT_AND_REPOSITORY_DEPOSIT_PLAN.md",
        "INTERIM_MONITORING_AND_SAFETY_REVIEW_PACKAGE.md",
        "MANUSCRIPT_AND_DISSEMINATION_PACKAGE.md",
    ]:
        assert document in text


def test_step147_templates_expose_operational_columns():
    templates = {
        "research_ethics_consent_template.csv": {"consent_version", "participant_id", "query_due_date", "data_destination"},
        "research_data_fair_planning_template.csv": {"checksum_verified", "schema_present_fields", "monthly_growth_mb", "last_restore_test"},
        "research_interim_monitoring_safety_template.csv": {"person_time_days", "system_organ_class", "report_due_date", "conditional_power"},
        "research_publication_dissemination_template.csv": {"manuscript_section", "claim_id", "author_approved", "review_status"},
    }
    base = ROOT / "data/research_planning_templates"
    for filename, expected in templates.items():
        columns = set(pd.read_csv(base / filename, nrows=0).columns)
        assert expected.issubset(columns)
