from __future__ import annotations

import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.core import database_file_signature, managed_connect  # noqa: E402

from biointel.quality.model_audit import audit_model_directory
from biointel.training.model_artifact import load_model_artifact_cached
from biointel.training.model_catalog import (
    catalog_json,
    default_model_path,
    sync_model_catalog,
    update_model_catalog,
)

MODELS = ROOT / "models"


def _models_signature(models: Path) -> tuple[tuple[str, int, int], ...]:
    paths = [models / "catalog.json", *sorted(models.glob("*.joblib"))]
    return tuple(
        (path.name, int(stat.st_mtime_ns), int(stat.st_size))
        for path in paths
        if path.is_file()
        for stat in (path.stat(),)
    )


@st.cache_data(ttl=300, show_spinner=False)
def _cached_model_quality(
    models_text: str,
    signature: tuple[tuple[str, int, int], ...],
):
    del signature
    models = Path(models_text)
    quality_audit = audit_model_directory(models)
    audit_by_model = {item["model_file"]: item for item in quality_audit["models"]}
    metadata_by_model = {}
    for path in sorted(models.glob("*.joblib")):
        try:
            artifact = load_model_artifact_cached(path, trusted_root=models)
        except Exception as exc:
            metadata_by_model[path.name] = {"task": "error", "estimator": str(exc)}
            continue
        metadata = artifact.metadata
        audit = audit_by_model.get(path.name, {})
        metadata_by_model[path.name] = {
            "task": metadata.task_type,
            "estimator": metadata.model_name,
            "model_version": metadata.model_version,
            "dataset": metadata.dataset_name,
            "test_metric": (
                metadata.metrics.get("roc_auc")
                if metadata.task_type == "classification"
                else metadata.metrics.get("rmse")
            ),
            "synthetic_demo": metadata.synthetic_demo,
            "quality_score": audit.get("score", 0.0),
            "release_eligible": audit.get("release_eligible", False),
            "quality_blockers": " • ".join(audit.get("blockers", [])),
        }
    return {"audit_by_model": audit_by_model, "metadata_by_model": metadata_by_model}


@st.cache_data(ttl=300, show_spinner=False)
def _cached_experiment_depth(
    database_text: str,
    signature: tuple[int, int, int, int, int, int],
    experiment_id: str,
):
    del signature
    try:
        with managed_connect(database_text) as connection:
            connection.row_factory = sqlite3.Row
            return {
                "folds": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM experiment_folds WHERE experiment_id=? ORDER BY fold_index",
                        (experiment_id,),
                    ).fetchall()
                ],
                "trials": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM hyperparameter_trials WHERE experiment_id=? ORDER BY trial_number",
                        (experiment_id,),
                    ).fetchall()
                ],
                "runtime": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM experiment_runtime_metrics WHERE experiment_id=? ORDER BY metric_name",
                        (experiment_id,),
                    ).fetchall()
                ],
                "events": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM experiment_events WHERE experiment_id=? ORDER BY created_at_utc",
                        (experiment_id,),
                    ).fetchall()
                ],
            }
    except sqlite3.OperationalError:
        return {"folds": [], "trials": [], "runtime": [], "events": []}


from biointel.ui.brand import branded_model_label_from_sidecar
from biointel.ui.components import smart_dataframe
from biointel.ui.theme import apply_theme, badge, hero

st.set_page_config(
    page_title="Model Lifecycle · BioIntel AI",
    page_icon="🏷️",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("model_lifecycle", key_prefix="step116_22_Model_Lifecycle_model_lifecycle_1", expanded=False)
hero(
    "🏷️ Model Lifecycle",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption(
    "Mark models as candidate, active or archived and choose the "
    "default model used by prediction workflows."
)

entries = sync_model_catalog(MODELS)
quality_snapshot = _cached_model_quality(str(MODELS), _models_signature(MODELS))
audit_by_model = quality_snapshot["audit_by_model"]
metadata_by_model = quality_snapshot["metadata_by_model"]
if not entries:
    st.info("No model artifacts are available.")
    st.stop()

rows = [
    {**asdict(entry), **metadata_by_model.get(entry.filename, {"task": "unavailable"})}
    for entry in entries
]

smart_dataframe(
    pd.DataFrame(rows),
    height=520,
    columns={
        "quality_score": st.column_config.ProgressColumn(
            "Quality score", min_value=0.0, max_value=100.0, format="%.1f"
        ),
        "synthetic_demo": st.column_config.CheckboxColumn("Synthetic"),
        "release_eligible": st.column_config.CheckboxColumn("Release eligible"),
    },
)

selected_name = st.selectbox(
    "Select model",
    [entry.filename for entry in entries],
    format_func=lambda name: branded_model_label_from_sidecar(
        MODELS / name, audit_by_model.get(name, {})
    ),
)
selected_entry = next(item for item in entries if item.filename == selected_name)
selected_artifact = load_model_artifact_cached(MODELS / selected_name, trusted_root=MODELS)
selected_audit = audit_by_model.get(selected_name, {})
if selected_audit.get("release_eligible"):
    badge("● Release quality gate passed", "success")
else:
    badge("● Demonstration/candidate only · activation blocked by quality policy", "warning")
    for blocker in selected_audit.get("blockers", []):
        st.caption(f"• {blocker}")
experiment_id = selected_artifact.metadata.experiment_id
experiment_database = ROOT / "reports" / "experiments.sqlite3"
experiment_depth = _cached_experiment_depth(
    str(experiment_database),
    database_file_signature(experiment_database),
    experiment_id,
)
fold_rows = experiment_depth["folds"]
trial_rows = experiment_depth["trials"]
runtime_rows = experiment_depth["runtime"]
event_rows = experiment_depth["events"]

if fold_rows or trial_rows or runtime_rows or event_rows:
    st.subheader("Experiment depth")
    fold_tab, trial_tab, runtime_tab, event_tab = st.tabs(
        ["Cross-validation folds", "Hyperparameter trials", "Runtime metrics", "Events"]
    )
    with fold_tab:
        st.dataframe(pd.DataFrame(fold_rows), width="stretch", hide_index=True)
    with trial_tab:
        st.dataframe(pd.DataFrame(trial_rows), width="stretch", hide_index=True)
    with runtime_tab:
        st.dataframe(pd.DataFrame(runtime_rows), width="stretch", hide_index=True)
    with event_tab:
        st.dataframe(pd.DataFrame(event_rows), width="stretch", hide_index=True)
    st.warning(
        "These records describe synthetic/reference benchmark models; they are not real experimental validation runs."
    )

with st.form("model_lifecycle_form"):
    state = st.selectbox(
        "Lifecycle state",
        ["candidate", "active", "archived"],
        index=["candidate", "active", "archived"].index(selected_entry.state),
    )
    default = st.checkbox(
        "Use as default model",
        value=selected_entry.is_default,
    )
    notes = st.text_area(
        "Lifecycle notes",
        value=selected_entry.notes,
    )
    submitted = st.form_submit_button(
        "Update lifecycle",
        type="primary",
    )

if submitted:
    try:
        updated = update_model_catalog(
            MODELS,
            selected_name,
            state=state,
            is_default=default,
            notes=notes,
            enforce_quality=True,
        )
    except Exception as exc:
        st.error(str(exc))
    else:
        _cached_model_quality.clear()
        st.success(f"Updated {updated.filename}: {updated.state}, default={updated.is_default}")
        st.rerun()

default_path = default_model_path(MODELS)
st.info("Current default: " + (default_path.name if default_path else "Not selected"))

st.download_button(
    "Download model catalog JSON",
    catalog_json(MODELS),
    "model_catalog.json",
    "application/json",
)

# Step 115 module-specific non-chart workspace: model_registry
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("model_registry", key_prefix="step115_22_Model_Lifecycle_model_registry", expanded=False)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
