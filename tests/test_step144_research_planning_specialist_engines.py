from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from biointel.research_planning.catalog import get_module
from biointel.research_planning.export import build_bundle
from biointel.research_planning.feature_density import PEAK_FEATURE_PROFILES, get_peak_profile
from biointel.research_planning.scientific import analyse, demo_frame
from biointel.research_planning.specialist_engines import (
    SPECIALIST_ENGINE_CATALOG,
    alpha_spending_boundaries,
    bayesian_assurance,
    bayesian_recruitment_update,
    biomarker_validation_workbench,
    build_biospecimen_inventory,
    cluster_design_effect,
    detect_temperature_excursions,
    dose_escalation_decisions,
    fit_response_surface,
    fmea_risk_workbench,
    generate_central_composite_design,
    literature_evidence_workbench,
    pert_schedule_simulation,
    preregistration_integrity_audit,
    simulate_group_sequential_trial,
    simulate_recruitment,
    specialist_engine_contract,
    stepped_wedge_variance,
)


SPECIALIST_KEYS = {
    "sample_size_power_studio",
    "clinical_trial_design_studio",
    "experimental_design_doe",
    "biomarker_study_planning",
    "sampling_biospecimen_planning",
    "research_feasibility_recruitment",
    "research_timeline_dependencies",
    "research_risk_mitigation",
    "evidence_gap_literature_planning",
    "preregistration_reproducibility",
}


def test_step144_explicit_profiles_and_engine_contracts_cover_all_twenty_modules():
    assert len(PEAK_FEATURE_PROFILES) == 20
    assert set(SPECIALIST_ENGINE_CATALOG) == SPECIALIST_KEYS
    for key in SPECIALIST_KEYS:
        profile = get_peak_profile(key)
        assert profile.feature_count >= 36
        assert len(profile.signature_visuals) >= 8
        contract = specialist_engine_contract(key)
        assert contract["specialist_engine"] is True
        assert len(contract["contract_sha256"]) == 64


def test_step144_literature_dedup_prisma_meta_analysis_and_contradiction():
    studies = pd.DataFrame([
        {"study_id": "S1", "title": "Randomized trial A", "doi": "https://doi.org/10.1000/A", "year": 2022, "design": "RCT", "quality": "High", "effect": 0.4, "standard_error": 0.1, "screening_status": "Included", "population": "Adults", "outcome": "Outcome"},
        {"study_id": "S2", "title": "Prospective cohort A", "doi": "10.1000/B", "year": 2023, "design": "Prospective cohort", "quality": "Moderate", "effect": -0.1, "standard_error": 0.2, "screening_status": "Included", "population": "Adults", "outcome": "Outcome"},
        {"study_id": "S3", "title": "Randomized trial A", "doi": "doi:10.1000/a", "year": 2022, "design": "RCT", "quality": "High", "effect": 0.4, "standard_error": 0.1, "screening_status": "Included", "population": "Adults", "outcome": "Outcome"},
    ])
    output = literature_evidence_workbench(studies)
    assert output.summary["exact_duplicate_records"] == 1
    assert output.summary["included_unique_studies"] == 2
    assert output.tables["prisma"].set_index("stage").loc["Meta-analysis", "records"] == 2
    assert output.tables["contradiction_matrix"]["contradiction_flag"].any()
    assert len(output.manifest()["manifest_sha256"]) == 64


def test_step144_preregistration_detects_switches_and_hashes_artifacts():
    items = pd.DataFrame([
        {"item": "Primary endpoint", "section": "Endpoint", "planned_value": "A", "executed_value": "A", "reported_value": "B", "locked": True, "deviation_reason": ""},
        {"item": "Population", "section": "Analysis", "planned_value": "ITT", "executed_value": "ITT", "reported_value": "ITT", "locked": True, "deviation_reason": ""},
    ])
    artifacts = pd.DataFrame([
        {"artifact": "plan.pdf", "declared_sha256": "a" * 64},
        {"artifact": "code.zip", "declared_sha256": "bad"},
    ])
    output = preregistration_integrity_audit(items, artifacts)
    assert output.summary["outcome_switches"] == 1
    assert output.summary["undisclosed_deviations"] == 1
    assert output.summary["verified_artifacts"] == 1
    assert output.primary["item_lock_sha256"].str.len().eq(64).all()


def test_step144_group_sequential_trial_and_dose_escalation_are_bounded_and_reproducible():
    boundaries = alpha_spending_boundaries(0.05, [0.33, 0.67, 1.0], "OBrien-Fleming")
    assert boundaries["information_fraction"].is_monotonic_increasing
    assert boundaries["cumulative_alpha"].is_monotonic_increasing
    first = simulate_group_sequential_trial(0.4, 240, simulations=1000, seed=144)
    second = simulate_group_sequential_trial(0.4, 240, simulations=1000, seed=144)
    assert first.summary == second.summary
    assert 0 <= first.summary["estimated_type1_error"] <= 0.1
    dose = dose_escalation_decisions(pd.DataFrame([
        {"dose": 1, "participants": 3, "dose_limiting_toxicities": 0},
        {"dose": 2, "participants": 6, "dose_limiting_toxicities": 1},
        {"dose": 3, "participants": 3, "dose_limiting_toxicities": 2},
    ]))
    assert dose.summary["recommended_mtd_screening"] == 2.0
    with pytest.raises(ValueError):
        simulate_group_sequential_trial(0.4, 240, simulations=100)


def test_step144_doe_generation_fit_alias_and_diagnostics():
    design = generate_central_composite_design(["temperature", "ph"], center_points=4, seed=144)
    design["response"] = 10 + 2 * design["temperature"] - design["ph"] + 0.8 * design["temperature"] * design["ph"]
    output = fit_response_surface(design, "response", ["temperature", "ph"])
    assert output.summary["rank"] == output.summary["parameters"]
    assert output.summary["r_squared"] > 0.99
    assert {"term", "coefficient"}.issubset(output.primary.columns)
    assert len(design) == 12


def test_step144_biomarker_validation_predictive_values_and_readiness():
    candidates = pd.DataFrame([
        {"biomarker": "A", "validation_n": 500, "prevalence": 0.2, "sensitivity": 0.9, "specificity": 0.9, "analytical_cv": 0.05, "external_validation": True, "cutoff_locked": True},
        {"biomarker": "B", "validation_n": 80, "prevalence": 0.2, "sensitivity": 0.7, "specificity": 0.75, "analytical_cv": 0.25, "external_validation": False, "cutoff_locked": False},
    ])
    output = biomarker_validation_workbench(candidates)
    assert output.primary.iloc[0]["biomarker"] == "A"
    assert output.primary[["ppv", "npv"]].stack().between(0, 1).all()
    assert len(output.tables["predictive_values"]) == 2 * 40 * 2
    assert output.summary["externally_validated"] == 1


def test_step144_assurance_cluster_and_stepped_wedge_planning():
    assurance = bayesian_assurance(0.35, 0.1, [80, 160, 320], draws=1000, seed=144)
    assert assurance["assurance"].is_monotonic_increasing
    assert cluster_design_effect(20, 0.05, 0.2) > 1
    stepped = stepped_wedge_variance(8, 4, 10, 0.05)
    assert stepped["total_participants"] == 320
    assert stepped["treatment_standard_error_standardized"] > 0


def test_step144_recruitment_simulation_bayesian_update_and_rescue():
    sites = pd.DataFrame([
        {"site": "A", "activation_mean": 1, "activation_sd": 0.2, "monthly_rate": 8, "rate_cv": 0.3, "screen_success": 0.7, "retention": 0.9, "capacity": 120},
        {"site": "B", "activation_mean": 3, "activation_sd": 0.8, "monthly_rate": 2, "rate_cv": 0.7, "screen_success": 0.5, "retention": 0.8, "capacity": 50},
    ])
    output = simulate_recruitment(sites, 100, months=18, simulations=500, seed=144)
    assert output.primary["median"].is_monotonic_increasing
    assert output.primary["completion_probability"].between(0, 1).all()
    updated = bayesian_recruitment_update(pd.DataFrame([
        {"site": "A", "observed_months": 3, "observed_recruits": 20},
        {"site": "B", "observed_months": 3, "observed_recruits": 4},
    ]))
    assert (updated["posterior_rate_ci_high"] >= updated["posterior_mean_monthly_rate"]).all()


def test_step144_biospecimen_lineage_volume_and_temperature_excursions():
    plan = pd.DataFrame([
        {"sample_type": "Plasma", "visit": "Baseline", "participants": 4, "volume_ml": 4, "aliquots": 2, "storage_temp": "-80C", "assay_volume_ml": 1, "reserve_fraction": 0.2},
    ])
    output = build_biospecimen_inventory(plan)
    assert output.summary["aliquots"] == 8
    assert output.primary["aliquot_id"].is_unique
    assert output.primary["parent_specimen_id"].nunique() == 4
    logger = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=6, freq="30min", tz="UTC"),
        "container_id": ["SHIP"] * 6,
        "temperature_c": [-80, -65, -65, -65, -80, -80],
    })
    excursions = detect_temperature_excursions(logger, -90, -70, minimum_minutes=30)
    assert len(excursions) == 1
    assert excursions.iloc[0]["duration_minutes"] >= 60


def test_step144_timeline_pert_cycle_detection_and_risk_fmea():
    tasks = pd.DataFrame([
        {"task": "A", "predecessor": "", "optimistic_days": 1, "most_likely_days": 2, "pessimistic_days": 4, "owner": "Lead"},
        {"task": "B", "predecessor": "A", "optimistic_days": 2, "most_likely_days": 3, "pessimistic_days": 6, "owner": "Ops"},
        {"task": "C", "predecessor": "A", "optimistic_days": 1, "most_likely_days": 2, "pessimistic_days": 3, "owner": "Data"},
        {"task": "D", "predecessor": "B;C", "optimistic_days": 1, "most_likely_days": 2, "pessimistic_days": 5, "owner": "Stats"},
    ])
    schedule = pert_schedule_simulation(tasks, simulations=500, seed=144)
    assert schedule.summary["p90_duration_days"] >= schedule.summary["p50_duration_days"]
    assert schedule.primary["criticality_index"].between(0, 1).all()
    cyclic = tasks.copy()
    cyclic.loc[0, "predecessor"] = "D"
    with pytest.raises(ValueError, match="cycle"):
        pert_schedule_simulation(cyclic, simulations=500)

    risks = pd.DataFrame([
        {"risk": "R1", "category": "Ops", "probability": 4, "impact": 5, "detectability": 3, "control_effectiveness": 0.25, "financial_impact": 100000, "time_impact_days": 30, "owner": "Ops"},
        {"risk": "R2", "category": "Data", "probability": 2, "impact": 3, "detectability": 2, "control_effectiveness": 0.75, "financial_impact": 20000, "time_impact_days": 10, "owner": "Data"},
    ])
    risk = fmea_risk_workbench(risks, simulations=1000, seed=144)
    assert (risk.primary["residual_rpn"] <= risk.primary["rpn"]).all()
    assert risk.summary["financial_exposure_p90"] >= risk.summary["financial_exposure_p50"]
    assert not risk.tables["bow_tie"].empty


def test_step144_export_bundle_includes_specialist_engine_contract():
    module = get_module("evidence_gap_literature_planning")
    result = analyse(module.key, demo_frame(module.key, 20))
    payload, manifest = build_bundle(module, result)
    assert manifest["bundle_sha256"]
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "specialist_engine_contract.json" in names
        assert b"specialist_engine" in archive.read("specialist_engine_contract.json")
        assert b"specialist_engine_contract" in archive.read("planning_os_capabilities.json")


def test_step144_specialist_renderer_dispatch_is_integrated():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "src/biointel/research_planning/feature_density_renderer.py").read_text()
    specialist = (root / "src/biointel/research_planning/specialist_renderer.py").read_text()
    assert "has_specialist_renderer(module_key)" in renderer
    for key in SPECIALIST_KEYS:
        assert f'"{key}"' in specialist
