from __future__ import annotations

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

from biointel.reports.model_card import build_model_card_markdown
from biointel.training.explainability import extract_global_feature_importance
from biointel.training.model_artifact import (
    discover_compatible_model_artifacts,
    load_model_artifact_cached,
)
from biointel.ui.components import smart_json
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import (
    apply_theme,
    hero,
)
from biointel.utils.exceptions import BioIntelError

st.set_page_config(
    page_title="Model Evaluation · BioIntel AI",
    page_icon="📊",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("model_evaluation", key_prefix="step116_7_Model_Evaluation_model_evaluation_1", expanded=False)
hero("📊 Saved Model Evaluation", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Compare validation and final held-out test metrics " "stored in trusted local model artifacts."
)

models_directory = ROOT / "models"
paths, incompatible_models = discover_compatible_model_artifacts(models_directory)
if incompatible_models:
    with st.expander(f"Excluded incompatible benchmark/model files · {len(incompatible_models)}"):
        st.dataframe(
            pd.DataFrame(
                [{"file": name, "reason": reason} for name, reason in incompatible_models.items()]
            ),
            width="stretch",
            hide_index=True,
        )
if not paths:
    st.info("No saved models found. Train a model first.")
    st.stop()

selected_paths = st.multiselect(
    "Models to compare",
    paths,
    default=paths[: min(2, len(paths))],
    format_func=lambda path: path.name,
)
if not selected_paths:
    st.stop()

records: list[dict[str, object]] = []
for path in selected_paths:
    try:
        artifact = load_model_artifact_cached(
            path,
            trusted_root=models_directory,
        )
        metadata = artifact.metadata
        base: dict[str, object] = {
            "File": path.name,
            "Task": metadata.task_type,
            "Model": metadata.model_name,
            "Version": metadata.model_version,
            "Dataset": metadata.dataset_name,
            "Dataset SHA-256": metadata.dataset_sha256[:12] + "…",
            "Experiment ID": metadata.experiment_id,
            "Split": metadata.split_strategy,
            "Threshold strategy": metadata.threshold_strategy,
            "Calibration": metadata.calibration_method,
            "Train rows": metadata.train_rows,
            "Validation rows": metadata.validation_rows,
            "Test rows": metadata.test_rows,
            "Synthetic demo": metadata.synthetic_demo,
        }
        base.update(
            {f"Validation {key}": value for key, value in metadata.validation_metrics.items()}
        )
        base.update({f"Test {key}": value for key, value in metadata.metrics.items()})
        records.append(base)

        with st.expander(path.name):
            smart_json(json.loads(artifact.metadata_json()))
            download_left, download_right = st.columns(2)
            download_left.download_button(
                f"Download metadata — {path.name}",
                artifact.metadata_json(),
                f"{path.stem}_metadata.json",
                "application/json",
                key=f"download_{path.name}",
                width="stretch",
            )
            download_right.download_button(
                f"Download model card — {path.name}",
                build_model_card_markdown(artifact),
                f"{path.stem}_model_card.md",
                "text/markdown",
                key=f"card_{path.name}",
                width="stretch",
            )
            st.write("Bootstrap confidence intervals")
            smart_json(metadata.confidence_intervals)
            st.write("Conformal uncertainty calibration")
            smart_json(metadata.uncertainty_calibration)
            importance = extract_global_feature_importance(artifact, top_n=30)
            if importance.empty:
                st.info("This estimator does not expose model-native global feature importance.")
            else:
                st.write("Global feature importance")
                st.plotly_chart(
                    px.bar(
                        importance.sort_values("importance"),
                        x="importance",
                        y="feature",
                        orientation="h",
                        title="Top model-native feature importance",
                    ),
                    width="stretch",
                )
                st.dataframe(importance, width="stretch", hide_index=True)
                st.caption("Importance is model-level association, not biological causality.")
    except BioIntelError as exc:
        st.error(f"{path.name}: {exc}")
    except Exception as exc:
        st.error(f"{path.name}: incompatible artifact — {exc}")

comparison = pd.DataFrame(records)
if not comparison.empty:
    st.subheader("Comparison table")
    st.dataframe(
        comparison,
        width="stretch",
        hide_index=True,
    )

    excluded = {
        "File",
        "Task",
        "Model",
        "Version",
        "Dataset",
        "Dataset SHA-256",
        "Experiment ID",
        "Split",
        "Threshold strategy",
        "Calibration",
        "Train rows",
        "Validation rows",
        "Test rows",
        "Synthetic demo",
    }
    numeric_metrics = [
        column
        for column in comparison.columns
        if column not in excluded and pd.api.types.is_numeric_dtype(comparison[column])
    ]
    melted = comparison.melt(
        id_vars=["File"],
        value_vars=numeric_metrics,
        var_name="Metric",
        value_name="Value",
    ).dropna()

    if not melted.empty:
        render_generic_visual_explorer(
            melted,
            key="model_evaluation_visuals",
            secondary=comparison,
            heading="Model comparison visual analytics",
        )
        st.plotly_chart(
            px.bar(
                melted,
                x="Metric",
                y="Value",
                color="File",
                barmode="group",
            ),
            width="stretch",
        )

st.info(
    "Only compare metrics when datasets, activity definitions and split "
    "strategies are comparable. Random-pair results can be optimistic when "
    "related drugs or targets occur across splits."
)

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("model_evaluation", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
