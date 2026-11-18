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

from biointel.data.data_packs import (
    data_library_summary,
    register_bundled_data_packs,
)
from biointel.training.model_artifact import (
    load_model_artifact_cached,
)
from biointel.training.model_catalog import (
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
def _cached_data_library_summary(root_text: str):
    return data_library_summary(root_text)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_model_library(root_text: str):
    root = Path(root_text)
    catalog = [entry for entry in sync_model_catalog(root / "models") if entry.state != "archived"]
    rows = []
    for entry in catalog:
        path = root / "models" / entry.filename
        try:
            artifact = load_model_artifact_cached(path, trusted_root=root / "models")
        except Exception as exc:
            rows.append(
                {
                    "filename": entry.filename,
                    "state": entry.state,
                    "default": entry.is_default,
                    "load_error": str(exc),
                }
            )
            continue
        metrics = artifact.metadata.metrics
        rows.append(
            {
                "filename": entry.filename,
                "state": entry.state,
                "default": entry.is_default,
                "task": artifact.metadata.task_type,
                "model": artifact.metadata.model_name,
                "dataset": artifact.metadata.dataset_name,
                "train_rows": artifact.metadata.train_rows,
                "test_rows": artifact.metadata.test_rows,
                "roc_auc": metrics.get("roc_auc"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "rmse": metrics.get("rmse"),
                "r2": metrics.get("r2"),
                "synthetic": artifact.metadata.synthetic_demo,
            }
        )
    return {"catalog_count": len(catalog), "rows": rows}


st.set_page_config(
    page_title="Data & Model Library · BioIntel AI",
    page_icon="🗃️",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("data_model_library", key_prefix="step116_33_Data_Model_Library_data_model_library_1", expanded=False)

hero(
    "Ready data, trained models and live-data recipes in one place.",
    (
        "Use bundled benchmark packs immediately, inspect pretrained model "
        "metrics, reseed the dataset registry and move to official ChEMBL "
        "data collection when internet access is available."
    ),
    eyebrow="Quality-Hardened · Data & Model Library",
    chips=[
        "160,000 5X pairs",
        "1,000 molecules",
        "160 targets",
        "23 pretrained models",
    ],
)

summary = _cached_data_library_summary(str(ROOT))
manifest = summary["manifest"]
benchmark = summary["benchmark"]
packs = manifest.get("packs", [])
model_library = _cached_model_library(str(ROOT))

badge(
    "● Bundled packs are ready" if packs else "● Generate data packs before use",
    "success" if packs else "warning",
)

total_rows = sum(int(pack.get("rows", 0)) for pack in packs)
largest_pack = max(
    (int(pack.get("rows", 0)) for pack in packs),
    default=0,
)
executive_kpis(
    [
        (
            "Rows across CSV files",
            f"{total_rows:,}",
            "Includes foundation subset and batch sample",
        ),
        (
            "Largest pack",
            f"{largest_pack:,}",
            "Rows available for local training",
        ),
        (
            "Trusted models",
            str(model_library["catalog_count"]),
            "Demo plus pack-v2, pack-v3, pack-v4 and pack-v5 artifacts",
        ),
        (
            "Best classifier",
            str(
                benchmark.get("best_models", {})
                .get("classification", {})
                .get("model_name", "Not trained")
            ),
            "Selected by held-out ROC-AUC",
        ),
    ]
)

data_tab, models_tab, recipes_tab, actions_tab = st.tabs(
    [
        "Data packs",
        "Model leaderboard",
        "ChEMBL recipes",
        "Quick actions",
    ]
)

with data_tab:
    professional_strip(
        "Bundled data packs",
        (
            "All bundled packs are deterministic synthetic benchmarks. "
            "They fill the modules and test the software, but they are not "
            "experimental biological evidence."
        ),
    )

    if not packs:
        st.warning("Data pack manifest is missing. Run BUILD_DATA_AND_MODELS_WINDOWS.bat.")
    else:
        st.dataframe(
            pd.DataFrame(packs),
            width="stretch",
            hide_index=True,
        )
        for pack in packs:
            path = ROOT / str(pack["filename"])
            with st.container(border=True):
                columns = st.columns([2.5, 1, 1, 1.2])
                columns[0].markdown(f"### {pack['title']}")
                columns[1].metric(
                    "Rows",
                    f"{int(pack['rows']):,}",
                )
                columns[2].metric(
                    "Compounds",
                    int(pack["compounds"]),
                )
                columns[3].metric(
                    "Targets",
                    int(pack["targets"]),
                )
                st.caption(str(pack["description"]))
                st.code(
                    str(pack["sha256"]),
                    language=None,
                )
                if path.is_file():
                    size_mb = path.stat().st_size / (1024 * 1024)
                    st.caption(f"File size: {size_mb:.2f} MB")
                    if st.toggle(
                        f"Prepare download — {pack['title']}",
                        key=f"prepare_download_{pack['key']}",
                    ):
                        st.download_button(
                            f"Download {pack['title']}",
                            path.read_bytes(),
                            path.name,
                            "text/csv",
                            key=f"download_{pack['key']}",
                        )

    library_info = manifest.get("libraries", {})
    if library_info:
        section_title("Reference libraries", "◈")
        smart_json(library_info)

    if st.button(
        "Register or refresh bundled datasets",
        type="primary",
    ):
        try:
            records = register_bundled_data_packs(ROOT)
            _cached_data_library_summary.clear()
        except Exception as exc:
            st.error(f"Registry update failed: {exc}")
        else:
            st.success(f"Registered {len(records)} task-specific dataset views.")
            st.dataframe(
                pd.DataFrame(records),
                width="stretch",
                hide_index=True,
            )

with models_tab:
    ranking = benchmark.get("ranking", [])
    if not ranking:
        st.warning("Model benchmark summary is missing. Run the Windows builder.")
    else:
        ranking_frame = pd.DataFrame(ranking)
        st.dataframe(
            ranking_frame,
            width="stretch",
            hide_index=True,
        )

    section_title("Trusted model artifacts", "🧠")
    model_rows = model_library["rows"]
    st.dataframe(
        pd.DataFrame(model_rows),
        width="stretch",
        hide_index=True,
    )
    st.warning(
        "Pack-v2 models are trained on deterministic synthetic data. "
        "Their strong software-benchmark metrics must not be interpreted "
        "as biological or clinical performance."
    )

with recipes_tab:
    recipe_path = ROOT / "data" / "recipes" / "chembl_starter_targets.csv"
    if recipe_path.is_file():
        recipes = read_csv_cached(recipe_path)
        st.dataframe(
            recipes,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download ChEMBL starter recipes",
            recipes.to_csv(index=False),
            "chembl_starter_targets.csv",
            "text/csv",
        )
    else:
        st.info("ChEMBL recipe file is missing.")

    st.info(
        "These are only starter target identifiers. The ChEMBL Builder "
        "downloads live official activity records and still requires assay, "
        "relation, unit and provenance review before research training."
    )
    page = PAGE_BY_KEY["chembl_builder"]
    try:
        st.page_link(
            page.path,
            label="Open ChEMBL Dataset Builder",
            icon=page.icon,
        )
    except (KeyError, RuntimeError):
        st.caption("Open ChEMBL Dataset Builder from the sidebar.")

with actions_tab:
    action_columns = st.columns(4)
    actions = [
        (
            "model_training",
            "Train a model",
            "Use foundation or extended bundled packs.",
        ),
        (
            "dti_predictor",
            "Run prediction",
            "Use the pretrained pack-v2 classifier.",
        ),
        (
            "batch_jobs",
            "Run batch sample",
            "Process the included 250-row input file.",
        ),
        (
            "dataset_registry",
            "Inspect lineage",
            "Review registered pack hashes and parents.",
        ),
    ]
    for column, (key, title, copy) in zip(
        action_columns,
        actions,
        strict=True,
    ):
        page = PAGE_BY_KEY[key]
        with column:
            st.markdown(f"### {page.icon} {title}")
            st.write(copy)
            try:
                st.page_link(
                    page.path,
                    label=f"Open {page.title}",
                    icon=page.icon,
                    width="stretch",
                )
            except (KeyError, RuntimeError):
                st.caption(f"Open {page.title} from the sidebar.")

    benchmark_path = ROOT / "reports" / "generated" / "data_pack_model_benchmark.json"
    if benchmark_path.is_file():
        st.download_button(
            "Download complete benchmark report",
            benchmark_path.read_bytes(),
            benchmark_path.name,
            "application/json",
        )
    st.download_button(
        "Download data library manifest",
        json.dumps(
            manifest,
            indent=2,
            default=str,
        ),
        "biointel_data_library_manifest.json",
        "application/json",
    )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='data_library', title='Data & Model Library', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
