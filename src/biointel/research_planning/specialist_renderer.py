from __future__ import annotations

from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json

from .specialist_engines import (
    EngineOutput,
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


def _show_output(output: EngineOutput, key: str) -> None:
    summary_metrics = []
    for name, value in output.summary.items():
        if isinstance(value, (int, float, str)) and "sha256" not in name:
            display = value
            if isinstance(value, float):
                display = f"{value:,.4g}"
            summary_metrics.append((name.replace("_", " ").title(), display, None))
    if summary_metrics:
        metric_cards(summary_metrics[:4])
    for warning in output.warnings:
        st.warning(warning)
    with st.expander("Specialist engine manifest", expanded=False):
        smart_json(output.manifest(), title="Engine output manifest", download_name=f"{output.engine_key}_manifest.json", key=f"{key}_engine_manifest")


def _sample_size_specialist(key: str) -> dict[str, Any]:
    c1, c2, c3, c4 = st.columns(4)
    effect_mean = float(c1.number_input("Expected standardized effect", 0.001, 5.0, 0.35, 0.01, key=f"{key}_assurance_effect"))
    effect_sd = float(c2.number_input("Effect uncertainty SD", 0.0, 5.0, 0.12, 0.01, key=f"{key}_assurance_sd"))
    alpha = float(c3.number_input("Two-sided alpha", 0.0001, 0.25, 0.05, 0.005, format="%.4f", key=f"{key}_assurance_alpha"))
    draws = int(c4.number_input("Assurance draws", 1_000, 50_000, 10_000, 1_000, key=f"{key}_assurance_draws"))
    sizes = [50, 80, 120, 160, 220, 300, 450, 650]
    assurance = bayesian_assurance(effect_mean, effect_sd, sizes, alpha=alpha, draws=draws, seed=144)
    st.plotly_chart(px.line(assurance, x="total_sample_size", y="assurance", markers=True, range_y=[0, 1], title="Bayesian assurance across total sample size"), width="stretch", key=f"{key}_assurance_chart")
    st.plotly_chart(px.line(assurance, x="total_sample_size", y=["p10_conditional_power", "median_conditional_power", "p90_conditional_power"], range_y=[0, 1], title="Conditional power uncertainty"), width="stretch", key=f"{key}_power_uncertainty")

    st.markdown("#### Group-sequential operating characteristics")
    c5, c6, c7 = st.columns(3)
    total_n = int(c5.number_input("Maximum total sample size", 20, 1_000_000, 300, 10, key=f"{key}_gs_n"))
    looks = int(c6.number_input("Interim looks including final", 2, 10, 3, 1, key=f"{key}_gs_looks"))
    method = c7.selectbox("Alpha spending", ["OBrien-Fleming", "Pocock"], key=f"{key}_gs_method")
    fractions = np.linspace(1 / looks, 1, looks)
    gs = simulate_group_sequential_trial(effect_mean, total_n, alpha, fractions, method, simulations=min(draws, 20_000), seed=144)
    _show_output(gs, f"{key}_gs")
    boundaries = gs.tables["boundaries"]
    st.plotly_chart(px.line(boundaries, x="information_fraction", y="two_sided_z_boundary", markers=True, title="Interim efficacy boundary"), width="stretch", key=f"{key}_gs_boundary")
    st.plotly_chart(px.bar(gs.primary, x="scenario", y="rejection_probability", color="scenario", range_y=[0, 1], title="Estimated type-I error and power"), width="stretch", key=f"{key}_gs_oc")

    st.markdown("#### Cluster and stepped-wedge adjustment")
    c8, c9, c10, c11 = st.columns(4)
    cluster_size = float(c8.number_input("Mean cluster size", 1.0, 10_000.0, 20.0, 1.0, key=f"{key}_cluster_size"))
    icc = float(c9.number_input("ICC", 0.0, 0.999, 0.05, 0.01, key=f"{key}_icc"))
    cv = float(c10.number_input("Cluster-size CV", 0.0, 5.0, 0.20, 0.05, key=f"{key}_cluster_cv"))
    clusters = int(c11.number_input("Stepped-wedge clusters", 4, 500, 12, 1, key=f"{key}_sw_clusters"))
    de = cluster_design_effect(cluster_size, icc, cv)
    sw = stepped_wedge_variance(clusters, 5, max(1, int(cluster_size)), icc)
    metric_cards([
        ("Cluster design effect", f"{de:.3f}", None),
        ("Inflated N from max N", int(np.ceil(total_n * de)), None),
        ("Stepped-wedge standardized SE", f"{sw['treatment_standard_error_standardized']:.4f}", None),
        ("Stepped-wedge participants", sw["total_participants"], None),
    ])
    smart_dataframe(assurance, height=300, key=f"{key}_assurance_table")
    return {"assurance": assurance.to_dict(orient="records"), "group_sequential": gs.manifest(), "cluster_design_effect": de, "stepped_wedge": sw}


def _clinical_trial_specialist(key: str) -> dict[str, Any]:
    c1, c2, c3, c4 = st.columns(4)
    effect = float(c1.number_input("Standardized treatment effect", 0.0, 5.0, 0.40, 0.05, key=f"{key}_trial_effect"))
    maximum_n = int(c2.number_input("Maximum total N", 20, 1_000_000, 240, 10, key=f"{key}_trial_n"))
    looks = int(c3.number_input("Analysis looks", 2, 10, 4, 1, key=f"{key}_trial_looks"))
    simulations = int(c4.number_input("OC simulations", 500, 50_000, 8_000, 500, key=f"{key}_trial_sims"))
    output = simulate_group_sequential_trial(effect, maximum_n, 0.05, np.linspace(1 / looks, 1, looks), "OBrien-Fleming", simulations, 144)
    _show_output(output, f"{key}_trial_oc")
    st.plotly_chart(px.line(output.tables["boundaries"], x="information_fraction", y="two_sided_z_boundary", markers=True, title="Group-sequential decision boundary"), width="stretch", key=f"{key}_trial_boundary")
    st.plotly_chart(px.bar(output.primary, x="scenario", y="rejection_probability", color="scenario", title="Operating characteristics"), width="stretch", key=f"{key}_trial_oc_chart")

    st.markdown("#### Dose-escalation review")
    default = pd.DataFrame([
        {"dose": 1.0, "participants": 3, "dose_limiting_toxicities": 0},
        {"dose": 2.0, "participants": 3, "dose_limiting_toxicities": 1},
        {"dose": 2.0, "participants": 3, "dose_limiting_toxicities": 0},
        {"dose": 3.0, "participants": 3, "dose_limiting_toxicities": 2},
    ]).groupby("dose", as_index=False).sum()
    doses = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_dose_editor"))
    dose_output = dose_escalation_decisions(doses)
    _show_output(dose_output, f"{key}_dose")
    dose_chart = dose_output.primary.copy()
    st.plotly_chart(px.scatter(dose_chart, x="dose", y="toxicity_rate", size="participants", color="decision_3plus3", error_y=dose_chart["toxicity_ci_high"] - dose_chart["toxicity_rate"], error_y_minus=dose_chart["toxicity_rate"] - dose_chart["toxicity_ci_low"], title="Dose toxicity and screening decision"), width="stretch", key=f"{key}_dose_chart")
    smart_dataframe(dose_output.primary, height=300, key=f"{key}_dose_table")
    return {"operating_characteristics": output.manifest(), "dose_escalation": dose_output.manifest()}


def _doe_specialist(key: str) -> dict[str, Any]:
    st.caption("Generate a randomized central-composite design and fit an estimable response-surface model. The starter response is synthetic and visibly labelled.")
    c1, c2, c3 = st.columns(3)
    factor_text = c1.text_input("Numeric factors", "Temperature,pH,Feed", key=f"{key}_doe_factors")
    center_points = int(c2.number_input("Center points", 1, 50, 6, 1, key=f"{key}_doe_centers"))
    noise_sd = float(c3.number_input("Starter response noise SD", 0.0, 100.0, 0.20, 0.05, key=f"{key}_doe_noise"))
    factors = [item.strip() for item in factor_text.split(",") if item.strip()]
    design = generate_central_composite_design(factors, center_points=center_points, seed=144)
    rng = np.random.default_rng(144)
    numeric = design[factors].astype(float)
    response = 10.0 + sum((idx + 1) * numeric[name] for idx, name in enumerate(factors))
    response = response + 1.5 * numeric[factors[0]] ** 2
    if len(factors) > 1:
        response = response - 1.0 * numeric[factors[0]] * numeric[factors[1]]
    design["response"] = response + rng.normal(0, noise_sd, len(design))
    design["response_source"] = "Synthetic starter response"
    edited = pd.DataFrame(st.data_editor(design, num_rows="fixed", width="stretch", key=f"{key}_doe_editor"))
    output = fit_response_surface(edited, "response", factors)
    _show_output(output, f"{key}_doe")
    st.plotly_chart(px.bar(output.primary.sort_values("coefficient", key=abs), x="coefficient", y="term", orientation="h", title="Response-surface coefficients"), width="stretch", key=f"{key}_doe_coeff")
    fitted = output.tables["fitted"]
    st.plotly_chart(px.scatter(fitted, x="predicted_response", y="response", color="residual", title="Observed versus predicted response"), width="stretch", key=f"{key}_doe_fit")
    alias = output.tables["alias"]
    if alias.empty:
        st.success("No term correlations at or above the alias-review threshold.")
    else:
        smart_dataframe(alias, height=260, key=f"{key}_alias")
    smart_dataframe(edited, height=320, key=f"{key}_design")
    return {"design_sha256": sha256(edited.to_csv(index=False).encode()).hexdigest(), "model": output.manifest()}


def _biomarker_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"biomarker": "Marker A", "validation_n": 300, "prevalence": 0.30, "sensitivity": 0.84, "specificity": 0.88, "analytical_cv": 0.08, "external_validation": True, "cutoff_locked": True},
        {"biomarker": "Marker B", "validation_n": 180, "prevalence": 0.30, "sensitivity": 0.78, "specificity": 0.82, "analytical_cv": 0.14, "external_validation": False, "cutoff_locked": True},
        {"biomarker": "Panel C", "validation_n": 120, "prevalence": 0.30, "sensitivity": 0.90, "specificity": 0.72, "analytical_cv": 0.21, "external_validation": False, "cutoff_locked": False},
    ])
    candidates = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_biomarker_editor"))
    output = biomarker_validation_workbench(candidates)
    _show_output(output, f"{key}_biomarker")
    primary = output.primary
    st.plotly_chart(px.scatter(primary, x="youden_j", y="maturity_score", size="validation_n", color="readiness", hover_name="biomarker", title="Diagnostic performance and validation maturity"), width="stretch", key=f"{key}_biomarker_maturity")
    predictive = output.tables["predictive_values"]
    selected = st.selectbox("Predictive-value candidate", primary["biomarker"].tolist(), key=f"{key}_biomarker_selected")
    st.plotly_chart(px.line(predictive.loc[predictive["biomarker"].eq(selected)], x="prevalence", y="value", color="metric", range_y=[0, 1], title=f"PPV/NPV sensitivity · {selected}"), width="stretch", key=f"{key}_biomarker_predictive")
    smart_dataframe(primary, height=320, key=f"{key}_biomarker_table")
    return {"validation": output.manifest()}


def _biospecimen_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"sample_type": "Plasma", "visit": "Baseline", "participants": 50, "volume_ml": 6.0, "aliquots": 4, "storage_temp": "-80C", "assay_volume_ml": 0.8, "reserve_fraction": 0.20},
        {"sample_type": "Serum", "visit": "Week 12", "participants": 50, "volume_ml": 5.0, "aliquots": 4, "storage_temp": "-80C", "assay_volume_ml": 0.7, "reserve_fraction": 0.20},
        {"sample_type": "Whole blood", "visit": "Baseline", "participants": 50, "volume_ml": 4.0, "aliquots": 2, "storage_temp": "-20C", "assay_volume_ml": 1.5, "reserve_fraction": 0.15},
    ])
    plan = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_biospecimen_editor"))
    output = build_biospecimen_inventory(plan)
    _show_output(output, f"{key}_biospecimen")
    storage = output.tables["storage"]
    st.plotly_chart(px.bar(storage, x="storage_temp", y="aliquots", color="sample_type", barmode="group", title="Storage demand by sample type"), width="stretch", key=f"{key}_storage")
    status = output.primary.groupby("volume_status", as_index=False).size().rename(columns={"size": "aliquots"})
    st.plotly_chart(px.bar(status, x="volume_status", y="aliquots", color="volume_status", title="Aliquot volume sufficiency"), width="stretch", key=f"{key}_volume_status")

    st.markdown("#### Temperature excursion test")
    timestamps = pd.date_range("2026-01-01", periods=24, freq="30min", tz="UTC")
    temperatures = np.r_[np.repeat(-78.0, 8), np.repeat(-65.0, 4), np.repeat(-79.0, 12)]
    logger = pd.DataFrame({"timestamp": timestamps, "container_id": "SHIP-001", "temperature_c": temperatures})
    excursions = detect_temperature_excursions(logger, -90, -70, 30)
    st.plotly_chart(px.line(logger, x="timestamp", y="temperature_c", color="container_id", title="Temperature logger trace"), width="stretch", key=f"{key}_temperature")
    if excursions.empty:
        st.success("No qualifying temperature excursions detected.")
    else:
        smart_dataframe(excursions, height=220, key=f"{key}_excursions")
    smart_dataframe(output.primary.head(2_000), height=320, key=f"{key}_inventory")
    return {"inventory": output.manifest(), "temperature_excursions": excursions.to_dict(orient="records")}


def _recruitment_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"site": "Site A", "activation_mean": 2.0, "activation_sd": 0.5, "monthly_rate": 6.0, "rate_cv": 0.35, "screen_success": 0.65, "retention": 0.90, "capacity": 100},
        {"site": "Site B", "activation_mean": 3.0, "activation_sd": 0.8, "monthly_rate": 4.0, "rate_cv": 0.45, "screen_success": 0.58, "retention": 0.88, "capacity": 80},
        {"site": "Site C", "activation_mean": 4.0, "activation_sd": 1.0, "monthly_rate": 8.0, "rate_cv": 0.50, "screen_success": 0.55, "retention": 0.85, "capacity": 120},
    ])
    sites = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_site_editor"))
    c1, c2, c3 = st.columns(3)
    target = int(c1.number_input("Recruitment target", 1, 1_000_000, 180, 10, key=f"{key}_target"))
    months = int(c2.number_input("Forecast horizon months", 1, 240, 24, 1, key=f"{key}_horizon"))
    simulations = int(c3.number_input("Recruitment simulations", 500, 20_000, 5_000, 500, key=f"{key}_recruit_sims"))
    output = simulate_recruitment(sites, target, months, simulations, 144)
    _show_output(output, f"{key}_recruit")
    forecast = output.primary
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=forecast["month"], y=forecast["p90"], mode="lines", line={"width": 0}, showlegend=False))
    fig.add_trace(go.Scatter(x=forecast["month"], y=forecast["p10"], mode="lines", fill="tonexty", name="P10–P90"))
    fig.add_trace(go.Scatter(x=forecast["month"], y=forecast["median"], mode="lines+markers", name="Median"))
    fig.add_hline(y=target, line_dash="dash", annotation_text="Target")
    fig.update_layout(title="Probabilistic recruitment forecast", xaxis_title="Month", yaxis_title="Retained participants")
    st.plotly_chart(fig, width="stretch", key=f"{key}_recruit_fan")
    st.plotly_chart(px.line(forecast, x="month", y="completion_probability", range_y=[0, 1], title="Probability of reaching target"), width="stretch", key=f"{key}_completion")

    observed = pd.DataFrame({"site": sites["site"], "observed_months": 3, "observed_recruits": np.maximum(0, np.round(pd.to_numeric(sites["monthly_rate"], errors="coerce").fillna(0) * 2.5)).astype(int)})
    updated = bayesian_recruitment_update(observed)
    st.markdown("#### Bayesian rate update from observed recruitment")
    smart_dataframe(updated, height=260, key=f"{key}_recruit_update")
    smart_dataframe(output.tables["site_summary"], height=280, key=f"{key}_site_summary")
    return {"forecast": output.manifest(), "bayesian_update": updated.to_dict(orient="records")}


def _timeline_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"task": "Protocol finalization", "predecessor": "", "optimistic_days": 20, "most_likely_days": 30, "pessimistic_days": 50, "owner": "Study team"},
        {"task": "Ethics approval", "predecessor": "Protocol finalization", "optimistic_days": 30, "most_likely_days": 45, "pessimistic_days": 90, "owner": "Regulatory"},
        {"task": "Site activation", "predecessor": "Ethics approval", "optimistic_days": 20, "most_likely_days": 35, "pessimistic_days": 60, "owner": "Operations"},
        {"task": "Recruitment", "predecessor": "Site activation", "optimistic_days": 120, "most_likely_days": 180, "pessimistic_days": 300, "owner": "Operations"},
        {"task": "Database lock", "predecessor": "Recruitment", "optimistic_days": 20, "most_likely_days": 30, "pessimistic_days": 60, "owner": "Data management"},
        {"task": "Primary analysis", "predecessor": "Database lock", "optimistic_days": 15, "most_likely_days": 25, "pessimistic_days": 45, "owner": "Statistics"},
    ])
    tasks = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_timeline_editor"))
    simulations = int(st.number_input("Schedule simulations", 500, 20_000, 5_000, 500, key=f"{key}_timeline_sims"))
    output = pert_schedule_simulation(tasks, simulations, 144)
    _show_output(output, f"{key}_timeline")
    schedule = output.primary.copy()
    schedule["start"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(schedule["baseline_start_day"], unit="D")
    schedule["finish"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(schedule["baseline_finish_day"], unit="D")
    st.plotly_chart(px.timeline(schedule, x_start="start", x_end="finish", y="task", color="critical_baseline", hover_data=["criticality_index", "slack_days"], title="PERT baseline and critical path"), width="stretch", key=f"{key}_timeline_gantt")
    distribution = output.tables["duration_distribution"]
    st.plotly_chart(px.histogram(distribution, x="project_duration_days", nbins=45, title="Project duration uncertainty"), width="stretch", key=f"{key}_timeline_distribution")
    st.plotly_chart(px.bar(schedule.sort_values("criticality_index"), x="criticality_index", y="task", orientation="h", title="Task criticality index"), width="stretch", key=f"{key}_criticality")
    smart_dataframe(schedule.drop(columns=["start", "finish"]), height=340, key=f"{key}_timeline_table")
    return {"schedule": output.manifest()}


def _risk_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"risk": "Slow recruitment", "category": "Operations", "probability": 4, "impact": 5, "detectability": 3, "control_effectiveness": 0.35, "financial_impact": 300000, "time_impact_days": 90, "owner": "Operations lead"},
        {"risk": "Assay failure", "category": "Laboratory", "probability": 2, "impact": 4, "detectability": 4, "control_effectiveness": 0.60, "financial_impact": 120000, "time_impact_days": 45, "owner": "Lab lead"},
        {"risk": "Data quality issue", "category": "Data", "probability": 3, "impact": 4, "detectability": 2, "control_effectiveness": 0.50, "financial_impact": 80000, "time_impact_days": 30, "owner": "Data manager"},
        {"risk": "Protocol amendment", "category": "Scientific", "probability": 2, "impact": 5, "detectability": 3, "control_effectiveness": 0.25, "financial_impact": 200000, "time_impact_days": 75, "owner": "Study lead"},
    ])
    risks = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_risk_editor"))
    simulations = int(st.number_input("Aggregate exposure simulations", 1_000, 50_000, 10_000, 1_000, key=f"{key}_risk_sims"))
    output = fmea_risk_workbench(risks, simulations, 144)
    _show_output(output, f"{key}_risk")
    primary = output.primary
    st.plotly_chart(px.scatter(primary, x="rpn", y="residual_rpn", size="financial_impact", color="risk_band", hover_name="risk", title="Gross and residual FMEA exposure"), width="stretch", key=f"{key}_risk_scatter")
    exposure = output.tables["exposure"]
    st.plotly_chart(px.histogram(exposure, x="financial_exposure", nbins=45, title="Aggregate financial exposure distribution"), width="stretch", key=f"{key}_risk_financial")
    st.plotly_chart(px.bar(output.tables["category"], x="category", y=["gross_rpn", "residual_rpn"], barmode="group", title="Control effectiveness by risk category"), width="stretch", key=f"{key}_risk_category")
    smart_dataframe(primary, height=340, key=f"{key}_risk_table")
    return {"risk": output.manifest()}


def _evidence_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"study_id": "S001", "title": "Randomized trial of intervention A", "doi": "10.1000/a1", "year": 2022, "design": "Randomized trial", "quality": "High", "effect": 0.42, "standard_error": 0.12, "screening_status": "Included", "population": "Adults", "outcome": "Primary outcome"},
        {"study_id": "S002", "title": "Randomised trial of intervention A", "doi": "10.1000/a2", "year": 2023, "design": "Randomized trial", "quality": "Moderate", "effect": 0.28, "standard_error": 0.14, "screening_status": "Included", "population": "Adults", "outcome": "Primary outcome"},
        {"study_id": "S003", "title": "Prospective cohort evaluation of intervention A", "doi": "10.1000/a3", "year": 2021, "design": "Prospective cohort", "quality": "Moderate", "effect": -0.10, "standard_error": 0.20, "screening_status": "Included", "population": "Adults", "outcome": "Primary outcome"},
        {"study_id": "S004", "title": "Randomized trial of intervention A", "doi": "10.1000/a1", "year": 2022, "design": "Randomized trial", "quality": "High", "effect": 0.42, "standard_error": 0.12, "screening_status": "Included", "population": "Adults", "outcome": "Primary outcome"},
        {"study_id": "S005", "title": "Pilot case series", "doi": "", "year": 2020, "design": "Case series", "quality": "Low", "effect": 0.60, "standard_error": 0.35, "screening_status": "Excluded", "population": "Adults", "outcome": "Primary outcome"},
    ])
    studies = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_literature_editor"))
    output = literature_evidence_workbench(studies)
    _show_output(output, f"{key}_evidence")
    st.plotly_chart(px.funnel(output.tables["prisma"], y="stage", x="records", title="PRISMA-style evidence flow"), width="stretch", key=f"{key}_prisma")
    unique = output.primary.loc[~output.primary["is_duplicate"] & output.primary["standard_error"].gt(0)].copy()
    if not unique.empty:
        unique["ci_low"] = unique["effect"] - 1.96 * unique["standard_error"]
        unique["ci_high"] = unique["effect"] + 1.96 * unique["standard_error"]
        st.plotly_chart(px.scatter(unique, x="effect", y="study_id", color="quality", error_x=unique["ci_high"] - unique["effect"], error_x_minus=unique["effect"] - unique["ci_low"], title="Study effects and confidence intervals"), width="stretch", key=f"{key}_forest")
    contradiction = output.tables["contradiction_matrix"]
    st.plotly_chart(px.scatter(contradiction, x="positive", y="negative", size="studies", color="contradiction_flag", hover_data=["population", "outcome"], title="Evidence direction and contradiction"), width="stretch", key=f"{key}_contradiction")
    smart_dataframe(output.primary, height=340, key=f"{key}_evidence_table")
    return {"evidence": output.manifest()}


def _prereg_specialist(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"item": "Primary endpoint", "section": "Endpoint", "planned_value": "Change at Week 12", "executed_value": "Change at Week 12", "reported_value": "Change at Week 12", "locked": True, "deviation_reason": ""},
        {"item": "Primary population", "section": "Analysis", "planned_value": "ITT", "executed_value": "ITT", "reported_value": "ITT", "locked": True, "deviation_reason": ""},
        {"item": "Secondary endpoint", "section": "Endpoint", "planned_value": "Response rate", "executed_value": "Response rate", "reported_value": "Durable response", "locked": True, "deviation_reason": "Clarified duration after blinded review"},
        {"item": "Missing-data method", "section": "Analysis", "planned_value": "MMRM", "executed_value": "Multiple imputation", "reported_value": "Multiple imputation", "locked": True, "deviation_reason": "Model diagnostics failed prespecified assumption"},
    ])
    items = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_prereg_editor"))
    artifact_default = pd.DataFrame([
        {"artifact": "analysis_plan.pdf", "declared_sha256": "a" * 64},
        {"artifact": "environment.lock", "declared_sha256": "b" * 64},
        {"artifact": "analysis_code.zip", "declared_sha256": "invalid"},
    ])
    artifacts = pd.DataFrame(st.data_editor(artifact_default, num_rows="dynamic", width="stretch", key=f"{key}_artifact_editor"))
    output = preregistration_integrity_audit(items, artifacts)
    _show_output(output, f"{key}_prereg")
    alignment = output.tables["alignment"].melt(id_vars="comparison", var_name="status", value_name="items")
    st.plotly_chart(px.bar(alignment, x="comparison", y="items", color="status", barmode="stack", title="Plan, execution and report alignment"), width="stretch", key=f"{key}_alignment")
    deviations = output.primary.loc[output.primary["severity"].ne("None")]
    if deviations.empty:
        st.success("No material preregistration deviations detected.")
    else:
        deviation_chart = deviations.assign(records=1)
        st.plotly_chart(px.bar(deviation_chart, x="item", y="records", color="severity", title="Deviation and outcome-switching review"), width="stretch", key=f"{key}_deviation_chart")
    smart_dataframe(output.primary, height=340, key=f"{key}_prereg_table")
    return {"integrity_audit": output.manifest()}


_SPECIALIST_RENDERERS = {
    "sample_size_power_studio": _sample_size_specialist,
    "clinical_trial_design_studio": _clinical_trial_specialist,
    "experimental_design_doe": _doe_specialist,
    "biomarker_study_planning": _biomarker_specialist,
    "sampling_biospecimen_planning": _biospecimen_specialist,
    "research_feasibility_recruitment": _recruitment_specialist,
    "research_timeline_dependencies": _timeline_specialist,
    "research_risk_mitigation": _risk_specialist,
    "evidence_gap_literature_planning": _evidence_specialist,
    "preregistration_reproducibility": _prereg_specialist,
}


def has_specialist_renderer(module_key: str) -> bool:
    return module_key in _SPECIALIST_RENDERERS


def render_specialist_engine(module_key: str, key_prefix: str) -> dict[str, Any]:
    renderer = _SPECIALIST_RENDERERS.get(module_key)
    if renderer is None:
        return {}
    st.info("Specialist engine workspace · calculations are bounded, deterministic and exported with checksums. Results remain planning support and require qualified review.")
    contract = specialist_engine_contract(module_key)
    with st.expander("Engine contract", expanded=False):
        smart_json(contract, title="Specialist engine contract", download_name=f"{module_key}_specialist_engine_contract.json", key=f"{key_prefix}_contract")
    return renderer(key_prefix)
