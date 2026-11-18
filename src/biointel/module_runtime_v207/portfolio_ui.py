from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.module_runtime_v207.portfolio import (
    bioinformatics_cohort_readiness,
    count_matrix_quality,
    demo_frame,
    discovery_assay_readiness,
    lab_assay_quality,
    pareto_rank_candidates,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight


def _input_table(*, key: str, demo_kind: str, label: str) -> pd.DataFrame | None:
    source = st.radio(
        f"{label} data source",
        ["Synthetic demonstration", "Upload CSV/TSV"],
        horizontal=True,
        key=f"{key}_source",
    )
    if source == "Synthetic demonstration":
        st.caption("Synthetic demonstration data · generated locally · not experimental or clinical evidence.")
        return demo_frame(demo_kind)
    upload = st.file_uploader(
        label,
        type=["csv", "tsv", "txt"],
        key=f"{key}_upload",
        help="Files are processed locally. The preview path is memory-limited and larger work should use staged/background ingestion.",
    )
    if upload is None:
        return None
    render_upload_preflight(
        upload,
        key=f"{key}_preflight",
        allowed_extensions=["csv", "tsv", "txt"],
        soft_limit_mb=100,
        hard_limit_mb=1024,
        module_key=key,
    )
    try:
        return read_uploaded_table(upload)
    except Exception as exc:
        st.error(f"Input stopped safely: {type(exc).__name__}: {exc}")
        return None


def _json_download(payload: dict[str, Any], *, file_name: str, key: str) -> None:
    def serialise(value: Any) -> Any:
        if isinstance(value, pd.DataFrame):
            return value.replace({float("nan"): None}).to_dict(orient="records")
        if isinstance(value, pd.Series):
            return value.replace({float("nan"): None}).tolist()
        if isinstance(value, dict):
            return {str(k): serialise(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [serialise(v) for v in value]
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    st.download_button(
        "Download complete local QC report",
        data=json.dumps(serialise(payload), indent=2, ensure_ascii=False, default=str),
        file_name=file_name,
        mime="application/json",
        key=key,
        width="stretch",
    )


def _run_button(key: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any] | None:
    state_key = f"step207_portfolio_result_{key}"
    if st.button("Run validated local workflow", type="primary", key=f"{key}_run", width="stretch"):
        try:
            with st.status("Running deterministic local checks…", expanded=False) as status:
                result = callback()
                st.session_state[state_key] = result
                status.update(label="Workflow completed", state="complete")
        except Exception as exc:
            st.session_state.pop(state_key, None)
            st.error(f"Workflow stopped safely: {type(exc).__name__}: {exc}")
    result = st.session_state.get(state_key)
    return result if isinstance(result, dict) else None


def _render_bioinformatics() -> None:
    metadata_tab, matrix_tab = st.tabs(["Cohort & reference readiness", "Count-matrix quality"])
    with metadata_tab:
        frame = _input_table(key="step207_bio_metadata", demo_kind="bioinformatics_metadata", label="Cohort metadata CSV/TSV")
        if frame is not None:
            st.dataframe(frame.head(50), hide_index=True, width="stretch")
            result = _run_button("step207_bio_metadata", lambda: bioinformatics_cohort_readiness(frame))
            if result:
                summary = result["summary"]
                cols = st.columns(4)
                cols[0].metric("Samples", summary["samples"])
                cols[1].metric("Internal readiness", f"{summary['readiness_score_internal']:.1f}/10")
                cols[2].metric("Blocking", summary["blocking_checks"])
                cols[3].metric("Review", summary["review_checks"])
                smart_dataframe(result["checks"], height=260)
                smart_dataframe(result["missingness"].head(30), height=300)
                for warning in result["warnings"]:
                    st.warning(warning)
                _json_download(result, file_name="BioIntel-Step207-bioinformatics-cohort-readiness.json", key="step207_bio_metadata_export")
    with matrix_tab:
        frame = _input_table(key="step207_bio_matrix", demo_kind="count_matrix", label="Feature × sample count matrix")
        if frame is not None:
            st.dataframe(frame.head(30), hide_index=True, width="stretch")
            result = _run_button("step207_bio_matrix", lambda: count_matrix_quality(frame))
            if result:
                summary = result["summary"]
                cols = st.columns(4)
                cols[0].metric("Features", summary["features"])
                cols[1].metric("Samples", summary["samples"])
                cols[2].metric("Zero fraction", f"{summary['zero_fraction']:.1%}")
                cols[3].metric("Library outliers", summary["library_size_outliers"])
                figure = px.bar(result["sample_qc"], x="sample", y="library_total", hover_data=["detected_features", "missing_fraction"], title="Library totals by sample")
                st.plotly_chart(figure, width="stretch")
                smart_dataframe(result["sample_qc"], height=320)
                smart_dataframe(result["feature_qc"].head(100), height=380)
                for warning in result["warnings"]:
                    st.warning(warning)
                _json_download(result, file_name="BioIntel-Step207-count-matrix-quality.json", key="step207_bio_matrix_export")


def _render_discovery() -> None:
    assay_tab, rank_tab = st.tabs(["Assay normalisation & replicate QC", "Multi-objective Pareto ranking"])
    with assay_tab:
        frame = _input_table(key="step207_discovery_assay", demo_kind="discovery_assay", label="Compound assay CSV/TSV")
        if frame is not None:
            st.dataframe(frame.head(50), hide_index=True, width="stretch")
            result = _run_button("step207_discovery_assay", lambda: discovery_assay_readiness(frame))
            if result:
                summary = result["summary"]
                cols = st.columns(4)
                cols[0].metric("Compounds", summary["compounds"])
                cols[1].metric("Assays", summary["assays"])
                cols[2].metric("Invalid values", summary["invalid_values"])
                cols[3].metric("Discordant replicates", summary["discordant_replicate_groups"])
                normalised = result["normalised_records"]
                if "pactivity" in normalised:
                    st.plotly_chart(px.histogram(normalised, x="pactivity", color="assay_id" if "assay_id" in normalised else None, nbins=30, title="Normalised pActivity distribution"), width="stretch")
                smart_dataframe(result["replicate_qc"], height=360)
                for warning in result["warnings"]:
                    st.warning(warning)
                _json_download(result, file_name="BioIntel-Step207-discovery-assay-QC.json", key="step207_discovery_assay_export")
    with rank_tab:
        frame = _input_table(key="step207_discovery_rank", demo_kind="pareto", label="Candidate-property CSV/TSV")
        if frame is not None:
            numeric = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
            maximize = st.multiselect("Objectives to maximise", numeric, default=[column for column in ("potency", "selectivity") if column in numeric], key="step207_rank_max")
            minimize = st.multiselect("Objectives to minimise", [column for column in numeric if column not in maximize], default=[column for column in ("clearance", "toxicity_proxy") if column in numeric], key="step207_rank_min")
            result = _run_button("step207_discovery_rank", lambda: pareto_rank_candidates(frame, maximize=maximize, minimize=minimize))
            if result:
                summary = result["summary"]
                cols = st.columns(4)
                cols[0].metric("Candidates", summary["candidates"])
                cols[1].metric("Ranked", summary["ranked"])
                cols[2].metric("Pareto front", summary["pareto_front"])
                cols[3].metric("Excluded", summary["excluded"])
                ranking = result["ranking"]
                if len(maximize + minimize) >= 2:
                    x, y = (maximize + minimize)[:2]
                    st.plotly_chart(px.scatter(ranking, x=x, y=y, color="pareto_front", size="weighted_internal_score", hover_data=["internal_rank"], title="Candidate objective space"), width="stretch")
                smart_dataframe(ranking, height=430)
                if not result["excluded"].empty:
                    smart_dataframe(result["excluded"], height=220)
                _json_download(result, file_name="BioIntel-Step207-discovery-pareto-ranking.json", key="step207_discovery_rank_export")


def _render_lab() -> None:
    frame = _input_table(key="step207_lab_assay", demo_kind="lab_assay", label="Assay/plate CSV or TSV")
    if frame is None:
        return
    st.dataframe(frame.head(60), hide_index=True, width="stretch")
    result = _run_button("step207_lab_assay", lambda: lab_assay_quality(frame))
    if not result:
        return
    summary = result["summary"]
    cols = st.columns(5)
    cols[0].metric("Rows", summary["rows"])
    cols[1].metric("Replicate groups", summary["replicate_groups"])
    cols[2].metric("High CV", summary["high_cv_groups"])
    cols[3].metric("Batch drift", summary["batch_drift_flags"])
    z_prime = summary["z_prime"]
    cols[4].metric("Z-prime", f"{z_prime:.3f}" if pd.notna(z_prime) and abs(z_prime) != float("inf") else "Not available")
    tabs = st.tabs(["Replicates", "Batch/plate drift", "Controls"])
    with tabs[0]:
        if not result["replicate_qc"].empty:
            st.plotly_chart(px.bar(result["replicate_qc"].head(50), x=result["replicate_qc"].columns[0], y="cv", title="Replicate coefficient of variation"), width="stretch")
            smart_dataframe(result["replicate_qc"], height=380)
    with tabs[1]:
        if not result["batch_qc"].empty:
            st.plotly_chart(px.bar(result["batch_qc"], x=result["batch_qc"].columns[0], y="drift_z", title="Batch/plate median drift (z proxy)"), width="stretch")
            smart_dataframe(result["batch_qc"], height=320)
    with tabs[2]:
        smart_dataframe(result["control_qc"], height=240)
    for warning in result["warnings"]:
        st.warning(warning)
    _json_download(result, file_name="BioIntel-Step207-lab-assay-quality.json", key="step207_lab_assay_export")


def render_step207_portfolio_panel(category: str, *, expanded: bool = True) -> None:
    with st.expander("Step207 category-wide validation & optimisation", expanded=expanded):
        st.caption("Local-first · deterministic · exportable · no online provider required")
        scientific_boundary_banner(
            source_kind="research_software",
            release_eligible=False,
            message="These workflows audit data and software readiness. They do not manufacture experimental evidence or replace specialist scientific review.",
        )
        if category == "Bioinformatics":
            _render_bioinformatics()
        elif category == "Discovery":
            _render_discovery()
        elif category == "Lab Analytics":
            _render_lab()
        else:
            smart_json({"status": "unsupported category", "category": category})


__all__ = ["render_step207_portfolio_panel"]
