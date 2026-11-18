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

from biointel.data.data_packs import verify_data_pack_integrity
from biointel.training.model_artifact import load_model_artifact_cached
from biointel.training.model_catalog import sync_model_catalog
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
)
from biointel.utils.runtime_cache import load_json_cached, read_csv_cached

st.set_page_config(
    page_title="Double Data ML · BioIntel AI",
    page_icon="⚡",
    layout="wide",
)
apply_theme()

PACK = ROOT / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv"
BATCH = ROOT / "data" / "packs" / "batch_prediction_sample_2000.csv"
BENCHMARK = ROOT / "data" / "packs" / "model_benchmark_summary.json"

hero(
    "Exact double-data training on 32,000 drug–target pairs.",
    (
        "Review 640 molecules, 50 protein targets, six pack-v4 ML models, "
        "held-out metrics, feature-cache savings and ready input templates."
    ),
    eyebrow="Quality-Hardened · Double Data ML",
    chips=[
        "32,000 pairs",
        "640 molecules",
        "50 targets",
        "6 new models",
    ],
)

integrity = verify_data_pack_integrity(ROOT)
benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
ranking = pd.DataFrame(benchmark.get("ranking", []))
double_ranking = ranking[
    ranking.get("training_pack", pd.Series(dtype=str)) == "double_ultra"
].copy()

badge(
    "● Double-data files verified" if integrity["valid"] else "● Data integrity failed",
    "success" if integrity["valid"] else "danger",
)
professional_strip(
    "Double Ultra v4",
    (
        "640 × 50 exact Cartesian pairs · drug-group classification split · "
        "target-group regression split"
    ),
)

executive_kpis(
    [
        ("Training pairs", "32,000", "Exactly 2× the 16,000-row Ultra pack"),
        ("Molecule library", "640", "31,360 molecule cache hits per model"),
        ("Protein library", "50", "31,950 protein cache hits per model"),
        ("Pack-v4 models", "6", "Three classification + three regression"),
    ]
)

data_tab, leaderboard_tab, templates_tab, comparison_tab = st.tabs(
    ["Data profile", "Double-data leaderboard", "Ready inputs", "Honest comparison"]
)

with data_tab:
    section_title("Double Ultra dataset", "⚡")
    if not PACK.is_file():
        st.error("Double-data CSV is missing. Run BUILD_DATA_AND_MODELS_WINDOWS.bat.")
    else:
        profile = load_json_cached(
            ROOT / "data" / "packs" / "double_data_profile.json",
            default={},
        )
        preview = read_csv_cached(PACK, nrows=100)
        columns = st.columns(5)
        columns[0].metric("Rows", f"{int(profile.get('rows', 0)):,}")
        columns[1].metric("Compounds", int(profile.get("molecules", 0)))
        columns[2].metric("Targets", int(profile.get("targets", 0)))
        columns[3].metric(
            "Positive label",
            f"{float(profile.get('positive_fraction', 0.0)):.1%}",
        )
        columns[4].metric(
            "Families",
            len(profile.get("target_family_counts", {})),
        )
        st.dataframe(preview, width="stretch", hide_index=True)
        if st.toggle(
            "Prepare complete 17 MB dataset download",
            key="prepare_double_download",
        ):
            st.download_button(
                "Download 32,000-row Double Ultra CSV",
                PACK.read_bytes(),
                PACK.name,
                "text/csv",
                type="primary",
            )

with leaderboard_tab:
    section_title("Pack-v4 held-out metrics", "🏆")
    if double_ranking.empty:
        st.warning("Double-data benchmark is missing.")
    else:
        task = st.radio(
            "Task",
            ["classification", "regression"],
            horizontal=True,
            key="double_task",
        )
        filtered = double_ranking[double_ranking["task_type"] == task]
        st.dataframe(filtered, width="stretch", hide_index=True)
        if task == "classification":
            st.bar_chart(filtered.set_index("model_name")[["test_roc_auc"]])
        else:
            st.bar_chart(filtered.set_index("model_name")[["test_rmse"]])

    catalog = sync_model_catalog(ROOT / "models")
    packv4 = [item for item in catalog if item.filename.startswith("packv4_double_")]
    artifact_rows = []
    for item in packv4:
        artifact = load_model_artifact_cached(
            ROOT / "models" / item.filename,
            trusted_root=ROOT / "models",
        )
        artifact_rows.append(
            {
                "filename": item.filename,
                "task": artifact.metadata.task_type,
                "algorithm": artifact.metadata.model_name,
                "train_rows": artifact.metadata.train_rows,
                "validation_rows": artifact.metadata.validation_rows,
                "test_rows": artifact.metadata.test_rows,
                "state": item.state,
                "default": item.is_default,
            }
        )
    st.dataframe(pd.DataFrame(artifact_rows), width="stretch", hide_index=True)

with templates_tab:
    section_title("Double-data input files", "📥")
    files = [
        ROOT / "data" / "templates" / "double_classification_training_template_250.csv",
        ROOT / "data" / "templates" / "double_regression_training_template_250.csv",
        ROOT / "data" / "templates" / "double_prediction_input_template_250.csv",
        BATCH,
    ]
    for path in files:
        with st.container(border=True):
            st.markdown(f"### {path.name}")
            if path.is_file():
                preview = read_csv_cached(path, nrows=8)
                st.dataframe(preview, width="stretch", hide_index=True)
                st.download_button(
                    f"Download {path.name}",
                    path.read_bytes(),
                    path.name,
                    "text/csv",
                    key=f"download_{path.stem}",
                )
            else:
                st.error("File missing")

with comparison_tab:
    section_title("What double data changed", "◎")
    st.info(
        "More rows improved stress coverage and entity diversity, but did not "
        "automatically beat the 16,000-row champion. The 32,000-row pack uses "
        "new molecules and targets, making grouped generalisation harder."
    )
    st.markdown(
        """
- Double-data classification leader: **Random Forest**, ROC-AUC about **0.881**
- Overall classification leader: **Extra Trees on Ultra**, ROC-AUC about **0.903**
- Double-data regression leader: **Extra Trees**, RMSE about **0.436**
- Overall regression leader: **Extra Trees on Foundation**, RMSE about **0.308**

This is expected: more synthetic diversity can make the held-out grouped split harder.
"""
    )
    links = st.columns(3)
    for column, key, label in (
        (links[0], "model_training", "Train with Double Data"),
        (links[1], "ml_autolab", "Open ML AutoLab"),
        (links[2], "chembl_builder", "Build Real ChEMBL Data"),
    ):
        page = PAGE_BY_KEY[key]
        with column:
            try:
                st.page_link(page.path, label=label, width="stretch")
            except (KeyError, RuntimeError):
                st.caption(f"Open {page.title} from the sidebar.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
