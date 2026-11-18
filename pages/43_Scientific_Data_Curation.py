from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.curation import curate_activity_dataset
from biointel.training.dataset_bias import analyze_dataset_bias
from biointel.ui.components import smart_json
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

st.set_page_config(page_title="Scientific Data Curation · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("data_curation", key_prefix="step116_43_Scientific_Data_Curation_data_curation_1", expanded=False)
hero("🧪 Scientific Data Curation & Bias Control", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Standardize compounds and targets, normalize activity units, score assay evidence, "
    "resolve duplicates and expose dataset concentration before model training."
)

source_mode = st.radio(
    "Data source",
    ["Preloaded demonstration dataset", "Upload CSV"],
    horizontal=True,
)
DEMO_ACTIVITY = ROOT / "data" / "examples" / "demo_workspace" / "BioIntel_Demo_Activity_Data.csv"
if source_mode == "Preloaded demonstration dataset":
    source = read_csv_cached(DEMO_ACTIVITY, low_memory=False)
    st.warning(
        "Loaded prepopulated demonstration/reference rows. These values are for learning the "
        "curation workflow and are not experimental evidence."
    )
    st.download_button(
        "Download demonstration activity CSV",
        DEMO_ACTIVITY.read_bytes(),
        DEMO_ACTIVITY.name,
        "text/csv",
    )
else:
    uploaded = st.file_uploader("Activity dataset CSV", type=["csv"])
    render_upload_preflight(
        uploaded, key="scientific_curation", allowed_extensions=["csv"], soft_limit_mb=50, hard_limit_mb=250
    )
    if uploaded is None:
        st.info(
            "Upload a CSV containing SMILES, protein sequence, activity value and unit. "
            "Optional fields include relation, activity type, UniProt accession, organism, "
            "assay ID, publication ID, confidence score and replicate count."
        )
        st.stop()
    if uploaded.size > 250 * 1024 * 1024:
        st.error("CSV exceeds the 250 MB safety limit.")
        st.stop()
    try:
        source = read_uploaded_table(uploaded, low_memory=False)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        st.stop()

st.dataframe(source.head(100), width="stretch", hide_index=True)
columns = list(source.columns)
if len(columns) < 4:
    st.error("At least four columns are required.")
    st.stop()

left, middle, right = st.columns(3)
smiles_column = left.selectbox(
    "SMILES column",
    columns,
    index=columns.index("canonical_smiles") if "canonical_smiles" in columns else 0,
)
sequence_column = middle.selectbox(
    "Protein sequence column",
    columns,
    index=(
        columns.index("protein_sequence")
        if "protein_sequence" in columns
        else min(1, len(columns) - 1)
    ),
)
value_column = right.selectbox(
    "Activity value column",
    columns,
    index=(
        columns.index("standard_value") if "standard_value" in columns else min(2, len(columns) - 1)
    ),
)

left, middle, right = st.columns(3)
unit_column = left.selectbox(
    "Activity unit column",
    columns,
    index=(
        columns.index("standard_units") if "standard_units" in columns else min(3, len(columns) - 1)
    ),
)
relation_options = ["None — assume =", *columns]
relation_selected = middle.selectbox(
    "Relation column",
    relation_options,
    index=(
        relation_options.index("standard_relation")
        if "standard_relation" in relation_options
        else 0
    ),
)
activity_options = ["None — unspecified", *columns]
activity_selected = right.selectbox(
    "Activity type column",
    activity_options,
    index=(activity_options.index("activity_type") if "activity_type" in activity_options else 0),
)

left, middle, right = st.columns(3)
active_threshold = left.slider("Active pActivity threshold", 4.0, 10.0, 6.0, 0.25)
aggregate_duplicates = middle.checkbox("Aggregate exact duplicate groups", value=True)
source_database = right.text_input("Source database", value="local_import")

if st.button("Curate and quality-check dataset", type="primary"):
    working = source.copy()
    if relation_selected.startswith("None"):
        working["_biointel_relation"] = "="
        relation_column = "_biointel_relation"
    else:
        relation_column = relation_selected
    if activity_selected.startswith("None"):
        working["_biointel_activity_type"] = "unspecified"
        activity_column = "_biointel_activity_type"
    else:
        activity_column = activity_selected
    try:
        curated, errors, summary = curate_activity_dataset(
            working,
            smiles_column=smiles_column,
            sequence_column=sequence_column,
            value_column=value_column,
            unit_column=unit_column,
            relation_column=relation_column,
            activity_type_column=activity_column,
            active_threshold=float(active_threshold),
            aggregate_duplicates=aggregate_duplicates,
            source_database=source_database.strip() or "local_import",
        )
        bias = analyze_dataset_bias(curated)
    except Exception as exc:
        st.error(str(exc))
    else:
        st.session_state["curated_activity"] = curated
        st.session_state["curation_errors"] = errors
        st.session_state["curation_summary"] = summary
        st.session_state["curation_bias"] = bias

curated = st.session_state.get("curated_activity")
summary = st.session_state.get("curation_summary")
bias = st.session_state.get("curation_bias")
errors = st.session_state.get("curation_errors")
if curated is not None and summary is not None and bias is not None:
    metrics = st.columns(6)
    metrics[0].metric("Input", summary.input_rows)
    metrics[1].metric("Curated", summary.curated_rows)
    metrics[2].metric("Invalid", summary.invalid_rows)
    metrics[3].metric("Duplicate groups", summary.duplicate_groups)
    metrics[4].metric("Conflict groups", summary.conflict_groups)
    metrics[5].metric("Unique targets", bias.unique_targets)

    overview, bias_tab, data_tab, error_tab = st.tabs(
        ["Quality overview", "Bias analysis", "Curated rows", "Rejected rows"]
    )
    with overview:
        smart_json(asdict(summary))
        if not curated.empty:
            counts = (
                curated["activity_state"]
                .value_counts()
                .rename_axis("state")
                .reset_index(name="rows")
            )
            st.plotly_chart(
                px.bar(counts, x="state", y="rows", title="Activity-state distribution"),
                width="stretch",
            )
    with bias_tab:
        smart_json(asdict(bias))
        if bias.warnings:
            for warning in bias.warnings:
                st.warning(warning)
        else:
            st.success("No major concentration warning was triggered by the built-in checks.")
    with data_tab:
        st.dataframe(curated, width="stretch", hide_index=True)
    with error_tab:
        st.dataframe(errors, width="stretch", hide_index=True)

    st.download_button(
        "Download curated CSV",
        curated.to_csv(index=False),
        "curated_activity_dataset.csv",
        "text/csv",
    )
    report = {"summary": asdict(summary), "bias": asdict(bias)}
    st.download_button(
        "Download curation report JSON",
        json.dumps(report, indent=2, default=str),
        "curation_quality_report.json",
        "application/json",
    )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scientific_curation', title='Scientific Data Curation', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
