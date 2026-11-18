from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

import pandas as pd

from biointel.research_planning.advanced_profiles import ADVANCED_PROFILES
from biointel.research_planning.amendment import compare_plans, impact_summary
from biointel.research_planning.assumptions import AssumptionRegistry
from biointel.research_planning.burden_budget import BudgetItem, BurdenItem, calculate_participant_burden, simulate_budget, site_workload_simulation
from biointel.research_planning.calculation_verification import verify_two_group_continuous
from biointel.research_planning.catalog import PLANNING_MODULES
from biointel.research_planning.collaboration import PlanningCollaborationStore
from biointel.research_planning.command_center import build_command_center, recommended_actions
from biointel.research_planning.consistency import audit_study_design, consistency_summary
from biointel.research_planning.digital_thread import ResearchDigitalThreadStore, ThreadLink, ThreadNode
from biointel.research_planning.estimands import Estimand, IntercurrentEvent, estimand_flow, estimand_validation_table
from biointel.research_planning.export import build_bundle
from biointel.research_planning.interoperability import build_define_xml_readiness, build_fhir_questionnaire, build_odm_xml, build_variable_mapping
from biointel.research_planning.scientific import analyse, demo_frame
from biointel.research_planning.simulation import DEFAULT_SCENARIOS, simulate_scenarios
from biointel.research_planning.standards import readiness_summary, validate_readiness
from biointel.ui.navigation import PAGE_CATALOG


def _ready_plan() -> dict:
    return {
        "protocol_id": "P-001", "protocol_version": "1.0", "background": "Background", "rationale": "Rationale",
        "primary_objective": "Objective", "secondary_objectives": ["Secondary"], "study_design": "Parallel",
        "allocation": "1:1", "blinding": "Assessor", "inclusion_criteria": ["A"], "exclusion_criteria": ["B"],
        "recruitment_setting": "Sites", "intervention": "Treatment", "comparator": "Control", "adherence_plan": "Tracked",
        "primary_endpoint": "primary_outcome", "endpoint_timing": "Week 12", "measurement_method": "Validated",
        "sample_size": 200, "effect_size": 0.35, "alpha": 0.05, "power": 0.8, "crf_plan": "CRF",
        "data_management_plan": "DMP", "monitoring_plan": "Monitoring", "ethics_status": "Planned",
        "consent_plan": "Consent", "dissemination_plan": "Publish", "critical_to_quality": ["Endpoint"],
        "risk_register": ["Recruitment"], "risk_owner": "Owner", "risk_trigger": "Threshold", "safety_plan": "Safety",
        "participant_burden": "Assessed", "privacy_plan": "Privacy", "source_data_plan": "Source", "audit_trail": "Audit",
        "data_quality_controls": ["Range"], "estimand_treatment": "Treatment", "estimand_population": "Population",
        "estimand_variable": "primary_outcome", "intercurrent_events": ["Discontinuation"],
        "intercurrent_strategy": ["Treatment policy"], "population_summary": "Difference", "estimator": "ANCOVA",
        "sensitivity_analyses": ["Per protocol"], "objectives": ["Objective"], "endpoints": ["primary_outcome"],
        "activities": ["Visit"], "epochs": ["Treatment"], "crf_variables": ["primary_outcome", "site"],
        "controlled_terminology": ["Status"], "units": ["SI"], "sdtm_mapping": True, "unique_subject_id": "USUBJID",
        "adam_mapping": True, "derivations": True, "analysis_flags": True, "fhir_mapping": True,
        "source_provenance": "source", "randomization_strata": ["site"], "protocol_sample_size": 200,
        "power_sample_size": 200, "visits": ["Baseline"], "biospecimen_visits": ["Baseline"],
        "estimand_ids": ["EST-001"], "sap_estimand_ids": ["EST-001"], "protocol_sha256": "a" * 64,
        "prereg_protocol_sha256": "a" * 64, "estimated_eligible_population": 500, "budget_total": 100000,
        "budget_contingency_fraction": 0.1,
    }


def test_step142_advanced_profiles_cover_all_eighteen_existing_planning_modules():
    expected = {module.key for module in PLANNING_MODULES} | {"biostatistics_design", "synthetic_cohort_trial"}
    assert set(ADVANCED_PROFILES) == expected
    assert all(len(profile.advanced_features) >= 12 for profile in ADVANCED_PROFILES.values())
    assert all(len(profile.advanced_visuals) >= 6 for profile in ADVANCED_PROFILES.values())
    assert all(profile.critical_checks for profile in ADVANCED_PROFILES.values())


def test_step142_digital_thread_persists_links_and_impact(tmp_path: Path):
    store = ResearchDigitalThreadStore(tmp_path / "thread.sqlite")
    a = store.upsert_node(ThreadNode("", "objective", "Primary objective", "study_protocol_designer"))
    b = store.upsert_node(ThreadNode("", "endpoint", "Primary endpoint", "endpoint_outcome_strategy"))
    c = store.upsert_node(ThreadNode("", "analysis", "Primary analysis", "statistical_analysis_plan"))
    store.link(ThreadLink(a, b, "drives"))
    store.link(ThreadLink(b, c, "analysed_by"))
    assert len(store.nodes()) == 3
    assert len(store.links()) == 2
    impact = store.impact_candidates(a)
    assert set(impact["node_id"]) == {b, c}
    assert store.orphan_report().empty


def test_step142_standards_and_estimand_readiness():
    standards = validate_readiness(_ready_plan())
    summary = readiness_summary(standards)
    assert summary["requirements"] >= 20
    assert summary["score"] == 100.0
    estimand = Estimand(
        "EST-001", "Objective", "Treatment", "Population", "Outcome", "Difference", "ANCOVA",
        (IntercurrentEvent("Discontinuation", "treatment policy"),), ("Tipping point",),
    )
    validation = estimand_validation_table([estimand])
    assert validation.iloc[0]["status"] == "Ready"
    assert not estimand_flow([estimand]).empty


def test_step142_scenario_simulation_is_deterministic_and_bounded():
    first = simulate_scenarios(DEFAULT_SCENARIOS, 500, 142)
    second = simulate_scenarios(DEFAULT_SCENARIOS, 500, 142)
    pd.testing.assert_frame_equal(first[0], second[0])
    assert len(first[0]) == 4
    assert first[0]["probability_target_analyzable"].between(0, 1).all()
    assert not first[1].empty and not first[2].empty


def test_step142_amendment_and_consistency_audits():
    changes = compare_plans({"primary_endpoint": "A", "sample_size": 100}, {"primary_endpoint": "B", "sample_size": 120})
    summary = impact_summary(changes)
    assert summary["changes"] == 2
    assert summary["critical"] == 2
    consistency = audit_study_design(_ready_plan())
    con = consistency_summary(consistency)
    assert con["score"] == 100.0


def test_step142_cdisc_fhir_odm_interoperability():
    variables = pd.DataFrame([
        {"variable": "participant_id", "label": "Participant ID", "data_type": "string"},
        {"variable": "lab_value", "label": "Lab value", "data_type": "float", "unit": "SI"},
    ])
    mapping = build_variable_mapping(variables)
    assert set(["cdash_variable", "sdtm_domain", "adam_dataset", "fhir_path"]).issubset(mapping.columns)
    questionnaire = build_fhir_questionnaire(mapping)
    assert questionnaire["resourceType"] == "Questionnaire"
    assert build_odm_xml(mapping).startswith(b"<?xml")
    assert (build_define_xml_readiness(mapping)["status"] == "Ready").all()


def test_step142_assumption_and_collaboration_stores(tmp_path: Path):
    assumptions = AssumptionRegistry(tmp_path / "assumptions.sqlite")
    assumption_id = assumptions.upsert("sample_size_power_studio", "Effect", 0.35, source="Study", sensitivity_low=0.25, sensitivity_high=0.45)
    assert assumption_id == 1
    assert len(assumptions.list()) == 1
    assert assumptions.sensitivity_gaps().empty

    collaboration = PlanningCollaborationStore(tmp_path / "collab.sqlite")
    thread_id = collaboration.create_thread("study_protocol_designer", "OBJ-1", "Review objective", "Reviewer")
    collaboration.add_comment(thread_id, "Reviewer", "Looks clear", "Statistician")
    request_id = collaboration.propose_change("study_protocol_designer", "OBJ-1", "Reviewer", "Clarify wording", "Improve precision")
    collaboration.decide_change(request_id, "Accepted", "Lead", "Approved")
    assert len(collaboration.threads()) == 1
    assert len(collaboration.comments(thread_id)) == 1
    assert collaboration.change_requests().iloc[0]["decision"] == "Accepted"


def test_step142_calculation_verification_burden_budget_and_sites():
    verification = verify_two_group_continuous(0.35, 0.05, 0.8)
    assert verification.status == "Verified"
    burden, burden_summary = calculate_participant_burden([
        BurdenItem("Visit", 3, 60, 30, 10, 15, False, 2),
    ])
    assert not burden.empty and burden_summary["total_visits"] == 3
    budget, distribution, budget_summary = simulate_budget([
        BudgetItem("Participants", "participant", 100, 1000, 0.1),
    ], 500, 142, 0.1)
    assert not budget.empty and len(distribution) == 500 and budget_summary["median_total"] > 0
    sites = site_workload_simulation(pd.DataFrame([{"site": "A", "participants": 20, "staff_fte": 1, "working_hours_per_month": 140}]), 4, 60)
    assert sites.iloc[0]["status"] in {"Within capacity", "At risk", "Overloaded"}


def test_step142_command_center_and_actions():
    readiness, blockers, standards, summary = build_command_center(_ready_plan())
    assert len(readiness) == 8
    assert summary["overall_readiness"] > 0
    assert len(standards) >= 20
    assert not recommended_actions(blockers).empty


def test_step142_exports_include_connected_planning_os_contracts():
    for module in PLANNING_MODULES:
        result = analyse(module.key, demo_frame(module.key, 24))
        payload, manifest = build_bundle(module, result)
        assert manifest["bundle_sha256"]
        with ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
            assert "planning_os_capabilities.json" in names
            assert "standards_readiness_requirements.json" in names
            assert "module_contract.json" in names


def test_step142_navigation_has_research_planning_modules_and_pages_exist():
    planning = [page for page in PAGE_CATALOG if page.category == "Research Planning"]
    assert len(planning) == 24
    titles = {page.title for page in planning}
    assert "Research Planning Command Center" in titles
    assert "Research Budget & Participant Burden Studio" in titles
    root = Path(__file__).resolve().parents[1]
    assert all((root / page.path).exists() for page in planning)


def test_step142_renderers_are_connected_to_all_eighteen_existing_modules():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "src/biointel/research_planning/renderer.py").read_text()
    biostatistics = (root / "pages/121_Biostatistics_Power_and_Experimental_Design_Studio.py").read_text()
    synthetic = (root / "pages/186_Synthetic_Cohort_Trial_Simulation_Lab.py").read_text()
    assert "render_connected_planning_os(module.key" in renderer
    assert 'render_connected_planning_os("biostatistics_design"' in biostatistics
    assert '_render_connected_planning_os("synthetic_cohort_trial"' in synthetic
