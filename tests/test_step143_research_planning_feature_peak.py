from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from biointel.research_planning.catalog import PLANNING_MODULES
from biointel.research_planning.export import build_bundle
from biointel.research_planning.feature_density import (
    allocation_audit,
    assumption_sensitivity,
    budget_cashflow,
    build_study_map,
    build_tfl_shells,
    change_impact,
    composite_endpoint_contribution,
    evaluate_cohort_rules,
    feature_inventory,
    generate_crf_test_cases,
    generate_synthetic_cohort,
    get_peak_profile,
    method_compatibility_matrix,
    minimization_randomization,
    participant_equity_burden,
    plan_quality_matrix,
    portfolio_readiness,
    profile_digest,
    protocol_redline,
    protocol_schedule_matrix,
    reviewer_timeline,
    score_endpoints,
    synthetic_privacy_utility,
    validate_crf_logic,
)
from biointel.research_planning.scientific import analyse, demo_frame


ALL_KEYS = {module.key for module in PLANNING_MODULES} | {
    "biostatistics_design",
    "synthetic_cohort_trial",
    "research_planning_command_center",
    "research_budget_participant_burden",
}


def _plan() -> dict:
    return {
        "primary_objective": "Objective",
        "primary_endpoint": "Outcome",
        "estimand_ids": ["EST-1"],
        "estimand_variable": "Outcome",
        "estimator": "ANCOVA",
        "primary_output": "Table 1",
        "effect_size": 0.35,
        "protocol_sample_size": 200,
        "power_sample_size": 200,
        "budget_total": 1000000,
        "duration_months": 18,
        "protocol_sha256": "a" * 64,
        "source_provenance": "Source",
        "reviewer": "Reviewer",
        "review_status": "Reviewed",
        "protocol_id": "P-1",
        "protocol_version": "1.0",
    }


def test_step143_profiles_cover_twenty_research_planning_pages():
    assert len(ALL_KEYS) == 20
    for key in ALL_KEYS:
        profile = get_peak_profile(key)
        inventory = feature_inventory(key)
        assert profile.feature_count >= 28
        assert len(profile.signature_visuals) >= 8
        assert len(profile.validation_checks) >= 4
        assert len(inventory) == profile.feature_count
        assert len(profile_digest(key)) == 64
        assert set(inventory["implementation_status"]) == {"Implemented"}


def test_step143_linked_study_map_sensitivity_quality_and_impact():
    nodes, edges = build_study_map(_plan())
    assert len(nodes) == 6 and len(edges) == 5
    sensitivity = assumption_sensitivity(0.35, 200, 1000000, 18)
    assert list(sensitivity["scenario"]) == ["Stress", "Conservative", "Base", "Optimistic"]
    assert sensitivity.loc[sensitivity["scenario"] == "Stress", "required_sample_size"].iloc[0] > 200
    quality = plan_quality_matrix(_plan())
    assert quality["score"].between(0, 100).all()
    impact = change_impact({**_plan(), "primary_endpoint": "Old"}, _plan())
    assert "statistical_analysis_plan" in set(impact["impacted_module"])
    assert set(impact["severity"]) == {"Critical"}


def test_step143_portfolio_and_budget_models():
    studies = pd.DataFrame([
        {"study_id": "A", "protocol": 90, "statistics": 80, "operations": 70, "data": 80, "risk": 75, "budget": 70, "reproducibility": 85},
        {"study_id": "B", "protocol": 80, "statistics": 75, "operations": 65, "data": 70, "risk": 40, "budget": 60, "reproducibility": 70},
    ])
    result, summary = portfolio_readiness(studies)
    assert summary["studies"] == 2
    assert summary["blocked"] == 1
    assert result["weighted_readiness"].between(0, 100).all()

    items = pd.DataFrame([
        {"category": "Sites", "quantity": 10, "unit_cost": 1000, "start_month": 1, "end_month": 6},
        {"category": "Participants", "quantity": 100, "unit_cost": 200, "start_month": 3, "end_month": 12},
    ])
    table, cashflow, budget = budget_cashflow(items, 12, 0.03, 1.0, 0.10)
    assert len(table) == 2 and len(cashflow) == 12
    assert budget["total_with_contingency"] > budget["base_total"]
    assert cashflow["cumulative_cost"].is_monotonic_increasing

    burden, burden_summary = participant_equity_burden(pd.DataFrame([
        {"subgroup": "A", "visits": 4, "visit_minutes": 60, "travel_minutes": 20, "questionnaire_minutes": 10, "digital_access_score": 1, "discomfort_score": 2},
        {"subgroup": "B", "visits": 4, "visit_minutes": 60, "travel_minutes": 120, "questionnaire_minutes": 20, "digital_access_score": 3, "discomfort_score": 4},
    ]))
    assert burden_summary["equity_gap"] > 0
    assert len(burden) == 2


def test_step143_protocol_crf_and_cohort_logic():
    schedule = pd.DataFrame([
        {"activity": "Consent", "visit": "Screen", "day": -7, "required": True},
        {"activity": "Outcome", "visit": "Week 12", "day": 84, "required": True},
    ])
    matrix, days = protocol_schedule_matrix(schedule)
    assert matrix.shape == (2, 2)
    assert list(days["day"]) == [-7, 84]
    redline = protocol_redline({"primary_endpoint": "A"}, {"primary_endpoint": "B"})
    assert redline.iloc[0]["impact_required"]

    fields = pd.DataFrame([
        {"variable": "consent", "data_type": "boolean", "required": True, "show_when_variable": "", "show_when_value": ""},
        {"variable": "outcome", "data_type": "float", "required": True, "show_when_variable": "consent", "show_when_value": "True"},
    ])
    validated, issues = validate_crf_logic(fields)
    assert issues.empty
    assert set(validated["logic_status"]) == {"Ready"}
    tests = generate_crf_test_cases(fields)
    assert len(tests) == 5

    cyclic = fields.copy()
    cyclic.loc[0, "show_when_variable"] = "outcome"
    _, cyclic_issues = validate_crf_logic(cyclic)
    assert "Skip-logic dependency cycle" in set(cyclic_issues["issue"])

    participants = pd.DataFrame({"participant_id": ["P1", "P2", "P3"], "age": [20, 17, 60], "diagnosis": ["Target", "Target", "Other"]})
    rules = pd.DataFrame([
        {"rule_id": "R1", "field": "age", "operator": ">=", "value": "18", "logic": "AND"},
        {"rule_id": "R2", "field": "diagnosis", "operator": "==", "value": "Target", "logic": "AND"},
    ])
    cohort, audit = evaluate_cohort_rules(participants, rules)
    assert cohort["eligible"].sum() == 1
    assert audit.iloc[-1]["eligible_after_rule"] == 1


def test_step143_endpoint_randomization_and_sap():
    endpoints = score_endpoints(pd.DataFrame([
        {"endpoint": "A", "clinical_relevance": 90, "validity": 90, "reliability": 90, "burden": 20, "missingness_risk": 10},
        {"endpoint": "B", "clinical_relevance": 70, "validity": 70, "reliability": 70, "burden": 50, "missingness_risk": 30},
    ]))
    assert endpoints.iloc[0]["endpoint"] == "A"
    assert endpoints.iloc[0]["recommended_role"] == "Primary candidate"

    contribution = composite_endpoint_contribution(pd.DataFrame([
        {"component": "A", "events": 50, "total_participants": 200, "clinical_weight": 1.0},
        {"component": "B", "events": 25, "total_participants": 200, "clinical_weight": 0.5},
    ]))
    assert np.isclose(contribution["contribution_fraction"].sum(), 1.0)

    participants = pd.DataFrame({
        "participant_id": [f"P{i}" for i in range(60)],
        "site": ["A", "B", "C"] * 20,
        "severity": ["Mild", "Severe"] * 30,
    })
    first = minimization_randomization(participants, ["site", "severity"], seed=143)
    second = minimization_randomization(participants, ["site", "severity"], seed=143)
    pd.testing.assert_frame_equal(first, second)
    audit, summary = allocation_audit(first, ["site", "severity"])
    assert summary["participants"] == 60
    assert summary["normalized_entropy"] > 0.9
    assert summary["maximum_stratum_imbalance"] <= 3
    assert not audit.empty

    shells = build_tfl_shells(pd.DataFrame([
        {"analysis_id": "A1", "endpoint": "Outcome", "population": "ITT", "model": "ANCOVA", "output_type": "Table", "source_dataset": "ADEFF"},
        {"analysis_id": "A2", "endpoint": "Outcome", "population": "ITT", "model": "ANCOVA", "output_type": "Figure", "source_dataset": "ADEFF"},
    ]))
    assert set(shells["shell_status"]) == {"Ready"}
    assert shells["lineage_key"].str.contains("ADEFF").all()
    assert len(method_compatibility_matrix()) == 16


def test_step143_synthetic_cohort_privacy_and_review_timeline():
    synthetic = generate_synthetic_cohort(250, 143, 0.05, 0.2)
    assert len(synthetic) == 250
    assert synthetic["synthetic_record"].all()
    real = synthetic.copy()
    real["age"] = real["age"] + 1
    comparison, summary = synthetic_privacy_utility(real, synthetic)
    assert summary["variables"] >= 5
    assert comparison["utility_score"].between(0, 100).all()

    timeline = reviewer_timeline(pd.DataFrame([
        {"timestamp": "2026-01-02T10:00:00Z", "actor": "B", "action": "Review", "module_key": "m", "status": "Reviewed"},
        {"timestamp": "2026-01-01T10:00:00Z", "actor": "A", "action": "Create", "module_key": "m", "status": "Draft"},
    ]))
    assert list(timeline["event_number"]) == [1, 2]
    assert timeline.iloc[0]["actor"] == "A"


def test_step143_export_bundle_contains_peak_feature_contract():
    module = PLANNING_MODULES[0]
    result = analyse(module.key, demo_frame(module.key, 30))
    payload, manifest = build_bundle(module, result)
    assert manifest["bundle_sha256"]
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "peak_feature_contract.json" in names
        assert "planning_os_capabilities.json" in names
        contract = archive.read("peak_feature_contract.json")
        assert b"signature_visuals" in contract


def test_step143_renderers_are_integrated_into_all_page_types():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "src/biointel/research_planning/renderer.py").read_text()
    assert "render_peak_feature_lab(module.key" in renderer
    for page in (
        "pages/121_Biostatistics_Power_and_Experimental_Design_Studio.py",
        "pages/186_Synthetic_Cohort_Trial_Simulation_Lab.py",
        "pages/221_Research_Planning_Command_Center.py",
        "pages/222_Research_Budget_Participant_Burden_Studio.py",
    ):
        assert "render_peak_feature_lab" in (root / page).read_text()


def test_step143_validation_guards_reject_invalid_inputs():
    with pytest.raises(ValueError):
        assumption_sensitivity(-1, 10, 1, 1)
    with pytest.raises(ValueError):
        portfolio_readiness(pd.DataFrame([{"study_id": "A"}]))
    with pytest.raises(ValueError):
        budget_cashflow(pd.DataFrame([{"category": "A"}]), 12)
    with pytest.raises(ValueError):
        minimization_randomization(pd.DataFrame({"participant_id": ["A", "A"]}), [])
    with pytest.raises(ValueError):
        generate_synthetic_cohort(5)
