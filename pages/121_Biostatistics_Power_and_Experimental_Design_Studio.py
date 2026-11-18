from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.study_design import (
    build_design_manifest,
    build_randomization_schedule,
    calculate_design,
    power_sensitivity,
    simulate_power,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Statistical Power & Study Design Studio · BioIntel AI", page_icon="📐", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("study_design", key_prefix="step116_121_Biostatistics_Power_and_Experimental_Design_Studio_study_design_1", expanded=False)
hero(
    "📐 Statistical Power & Study Design Studio",
    "Plan transparent, reproducible studies with sample-size calculations, sensitivity analysis, simulation checks, stratified randomisation and protocol-ready manifests.",
    eyebrow="Research Planning · Statistical Rigor",
    chips=["11 design families", "Multiplicity", "Simulation", "Randomisation", "Protocol manifest"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="These calculations are planning aids. Confirmatory, regulated or clinically consequential studies require protocol-specific statistical review and justified assumptions.",
)

DESIGNS = {
    "Two independent means": "two_group_continuous",
    "Paired continuous outcome": "paired_continuous",
    "Two independent proportions": "two_proportions",
    "One-way ANOVA": "one_way_anova",
    "Correlation": "correlation",
    "Time-to-event / log-rank": "survival",
    "Precision for a mean": "precision_mean",
    "Non-inferiority": "noninferiority",
    "Equivalence": "equivalence",
    "Repeated measures": "repeated_measures",
    "Cluster-randomized design": "cluster_randomized",
}

plan_tab, sensitivity_tab, simulation_tab, randomization_tab, protocol_tab = st.tabs(
    ["1 · Power & sample size", "2 · Sensitivity", "3 · Simulation", "4 · Randomisation", "5 · Protocol manifest"]
)

with plan_tab:
    with st.form("study_design_form"):
        c1, c2, c3 = st.columns(3)
        design_label = c1.selectbox("Study design", list(DESIGNS), key="sd_design")
        alpha = c2.number_input("Family-wise alpha", min_value=0.0001, max_value=0.25, value=0.05, step=0.005, format="%.4f")
        power = c3.number_input("Target power", min_value=0.5, max_value=0.999, value=0.8, step=0.01, format="%.3f")
        c4, c5, c6 = st.columns(3)
        dropout = c4.number_input("Dropout / unusable fraction", min_value=0.0, max_value=0.79, value=0.10, step=0.01, format="%.2f")
        allocation_ratio = c5.number_input("Group 2 : Group 1 allocation", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
        two_sided = c6.toggle("Two-sided test", value=True)
        c7, c8 = st.columns(2)
        multiplicity = c7.number_input("Primary hypotheses", min_value=1, max_value=100, value=1, step=1)
        multiplicity_method = c8.selectbox("Multiplicity policy", ["none", "Bonferroni", "Sidak"])

        design_key = DESIGNS[design_label]
        params: dict[str, float | int | bool | str] = {}
        if design_key in {"two_group_continuous", "paired_continuous", "one_way_anova", "repeated_measures", "cluster_randomized"}:
            params["effect_size"] = st.number_input("Standardized effect size", min_value=0.01, max_value=5.0, value=0.5, step=0.05)
        if design_key == "two_proportions":
            p1, p2 = st.columns(2)
            params["proportion_1"] = p1.number_input("Expected proportion · Group 1", min_value=0.001, max_value=0.999, value=0.50, step=0.01)
            params["proportion_2"] = p2.number_input("Expected proportion · Group 2", min_value=0.001, max_value=0.999, value=0.70, step=0.01)
        if design_key == "one_way_anova":
            params["groups"] = st.number_input("Number of groups", min_value=2, max_value=20, value=3, step=1)
        if design_key == "correlation":
            params["correlation"] = st.number_input("Expected correlation", min_value=-0.95, max_value=0.95, value=0.30, step=0.05)
        if design_key == "survival":
            s1, s2 = st.columns(2)
            params["hazard_ratio"] = s1.number_input("Expected hazard ratio", min_value=0.10, max_value=5.0, value=0.70, step=0.05)
            params["event_fraction"] = s2.number_input("Expected event fraction", min_value=0.05, max_value=0.99, value=0.70, step=0.05)
        if design_key in {"precision_mean", "noninferiority", "equivalence"}:
            m1, m2 = st.columns(2)
            params["standard_deviation"] = m1.number_input("Assumed standard deviation", min_value=0.0001, max_value=1_000_000.0, value=1.0, step=0.1)
            if design_key == "precision_mean":
                params["half_width"] = m2.number_input("Desired confidence-interval half-width", min_value=0.0001, max_value=1_000_000.0, value=0.25, step=0.05)
            else:
                params["margin"] = m2.number_input("Scientific margin", min_value=0.0001, max_value=1_000_000.0, value=0.30, step=0.05)
        if design_key == "repeated_measures":
            r1, r2 = st.columns(2)
            params["measurements"] = r1.number_input("Measurements per participant", min_value=2, max_value=100, value=3, step=1)
            params["repeated_measure_correlation"] = r2.number_input("Within-participant correlation", min_value=0.0, max_value=0.90, value=0.50, step=0.05)
        if design_key == "cluster_randomized":
            k1, k2 = st.columns(2)
            params["cluster_size"] = k1.number_input("Average cluster size", min_value=2, max_value=100_000, value=20, step=1)
            params["intraclass_correlation"] = k2.number_input("Intraclass correlation", min_value=0.0, max_value=0.99, value=0.05, step=0.01)
        submitted = st.form_submit_button("Calculate study design", type="primary", width="stretch")

    design_inputs = {
        "design_key": design_key,
        "alpha": float(alpha),
        "power": float(power),
        "dropout_fraction": float(dropout),
        "two_sided": bool(two_sided),
        "allocation_ratio": float(allocation_ratio),
        "multiplicity": int(multiplicity),
        "multiplicity_method": str(multiplicity_method),
        **params,
    }
    if submitted or "step112_design_result" not in st.session_state:
        try:
            result = calculate_design(design_key, **{key: value for key, value in design_inputs.items() if key != "design_key"})
            previous_inputs = st.session_state.get("step112_design_inputs")
            st.session_state["step112_design_result"] = result
            st.session_state["step112_design_inputs"] = design_inputs
            if previous_inputs != design_inputs:
                for stale_key in (
                    "step112_sensitivity",
                    "step112_sensitivity_signature",
                    "step112_simulation",
                    "step112_simulation_signature",
                    "step112_protocol_manifest",
                ):
                    st.session_state.pop(stale_key, None)
        except Exception as exc:
            for stale_key in (
                "step112_design_result",
                "step112_design_inputs",
                "step112_sensitivity",
                "step112_sensitivity_signature",
                "step112_simulation",
                "step112_simulation_signature",
                "step112_protocol_manifest",
            ):
                st.session_state.pop(stale_key, None)
            st.error(f"Design calculation failed: {exc}")

    result = st.session_state.get("step112_design_result")
    if result is not None:
        metric_cards([
            ("Total recruitment", f"{result.total_sample_size:,}", "Includes the configured dropout fraction"),
            ("Complete-case total", f"{result.complete_case_total:,}", "Required analysable observations"),
            ("Target power", f"{result.target_power:.1%}", None),
            ("Adjusted alpha", f"{result.assumptions['adjusted_alpha']:.4g}", "After multiplicity adjustment"),
        ])
        allocation = pd.DataFrame([{"group": group, "sample_size": size} for group, size in result.group_sizes.items()])
        st.plotly_chart(px.bar(allocation, x="group", y="sample_size", text="sample_size", title="Planned allocation"), width="stretch")
        smart_json(result.to_dict(), title="Transparent design result", download_name="study_design_result.json", key="step112_design_result_json")
        if result.warnings:
            for warning in result.warnings:
                st.warning(warning)

with sensitivity_tab:
    result = st.session_state.get("step112_design_result")
    base = dict(st.session_state.get("step112_design_inputs", {}))
    if result is None or not base:
        st.info("Calculate a design first.")
    else:
        vary_choices = ["effect_size", "power", "dropout_fraction", "alpha"]
        if base["design_key"] == "two_proportions":
            vary_choices = ["proportion_2", "power", "dropout_fraction", "alpha"]
        vary = st.selectbox("Sensitivity parameter", vary_choices)
        if vary in {"power"}:
            lower, upper = 0.60, 0.99
        elif vary in {"dropout_fraction"}:
            lower, upper = 0.0, 0.50
        elif vary in {"alpha"}:
            lower, upper = 0.001, 0.10
        elif vary == "proportion_2":
            lower, upper = 0.05, 0.95
        else:
            lower, upper = 0.10, 1.50
        range_values = st.slider("Sensitivity range", min_value=float(lower), max_value=float(upper), value=(float(lower), float(upper)))
        points = st.slider("Scenarios", 5, 50, 20)
        sensitivity_signature = json.dumps(
            {
                "base": base,
                "vary": vary,
                "range": [float(range_values[0]), float(range_values[1])],
                "points": int(points),
            },
            sort_keys=True,
            default=str,
        )
        generate_sensitivity = st.button("Generate sensitivity analysis", width="stretch")
        if generate_sensitivity or st.session_state.get("step112_sensitivity_signature") != sensitivity_signature:
            try:
                values = np.linspace(range_values[0], range_values[1], int(points)).tolist()
                clean_base = {key: value for key, value in base.items() if key != "design_key"}
                st.session_state["step112_sensitivity"] = power_sensitivity(base["design_key"], values, vary=vary, base=clean_base)
                st.session_state["step112_sensitivity_signature"] = sensitivity_signature
            except Exception as exc:
                st.session_state.pop("step112_sensitivity", None)
                st.session_state.pop("step112_sensitivity_signature", None)
                st.error(f"Sensitivity analysis failed: {exc}")
        sensitivity = st.session_state.get("step112_sensitivity", pd.DataFrame())
        if not sensitivity.empty:
            ok = sensitivity[sensitivity["status"] == "ok"].copy()
            if not ok.empty and vary in ok.columns:
                st.plotly_chart(px.line(ok, x=vary, y="total_sample_size", markers=True, title="Recruitment sensitivity"), width="stretch")
            elif vary not in sensitivity.columns:
                st.warning("Sensitivity settings changed. Regenerate the analysis for the selected parameter.")
            smart_dataframe(sensitivity, height=420, key="step112_sensitivity_table")
            st.download_button("Download sensitivity table", sensitivity.to_csv(index=False).encode(), "study_design_sensitivity.csv", "text/csv", width="stretch")

with simulation_tab:
    base = dict(st.session_state.get("step112_design_inputs", {}))
    result = st.session_state.get("step112_design_result")
    supported = base.get("design_key") in {"two_group_continuous", "two_proportions"}
    if result is None:
        st.info("Calculate a design first.")
    elif not supported:
        st.info("Monte-Carlo verification currently supports two independent continuous means and two independent proportions.")
    else:
        s1, s2 = st.columns(2)
        simulations = s1.number_input("Monte-Carlo simulations", min_value=100, max_value=100_000, value=2_000, step=100)
        seed = s2.number_input("Simulation seed", min_value=0, max_value=2_147_483_647, value=42, step=1)
        simulation_signature = json.dumps(
            {
                "base": base,
                "complete_case_total": int(result.complete_case_total),
                "simulations": int(simulations),
                "seed": int(seed),
            },
            sort_keys=True,
            default=str,
        )
        if st.button("Run simulation power check", type="primary", width="stretch"):
            try:
                sim = simulate_power(
                    base["design_key"],
                    total_sample_size=result.complete_case_total,
                    effect_size=float(base.get("effect_size", 0.5)),
                    proportion_1=float(base.get("proportion_1", 0.5)),
                    proportion_2=float(base.get("proportion_2", 0.7)),
                    alpha=float(base.get("alpha", 0.05)),
                    allocation_ratio=float(base.get("allocation_ratio", 1.0)),
                    simulations=int(simulations),
                    seed=int(seed),
                )
                st.session_state["step112_simulation"] = sim
                st.session_state["step112_simulation_signature"] = simulation_signature
            except Exception as exc:
                st.session_state.pop("step112_simulation", None)
                st.session_state.pop("step112_simulation_signature", None)
                st.error(str(exc))
        sim = st.session_state.get("step112_simulation")
        if sim and st.session_state.get("step112_simulation_signature") != simulation_signature:
            st.info("Simulation settings changed. Run the simulation again to refresh the estimate.")
            sim = None
        if sim:
            metric_cards([
                ("Estimated power", f"{sim['estimated_power']:.1%}", None),
                ("Target power", f"{result.target_power:.1%}", None),
                ("Monte-Carlo SE", f"{sim['monte_carlo_standard_error']:.4f}", None),
                ("Simulations", f"{sim['simulations']:,}", None),
            ])
            smart_json(sim, title="Simulation verification", download_name="simulation_power_check.json", key="step112_simulation_json")

with randomization_tab:
    st.caption("Create reproducible, stratified, variable-block allocation. Use a concealed seed for production studies.")
    source = st.radio("Participant source", ["Generate identifiers", "Paste identifiers and optional strata"], horizontal=True)
    if source == "Generate identifiers":
        n = st.number_input("Number of participants", min_value=2, max_value=100_000, value=40, step=2)
        sample_ids = [f"P{index + 1:05d}" for index in range(int(n))]
        strata_map = {sample: "All" for sample in sample_ids}
    else:
        raw = st.text_area("One participant per line: ID or ID<TAB>Stratum", height=180, value="P001\tSite A\nP002\tSite A\nP003\tSite B\nP004\tSite B")
        sample_ids, strata_map = [], {}
        for line in raw.splitlines():
            parts = [item.strip() for item in line.split("\t")]
            if parts and parts[0]:
                sample_ids.append(parts[0])
                strata_map[parts[0]] = parts[1] if len(parts) > 1 and parts[1] else "All"
    r1, r2, r3 = st.columns(3)
    groups_text = r1.text_input("Groups", value="Control,Treatment")
    block_text = r2.text_input("Variable block sizes", value="4,6")
    seed_text = r3.text_input("Seed (blank = secure random)", value="")
    blind_labels = st.toggle("Create blinded arm labels", value=True)
    if st.button("Generate randomisation schedule", type="primary", width="stretch"):
        try:
            groups = [item.strip() for item in groups_text.split(",") if item.strip()]
            block_sizes = tuple(int(item.strip()) for item in block_text.split(",") if item.strip())
            seed_value = int(seed_text) if seed_text.strip() else None
            schedule = build_randomization_schedule(sample_ids, groups, strata=strata_map, block_sizes=block_sizes, seed=seed_value, blind_labels=blind_labels)
            st.session_state["step112_randomization"] = schedule
        except Exception as exc:
            st.session_state.pop("step112_randomization", None)
            st.session_state.pop("step112_protocol_manifest", None)
            st.error(f"Randomisation failed: {exc}")
    schedule = st.session_state.get("step112_randomization", pd.DataFrame())
    if not schedule.empty:
        allocation_summary = schedule.groupby(["stratum", "assigned_group"], as_index=False).size().rename(columns={"size": "participants"})
        st.plotly_chart(px.bar(allocation_summary, x="stratum", y="participants", color="assigned_group", barmode="group", title="Stratified allocation balance"), width="stretch")
        smart_dataframe(schedule, height=440, key="step112_randomization_table")
        st.download_button("Download allocation schedule", schedule.to_csv(index=False).encode(), "randomization_schedule.csv", "text/csv", width="stretch")

with protocol_tab:
    result = st.session_state.get("step112_design_result")
    if result is None:
        st.info("Calculate a design first.")
    else:
        p1, p2 = st.columns(2)
        endpoint = p1.text_input("Primary endpoint", value="Primary quantitative endpoint")
        estimand = p2.text_input("Estimand", value="Difference in group means at the primary time point")
        inclusion = st.text_area("Inclusion criteria", value="Pre-specified eligible population")
        exclusion = st.text_area("Exclusion criteria", value="Pre-specified data-quality and eligibility exclusions")
        missing_policy = st.text_area("Missing-data policy", value="Primary complete-case analysis with sensitivity analysis under multiple imputation")
        multiplicity_policy = st.text_area("Multiplicity policy", value=str(st.session_state.get("step112_design_inputs", {}).get("multiplicity_method", "none")))
        if st.button("Build protocol-ready manifest", type="primary", width="stretch"):
            schedule = st.session_state.get("step112_randomization", pd.DataFrame())
            random_seed = int(schedule["seed"].iloc[0]) if not schedule.empty else None
            manifest = build_design_manifest(
                result,
                endpoint=endpoint,
                estimand=estimand,
                inclusion_criteria=inclusion,
                exclusion_criteria=exclusion,
                missing_data_policy=missing_policy,
                multiplicity_policy=multiplicity_policy,
                randomization_seed=random_seed,
            )
            st.session_state["step112_protocol_manifest"] = manifest
        manifest = st.session_state.get("step112_protocol_manifest")
        if manifest:
            smart_json(manifest, title="Study design manifest", download_name="study_design_manifest.json", key="step112_manifest_json")
            st.download_button("Download protocol manifest", json.dumps(manifest, indent=2, sort_keys=True).encode(), "study_design_manifest.json", "application/json", width="stretch", key="step112_manifest_download")

# Step 115 non-chart visual: plate_map_editor
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("plate_map_editor", key_prefix="step115_121_Biostatistics_Power_and_Experimental_Design_Studio_plate_map_editor", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='biostatistics_design', title='Biostatistics, Power & Experimental Design Studio', category='Research Planning')

st.divider()
section_title("Connected Research Planning OS", "network")
from biointel.research_planning.advanced_renderer import render_connected_planning_os
render_connected_planning_os("biostatistics_design", None, key_prefix="rp_os_biostatistics_design")


st.divider()
section_title("Peak Feature Lab", "analysis")
from biointel.research_planning.feature_density_renderer import render_peak_feature_lab
render_peak_feature_lab("biostatistics_design", None, key_prefix="rp_peak_biostatistics_design")

st.divider()
section_title("Full Research Lifecycle Readiness", "network")
from biointel.research_planning.lifecycle_renderer import render_lifecycle_readiness_panel
render_lifecycle_readiness_panel("biostatistics_design", context=st.session_state.get("biointel_master_research_plan", {}), key_prefix="rp_lifecycle_biostatistics")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
