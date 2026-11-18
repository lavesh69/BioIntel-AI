from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.training.external_validation import evaluate_external_dataset
from biointel.training.model_artifact import (
    discover_compatible_model_artifacts,
    load_model_artifact_cached,
)
from biointel.ui.components import smart_json
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import analysis_run, read_uploaded_table, render_upload_preflight
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title="External Validation & Drift · BioIntel AI", page_icon="🧭", layout="wide"
)
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("external_validation", key_prefix="step116_14_External_Validation_Drift_external_validation_1", expanded=False)
hero(
    "🧭 External Validation & Dataset Drift",
    "Select inputs quickly, then load the frozen estimator only when validation is requested.",
    eyebrow="Step 97 · Lazy model loading and upload-safe validation",
)

models, incompatible_models = discover_compatible_model_artifacts(ROOT / "models")
if incompatible_models:
    st.caption(
        f"Excluded {len(incompatible_models)} incompatible benchmark/model file(s) from this workflow."
    )
if not models:
    st.error("No compatible BioIntel model artifact was found.")
    st.stop()

selected = st.selectbox("Frozen model", models, format_func=lambda path: path.name)
# Read the lightweight JSON sidecar on initial render. The estimator is deserialized only after Run.
task_type = "classification"
sidecar = selected.with_suffix(".json")
try:
    if sidecar.is_file():
        task_type = str(json.loads(sidecar.read_text(encoding="utf-8")).get("task_type", task_type))
except (OSError, json.JSONDecodeError):
    st.warning("The model metadata sidecar could not be read; task type will be verified during the run.")

source = st.radio(
    "Validation data source",
    ["Coverage independent validation", "Coverage shifted drift sample", "Upload labelled table"],
    horizontal=True,
)
df: pd.DataFrame | None = None
input_sha = ""
if source == "Upload labelled table":
    uploaded = st.file_uploader(
        "Independent labelled CSV/TSV/Excel",
        type=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
    )
    profile = render_upload_preflight(
        uploaded,
        key="external_validation",
        allowed_extensions=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
        soft_limit_mb=40,
        hard_limit_mb=350,
    )
    if uploaded is not None:
        try:
            df = read_uploaded_table(uploaded, max_cells=15_000_000)
            input_sha = profile.sha256 if profile else ""
        except Exception as exc:
            st.error(f"Validation table could not be loaded: {exc}")
            st.stop()
else:
    prefix = "external_validation" if source == "Coverage independent validation" else "drift_validation"
    filename = (
        f"{prefix}_classification_{5000 if prefix == 'external_validation' else 2000}.csv"
        if task_type == "classification"
        else f"{prefix}_regression_{5000 if prefix == 'external_validation' else 2000}.csv"
    )
    path = ROOT / "data" / "coverage" / filename
    if path.is_file():
        df = read_csv_cached(path)
        input_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        st.download_button("Download selected validation CSV", path.read_bytes(), path.name, "text/csv")
    else:
        st.error("Coverage validation data is missing. Run SEED_COMPLETE_DATA_WINDOWS.bat.")

if df is not None:
    st.caption(f"Model task: {task_type} · Validation rows: {len(df):,}")
    st.dataframe(df.head(50), width="stretch")
    run_signature = hashlib.sha256(
        f"{selected.resolve()}|{selected.stat().st_mtime_ns}|{input_sha}|{len(df)}".encode("utf-8")
    ).hexdigest()
    if st.button("Run external validation", type="primary", width="stretch"):
        try:
            with analysis_run("Loading frozen model and evaluating the independent dataset") as run:
                run.stage("Loading verified model artifact", progress=0.2)
                artifact = load_model_artifact_cached(selected, trusted_root=ROOT / "models")
                run.stage("Validating schema and generating predictions", progress=0.45)
                result = evaluate_external_dataset(artifact, df)
                run.stage("Computing drift and conformal diagnostics", progress=0.9)
            st.session_state["ext_result"] = result
            st.session_state["ext_result_signature"] = run_signature
        except Exception as exc:
            st.error(f"External validation could not complete: {exc}")

    result = st.session_state.get("ext_result")
    if st.session_state.get("ext_result_signature") != run_signature:
        result = None
    if result:
        a, b, c, d = st.columns(4)
        a.metric("Input", result.input_rows)
        b.metric("Valid", result.valid_rows)
        c.metric("Invalid", result.invalid_rows)
        d.metric("Drift", result.drift.get("status"))
        metrics_tab, drift_tab, predictions_tab, errors_tab = st.tabs(
            ["Metrics", "Drift", "Predictions", "Errors"]
        )
        with metrics_tab:
            smart_json({"metrics": result.metrics, "conformal": result.conformal_diagnostics})
        with drift_tab:
            smart_json({key: value for key, value in result.drift.items() if key != "top_shifted_features"})
            shifts = pd.DataFrame(result.drift.get("top_shifted_features", []))
            if not shifts.empty:
                st.plotly_chart(
                    px.bar(shifts, x="standardized_mean_shift", y="feature", orientation="h"),
                    width="stretch",
                )
        with predictions_tab:
            st.dataframe(result.predictions, width="stretch")
        with errors_tab:
            st.dataframe(result.errors, width="stretch")
        report = {
            "metrics": result.metrics,
            "conformal": result.conformal_diagnostics,
            "drift": result.drift,
            "dataset_sha256": result.dataset_sha256,
            "model": selected.name,
        }
        st.download_button(
            "Download report JSON",
            json.dumps(report, indent=2, default=str),
            "external_validation.json",
            "application/json",
        )

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("external_validation", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
