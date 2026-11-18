from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import (
    precision_recall_curve,
    roc_curve,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.dataset_registry import register_dataset
from biointel.dti.dataset_validation import validate_dti_dataset
from biointel.reports.model_card import build_model_card_markdown
from biointel.training.experiment_registry import register_experiment
from biointel.training.model_artifact import save_model_artifact
from biointel.training.model_catalog import (
    default_model_path,
    sync_model_catalog,
    update_model_catalog,
)
from biointel.training.trainers import (
    TrainingConfig,
    train_dti_model,
)
from biointel.ui.components import smart_json
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import (
    apply_theme,
    hero,
    section_title,
)
from biointel.ui.workflow import indeterminate_loader, read_uploaded_table, render_upload_preflight
from biointel.utils.exceptions import TrainingError

st.set_page_config(
    page_title="DTI Model Training · BioIntel AI",
    page_icon="🧠",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("model_training", key_prefix="step116_5_Model_Training_model_training_1", expanded=False)
hero(
    "Train models with clean splits and visible evidence.",
    (
        "Audit the dataset, isolate train/validation/test partitions, "
        "calibrate uncertainty and save a reproducible model artifact."
    ),
    eyebrow="DTI model studio",
    chips=["Leakage-aware", "Conformal uncertainty", "Model cards"],
)
section_title("Training configuration", "⚙️")

bundled_sources = {
    "Quick demo — 96 rows": {
        "path": ROOT / "data/examples/synthetic_dti_demo.csv",
        "task": "classification",
        "name": "synthetic_quick_demo",
        "version": "1.0",
    },
    "Foundation pack — 1,920 rows": {
        "path": ROOT / "data/packs/synthetic_foundation_dti_v2.csv",
        "task": "classification",
        "name": "biointel_foundation_dti_v2",
        "version": "2.0",
    },
    "Extended pack — 5,760 rows": {
        "path": ROOT / "data/packs/synthetic_extended_dti_v2.csv",
        "task": "classification",
        "name": "biointel_extended_dti_v2",
        "version": "2.0",
    },
    "Ultra pack — 16,000 rows": {
        "path": ROOT / "data/packs/synthetic_ultra_dti_v3.csv",
        "task": "classification",
        "name": "biointel_ultra_dti_v3",
        "version": "3.0",
    },
    "Double Ultra pack — 32,000 rows": {
        "path": ROOT / "data/packs/synthetic_double_ultra_dti_v4.csv",
        "task": "classification",
        "name": "biointel_double_ultra_dti_v4",
        "version": "4.0",
    },
    "5X Ultra pack — 160,000 rows": {
        "path": ROOT / "data/packs/synthetic_5x_ultra_dti_v5.csv",
        "task": "classification",
        "name": "biointel_5x_ultra_dti_v5",
        "version": "5.0",
    },
}

source = st.selectbox(
    "Dataset source",
    ["Upload CSV", *bundled_sources],
    index=3,
)

dataframe: pd.DataFrame | None = None
synthetic_demo = False
default_task = "classification"
default_dataset_name = "user_dataset"
default_dataset_version = "1.0"
default_split_strategy = "random_pair"

if source == "Upload CSV":
    uploaded = st.file_uploader(
        "Upload DTI dataset",
        type=["csv"],
    )
    render_upload_preflight(
        uploaded, key="dti_training", allowed_extensions=["csv"], soft_limit_mb=50, hard_limit_mb=250
    )
    if uploaded is not None:
        if uploaded.size > 250 * 1024 * 1024:
            st.error("CSV exceeds the 250 MB safety limit.")
            st.stop()
        try:
            dataframe = read_uploaded_table(uploaded)
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            st.stop()
else:
    selected_source = bundled_sources[source]
    source_path = selected_source["path"]
    if not source_path.is_file():
        st.error("Bundled data pack is missing. Run " "BUILD_DATA_AND_MODELS_WINDOWS.bat.")
        st.stop()
    if source.startswith("5X"):
        st.info(
            "5X mode loads 160,000 rows only after explicit selection. "
            "Use Extended or Foundation for fast iteration."
        )
    dataframe = read_csv_cached(source_path, low_memory=False)
    synthetic_demo = True
    default_task = str(selected_source["task"])
    default_dataset_name = str(selected_source["name"])
    default_dataset_version = str(selected_source["version"])
    default_split_strategy = "drug_group"

if dataframe is None:
    st.info("Upload a dataset or choose a bundled data pack.")
    st.stop()

st.subheader("Dataset preview")
st.dataframe(dataframe.head(50), width="stretch", hide_index=True)
if synthetic_demo:
    st.warning(
        "Bundled packs are deterministic synthetic benchmarks for software "
        "testing and training practice. They are not experimental evidence."
    )

task = st.radio(
    "Task",
    ["classification", "regression"],
    index=0 if default_task == "classification" else 1,
    horizontal=True,
)

try:
    quality = validate_dti_dataset(dataframe, task)
except Exception as exc:
    st.error(f"Dataset validation failed: {exc}")
    st.stop()

quality_columns = st.columns(5)
quality_columns[0].metric("Original rows", quality.total_rows)
quality_columns[1].metric("Clean unique rows", quality.valid_rows)
quality_columns[2].metric("Invalid rows", quality.invalid_rows)
quality_columns[3].metric("Exact duplicates", quality.duplicate_rows)
quality_columns[4].metric("Conflicting groups", quality.conflicting_groups)

with st.expander("Data-quality details", expanded=False):
    smart_json(quality.summary)
    if not quality.errors.empty:
        st.write("Invalid rows")
        st.dataframe(quality.errors, width="stretch", hide_index=True)
    if not quality.duplicates.empty:
        st.write("Removed exact duplicates")
        st.dataframe(quality.duplicates, width="stretch", hide_index=True)
    if not quality.conflicts.empty:
        st.write("Removed conflicting drug–target pairs")
        st.dataframe(quality.conflicts, width="stretch", hide_index=True)

if quality.valid_rows < 12:
    st.error(
        "At least 12 valid unique rows are required after cleaning. "
        "Larger and more diverse datasets are strongly recommended."
    )
    st.stop()

with st.form("training_configuration"):
    left, middle, right = st.columns(3)

    if task == "classification":
        model_choices = [
            "random_forest",
            "logistic_regression",
            "hist_gradient_boosting",
        ]
    else:
        model_choices = [
            "random_forest",
            "ridge",
            "hist_gradient_boosting",
        ]

    model_name = left.selectbox("Model", model_choices)
    split_options = [
        "random_pair",
        "drug_group",
        "target_group",
        "scaffold",
        "temporal",
        "cold_drug_target",
        "protein_cluster",
    ]
    split_strategy = middle.selectbox(
        "Split strategy",
        split_options,
        index=split_options.index(default_split_strategy),
        help=(
            "Temporal, cold drug-target and protein-cluster splits provide stricter "
            "scientific leakage control but require the matching columns and diversity."
        ),
    )
    dataset_name = right.text_input(
        "Dataset name",
        value=default_dataset_name,
    )

    split_left, split_middle, split_right = st.columns(3)
    test_fraction = split_left.slider(
        "Final test fraction",
        0.10,
        0.40,
        0.20,
        0.05,
    )
    validation_fraction = split_middle.slider(
        "Validation fraction",
        0.10,
        0.30,
        0.15,
        0.05,
    )
    random_seed = split_right.number_input(
        "Random seed",
        min_value=0,
        max_value=999999,
        value=42,
    )

    temporal_column = "publication_date"
    sequence_identity_threshold = 0.70
    if split_strategy == "temporal":
        temporal_column = st.text_input(
            "Temporal date column",
            value="publication_date",
            help="Rows are ordered by this date; the newest rows become validation/test data.",
        )
    elif split_strategy == "protein_cluster":
        sequence_identity_threshold = st.slider(
            "Maximum cross-split protein identity threshold",
            0.40,
            1.00,
            0.70,
            0.05,
        )
    elif split_strategy == "cold_drug_target":
        st.caption("Requires drug_id and target_id; both entities are unseen in the test split.")

    feature_left, feature_middle, feature_right = st.columns(3)
    fingerprint_bits = feature_left.selectbox(
        "Morgan fingerprint bits",
        [128, 256, 512, 1024, 2048],
        index=1,
    )
    fingerprint_radius = feature_middle.selectbox(
        "Morgan radius",
        [1, 2, 3],
        index=1,
    )
    include_dipeptides = feature_right.checkbox(
        "Include 400 dipeptide features",
        value=False,
    )

    threshold_strategy = "fixed"
    decision_threshold = 0.5
    calibration_method = "none"

    if task == "classification":
        class_left, class_middle, class_right = st.columns(3)
        threshold_strategy = class_left.selectbox(
            "Threshold strategy",
            ["fixed", "optimize_f1", "optimize_balanced"],
            help=(
                "Optimized thresholds are selected on validation data only. "
                "The final test set remains untouched."
            ),
        )
        decision_threshold = class_middle.slider(
            "Fixed decision threshold",
            0.05,
            0.95,
            0.50,
            0.05,
            disabled=threshold_strategy != "fixed",
        )
        calibration_method = class_right.selectbox(
            "Probability calibration",
            ["none", "sigmoid", "isotonic"],
            help=("Calibration is fitted inside cross-validation on the training split."),
        )

    model_version = st.text_input(
        "Model version",
        value="2.0.0" if synthetic_demo else "1.0.0",
    )
    conformal_alpha = st.slider("Conformal error rate α", 0.05, 0.30, 0.10, 0.05)
    submitted = st.form_submit_button(
        "Train and evaluate model",
        type="primary",
    )

if submitted:
    config = TrainingConfig(
        task_type=task,
        model_name=model_name,
        split_strategy=split_strategy,
        test_fraction=float(test_fraction),
        validation_fraction=float(validation_fraction),
        random_seed=int(random_seed),
        decision_threshold=float(decision_threshold),
        threshold_strategy=threshold_strategy,
        calibration_method=calibration_method,
        fingerprint_radius=int(fingerprint_radius),
        fingerprint_bits=int(fingerprint_bits),
        include_dipeptides=include_dipeptides,
        dataset_name=dataset_name.strip() or "dataset",
        dataset_version=default_dataset_version,
        model_version=model_version.strip() or "1.0.0",
        synthetic_demo=synthetic_demo,
        conformal_alpha=float(conformal_alpha),
        temporal_column=temporal_column,
        sequence_identity_threshold=float(sequence_identity_threshold),
    )

    with indeterminate_loader("Cleaning, featurizing, splitting, training and evaluating..."):
        try:
            result = train_dti_model(dataframe, config)
        except TrainingError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Unexpected training error: {exc}")
            st.stop()

    st.session_state["training_result"] = result
    st.session_state["training_config"] = config
    try:
        registered_dataset = register_dataset(
            ROOT / "reports" / "datasets.sqlite3",
            quality.cleaned,
            dataset_name=config.dataset_name,
            dataset_version=config.dataset_version,
            task_type=config.task_type,
            source_description=(
                "Bundled synthetic demonstration dataset"
                if synthetic_demo
                else "Model-training CSV upload"
            ),
            activity_type=config.activity_type,
            notes=("Automatically registered by the training workflow."),
            metadata={
                "experiment_id": result.artifact.metadata.experiment_id,
                "valid_rows": quality.valid_rows,
                "invalid_rows": quality.invalid_rows,
                "duplicate_rows": quality.duplicate_rows,
                "conflicting_groups": quality.conflicting_groups,
            },
        )
        st.session_state["registered_dataset_sha256"] = registered_dataset.dataset_sha256
    except Exception as exc:
        st.session_state["dataset_registry_warning"] = str(exc)

if "training_result" not in st.session_state:
    st.warning(
        "Configure the run and press **Train and evaluate model**. "
        "Synthetic metrics are demonstrations only."
    )
    st.stop()

result = st.session_state["training_result"]
config = st.session_state["training_config"]
task = result.artifact.metadata.task_type
model_name = result.artifact.metadata.model_name
dataset_name = result.artifact.metadata.dataset_name

status_left, status_right = st.columns([3, 1])
status_left.success(
    "Training result is preserved for this browser session. "
    f"Experiment: {result.artifact.metadata.experiment_id}"
)
if st.session_state.get("registered_dataset_sha256"):
    st.caption("Dataset registry SHA-256: " + st.session_state["registered_dataset_sha256"])
if st.session_state.get("dataset_registry_warning"):
    st.warning(
        "Dataset registry update was skipped: " + st.session_state["dataset_registry_warning"]
    )
if status_right.button("Clear result"):
    del st.session_state["training_result"]
    del st.session_state["training_config"]
    st.rerun()
row_columns = st.columns(3)
row_columns[0].metric("Training rows", result.train_rows)
row_columns[1].metric("Validation rows", result.validation_rows)
row_columns[2].metric("Final test rows", result.test_rows)

c1, c2 = st.columns(2)
with c1.expander("Bootstrap 95% confidence intervals"):
    smart_json(result.artifact.metadata.confidence_intervals)
with c2.expander("Conformal uncertainty calibration"):
    smart_json(result.artifact.metadata.uncertainty_calibration)

if task == "classification":
    threshold = result.artifact.metadata.decision_threshold
    st.metric(
        "Decision threshold",
        f"{threshold:.3f}" if threshold is not None else "N/A",
    )

validation_tab, test_tab, audit_tab = st.tabs(
    ["Validation metrics", "Final test metrics", "Training audit"]
)

with validation_tab:
    st.dataframe(
        pd.DataFrame(
            [{"Metric": key, "Value": value} for key, value in result.validation_metrics.items()]
        ),
        width="stretch",
        hide_index=True,
    )

with test_tab:
    st.dataframe(
        pd.DataFrame([{"Metric": key, "Value": value} for key, value in result.metrics.items()]),
        width="stretch",
        hide_index=True,
    )

    if task == "classification":
        predictions = result.predictions
        y_true = predictions["actual"].to_numpy()
        probabilities = predictions["positive_probability"].to_numpy()

        if len(set(y_true.tolist())) == 2:
            false_positive_rate, true_positive_rate, _ = roc_curve(y_true, probabilities)
            precision, recall, _ = precision_recall_curve(y_true, probabilities)
            chart_left, chart_right = st.columns(2)
            chart_left.plotly_chart(
                px.line(
                    x=false_positive_rate,
                    y=true_positive_rate,
                    labels={"x": "False-positive rate", "y": "True-positive rate"},
                    title="Final test ROC curve",
                ),
                width="stretch",
            )
            chart_right.plotly_chart(
                px.line(
                    x=recall,
                    y=precision,
                    labels={"x": "Recall", "y": "Precision"},
                    title="Final test precision–recall curve",
                ),
                width="stretch",
            )
        st.dataframe(predictions, width="stretch", hide_index=True)
    else:
        predictions = result.predictions.copy()
        predictions["residual"] = predictions["actual"] - predictions["predicted"]
        chart_left, chart_right = st.columns(2)
        chart_left.plotly_chart(
            px.scatter(
                predictions,
                x="actual",
                y="predicted",
                title="Final test: actual vs predicted",
            ),
            width="stretch",
        )
        chart_right.plotly_chart(
            px.scatter(
                predictions,
                x="predicted",
                y="residual",
                title="Final test residuals",
            ),
            width="stretch",
        )
        st.dataframe(predictions, width="stretch", hide_index=True)

with audit_tab:
    smart_json(result.data_quality_summary)
    if not result.feature_errors.empty:
        st.warning(f"{len(result.feature_errors)} rows failed during feature extraction.")
        st.dataframe(
            result.feature_errors,
            width="stretch",
            hide_index=True,
        )

models_directory = ROOT / "models"
models_directory.mkdir(parents=True, exist_ok=True)
safe_name = (
    "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in dataset_name.strip()
    ).strip("_")
    or "dataset"
)
default_filename = f"{safe_name}_{task}_{model_name}_{config.model_version}.joblib"
filename = st.text_input(
    "Model artifact filename",
    value=default_filename,
)
save_clicked = st.button("Save trusted local model", type="primary")

if save_clicked:
    output_name = Path(filename).name
    if not output_name.endswith(".joblib"):
        output_name += ".joblib"
    saved = save_model_artifact(
        result.artifact,
        models_directory / output_name,
    )
    register_experiment(
        ROOT / "reports" / "experiments.sqlite3",
        result.artifact,
        saved.name,
    )
    sync_model_catalog(models_directory)
    first_model = default_model_path(models_directory) is None
    update_model_catalog(
        models_directory,
        saved.name,
        state="active" if first_model else "candidate",
        is_default=first_model,
        notes=("Automatically added by the training workflow."),
    )
    st.success(f"Saved model, experiment and lifecycle entry: {saved.name}")
    metadata_column, card_column = st.columns(2)
    metadata_column.download_button(
        "Download readable model metadata",
        result.artifact.metadata_json(),
        saved.with_suffix(".json").name,
        "application/json",
        width="stretch",
    )
    card_column.download_button(
        "Download model card",
        build_model_card_markdown(result.artifact),
        saved.with_suffix(".model_card.md").name,
        "text/markdown",
        width="stretch",
    )

st.download_button(
    "Download final test predictions CSV",
    result.predictions.to_csv(index=False),
    "final_test_predictions.csv",
    "text/csv",
)
st.download_button(
    "Download training summary JSON",
    json.dumps(
        {
            "metadata": json.loads(result.artifact.metadata_json()),
            "validation_metrics": result.validation_metrics,
            "test_metrics": result.metrics,
        },
        indent=2,
        default=str,
    ),
    "training_summary.json",
    "application/json",
)

st.info(
    "Metrics from synthetic or small datasets are not scientifically meaningful. "
    "Use curated experimental data, consistent assay definitions, realistic "
    "negative examples and leakage-resistant evaluation."
)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
