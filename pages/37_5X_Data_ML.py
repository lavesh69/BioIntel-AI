from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import (
    data_library_summary,
    verify_data_pack_integrity,
)
from biointel.training.model_artifact import (
    load_model_artifact_cached,
)
from biointel.training.model_catalog import (
    default_model_path,
    sync_model_catalog,
)
from biointel.ui.components import smart_json
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
)
from biointel.utils.runtime_cache import (
    load_json_cached,
    read_csv_cached,
)

st.set_page_config(
    page_title="5X Data ML · BioIntel AI",
    page_icon="🚀",
    layout="wide",
)

apply_theme()
summary = data_library_summary(ROOT)
integrity = verify_data_pack_integrity(ROOT)
benchmark = summary["benchmark"]
ranking = pd.DataFrame(benchmark.get("ranking", []))
five_x_ranking = (
    ranking[ranking["training_pack"] == "five_x_ultra"].copy()
    if not ranking.empty and "training_pack" in ranking.columns
    else pd.DataFrame()
)
step19_results = benchmark.get(
    "step19_results",
    [],
)
catalog = sync_model_catalog(ROOT / "models")
five_x_models = [entry for entry in catalog if entry.filename.startswith("packv5_5x_")]

hero(
    "Five-times data training with leakage-resistant full-data ML.",
    (
        "Inspect the exact 160,000-pair pack, six full-data models, "
        "grouped holdout metrics, feature-cache efficiency and ready "
        "training/prediction templates."
    ),
    eyebrow="Quality-Hardened · 5X Data ML",
    chips=[
        "160,000 pairs",
        "1,000 molecules",
        "160 targets",
        "23 registered demonstration models",
    ],
)

badge(
    (
        "● 5X data and model suite verified"
        if integrity["valid"]
        else "● Data-pack integrity requires attention"
    ),
    "success" if integrity["valid"] else "danger",
)

best = benchmark.get("best_models", {})
classification_best = best.get("classification", {})
regression_best = best.get("regression", {})

professional_strip(
    "Full-data benchmark",
    (
        f"{len(five_x_models)} pack-v5 model(s) · "
        f"{len(catalog)} total artifact(s) · "
        "drug-group classification and target-group regression"
    ),
)

executive_kpis(
    [
        (
            "5X pairs",
            "160,000",
            "1,000 molecules × 160 targets",
        ),
        (
            "5X classifier leader",
            "Extra Trees",
            "ROC-AUC 0.9085",
        ),
        (
            "5X regression leader",
            "Extra Trees",
            "RMSE 0.3155",
        ),
        (
            "Global default",
            str(
                classification_best.get(
                    "model_name",
                    "Not available",
                )
            ),
            str(
                classification_best.get(
                    "filename",
                    "No default",
                )
            ),
        ),
    ]
)

dataset_tab, models_tab, templates_tab, verification_tab = st.tabs(
    [
        "5X dataset",
        "Model leaderboard",
        "Input templates",
        "Verification",
    ]
)

with dataset_tab:
    section_title("160,000-pair dataset", "🧬")
    dataset_path = ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv"
    if not dataset_path.is_file():
        st.error("5X data pack is missing. Run " "BUILD_DATA_AND_MODELS_WINDOWS.bat.")
    else:
        profile = load_json_cached(
            ROOT / "data" / "packs" / "5x_data_profile.json",
            default={},
        )
        preview = read_csv_cached(
            dataset_path,
            nrows=100,
        )
        columns = st.columns(5)
        columns[0].metric("Rows", f"{int(profile.get('rows', 0)):,}")
        columns[1].metric(
            "Molecules",
            f"{int(profile.get('molecules', 0)):,}",
        )
        columns[2].metric(
            "Targets",
            f"{int(profile.get('targets', 0)):,}",
        )
        columns[3].metric(
            "Positive labels",
            f"{float(profile.get('positive_fraction', 0.0)) * 100:.2f}%",
        )
        columns[4].metric(
            "Activity range",
            (
                f"{float(profile.get('p_activity_min', 0.0)):.2f}–"
                f"{float(profile.get('p_activity_max', 0.0)):.2f}"
            ),
        )
        st.dataframe(
            preview,
            width="stretch",
            hide_index=True,
        )
        family_counts = pd.Series(
            profile.get("target_family_counts", {}),
            dtype=int,
        )
        st.bar_chart(family_counts)
        st.caption(
            "Optimized preview mode: only 100 rows are loaded until a full "
            "training or download action is explicitly requested."
        )
        if st.toggle(
            "Prepare complete 80 MB dataset download",
            key="prepare_5x_download",
        ):
            st.download_button(
                "Download complete 5X dataset",
                dataset_path.read_bytes(),
                dataset_path.name,
                "text/csv",
            )

with models_tab:
    section_title("Six full-data models", "🏆")
    if five_x_ranking.empty:
        st.warning("5X benchmark results are missing. Run the " "Quality-Hardened training suite.")
    else:
        st.dataframe(
            five_x_ranking,
            width="stretch",
            hide_index=True,
        )
        task = st.radio(
            "Leaderboard task",
            ["classification", "regression"],
            horizontal=True,
        )
        task_rows = five_x_ranking[five_x_ranking["task_type"] == task]
        metric = "test_roc_auc" if task == "classification" else "test_rmse"
        if metric in task_rows:
            st.bar_chart(task_rows[["model_name", metric]].dropna().set_index("model_name"))

    section_title("Pack-v5 artifacts", "🧠")
    artifact_rows = []
    for entry in five_x_models:
        path = ROOT / "models" / entry.filename
        try:
            artifact = load_model_artifact_cached(
                path,
                trusted_root=ROOT / "models",
            )
        except Exception as exc:
            artifact_rows.append(
                {
                    "filename": entry.filename,
                    "load_error": str(exc),
                }
            )
            continue
        metrics = artifact.metadata.metrics
        split = artifact.metadata.data_quality_summary.get(
            "split_summary",
            {},
        )
        artifact_rows.append(
            {
                "filename": entry.filename,
                "task": artifact.metadata.task_type,
                "algorithm": artifact.metadata.model_name,
                "train_rows": artifact.metadata.train_rows,
                "validation_rows": (artifact.metadata.validation_rows),
                "test_rows": artifact.metadata.test_rows,
                "group_overlap": split.get("group_overlap"),
                "roc_auc": metrics.get("roc_auc"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "rmse": metrics.get("rmse"),
                "r2": metrics.get("r2"),
                "default": entry.is_default,
            }
        )
    st.dataframe(
        pd.DataFrame(artifact_rows),
        width="stretch",
        hide_index=True,
    )

with templates_tab:
    section_title("Ready 5X inputs", "📥")
    template_specs = [
        (
            "Classification training",
            "five_x_classification_training_template_500.csv",
        ),
        (
            "Regression training",
            "five_x_regression_training_template_500.csv",
        ),
        (
            "Prediction input",
            "five_x_prediction_input_template_500.csv",
        ),
    ]
    for title, filename in template_specs:
        path = ROOT / "data" / "templates" / filename
        with st.container(border=True):
            st.markdown(f"### {title}")
            if path.is_file():
                frame = read_csv_cached(path)
                st.dataframe(
                    frame.head(10),
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    f"Download {filename}",
                    path.read_bytes(),
                    filename,
                    "text/csv",
                    key=f"five_x_{filename}",
                )
            else:
                st.error(f"Missing template: {filename}")

    batch_path = ROOT / "data" / "packs" / "batch_prediction_sample_5000.csv"
    if batch_path.is_file():
        st.download_button(
            "Download 5,000-row batch input",
            batch_path.read_bytes(),
            batch_path.name,
            "text/csv",
        )

with verification_tab:
    section_title("Training integrity", "✅")
    verification_rows = []
    for result in step19_results:
        split = result.get("split_summary", {})
        cache = result.get("feature_cache", {})
        verification_rows.append(
            {
                "filename": result.get("filename"),
                "task": result.get("task_type"),
                "training_pack": result.get("training_pack"),
                "source_rows": result.get("source_rows"),
                "train_rows": result.get("train_rows"),
                "validation_rows": result.get("validation_rows"),
                "test_rows": result.get("test_rows"),
                "split_strategy": split.get("strategy"),
                "group_overlap": split.get("group_overlap"),
                "unique_drugs": cache.get("unique_drugs"),
                "unique_targets": cache.get("unique_targets"),
                "matrix_dtype": cache.get("matrix_dtype"),
                "matrix_mb": (
                    round(
                        float(
                            cache.get(
                                "matrix_bytes",
                                0,
                            )
                        )
                        / (1024 * 1024),
                        2,
                    )
                ),
            }
        )
    st.dataframe(
        pd.DataFrame(verification_rows),
        width="stretch",
        hide_index=True,
    )
    smart_json(integrity)

    default = default_model_path(ROOT / "models", require_compatible=True)
    st.info(
        "Default prediction model: " + (default.name if default is not None else "Not selected")
    )
    st.warning(
        "5X data and pack-v5 models are deterministic synthetic "
        "software benchmarks. Strong held-out metrics do not establish "
        "biological or clinical validity."
    )

    columns = st.columns(3)
    for column, key, label in (
        (
            columns[0],
            "model_training",
            "Open Model Training",
        ),
        (
            columns[1],
            "ml_autolab",
            "Open ML AutoLab",
        ),
        (
            columns[2],
            "data_coverage",
            "Open Data Coverage",
        ),
    ):
        page = PAGE_BY_KEY[key]
        with column:
            try:
                st.page_link(
                    page.path,
                    label=label,
                    icon=page.icon,
                    width="stretch",
                )
            except (KeyError, RuntimeError):
                st.caption(f"Open {page.title} from the sidebar.")

    benchmark_path = ROOT / "reports" / "generated" / "step19_5x_ml_benchmark.json"
    if benchmark_path.is_file():
        st.download_button(
            "Download complete 5X benchmark JSON",
            benchmark_path.read_bytes(),
            benchmark_path.name,
            "application/json",
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
