from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.dti.activity import standardize_activity
from biointel.dti.dataset_validation import (
    validate_dti_dataset,
)
from biointel.ui.components import smart_json
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

st.set_page_config(
    page_title="DTI Data Quality · BioIntel AI",
    page_icon="🧹",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("data_quality", key_prefix="step116_8_Data_Quality_Activity_data_quality_1", expanded=False)
hero("🧹 DTI Data Quality & Activity Standardization", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")

activity_tab, dataset_tab = st.tabs(["Activity converter", "Dataset quality audit"])

with activity_tab:
    left, middle, right = st.columns(3)
    activity_type = left.selectbox("Activity type", ["Kd", "Ki", "IC50", "EC50"])
    value = middle.number_input(
        "Activity value",
        min_value=0.000000001,
        value=1000.0,
        format="%.9f",
    )
    unit = right.selectbox(
        "Unit",
        ["M", "mM", "uM", "µM", "nM", "pM"],
        index=4,
    )

    try:
        result = standardize_activity(activity_type, value, unit)
        output_left, output_right = st.columns(2)
        output_left.metric(
            "Molar concentration",
            f"{result.molar_value:.6e} M",
        )
        output_right.metric(
            "pActivity",
            f"{result.p_activity:.4f}",
        )
        st.caption(
            "pActivity = −log10(activity in molar units). " "Do not mix assay types by default."
        )
    except ValueError as exc:
        st.error(str(exc))

with dataset_tab:
    dataset_source = st.selectbox(
        "Dataset source",
        [
            "Foundation pack — 1,920 rows",
            "Extended pack — 5,760 rows",
            "Ultra pack — 16,000 rows",
            "Double Ultra pack — 32,000 rows",
            "5X Ultra pack — 160,000 rows",
            "Upload CSV",
        ],
    )
    task = st.radio(
        "Dataset task",
        ["classification", "regression"],
        horizontal=True,
    )

    dataframe: pd.DataFrame | None = None
    if dataset_source == "Upload CSV":
        uploaded = st.file_uploader(
            "Upload DTI CSV",
            type=["csv"],
            key="quality_csv",
        )
        render_upload_preflight(
            uploaded, key="dti_quality", allowed_extensions=["csv"], soft_limit_mb=50, hard_limit_mb=250
        )
        if uploaded is not None:
            try:
                if uploaded.size > 250 * 1024 * 1024:
                    raise ValueError("CSV exceeds the 250 MB limit.")
                dataframe = read_uploaded_table(uploaded)
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")
                st.stop()
    else:
        if dataset_source.startswith("Foundation"):
            filename = "synthetic_foundation_dti_v2.csv"
        elif dataset_source.startswith("5X"):
            filename = "synthetic_5x_ultra_dti_v5.csv"
        elif dataset_source.startswith("Double"):
            filename = "synthetic_double_ultra_dti_v4.csv"
        elif dataset_source.startswith("Ultra"):
            filename = "synthetic_ultra_dti_v3.csv"
        else:
            filename = "synthetic_extended_dti_v2.csv"
        pack_path = ROOT / "data" / "packs" / filename
        if not pack_path.is_file():
            st.error("Bundled data pack is missing. Run " "BUILD_DATA_AND_MODELS_WINDOWS.bat.")
            st.stop()
        dataframe = read_csv_cached(pack_path)
        st.warning("Bundled packs are synthetic software benchmarks, " "not experimental evidence.")

    if dataframe is None:
        st.info(
            "Choose a bundled pack or upload a CSV to audit "
            "invalid rows, duplicates and conflicts."
        )
    else:
        try:
            report = validate_dti_dataset(
                dataframe,
                task,
            )
        except Exception as exc:
            st.error(f"Audit failed: {exc}")
            st.stop()

        metrics = st.columns(5)
        metrics[0].metric("Original", report.total_rows)
        metrics[1].metric("Clean unique", report.valid_rows)
        metrics[2].metric("Invalid", report.invalid_rows)
        metrics[3].metric("Duplicates", report.duplicate_rows)
        metrics[4].metric(
            "Conflicting groups",
            report.conflicting_groups,
        )
        smart_json(report.summary)

        clean_tab, errors_tab, dup_tab, conflict_tab = st.tabs(
            ["Cleaned", "Invalid", "Duplicates", "Conflicts"]
        )
        clean_tab.dataframe(
            report.cleaned,
            width="stretch",
            hide_index=True,
        )
        errors_tab.dataframe(
            report.errors,
            width="stretch",
            hide_index=True,
        )
        dup_tab.dataframe(
            report.duplicates,
            width="stretch",
            hide_index=True,
        )
        conflict_tab.dataframe(
            report.conflicts,
            width="stretch",
            hide_index=True,
        )

        st.download_button(
            "Download cleaned CSV",
            report.cleaned.to_csv(index=False),
            "cleaned_dti_dataset.csv",
            "text/csv",
        )
        st.download_button(
            "Download quality report JSON",
            json.dumps(report.summary, indent=2, default=str),
            "data_quality_report.json",
            "application/json",
        )

st.info(
    "Kd, Ki, IC50 and EC50 describe different experimental "
    "concepts. Use a consistent activity definition."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='data_quality', title='Data Quality & Activity', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
