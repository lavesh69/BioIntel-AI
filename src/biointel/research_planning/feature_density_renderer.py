from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json

from .specialist_renderer import has_specialist_renderer, render_specialist_engine

from .feature_density import (
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


def _default_plan(module_key: str, result: Any | None = None) -> dict[str, Any]:
    summary = getattr(result, "summary", {}) if result is not None else {}
    sample_size = int(summary.get("total_sample_size", summary.get("records", 200)) or 200) if isinstance(summary, dict) else 200
    digest = str(summary.get("input_sha256", "")) if isinstance(summary, dict) else ""
    return {
        "protocol_id": "BIOINTEL-PLAN-001",
        "protocol_version": "0.1-draft",
        "primary_objective": "Evaluate the prespecified primary objective",
        "primary_endpoint": "primary_outcome",
        "estimand_ids": ["EST-001"],
        "estimand_variable": "primary_outcome",
        "estimator": "Covariate-adjusted model",
        "primary_output": "Primary analysis table",
        "protocol_sample_size": sample_size,
        "power_sample_size": sample_size,
        "sample_size": sample_size,
        "effect_size": 0.35,
        "budget_total": 1_000_000.0,
        "duration_months": 18.0,
        "visits": ["Screening", "Baseline", "Follow-up"],
        "inclusion_criteria": ["Target population"],
        "randomization_strata": ["site"],
        "protocol_sha256": digest or sha256(module_key.encode()).hexdigest(),
        "source_provenance": digest or "Starter planning context",
        "reviewer": "Local reviewer",
        "review_status": "Needs review",
        "module_key": module_key,
    }


def _sankey(nodes: pd.DataFrame, edges: pd.DataFrame, title: str) -> go.Figure:
    if nodes.empty or edges.empty:
        return go.Figure().update_layout(title=title)
    labels = nodes["label"].astype(str).tolist()
    index = {node_id: idx for idx, node_id in enumerate(nodes["node_id"].astype(str))}
    return go.Figure(go.Sankey(
        node={"label": labels, "pad": 14, "thickness": 15},
        link={
            "source": [index[str(value)] for value in edges["source"]],
            "target": [index[str(value)] for value in edges["target"]],
            "value": pd.to_numeric(edges.get("weight", 1), errors="coerce").fillna(1).tolist(),
            "label": edges.get("relationship", pd.Series([""] * len(edges))).astype(str).tolist(),
        },
    )).update_layout(title=title)


def _download_json(label: str, payload: Any, filename: str, key: str) -> None:
    st.download_button(label, json.dumps(payload, indent=2, default=str).encode(), filename, "application/json", key=key)


def _shared_linked_visuals(module_key: str, plan: Mapping[str, Any], key: str) -> None:
    nodes, edges = build_study_map(plan)
    sensitivity = assumption_sensitivity(
        effect_size=float(plan.get("effect_size", 0.35) or 0.35),
        sample_size=int(plan.get("protocol_sample_size", plan.get("sample_size", 200)) or 200),
        budget=float(plan.get("budget_total", 1_000_000) or 0),
        duration_months=float(plan.get("duration_months", 18) or 18),
    )
    quality = plan_quality_matrix(plan)
    tabs = st.tabs(["Study map", "Assumption sensitivity", "Plan quality", "Change impact"])
    with tabs[0]:
        st.plotly_chart(_sankey(nodes, edges, "Objective → endpoint → estimand → variable → model → output"), width="stretch", key=f"{key}_study_map")
        smart_dataframe(nodes, height=260, key=f"{key}_study_nodes")
    with tabs[1]:
        st.plotly_chart(px.line(sensitivity, x="effect_size", y="required_sample_size", color="scenario", markers=True, title="Effect-size sensitivity and required sample size"), width="stretch", key=f"{key}_sensitivity_n")
        st.plotly_chart(px.scatter(sensitivity, x="duration_months", y="budget", color="scenario", size="required_sample_size", title="Budget and duration sensitivity"), width="stretch", key=f"{key}_sensitivity_budget")
        smart_dataframe(sensitivity, height=260, key=f"{key}_sensitivity_table")
    with tabs[2]:
        pivot = quality.pivot(index="module_key", columns="dimension", values="score")
        st.plotly_chart(px.imshow(pivot, text_auto=".0f", zmin=0, zmax=100, aspect="auto", title="Connected plan quality matrix"), width="stretch", key=f"{key}_quality_heatmap")
        smart_dataframe(quality, height=300, key=f"{key}_quality_table")
    with tabs[3]:
        previous = dict(plan)
        previous["protocol_sample_size"] = max(2, int(plan.get("protocol_sample_size", 200) or 200) - 20)
        previous["primary_endpoint"] = "Previous primary endpoint"
        impact = change_impact(previous, plan)
        if impact.empty:
            st.success("No change-impact actions are required for the current comparison.")
        else:
            counts = impact.groupby(["impacted_module", "severity"], as_index=False).size().rename(columns={"size": "changes"})
            st.plotly_chart(px.bar(counts, x="impacted_module", y="changes", color="severity", title="Modules affected by plan changes"), width="stretch", key=f"{key}_impact_chart")
            smart_dataframe(impact, height=320, key=f"{key}_impact_table")


def _command_center_lab(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"study_id": "STUDY-001", "protocol": 92, "statistics": 86, "operations": 74, "data": 82, "risk": 70, "budget": 76, "reproducibility": 88, "owner": "Study lead"},
        {"study_id": "STUDY-002", "protocol": 80, "statistics": 78, "operations": 62, "data": 75, "risk": 45, "budget": 68, "reproducibility": 72, "owner": "Program lead"},
        {"study_id": "STUDY-003", "protocol": 66, "statistics": 72, "operations": 58, "data": 64, "risk": 61, "budget": 55, "reproducibility": 69, "owner": "Study lead"},
    ])
    edited = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_portfolio_editor"))
    result, summary = portfolio_readiness(edited)
    metric_cards([
        ("Studies", summary["studies"], None),
        ("Portfolio readiness", f"{summary['portfolio_readiness']:.1f}%", None),
        ("Ready", summary["ready"], None),
        ("Blocked", summary["blocked"], None),
    ])
    st.plotly_chart(px.bar(result, x="study_id", y="weighted_readiness", color="status", range_y=[0, 100], title="Portfolio readiness by study"), width="stretch", key=f"{key}_portfolio_chart")
    matrix = result.set_index("study_id")[["protocol", "statistics", "operations", "data", "risk", "budget", "reproducibility"]]
    st.plotly_chart(px.imshow(matrix, text_auto=".0f", zmin=0, zmax=100, aspect="auto", title="Cross-study readiness matrix"), width="stretch", key=f"{key}_portfolio_matrix")
    smart_dataframe(result, height=320, key=f"{key}_portfolio_table")
    return {"portfolio": result.to_dict(orient="records"), "summary": summary}


def _budget_lab(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"category": "Start-up", "quantity": 1, "unit_cost": 250000, "start_month": 1, "end_month": 3, "owner": "Sponsor"},
        {"category": "Sites", "quantity": 10, "unit_cost": 18000, "start_month": 2, "end_month": 8, "owner": "Operations"},
        {"category": "Participants", "quantity": 220, "unit_cost": 3800, "start_month": 4, "end_month": 18, "owner": "Operations"},
        {"category": "Assays", "quantity": 440, "unit_cost": 210, "start_month": 4, "end_month": 20, "owner": "Laboratory"},
    ])
    items = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_cashflow_editor"))
    c1, c2, c3, c4 = st.columns(4)
    months = int(c1.number_input("Planning months", 1, 600, 24, key=f"{key}_months"))
    inflation = float(c2.number_input("Annual inflation", -0.50, 2.0, 0.04, 0.01, format="%.2f", key=f"{key}_inflation"))
    exchange_rate = float(c3.number_input("Exchange rate", 0.000001, 100000.0, 1.0, format="%.4f", key=f"{key}_exchange"))
    contingency = float(c4.number_input("Contingency fraction", 0.0, 1.0, 0.12, 0.01, key=f"{key}_contingency"))
    table, cashflow, summary = budget_cashflow(items, months, inflation, exchange_rate, contingency)
    metric_cards([
        ("Base total", f"{summary['base_total']:,.0f}", None),
        ("Inflated total", f"{summary['inflated_total']:,.0f}", None),
        ("With contingency", f"{summary['total_with_contingency']:,.0f}", None),
        ("Peak burn month", summary["peak_burn_month"], f"{summary['peak_monthly_burn']:,.0f}"),
    ])
    st.plotly_chart(px.area(cashflow, x="month", y="planned_cost", title="Monthly study cash-flow forecast"), width="stretch", key=f"{key}_cashflow")
    st.plotly_chart(px.line(cashflow, x="month", y="cumulative_cost", title="Cumulative cash requirement"), width="stretch", key=f"{key}_cumulative")
    subgroup_default = pd.DataFrame([
        {"subgroup": "Local participants", "visits": 6, "visit_minutes": 75, "travel_minutes": 30, "questionnaire_minutes": 15, "digital_access_score": 1, "discomfort_score": 3},
        {"subgroup": "Remote participants", "visits": 6, "visit_minutes": 75, "travel_minutes": 120, "questionnaire_minutes": 20, "digital_access_score": 2, "discomfort_score": 3},
        {"subgroup": "Accessibility support", "visits": 6, "visit_minutes": 90, "travel_minutes": 75, "questionnaire_minutes": 30, "digital_access_score": 4, "discomfort_score": 4},
    ])
    subgroup = pd.DataFrame(st.data_editor(subgroup_default, num_rows="dynamic", width="stretch", key=f"{key}_equity_editor"))
    equity, equity_summary = participant_equity_burden(subgroup)
    st.plotly_chart(px.bar(equity, x="subgroup", y="burden_score", color="time_hours", title="Participant burden equity by subgroup"), width="stretch", key=f"{key}_equity")
    smart_dataframe(equity, height=260, key=f"{key}_equity_table")
    return {"cashflow": cashflow.to_dict(orient="records"), "summary": summary, "equity_summary": equity_summary}


def _protocol_lab(key: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    default = pd.DataFrame([
        {"activity": "Informed consent", "visit": "Screening", "day": -14, "required": True},
        {"activity": "Eligibility", "visit": "Screening", "day": -14, "required": True},
        {"activity": "Randomization", "visit": "Baseline", "day": 0, "required": True},
        {"activity": "Primary endpoint", "visit": "Follow-up", "day": 84, "required": True},
        {"activity": "Safety follow-up", "visit": "Safety", "day": 98, "required": True},
    ])
    schedule = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_schedule_editor"))
    matrix, visit_days = protocol_schedule_matrix(schedule)
    st.plotly_chart(px.imshow(matrix.astype(int), text_auto=True, zmin=0, zmax=1, aspect="auto", title="Schedule of activities"), width="stretch", key=f"{key}_schedule_matrix")
    st.plotly_chart(px.scatter(visit_days, x="day", y="visit", size=[20] * len(visit_days), title="Participant journey timeline"), width="stretch", key=f"{key}_journey")
    previous = dict(plan)
    previous["primary_endpoint"] = "Previous endpoint"
    previous["protocol_sample_size"] = max(2, int(plan.get("protocol_sample_size", 200)) - 20)
    redline = protocol_redline(previous, plan)
    smart_dataframe(redline, height=260, key=f"{key}_redline")
    return {"schedule": schedule.to_dict(orient="records"), "visit_days": visit_days.to_dict(orient="records"), "redline": redline.to_dict(orient="records")}


def _crf_lab(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"variable": "participant_id", "data_type": "string", "required": True, "show_when_variable": "", "show_when_value": "", "visit": "All", "label": "Participant ID"},
        {"variable": "consent", "data_type": "boolean", "required": True, "show_when_variable": "", "show_when_value": "", "visit": "Screening", "label": "Consent obtained"},
        {"variable": "primary_outcome", "data_type": "float", "required": True, "show_when_variable": "consent", "show_when_value": "True", "visit": "Follow-up", "label": "Primary outcome"},
        {"variable": "adverse_event", "data_type": "boolean", "required": False, "show_when_variable": "", "show_when_value": "", "visit": "All", "label": "Adverse event"},
        {"variable": "adverse_event_grade", "data_type": "choice", "required": False, "show_when_variable": "adverse_event", "show_when_value": "True", "visit": "All", "label": "Adverse event grade"},
    ])
    fields = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_crf_editor"))
    validated, issues = validate_crf_logic(fields)
    tests = generate_crf_test_cases(fields)
    metric_cards([
        ("Fields", len(validated), None),
        ("Critical issues", int((issues.get("severity", pd.Series(dtype=str)) == "Critical").sum()), None),
        ("Automated test cases", len(tests), None),
        ("Visits", validated.get("visit", pd.Series(dtype=str)).nunique(), None),
    ])
    dependencies = validated[validated["show_when_variable"].astype(str).str.len() > 0][["show_when_variable", "variable"]]
    if not dependencies.empty:
        nodes = pd.DataFrame({"node_id": list(dict.fromkeys([*dependencies["show_when_variable"], *dependencies["variable"]]))})
        nodes["label"] = nodes["node_id"]
        edges = dependencies.rename(columns={"show_when_variable": "source", "variable": "target"}).assign(relationship="controls", weight=1.0)
        st.plotly_chart(_sankey(nodes, edges, "CRF field dependency and skip-logic graph"), width="stretch", key=f"{key}_crf_dependencies")
    visit_matrix = pd.crosstab(validated.get("visit", "Unassigned"), validated["data_type"])
    st.plotly_chart(px.imshow(visit_matrix, text_auto=True, aspect="auto", title="Visit-form coverage"), width="stretch", key=f"{key}_visit_matrix")
    smart_dataframe(issues, height=240, key=f"{key}_crf_issues")
    smart_dataframe(tests, height=300, key=f"{key}_crf_tests")
    return {"fields": validated.to_dict(orient="records"), "issues": issues.to_dict(orient="records"), "test_cases": tests.to_dict(orient="records")}


def _cohort_lab(key: str) -> dict[str, Any]:
    rng = np.random.default_rng(143)
    participants = pd.DataFrame({
        "participant_id": [f"P{index:04d}" for index in range(1, 301)],
        "age": rng.integers(18, 85, 300),
        "site": rng.choice(["Site A", "Site B", "Site C"], 300),
        "diagnosis": rng.choice(["Target", "Other"], 300, p=[0.72, 0.28]),
        "lab_value": rng.normal(50, 15, 300),
    })
    rules_default = pd.DataFrame([
        {"rule_id": "R1", "field": "age", "operator": ">=", "value": "18", "logic": "AND"},
        {"rule_id": "R2", "field": "age", "operator": "<=", "value": "75", "logic": "AND"},
        {"rule_id": "R3", "field": "diagnosis", "operator": "==", "value": "Target", "logic": "AND"},
        {"rule_id": "R4", "field": "lab_value", "operator": ">=", "value": "25", "logic": "AND"},
    ])
    rules = pd.DataFrame(st.data_editor(rules_default, num_rows="dynamic", width="stretch", key=f"{key}_rules_editor"))
    result, audit = evaluate_cohort_rules(participants, rules)
    metric_cards([
        ("Screened", len(result), None),
        ("Eligible", int(result["eligible"].sum()), None),
        ("Eligibility rate", f"{result['eligible'].mean():.1%}", None),
        ("Rules", len(audit), None),
    ])
    funnel = pd.DataFrame([{"stage": "Screened", "participants": len(result)}, *[{"stage": str(row["rule_id"]), "participants": int(row["eligible_after_rule"])} for _, row in audit.iterrows()]])
    st.plotly_chart(px.funnel(funnel, y="stage", x="participants", title="Eligibility attrition funnel"), width="stretch", key=f"{key}_cohort_funnel")
    site = result.groupby("site", as_index=False)["eligible"].agg(["sum", "count"]).reset_index().rename(columns={"sum": "eligible", "count": "screened"})
    site["eligibility_rate"] = site["eligible"] / site["screened"]
    st.plotly_chart(px.bar(site, x="site", y="eligibility_rate", text="eligible", range_y=[0, 1], title="Site-level eligible population"), width="stretch", key=f"{key}_site_feasibility")
    smart_dataframe(audit, height=260, key=f"{key}_cohort_audit")
    return {"audit": audit.to_dict(orient="records"), "eligible": int(result["eligible"].sum())}


def _endpoint_lab(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"endpoint": "Primary symptom score", "clinical_relevance": 95, "validity": 88, "reliability": 84, "burden": 35, "missingness_risk": 20},
        {"endpoint": "Functional assessment", "clinical_relevance": 86, "validity": 82, "reliability": 80, "burden": 50, "missingness_risk": 25},
        {"endpoint": "Biomarker response", "clinical_relevance": 72, "validity": 78, "reliability": 90, "burden": 65, "missingness_risk": 15},
        {"endpoint": "Healthcare utilization", "clinical_relevance": 75, "validity": 70, "reliability": 74, "burden": 15, "missingness_risk": 35},
    ])
    endpoints = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_endpoint_editor"))
    ranked = score_endpoints(endpoints)
    st.plotly_chart(px.scatter(ranked, x="burden", y="value_score", size="net_priority", color="recommended_role", hover_name="endpoint", title="Endpoint value versus participant burden"), width="stretch", key=f"{key}_endpoint_value")
    st.plotly_chart(px.bar(ranked, x="endpoint", y="net_priority", color="recommended_role", title="Endpoint strategy priority"), width="stretch", key=f"{key}_endpoint_rank")
    composite_default = pd.DataFrame([
        {"component": "Hospitalization", "events": 35, "total_participants": 200, "clinical_weight": 1.0},
        {"component": "Urgent care", "events": 50, "total_participants": 200, "clinical_weight": 0.6},
        {"component": "Rescue treatment", "events": 70, "total_participants": 200, "clinical_weight": 0.4},
    ])
    components = pd.DataFrame(st.data_editor(composite_default, num_rows="dynamic", width="stretch", key=f"{key}_composite_editor"))
    contribution = composite_endpoint_contribution(components)
    st.plotly_chart(px.bar(contribution, x="component", y="contribution_fraction", color="dominance_flag", title="Composite endpoint contribution"), width="stretch", key=f"{key}_composite")
    smart_dataframe(ranked, height=260, key=f"{key}_endpoint_table")
    return {"ranked_endpoints": ranked.to_dict(orient="records"), "composite": contribution.to_dict(orient="records")}


def _randomization_lab(key: str) -> dict[str, Any]:
    participants = pd.DataFrame({
        "participant_id": [f"P{index:04d}" for index in range(1, 121)],
        "site": ["Site A", "Site B", "Site C"] * 40,
        "severity": (["Mild", "Moderate", "Severe", "Moderate"] * 30),
    })
    c1, c2, c3 = st.columns(3)
    seed = int(c1.number_input("Securely recorded seed", 0, 2_147_483_647, 143, key=f"{key}_random_seed"))
    probability = float(c2.slider("Minimization bias probability", 0.50, 1.00, 0.80, 0.05, key=f"{key}_bias"))
    arms_text = c3.text_input("Arms", "Control,Treatment", key=f"{key}_arms")
    arms = [item.strip() for item in arms_text.split(",") if item.strip()]
    assignments = minimization_randomization(participants, ["site", "severity"], arms, seed, probability)
    audit, summary = allocation_audit(assignments, ["site", "severity"])
    metric_cards([
        ("Participants", summary["participants"], None),
        ("Max stratum imbalance", summary["maximum_stratum_imbalance"], None),
        ("Assignment entropy", f"{summary['normalized_entropy']:.3f}", None),
        ("Allocation digest", summary["allocation_digest"][:14] + "…", None),
    ])
    trajectory = assignments.assign(one=1).pivot_table(index="sequence", columns="assigned_arm", values="one", aggfunc="sum", fill_value=0).cumsum().reset_index()
    melted = trajectory.melt(id_vars="sequence", var_name="arm", value_name="participants")
    st.plotly_chart(px.line(melted, x="sequence", y="participants", color="arm", title="Sequential allocation balance"), width="stretch", key=f"{key}_allocation_trajectory")
    st.plotly_chart(px.bar(audit, x="level", y="absolute_imbalance", color="stratum", barmode="group", title="Covariate imbalance audit"), width="stretch", key=f"{key}_allocation_audit_chart")
    smart_dataframe(assignments.head(500), height=320, key=f"{key}_assignments")
    return {"summary": summary, "audit": audit.to_dict(orient="records"), "assignments": assignments.to_dict(orient="records")}


def _sap_lab(key: str) -> dict[str, Any]:
    default = pd.DataFrame([
        {"analysis_id": "A001", "endpoint": "Primary outcome", "population": "ITT", "model": "ANCOVA", "output_type": "Table", "source_dataset": "ADSL+ADEFF", "estimand_id": "EST-001"},
        {"analysis_id": "A002", "endpoint": "Primary outcome", "population": "ITT", "model": "ANCOVA", "output_type": "Figure", "source_dataset": "ADEFF", "estimand_id": "EST-001"},
        {"analysis_id": "A003", "endpoint": "Safety events", "population": "Safety", "model": "Descriptive", "output_type": "Table", "source_dataset": "ADAE", "estimand_id": "EST-SAFE"},
        {"analysis_id": "A004", "endpoint": "Participant disposition", "population": "All enrolled", "model": "Descriptive", "output_type": "Listing", "source_dataset": "ADSL", "estimand_id": "EST-DISP"},
    ])
    analyses = pd.DataFrame(st.data_editor(default, num_rows="dynamic", width="stretch", key=f"{key}_sap_editor"))
    shells = build_tfl_shells(analyses)
    metric_cards([
        ("Analyses", len(shells), None),
        ("Tables", int((shells["output_type"] == "Table").sum()), None),
        ("Figures", int((shells["output_type"] == "Figure").sum()), None),
        ("Listings", int((shells["output_type"] == "Listing").sum()), None),
    ])
    flow = shells[["source_dataset", "model", "shell_title"]].copy()
    nodes = pd.DataFrame({"node_id": list(dict.fromkeys([*flow["source_dataset"], *flow["model"], *flow["shell_title"]]))})
    nodes["label"] = nodes["node_id"]
    e1 = flow.rename(columns={"source_dataset": "source", "model": "target"})[["source", "target"]].assign(relationship="analysed by", weight=1.0)
    e2 = flow.rename(columns={"model": "source", "shell_title": "target"})[["source", "target"]].assign(relationship="reported as", weight=1.0)
    st.plotly_chart(_sankey(nodes, pd.concat([e1, e2], ignore_index=True), "Dataset → model → TFL lineage"), width="stretch", key=f"{key}_sap_lineage")
    matrix = pd.crosstab(shells["population"], shells["output_type"])
    st.plotly_chart(px.imshow(matrix, text_auto=True, aspect="auto", title="Analysis population and output coverage"), width="stretch", key=f"{key}_sap_matrix")
    smart_dataframe(shells, height=340, key=f"{key}_sap_shells")
    return {"shells": shells.to_dict(orient="records")}


def _biostatistics_lab(key: str) -> dict[str, Any]:
    matrix = method_compatibility_matrix()
    st.plotly_chart(px.imshow(matrix.pivot(index="outcome_type", columns="design", values="compatible").astype(int), text_auto=True, zmin=0, zmax=1, aspect="auto", title="Outcome and design compatibility"), width="stretch", key=f"{key}_method_matrix")
    smart_dataframe(matrix, height=320, key=f"{key}_method_table")
    sensitivity = assumption_sensitivity(0.30, 220, 1_200_000, 20)
    st.plotly_chart(px.bar(sensitivity, x="scenario", y="required_sample_size", color="scenario", title="Power-assumption sensitivity"), width="stretch", key=f"{key}_bio_sensitivity")
    return {"compatibility": matrix.to_dict(orient="records"), "sensitivity": sensitivity.to_dict(orient="records")}


def _synthetic_lab(key: str) -> dict[str, Any]:
    c1, c2, c3 = st.columns(3)
    n = int(c1.number_input("Synthetic participants", 10, 100_000, 500, 10, key=f"{key}_synthetic_n"))
    missingness = float(c2.slider("MNAR-like missingness", 0.0, 0.50, 0.05, 0.01, key=f"{key}_synthetic_missing"))
    site_effect = float(c3.slider("Site heterogeneity", 0.0, 2.0, 0.25, 0.05, key=f"{key}_synthetic_site"))
    synthetic = generate_synthetic_cohort(n, 143, missingness, site_effect)
    rng = np.random.default_rng(142)
    real = synthetic.copy()
    real["age"] = np.clip(real["age"] + rng.normal(1.5, 2.0, len(real)), 18, 90)
    real["baseline"] = pd.to_numeric(real["baseline"], errors="coerce") + rng.normal(0.1, 0.2, len(real))
    comparison, summary = synthetic_privacy_utility(real, synthetic)
    metric_cards([
        ("Synthetic participants", len(synthetic), None),
        ("Mean utility", f"{summary['mean_utility_score']:.1f}%", None),
        ("Variables compared", summary["variables"], None),
        ("Disclosure warning", "Yes" if summary["disclosure_warning"] else "No", None),
    ])
    st.plotly_chart(px.bar(comparison, x="variable", y="utility_score", color="nearest_real_distance_median", title="Synthetic data utility and privacy distance"), width="stretch", key=f"{key}_privacy_utility")
    trajectory = synthetic.groupby(["site", "treatment"], as_index=False)["outcome"].mean()
    st.plotly_chart(px.bar(trajectory, x="site", y="outcome", color="treatment", barmode="group", title="Synthetic treatment outcome by site"), width="stretch", key=f"{key}_synthetic_site_chart")
    smart_dataframe(synthetic.head(500), height=320, key=f"{key}_synthetic_table")
    return {"summary": summary, "comparison": comparison.to_dict(orient="records")}


def _generic_lab(module_key: str, key: str) -> dict[str, Any]:
    profile = get_peak_profile(module_key)
    validation = pd.DataFrame({
        "check": profile.validation_checks,
        "status": ["Needs review"] * len(profile.validation_checks),
        "owner": ["Study team"] * len(profile.validation_checks),
        "evidence_required": [True] * len(profile.validation_checks),
    })
    st.plotly_chart(px.bar(validation.assign(score=65), x="check", y="score", color="status", range_y=[0, 100], title="Module-specific validation readiness"), width="stretch", key=f"{key}_generic_validation")
    smart_dataframe(validation, height=280, key=f"{key}_generic_validation_table")
    return {"validation": validation.to_dict(orient="records")}


def _specialist_lab(module_key: str, plan: Mapping[str, Any], key: str) -> dict[str, Any]:
    dispatch = {
        "research_planning_command_center": lambda: _command_center_lab(key),
        "research_budget_participant_burden": lambda: _budget_lab(key),
        "study_protocol_designer": lambda: _protocol_lab(key, plan),
        "data_collection_crf_designer": lambda: _crf_lab(key),
        "cohort_eligibility_builder": lambda: _cohort_lab(key),
        "endpoint_outcome_strategy": lambda: _endpoint_lab(key),
        "randomization_blinding_allocation": lambda: _randomization_lab(key),
        "statistical_analysis_plan": lambda: _sap_lab(key),
        "biostatistics_design": lambda: _biostatistics_lab(key),
        "synthetic_cohort_trial": lambda: _synthetic_lab(key),
    }
    if module_key in dispatch:
        return dispatch[module_key]()
    if has_specialist_renderer(module_key):
        return render_specialist_engine(module_key, key)
    return _generic_lab(module_key, key)


def render_peak_feature_lab(
    module_key: str,
    result: Any | None = None,
    plan: Mapping[str, Any] | None = None,
    key_prefix: str | None = None,
) -> None:
    key = key_prefix or f"rp_peak_{module_key}"
    profile = get_peak_profile(module_key)
    working_plan = dict(_default_plan(module_key, result))
    if plan:
        working_plan.update(dict(plan))
    st.caption("Peak Feature Lab adds bounded planning calculations and decision-support visuals. Outputs require scientific, statistical, ethical and operational review before use.")
    tabs = st.tabs(["Feature inventory", "Specialist workspace", "Linked visuals", "Validation & export"])
    with tabs[0]:
        inventory = feature_inventory(module_key)
        metric_cards([
            ("Implemented feature contracts", profile.feature_count, None),
            ("Feature groups", len(profile.feature_groups), None),
            ("Signature visuals", len(profile.signature_visuals), None),
            ("Profile digest", profile_digest(module_key)[:14] + "…", None),
        ])
        grouped = inventory.groupby("group", as_index=False).size().rename(columns={"size": "features"})
        st.plotly_chart(px.bar(grouped, x="group", y="features", title="Feature density by capability group"), width="stretch", key=f"{key}_feature_density")
        smart_dataframe(inventory, height=400, key=f"{key}_inventory")
    specialist_payload: dict[str, Any] = {}
    with tabs[1]:
        try:
            specialist_payload = _specialist_lab(module_key, working_plan, key)
            st.session_state[f"{key}_specialist_payload"] = specialist_payload
        except Exception as exc:
            recovery = sha256(f"{module_key}|peak|{type(exc).__name__}|{exc}".encode()).hexdigest()[:12].upper()
            st.error(f"Peak specialist calculation stopped safely · RPX-{recovery}\n\n{exc}")
    with tabs[2]:
        try:
            _shared_linked_visuals(module_key, working_plan, key)
        except Exception as exc:
            recovery = sha256(f"{module_key}|linked|{type(exc).__name__}|{exc}".encode()).hexdigest()[:12].upper()
            st.error(f"Linked planning visual stopped safely · RPXV-{recovery}\n\n{exc}")
    with tabs[3]:
        inventory = feature_inventory(module_key)
        checks = pd.DataFrame({
            "check": profile.validation_checks,
            "status": ["Needs review"] * len(profile.validation_checks),
            "evidence": ["Attach source or reviewer decision"] * len(profile.validation_checks),
        })
        smart_dataframe(checks, height=260, key=f"{key}_checks")
        payload = {
            "module_key": module_key,
            "profile_digest": profile_digest(module_key),
            "feature_inventory": inventory.to_dict(orient="records"),
            "signature_visuals": list(profile.signature_visuals),
            "validation_checks": checks.to_dict(orient="records"),
            "working_plan": working_plan,
            "specialist_output": st.session_state.get(f"{key}_specialist_payload", specialist_payload),
        }
        smart_json(payload, title="Peak feature manifest", download_name=f"{module_key}_peak_feature_manifest.json", key=f"{key}_manifest")
        _download_json("Download peak feature manifest", payload, f"{module_key}_peak_feature_manifest.json", f"{key}_manifest_download")
