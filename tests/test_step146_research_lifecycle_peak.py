from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from biointel.research_planning.command_center import build_command_center
from biointel.research_planning.digital_thread import ResearchDigitalThreadStore, ThreadLink, ThreadNode
from biointel.research_planning.lifecycle_engines import (
    LIFECYCLE_ENGINE_CATALOG,
    ethics_consent_workbench,
    fair_data_management_workbench,
    interim_monitoring_safety_workbench,
    publication_dissemination_workbench,
)


ROOT = Path(__file__).resolve().parents[1]


def test_step146_lifecycle_engine_catalog_and_new_pages_are_complete():
    assert set(LIFECYCLE_ENGINE_CATALOG) == {
        "research_ethics_consent",
        "research_data_fair_planning",
        "research_interim_monitoring_safety",
        "research_publication_dissemination",
    }
    pages = {
        "pages/223_Research_Ethics_Consent_Participant_Protection_Studio.py",
        "pages/224_Research_Data_Management_FAIR_Planning_Studio.py",
        "pages/225_Data_Monitoring_Interim_Review_Safety_Studio.py",
        "pages/226_Publication_Dissemination_Knowledge_Translation_Studio.py",
    }
    for page in pages:
        text = (ROOT / page).read_text(encoding="utf-8")
        assert "render_lifecycle_module" in text
        assert "render_peak_visual_suite" in text


def test_step146_ethics_consent_readiness_blockers_and_hashes():
    frame = pd.DataFrame([
        {"item_id": "E1", "domain": "Consent", "requirement": "Consent form", "status": "Ready", "risk_level": "High", "vulnerable_group": "All", "consent_required": True, "privacy_sensitive": True, "owner": "Ethics", "evidence_reference": "consent-v1"},
        {"item_id": "E2", "domain": "Safeguards", "requirement": "Vulnerable group safeguards", "status": "Not started", "risk_level": "Critical", "vulnerable_group": "Vulnerable", "consent_required": True, "privacy_sensitive": True, "owner": "", "evidence_reference": ""},
    ])
    output = ethics_consent_workbench(frame)
    assert output.summary["requirements"] == 2
    assert output.summary["critical_blockers"] >= 1
    assert output.summary["consent_coverage_percent"] == 50.0
    assert output.primary["weighted_gap"].max() > 0
    assert len(output.manifest()["manifest_sha256"]) == 64
    with pytest.raises(ValueError, match="unique"):
        ethics_consent_workbench(pd.concat([frame, frame.iloc[[0]]], ignore_index=True))


def test_step146_fair_data_management_scores_and_backup_controls():
    frame = pd.DataFrame([
        {"asset_id": "A1", "data_type": "Table", "format": "CSV", "metadata_standard": "Dictionary", "persistent_id": "local:a1", "access_level": "Controlled", "retention_years": 10, "repository": "Archive", "licence": "Research use", "owner": "Steward", "backup_copies": 3, "encryption": "AES-256"},
        {"asset_id": "A2", "data_type": "Code", "format": "BIN", "metadata_standard": "", "persistent_id": "", "access_level": "Internal", "retention_years": 0, "repository": "", "licence": "", "owner": "", "backup_copies": 0, "encryption": "No"},
    ])
    output = fair_data_management_workbench(frame)
    assert output.summary["assets"] == 2
    assert 0 <= output.summary["overall_fair_score"] <= 100
    assert output.summary["critical_issues"] >= 1
    assert set(output.tables["fair_dimensions"]["dimension"]) == {"Findable", "Accessible", "Interoperable", "Reusable"}
    assert output.primary.loc[output.primary["asset_id"] == "A1", "fair_score"].iloc[0] > output.primary.loc[output.primary["asset_id"] == "A2", "fair_score"].iloc[0]
    bad = frame.copy()
    bad.loc[0, "retention_years"] = -1
    with pytest.raises(ValueError, match="Retention years"):
        fair_data_management_workbench(bad)


def test_step146_interim_monitoring_signal_threshold_and_rate_ratio():
    frame = pd.DataFrame([
        {"participant_id": "P1", "arm": "Control", "event_id": "EV1", "event_type": "Headache", "severity": "Mild", "serious": False, "relatedness": "Unlikely", "event_day": 5, "resolved": True, "reportable": False},
        {"participant_id": "P2", "arm": "Treatment", "event_id": "EV2", "event_type": "Hospitalisation", "severity": "Severe", "serious": True, "relatedness": "Possible", "event_day": 10, "resolved": False, "reportable": True},
        {"participant_id": "P3", "arm": "Treatment", "event_id": "EV3", "event_type": "Hospitalisation", "severity": "Severe", "serious": True, "relatedness": "Probable", "event_day": 15, "resolved": False, "reportable": True},
    ])
    output = interim_monitoring_safety_workbench(frame, serious_rate_threshold=0.25)
    assert output.summary["serious_events"] == 2
    assert output.summary["immediate_reviews"] == 2
    assert output.summary["arms_over_threshold"] >= 1
    assert not output.tables["arm_comparisons"].empty
    assert output.tables["timeline"]["cumulative_events"].ge(1).all()
    with pytest.raises(ValueError, match="between 0 and 1"):
        interim_monitoring_safety_workbench(frame, serious_rate_threshold=1.1)


def test_step146_publication_dissemination_open_science_and_overdue():
    frame = pd.DataFrame([
        {"output_id": "O1", "title": "Manuscript", "audience": "Researchers", "channel": "Journal", "owner": "Lead", "target_date": "2026-01-01", "status": "Draft", "open_access": True, "lay_summary": False, "data_statement": True, "code_available": True, "accessibility_review": False, "priority": "Critical"},
        {"output_id": "O2", "title": "Participant summary", "audience": "Participants", "channel": "Lay summary", "owner": "Engagement", "target_date": "2027-01-01", "status": "Complete", "open_access": True, "lay_summary": True, "data_statement": True, "code_available": False, "accessibility_review": True, "priority": "High"},
    ])
    output = publication_dissemination_workbench(frame, today="2026-07-13")
    assert output.summary["outputs"] == 2
    assert output.summary["overdue_outputs"] == 1
    assert output.summary["audiences_covered"] == 2
    assert output.primary["open_science_score"].between(0, 100).all()
    assert not output.tables["audience_summary"].empty


def test_step146_command_center_is_backwards_compatible_and_expands_with_lifecycle_scores():
    basic_plan = {
        "protocol_id": "P1",
        "protocol_version": "1.0",
        "primary_endpoint": "Outcome",
        "protocol_sample_size": 100,
        "power_sample_size": 100,
        "estimated_eligible_population": 200,
    }
    readiness, _, _, _ = build_command_center(basic_plan)
    assert len(readiness) == 8
    lifecycle_plan = dict(basic_plan, ethics_consent_score=80, fair_data_score=75, monitoring_readiness_score=65, dissemination_readiness_score=60)
    lifecycle_readiness, _, _, summary = build_command_center(lifecycle_plan)
    assert len(lifecycle_readiness) == 12
    assert {"Ethics and consent", "FAIR data management", "Interim monitoring", "Dissemination readiness"}.issubset(set(lifecycle_readiness["dimension"]))
    assert summary["overall_readiness"] > 0


def test_step146_navigation_and_existing_module_lifecycle_integration():
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    for key in LIFECYCLE_ENGINE_CATALOG:
        assert f"'{key}'" in navigation
    renderer = (ROOT / "src/biointel/research_planning/renderer.py").read_text(encoding="utf-8")
    assert "Lifecycle & governance" in renderer
    assert "render_lifecycle_readiness_panel" in renderer
    for page in [
        "pages/121_Biostatistics_Power_and_Experimental_Design_Studio.py",
        "pages/186_Synthetic_Cohort_Trial_Simulation_Lab.py",
        "pages/222_Research_Budget_Participant_Burden_Studio.py",
    ]:
        assert "render_lifecycle_readiness_panel" in (ROOT / page).read_text(encoding="utf-8")


def test_step146_lifecycle_nodes_are_supported_by_digital_thread(tmp_path: Path):
    store = ResearchDigitalThreadStore(tmp_path / "thread.sqlite")
    protocol = store.upsert_node(ThreadNode("", "protocol", "Protocol", "study_protocol_designer", "Draft", {}))
    ethics = store.upsert_node(ThreadNode("", "ethics_plan", "Ethics plan", "research_ethics_consent", "Needs review", {"score": 70}))
    fair = store.upsert_node(ThreadNode("", "data_management_plan", "Data plan", "research_data_fair_planning", "Reviewed", {"score": 85}))
    store.link(ThreadLink(protocol, ethics, "governs_lifecycle", True))
    store.link(ThreadLink(protocol, fair, "governs_lifecycle", True))
    assert len(store.nodes()) == 3
    assert len(store.links()) == 2
    assert store.impact_candidates(protocol)["node_id"].nunique() == 2
