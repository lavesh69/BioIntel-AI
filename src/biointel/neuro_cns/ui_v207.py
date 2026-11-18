from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from biointel.neuro_cns.translational_v207 import (
    FEATURES,
    brain_network_vulnerability_analysis,
    cognitive_trajectory_analysis,
    demo_frame,
    digital_neurology_sensor_analysis,
    fluid_biomarker_panel,
    neurodevelopmental_trajectory_analysis,
    neuroimmune_interaction_analysis,
    neurorehabilitation_response_analysis,
    neurovascular_research_profile,
    polypharmacy_cns_burden,
    sleep_circadian_profile,
)
from biointel.neuro_cns.visuals_v207 import figures_for
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import section_title

SafeRun = Callable[[str, str, Callable[[], Any]], Any | None]
SaveResult = Callable[[str, Any], None]
CsvUpload = Callable[..., pd.DataFrame | None]

FEATURE_BY_KEY = {key: (title, description) for key, title, description in FEATURES}


def _network_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if data.shape[1] == data.shape[0] + 1:
        first = data.columns[0]
        labels = data[first].astype(str)
        data = data.drop(columns=[first])
        data.index = labels
    if data.shape[0] == data.shape[1] and list(data.index) == list(range(len(data))):
        data.index = data.columns.astype(str)
    return data


def _source_frame(feature_key: str, csv_upload: CsvUpload) -> pd.DataFrame:
    title, _ = FEATURE_BY_KEY[feature_key]
    uploaded = csv_upload(
        f"Optional CSV/TSV for {title}",
        f"step207_{feature_key}_upload",
        help_text="Files above the interactive preview boundary are staged safely by the shared upload layer.",
    )
    if uploaded is None:
        st.info("Using clearly labelled synthetic demonstration data. Upload a table to analyse your own de-identified research data.")
        frame = demo_frame(feature_key)
    else:
        frame = uploaded
    st.caption(f"Input preview · {len(frame):,} rows × {len(frame.columns):,} columns")
    smart_dataframe(frame.head(250), key=f"step207_{feature_key}_input", height=300)
    return frame


def _run_function(feature_key: str, frame: pd.DataFrame) -> tuple[Callable[[], dict[str, Any]], dict[str, Any]]:
    params: dict[str, Any] = {}
    if feature_key == "neurovascular_research":
        return lambda: neurovascular_research_profile(frame), params
    if feature_key == "sleep_circadian":
        columns = frame.columns.astype(str).tolist()
        timestamp = st.selectbox("Timestamp column", columns, index=columns.index("timestamp") if "timestamp" in columns else 0, key="v207_sleep_time")
        activity = st.selectbox("Activity column", columns, index=columns.index("activity") if "activity" in columns else min(1, len(columns)-1), key="v207_sleep_activity")
        heart_options = ["None", *columns]
        heart_default = heart_options.index("heart_rate") if "heart_rate" in heart_options else 0
        heart = st.selectbox("Optional heart-rate column", heart_options, index=heart_default, key="v207_sleep_hr")
        params = {"timestamp_col": timestamp, "activity_col": activity, "heart_rate_col": None if heart == "None" else heart}
        return lambda: sleep_circadian_profile(frame, **params), params
    if feature_key == "fluid_biomarkers":
        columns = frame.columns.astype(str).tolist()
        group = st.selectbox("Two-group column", columns, index=columns.index("group") if "group" in columns else 0, key="v207_biomarker_group")
        groups = frame[group].dropna().astype(str).unique().tolist() if group in frame else []
        positive = st.selectbox("Positive/research condition", groups or ["condition"], index=max(0, len(groups)-1), key="v207_biomarker_positive")
        iterations = st.slider("Bootstrap iterations", 50, 1000, 200, 50, key="v207_biomarker_boot")
        params = {"group_col": group, "positive_group": positive, "bootstrap_iterations": iterations}
        return lambda: fluid_biomarker_panel(frame, **params), params
    if feature_key == "digital_neurology":
        columns = frame.columns.astype(str).tolist()
        timestamp = st.selectbox("Timestamp column", columns, index=columns.index("timestamp") if "timestamp" in columns else 0, key="v207_digital_time")
        window = st.slider("Window seconds", 2.0, 60.0, 10.0, 1.0, key="v207_digital_window")
        params = {"timestamp_col": timestamp, "window_seconds": window}
        return lambda: digital_neurology_sensor_analysis(frame, **params), params
    if feature_key == "neuroimmune_interactions":
        columns = frame.columns.astype(str).tolist()
        condition = st.selectbox("Condition column", columns, index=columns.index("condition") if "condition" in columns else 0, key="v207_immune_condition")
        params = {"condition_col": condition}
        return lambda: neuroimmune_interaction_analysis(frame, **params), params
    if feature_key == "cognitive_trajectory":
        c1, c2 = st.columns(2)
        higher = c1.checkbox("Higher score means better function", value=True, key="v207_cog_direction")
        rapid = c2.number_input("Rapid-change threshold per year", min_value=0.1, value=2.0, step=0.1, key="v207_cog_threshold")
        params = {"higher_is_better": higher, "rapid_change_per_year": rapid}
        return lambda: cognitive_trajectory_analysis(frame, **params), params
    if feature_key == "neurorehabilitation":
        columns = frame.columns.astype(str).tolist()
        c1, c2 = st.columns(2)
        baseline = c1.selectbox("Baseline column", columns, index=columns.index("baseline") if "baseline" in columns else 0, key="v207_rehab_baseline")
        followup = c2.selectbox("Follow-up column", columns, index=columns.index("followup") if "followup" in columns else min(1, len(columns)-1), key="v207_rehab_followup")
        higher = c1.checkbox("Higher score means improvement", value=True, key="v207_rehab_direction")
        mcid = c2.number_input("MCID", min_value=0.0, value=3.0, step=0.5, key="v207_rehab_mcid")
        reliability = st.slider("Instrument reliability", 0.50, 0.99, 0.90, 0.01, key="v207_rehab_reliability")
        params = {"baseline_col": baseline, "followup_col": followup, "higher_is_better": higher, "mcid": mcid, "reliability": reliability}
        return lambda: neurorehabilitation_response_analysis(frame, **params), params
    if feature_key == "polypharmacy_cns":
        return lambda: polypharmacy_cns_burden(frame), params
    if feature_key == "brain_network_vulnerability":
        threshold = st.slider("Absolute connectivity threshold", 0.05, 0.90, 0.30, 0.05, key="v207_network_threshold")
        matrix = _network_matrix(frame)
        params = {"threshold": threshold}
        return lambda: brain_network_vulnerability_analysis(matrix, **params), params
    if feature_key == "neurodevelopmental_trajectory":
        return lambda: neurodevelopmental_trajectory_analysis(frame), params
    raise KeyError(feature_key)


def _render_result(feature_key: str, result: dict[str, Any]) -> None:
    figures = figures_for(feature_key, result)
    summary = result.get("summary") or result.get("cohort_summary") or result.get("global_metrics")
    if isinstance(summary, dict):
        metric_items = []
        for key, value in list(summary.items())[:4]:
            if isinstance(value, float):
                display = f"{value:.3g}"
            else:
                display = value
            metric_items.append((key.replace("_", " ").title(), display, None))
        if metric_items:
            metric_cards(metric_items)
    tabs = []
    if figures:
        tabs.append("Scientific visuals")
    dataframes = [(key, value) for key, value in result.items() if isinstance(value, pd.DataFrame)]
    if dataframes:
        tabs.append("Result tables")
    tabs.append("Method & boundary")
    containers = st.tabs(tabs)
    index = 0
    if figures:
        with containers[index]:
            figure_tabs = st.tabs([name.replace("_", " ").title() for name in figures])
            for tab, (_, figure) in zip(figure_tabs, figures.items()):
                with tab:
                    st.plotly_chart(figure, width="stretch")
        index += 1
    if dataframes:
        with containers[index]:
            table_tabs = st.tabs([name.replace("_", " ").title() for name, _ in dataframes])
            for tab, (name, table) in zip(table_tabs, dataframes):
                with tab:
                    smart_dataframe(table, key=f"v207_{feature_key}_{name}", height=420)
                    st.download_button(
                        "Download CSV",
                        table.to_csv(index=True).encode("utf-8"),
                        f"BioIntel-Neuro-{feature_key}-{name}.csv",
                        "text/csv",
                        key=f"v207_download_{feature_key}_{name}",
                        width="stretch",
                    )
        index += 1
    with containers[index]:
        metadata = {key: value for key, value in result.items() if not isinstance(value, pd.DataFrame)}
        smart_json(metadata, title="Method metadata", download_name=f"BioIntel-Neuro-{feature_key}-metadata.json", key=f"v207_meta_{feature_key}")
        scientific_boundary_banner(
            source_kind="research_software",
            release_eligible=False,
            message=str(result.get("scientific_boundary", "Research-only analysis.")),
        )


def render_step207_neuro_feature(
    feature_key: str,
    *,
    safe_run: SafeRun,
    save_result: SaveResult,
    csv_upload: CsvUpload,
) -> None:
    title, description = FEATURE_BY_KEY[feature_key]
    st.subheader(title)
    st.caption(description)
    frame = _source_frame(feature_key, csv_upload)
    run, parameters = _run_function(feature_key, frame)
    if st.button("Run research workflow", type="primary", key=f"v207_run_{feature_key}", width="stretch"):
        result = safe_run(feature_key, f"Running {title}", run)
        if result:
            result["run_parameters"] = parameters
            save_result(feature_key, result)
    stored = st.session_state.get("_biointel_neuro_cns_results", {}).get(feature_key)
    if isinstance(stored, dict):
        _render_result(feature_key, stored)


def render_step207_neuro_portfolio(*, safe_run: SafeRun) -> None:
    section_title("Ten Step207 Neuro/CNS additions", "✦")
    st.caption(
        "New local-first research workflows extend neurovascular, circadian, fluid-biomarker, digital-neurology, neuroimmune, cognitive, rehabilitation, medication-burden, connectome-resilience and developmental analysis."
    )
    rows = pd.DataFrame(
        [
            {"feature_key": key, "feature": title, "purpose": description, "demo": "Synthetic/reference labelled"}
            for key, title, description in FEATURES
        ]
    )
    smart_dataframe(rows, key="step207_neuro_portfolio", height=390)
    if st.button("Run all ten synthetic smoke workflows", key="v207_run_all_smoke", width="stretch"):
        functions = {
            "neurovascular_research": neurovascular_research_profile,
            "sleep_circadian": sleep_circadian_profile,
            "fluid_biomarkers": fluid_biomarker_panel,
            "digital_neurology": digital_neurology_sensor_analysis,
            "neuroimmune_interactions": neuroimmune_interaction_analysis,
            "cognitive_trajectory": cognitive_trajectory_analysis,
            "neurorehabilitation": neurorehabilitation_response_analysis,
            "polypharmacy_cns": polypharmacy_cns_burden,
            "brain_network_vulnerability": brain_network_vulnerability_analysis,
            "neurodevelopmental_trajectory": neurodevelopmental_trajectory_analysis,
        }
        outcomes = []
        for key, function in functions.items():
            try:
                result = function(demo_frame(key))
                frame_outputs = sum(isinstance(value, pd.DataFrame) for value in result.values())
                outcomes.append({"feature_key": key, "status": "passed", "table_outputs": frame_outputs, "boundary_present": bool(result.get("scientific_boundary"))})
            except Exception as exc:
                outcomes.append({"feature_key": key, "status": "failed", "table_outputs": 0, "boundary_present": False, "error": f"{type(exc).__name__}: {exc}"})
        st.session_state["_biointel_step207_neuro_smoke"] = pd.DataFrame(outcomes)
    outcomes = st.session_state.get("_biointel_step207_neuro_smoke")
    if isinstance(outcomes, pd.DataFrame):
        passed = int((outcomes["status"] == "passed").sum())
        metric_cards([("Workflows passed", passed, f"/{len(outcomes)}"), ("Failures", int((outcomes["status"] == "failed").sum()), None)])
        smart_dataframe(outcomes, key="step207_neuro_smoke_results")
    scientific_boundary_banner(
        source_kind="demo_reference",
        release_eligible=False,
        message="Synthetic smoke workflows establish software execution only. They do not create external scientific, clinical, wet-lab or regulatory validation.",
    )


__all__ = ["render_step207_neuro_feature", "render_step207_neuro_portfolio"]
