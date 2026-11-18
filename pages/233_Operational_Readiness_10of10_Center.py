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

from biointel.operational_v164 import operational_matrix, provisioning_catalog, runtime_inventory  # noqa: E402
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="Operational Readiness 10/10 · BioIntel AI", page_icon="OR", layout="wide")
apply_theme()
hero(
    "Operational Readiness 10/10 Center",
    "Provision, detect and qualify specialist runtimes, production references, task-specific model packages and external evidence without converting missing third-party artifacts into fake green checks.",
    eyebrow="BioIntel AI · Step 164 Operational Qualification",
    chips=["80 dynamic release gates", "53 executable recipes", "Reference intake validation", "Model package validation", "Fail closed"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Step 164 fixes every software-owned operational gap. A module becomes real-world release eligible only after actual tools, reference releases, task-specific models, independent/prospective evidence and expert sign-off are attached and verified.",
)


@st.cache_data(ttl=120, show_spinner=False)
def _matrix() -> pd.DataFrame:
    return operational_matrix(ROOT, detect_runtime=False)


@st.cache_data(ttl=120, show_spinner=False)
def _catalog() -> pd.DataFrame:
    return provisioning_catalog()


matrix = _matrix()
catalog = _catalog()
metric_cards(
    [
        ("Software-owned operational score", f"{int((matrix['software_owned_score'] == 10.0).sum())}/{len(matrix)}", "10/10 controls"),
        ("Executable engine recipes", f"{int(catalog['software_recipe_complete'].astype(bool).sum())}/{len(catalog)}", "Conda/Python/manual routes"),
        ("Production references qualified", int(matrix["production_references_qualified"].sum()), "Real assets only"),
        ("Real-world release eligible", int(matrix["real_world_release_eligible"].astype(bool).sum()), "All gates required"),
    ]
)

section_title("Live operational qualification matrix", "OR")
view = st.selectbox(
    "View",
    ["All modules", "Highest runtime burden", "Model-required modules", "Release blockers"],
    key="step164_matrix_view",
)
visible = matrix.copy()
if view == "Highest runtime burden":
    visible = visible.sort_values(["specialist_engines_required", "production_references_required"], ascending=[False, False])
elif view == "Model-required modules":
    visible = visible.loc[visible["task_specific_model_required"].astype(bool)]
elif view == "Release blockers":
    visible = visible.loc[~visible["real_world_release_eligible"].astype(bool)]
smart_dataframe(visible, height=620, key="step164_matrix")
st.download_button(
    "Download operational readiness matrix",
    matrix.to_csv(index=False).encode("utf-8"),
    "biointel_step164_operational_readiness_matrix.csv",
    "text/csv",
    width="stretch",
)

section_title("Specialist runtime provisioning", "RT")
smart_dataframe(catalog, height=520, key="step164_catalog")
st.caption("Automatic package-manager routes are generated only where an identifiable package exists. Provider-licensed tools and model weights stay manual and require licence acceptance, checksums and smoke-test evidence.")

if st.button("Probe this computer for specialist tools", width="stretch"):
    with st.spinner("Checking executable paths and versions…"):
        inventory = runtime_inventory()
    smart_dataframe(inventory, height=520, key="step164_inventory")
    st.download_button(
        "Download runtime inventory",
        inventory.to_csv(index=False).encode("utf-8"),
        "biointel_step164_runtime_inventory.csv",
        "text/csv",
        width="stretch",
    )

section_title("Qualification workflow", "QF")
smart_json(
    {
        "1_provision_runtime": "Run the Step 164 runtime manager in dry-run mode, review licences, then explicitly execute the selected backend.",
        "2_attach_references": "Copy a template from data/step164/reference_intake_templates into UserData/step164/references/<module>/ and attach the real asset with release ID, licence, checksum, record count and reviewer.",
        "3_attach_task_model": "Use the task-model intake template and provide model/data hashes, model card, split manifest, untouched holdout outputs, uncertainty diagnostics and environment manifest.",
        "4_attach_external_evidence": "Provide independent data/site results, prospective or orthogonal validation and signed domain-expert review.",
        "5_release_gate": "BioIntel recalculates the module decision. Missing, mismatched or incomplete evidence keeps the module research-only.",
    },
    title="Step 164 controlled qualification",
    key="step164_workflow",
)

summary = {
    "schema": "biointel.step164.ui-summary.v1",
    "modules": len(matrix),
    "software_owned_10of10": int((matrix["software_owned_score"] == 10.0).sum()),
    "engine_recipes_complete": int(catalog["software_recipe_complete"].astype(bool).sum()),
    "production_references_qualified": int(matrix["production_references_qualified"].sum()),
    "real_world_release_eligible": int(matrix["real_world_release_eligible"].astype(bool).sum()),
    "external_evidence_not_inferred": True,
}
st.download_button(
    "Download summary JSON",
    json.dumps(summary, indent=2).encode("utf-8"),
    "biointel_step164_summary.json",
    "application/json",
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
