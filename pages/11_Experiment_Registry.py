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

from biointel.training.experiment_registry import (
    delete_experiment,
    list_experiments,
)

REGISTRY = ROOT / "reports" / "experiments.sqlite3"

from biointel.ui.components import smart_json
from biointel.ui.performance import read_sql_cached
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero

st.set_page_config(
    page_title="Experiment Registry · BioIntel AI",
    page_icon="🗂️",
    layout="wide",
)

apply_theme()
hero("🗂️ Experiment Registry", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Local reproducibility history. Raw sequences and complete datasets are "
    "not stored in the registry."
)

records = list_experiments(REGISTRY)
if not records:
    st.info("No registered experiments yet. Train and save a model to create one.")
    st.stop()

display = pd.DataFrame(records)
registry_counts = read_sql_cached(
    REGISTRY,
    """
    SELECT
      (SELECT COUNT(*) FROM experiment_artifacts WHERE status='available') AS artifact_count,
      (SELECT COUNT(*) FROM experiment_dataset_bindings WHERE verified=1) AS binding_count,
      (SELECT COUNT(*) FROM experiment_validation_requirements WHERE status='blocked') AS blocked_count
    """,
).iloc[0]
artifact_count = int(registry_counts["artifact_count"])
binding_count = int(registry_counts["binding_count"])
blocked_count = int(registry_counts["blocked_count"])
metrics = st.columns(5)
metrics[0].metric("Experiments", len(display))
metrics[1].metric("Synthetic/demo", int(display["synthetic_demo"].sum()))
metrics[2].metric("Verified bindings", binding_count)
metrics[3].metric("Available artifacts", artifact_count)
metrics[4].metric("Blocked requirements", blocked_count)
summary_columns = [
    "experiment_id",
    "trained_at_utc",
    "model_file",
    "model_name",
    "model_version",
    "task_type",
    "dataset_name",
    "dataset_version",
    "dataset_sha256",
    "split_strategy",
    "synthetic_demo",
    "train_rows",
    "validation_rows",
    "test_rows",
]
st.dataframe(
    display[summary_columns],
    width="stretch",
    hide_index=True,
)

selected = st.selectbox(
    "Inspect experiment",
    [record["experiment_id"] for record in records],
)
record = next(item for item in records if item["experiment_id"] == selected)

left, right = st.columns(2)
with left:
    st.subheader("Final test metrics")
    smart_json(json.loads(record["metrics_json"]))
with right:
    st.subheader("Validation metrics")
    smart_json(json.loads(record["validation_metrics_json"]))

with st.expander("Complete stored metadata"):
    smart_json(json.loads(record["metadata_json"]))

detail_tabs = st.tabs(["Dataset bindings", "Artifacts", "Validation requirements", "Cross-validation folds", "Hyperparameter trials"])
queries = [
    ("SELECT binding_role,dataset_sha256,verified,verification_message,created_at_utc FROM experiment_dataset_bindings WHERE experiment_id=? ORDER BY binding_role", detail_tabs[0]),
    ("SELECT artifact_type,relative_path,size_bytes,status,sha256,created_at_utc FROM experiment_artifacts WHERE experiment_id=? ORDER BY artifact_type", detail_tabs[1]),
    ("SELECT requirement_label,status,message,evidence_reference,checked_at_utc FROM experiment_validation_requirements WHERE experiment_id=? ORDER BY status,requirement_label", detail_tabs[2]),
    ("SELECT fold_index,train_rows,validation_rows,test_rows,metrics_json,validation_metrics_json,split_metadata_json FROM experiment_folds WHERE experiment_id=? ORDER BY fold_index", detail_tabs[3]),
    ("SELECT trial_number,parameters_json,objective_name,objective_value,state,duration_seconds FROM hyperparameter_trials WHERE experiment_id=? ORDER BY trial_number", detail_tabs[4]),
]
for query_text, tab in queries:
    rows = read_sql_cached(REGISTRY, query_text, params=(selected,))
    with tab:
        if rows.empty:
            st.info("No records are available for this experiment.")
        else:
            st.dataframe(rows, width="stretch", hide_index=True)

if bool(record.get("synthetic_demo")):
    st.warning("This experiment uses synthetic/reference training data. Registry completeness does not make it scientifically validated.")

st.download_button(
    "Download registry CSV",
    display.to_csv(index=False),
    "biointel_experiment_registry.csv",
    "text/csv",
)

with st.expander("Remove registry entry"):
    st.warning("This removes only the registry row. It does not delete the model file.")
    confirm = st.checkbox(
        f"Confirm removal of {selected}",
        key="confirm_registry_delete",
    )
    if st.button("Remove selected registry entry", disabled=not confirm):
        if delete_experiment(REGISTRY, selected):
            st.success("Registry entry removed. Refresh the page.")
        else:
            st.error("Registry entry was not found.")

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("experiment_registry", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
