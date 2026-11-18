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
from biointel.utils.runtime_cache import read_csv_cached


@st.cache_data(ttl=300, show_spinner=False)
def _cached_autolab_snapshot(root_text: str):
    root = Path(root_text)
    models = root / "models"
    catalog = sync_model_catalog(models)
    artifact_rows = []
    for entry in catalog:
        path = models / entry.filename
        try:
            artifact = load_model_artifact_cached(path, trusted_root=models)
        except Exception as exc:
            artifact_rows.append(
                {
                    "filename": entry.filename,
                    "state": entry.state,
                    "load_error": str(exc),
                }
            )
            continue
        artifact_rows.append(
            {
                "filename": entry.filename,
                "default": entry.is_default,
                "state": entry.state,
                "task": artifact.metadata.task_type,
                "algorithm": artifact.metadata.model_name,
                "dataset": artifact.metadata.dataset_name,
                "train_rows": artifact.metadata.train_rows,
                "validation_rows": artifact.metadata.validation_rows,
                "test_rows": artifact.metadata.test_rows,
                "artifact_version": artifact.metadata.artifact_version,
            }
        )
    default = default_model_path(models, require_compatible=True)
    return {
        "summary": data_library_summary(root),
        "integrity": verify_data_pack_integrity(root),
        "catalog_count": len(catalog),
        "artifact_rows": artifact_rows,
        "default_model": default.name if default else "",
    }


from biointel.step121.panels import render_automl_upgrade

st.set_page_config(
    page_title="ML AutoLab · BioIntel AI",
    page_icon="🧠",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("ml_autolab", key_prefix="step116_34_ML_AutoLab_ml_autolab_1", expanded=False)
snapshot = _cached_autolab_snapshot(str(ROOT))
summary = snapshot["summary"]
integrity = snapshot["integrity"]
benchmark = summary["benchmark"]
ranking = pd.DataFrame(benchmark.get("ranking", []))
catalog_count = int(snapshot["catalog_count"])

hero(
    "Dataset-wise machine-learning benchmarking and ready inputs.",
    (
        "Compare classification and regression algorithms, identify the "
        "champion artifact, download input templates and launch training "
        "with Foundation, Extended, Ultra, Double Ultra or 5X data."
    ),
    eyebrow="Quality-Hardened · ML AutoLab",
    chips=[
        "160,000-pair 5X pack",
        "Full-data tree + linear ML",
        "Champion selection",
        "Ready templates",
    ],
)

badge(
    (
        "● ML data and models verified"
        if integrity["valid"]
        else "● Data integrity requires attention"
    ),
    "success" if integrity["valid"] else "danger",
)

best_models = benchmark.get("best_models", {})
professional_strip(
    "Automated benchmark",
    (
        f"{len(ranking)} ranked model(s) · "
        f"{catalog_count} trusted artifact(s) · "
        f"{integrity['checked_files']} verified input file(s)"
    ),
)

executive_kpis(
    [
        (
            "5X Ultra pairs",
            "160,000",
            "1,000 molecules × 160 protein targets",
        ),
        (
            "Best classifier",
            str(
                best_models.get("classification", {}).get(
                    "model_name",
                    "Not available",
                )
            ),
            "Selected by held-out ROC-AUC",
        ),
        (
            "Best regressor",
            str(
                best_models.get("regression", {}).get(
                    "model_name",
                    "Not available",
                )
            ),
            "Selected by lowest held-out RMSE",
        ),
        (
            "Model artifacts",
            str(catalog_count),
            "Demo plus pack-v2 through pack-v5 models",
        ),
    ]
)

ml_autolab_view = st.radio(
    "ML AutoLab view",
    ["ML leaderboard", "Input templates", "Dataset-wise plan", "Artifact details"],
    horizontal=True,
    key="ml_autolab_view",
    label_visibility="collapsed",
)

if ml_autolab_view == "ML leaderboard":
    section_title("Classification and regression ranking", "🏆")
    if ranking.empty:
        st.warning("Benchmark summary is missing. Run BUILD_DATA_AND_MODELS_WINDOWS.bat.")
    else:
        task = st.radio(
            "Task",
            ["classification", "regression"],
            horizontal=True,
        )
        filtered = ranking[ranking["task_type"] == task].copy()
        st.dataframe(
            filtered,
            width="stretch",
            hide_index=True,
        )
        if task == "classification" and "test_roc_auc" in filtered:
            chart = filtered[["model_name", "test_roc_auc"]].dropna()
            st.bar_chart(chart.set_index("model_name"))
        elif task == "regression" and "test_rmse" in filtered:
            chart = filtered[["model_name", "test_rmse"]].dropna()
            st.bar_chart(chart.set_index("model_name"))

        st.download_button(
            "Download complete leaderboard CSV",
            ranking.to_csv(index=False),
            "step19_ml_leaderboard.csv",
            "text/csv",
        )

if ml_autolab_view == "Input templates":
    section_title("Ready data-input templates", "📥")
    template_directory = ROOT / "data" / "templates"
    templates = [
        (
            "Classification training input",
            template_directory / "classification_training_template.csv",
            "canonical_smiles, protein_sequence and label",
        ),
        (
            "Regression training input",
            template_directory / "regression_training_template.csv",
            "canonical_smiles, protein_sequence and p_activity",
        ),
        (
            "Prediction input",
            template_directory / "prediction_input_template.csv",
            "canonical_smiles and protein_sequence",
        ),
        (
            "Double-data classification input",
            template_directory / "double_classification_training_template_250.csv",
            "250 ready rows with label",
        ),
        (
            "Double-data regression input",
            template_directory / "double_regression_training_template_250.csv",
            "250 ready rows with p_activity",
        ),
        (
            "Double-data prediction input",
            template_directory / "double_prediction_input_template_250.csv",
            "250 ready prediction rows",
        ),
        (
            "5X classification input",
            template_directory / "five_x_classification_training_template_500.csv",
            "500 ready rows with label",
        ),
        (
            "5X regression input",
            template_directory / "five_x_regression_training_template_500.csv",
            "500 ready rows with p_activity",
        ),
        (
            "5X prediction input",
            template_directory / "five_x_prediction_input_template_500.csv",
            "500 ready prediction rows",
        ),
    ]
    for title, path, description in templates:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.caption(description)
            if path.is_file():
                frame = read_csv_cached(path)
                st.dataframe(
                    frame.head(10),
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    f"Download {path.name}",
                    path.read_bytes(),
                    path.name,
                    "text/csv",
                    key=f"template_{path.stem}",
                )
            else:
                st.error(f"Missing template: {path.name}")

if ml_autolab_view == "Dataset-wise plan":
    section_title("Dataset-wise ML recommendation", "🧭")
    plans = pd.DataFrame(
        [
            {
                "Dataset": "Quick demo",
                "Rows": "96",
                "Recommended use": "UI check and learning",
                "Models": "Logistic / Ridge",
                "Split": "random_pair",
            },
            {
                "Dataset": "Foundation",
                "Rows": "1,920",
                "Recommended use": "Fast experiments",
                "Models": "RF, Extra Trees, Ridge, SGD",
                "Split": "drug_group / target_group",
            },
            {
                "Dataset": "Extended",
                "Rows": "5,760",
                "Recommended use": "Main local benchmark",
                "Models": "RF, Logistic, Extra Trees, Elastic Net",
                "Split": "drug_group / target_group",
            },
            {
                "Dataset": "Ultra",
                "Rows": "16,000",
                "Recommended use": "High-data classification and stress testing",
                "Models": "Extra Trees, SGD Logistic",
                "Split": "drug_group",
            },
            {
                "Dataset": "Double Ultra",
                "Rows": "32,000",
                "Recommended use": "Maximum bundled stress testing and diversity",
                "Models": "RF, Extra Trees, SGD, Ridge",
                "Split": "drug_group / target_group",
            },
            {
                "Dataset": "5X Ultra",
                "Rows": "160,000",
                "Recommended use": "Full-data benchmark and scalability validation",
                "Models": "Extra Trees, RF, SGD, Ridge",
                "Split": "drug_group / target_group",
            },
            {
                "Dataset": "Curated ChEMBL",
                "Rows": "Variable",
                "Recommended use": "Real research training",
                "Models": "Compare multiple models",
                "Split": "scaffold + target group",
            },
        ]
    )
    st.dataframe(
        plans,
        width="stretch",
        hide_index=True,
    )

    st.warning(
        "The Ultra, Double Ultra and 5X packs are synthetic. Use them to test ML pipelines and "
        "computational behaviour, not to claim biological performance."
    )

    launch_columns = st.columns(3)
    for column, key, label in (
        (
            launch_columns[0],
            "model_training",
            "Open Model Training",
        ),
        (
            launch_columns[1],
            "data_library",
            "Open Data Library",
        ),
        (
            launch_columns[2],
            "chembl_builder",
            "Build Real ChEMBL Data",
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

if ml_autolab_view == "Artifact details":
    section_title("Trusted model artifacts", "🧠")
    rows = snapshot["artifact_rows"]
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
    )

    default_name = str(snapshot.get("default_model", ""))
    st.info("Default prediction artifact: " + (default_name or "Not selected"))

    benchmark_path = ROOT / "reports" / "generated" / "step19_5x_ml_benchmark.json"
    if benchmark_path.is_file():
        st.download_button(
            "Download Quality-Hardened benchmark JSON",
            benchmark_path.read_bytes(),
            benchmark_path.name,
            "application/json",
        )

    smart_json(
        {
            "best_models": best_models,
            "data_integrity": integrity,
        }
    )
render_automl_upgrade(key_prefix="step121_automl")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
