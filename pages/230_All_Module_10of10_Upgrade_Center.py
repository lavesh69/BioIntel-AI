from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.readiness_v161 import (  # noqa: E402
    portfolio_upgrade_matrix,
    portfolio_upgrade_summary,
    runtime_detection_matrix,
    runtime_recipe_catalog,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="All-Module 10/10 Upgrade · BioIntel AI", page_icon="U10", layout="wide")
apply_theme()
hero(
    "All-Module 10/10 Upgrade Center",
    "Verify complete software-owned upgrades for all 80 scientific modules: native execution, managed specialist paths, checksum-verified development references and external-validation protocols.",
    eyebrow="BioIntel AI · Step 161 Operational Scientific Upgrade",
    chips=["80/80 upgrade contracts", "53 runtime recipes", "Development reference kits", "Validation protocols", "No false external claims"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Step 161 10/10 means the software-side upgrade path is complete. Installed specialist binaries, production-size licensed references and genuine independent/wet-lab/clinical evidence are detected and scored separately.",
)


@st.cache_data(ttl=120, show_spinner=False)
def _matrix():
    return portfolio_upgrade_matrix(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def _runtime():
    return runtime_detection_matrix()


matrix = _matrix()
summary = portfolio_upgrade_summary(matrix)
metric_cards(
    [
        ("Scientific modules", summary["modules"], "Registered profiles"),
        ("Step 161 10/10", f"{summary['step161_10_of_10']}/{summary['modules']}", "Software upgrade complete"),
        ("Execution paths", f"{summary['execution_paths_10_of_10']}/{summary['modules']}", "Native + managed specialist paths"),
        ("Real-world release eligible", summary["real_world_release_eligible"], "Installed tools + production refs + external evidence"),
    ]
)

section_title("Module upgrade matrix", "🧬")
view = st.selectbox(
    "View",
    [
        "All modules",
        "Software upgrade below 10/10",
        "Specialist tools not installed",
        "Production references incomplete",
        "External validation incomplete",
        "Real-world release eligible",
    ],
    key="step161_upgrade_filter",
)
visible = matrix.copy()
if view == "Software upgrade below 10/10":
    visible = visible.loc[visible.step161_upgrade_score < 10.0]
elif view == "Specialist tools not installed":
    visible = visible.loc[visible.specialist_engines_installed < visible.specialist_engines_required]
elif view == "Production references incomplete":
    visible = visible.loc[visible.production_references_qualified < visible.production_references_required]
elif view == "External validation incomplete":
    visible = visible.loc[visible.external_evidence_score < 100.0]
elif view == "Real-world release eligible":
    visible = visible.loc[visible.real_world_release_eligible.astype(bool)]

columns = [
    "module_key",
    "title",
    "native_family",
    "internal_quality_score",
    "execution_path_score",
    "development_reference_score",
    "validation_protocol_score",
    "step161_upgrade_score",
    "specialist_engines_installed",
    "specialist_engines_required",
    "production_references_qualified",
    "production_references_required",
    "external_evidence_score",
    "real_world_release_eligible",
    "remaining_external_blockers",
]
smart_dataframe(visible[columns], height=620, key="step161_module_upgrade_matrix")
st.download_button(
    "Download complete Step 161 module upgrade matrix",
    data=matrix.to_csv(index=False).encode("utf-8"),
    file_name="biointel_step161_module_upgrade_matrix.csv",
    mime="text/csv",
    width="stretch",
)

section_title("Specialist runtime provisioning", "🛠️")
runtime = _runtime()
recipe = runtime_recipe_catalog()
left, right = st.columns(2)
with left:
    metric_cards(
        [
            ("Managed recipes", f"{int(recipe.recipe_complete.astype(bool).sum())}/{len(recipe)}", "All declared external engines"),
            ("Installed now", f"{int(runtime.installed.astype(bool).sum())}/{len(runtime)}", "This computer only"),
        ]
    )
with right:
    st.caption("A complete provisioning recipe is not the same as an installed, licensed and validated runtime. Step 161 preserves that distinction.")
smart_dataframe(
    runtime[
        [
            "engine",
            "label",
            "category",
            "installed",
            "detected_version",
            "install_strategy",
            "execution_backends",
            "manual_action_required",
            "model_or_database_required",
            "recipe_complete",
        ]
    ],
    height=500,
    key="step161_runtime_matrix",
)

with st.expander("How Step 161 reaches 10/10", expanded=False):
    st.markdown(
        "Each module must retain the Step 160 ten-point internal quality score, have a protected native or managed execution path, include checksum-verified development references for regression testing, and carry a versioned independent/prospective validation protocol. "
        "Production release still requires the actual specialist runtime, production-qualified references and genuine external evidence."
    )
    smart_json(summary, title="Step 161 upgrade summary", download_name="biointel_step161_upgrade_summary.json", key="step161_summary")
    st.download_button(
        "Download JSON summary",
        data=json.dumps(summary, indent=2).encode("utf-8"),
        file_name="biointel_step161_upgrade_summary.json",
        mime="application/json",
        width="stretch",
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
