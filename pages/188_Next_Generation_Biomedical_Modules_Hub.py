from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.catalog import NEXTGEN_MODULES
from biointel.ui.components import smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Next-Generation Biomedical Modules Hub · BioIntel AI", page_icon="✨", layout="wide")
apply_theme()

hero(
    "Next-Generation Biomedical Modules Hub",
    "Fifteen new biomedical workspaces spanning pathology, long-read epigenomics, foundation models, AMR, cell and gene therapy, federated AI, clinical biomarkers and experimental planning.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["15 new modules", "Scientific intelligence", "75 specialist visuals", "Transparent evidence boundaries"],
)

modules = [module for module in NEXTGEN_MODULES if 173 <= module.page_number <= 187]
section_title("Launch a new workspace", "✨")
query = st.text_input("Search the Step 128 modules", placeholder="pathology, AMR, CAR-T, foundation model, survival…")
filtered = [
    module for module in modules
    if not query.strip() or query.lower() in (module.title + " " + module.summary + " " + " ".join(module.keywords)).lower()
]

for start in range(0, len(filtered), 3):
    columns = st.columns(3, gap="large")
    for column, module in zip(columns, filtered[start:start + 3]):
        with column:
            with st.container(border=True):
                st.markdown(f"### {module.icon} {module.title}")
                st.caption(module.category)
                st.write(module.summary)
                st.caption("Inputs: " + ", ".join(module.accepted_inputs[:2]))
                st.page_link(f"pages/{module.page_number}_{next(p.name.split('_', 1)[1] for p in (ROOT / 'pages').glob(f'{module.page_number}_*.py'))}", label="Open workspace")

section_title("Capability matrix", "▦")
smart_dataframe(
    pd.DataFrame([
        {
            "Module": module.title,
            "Category": module.category,
            "Required fields": len(module.required_columns),
            "Workflow stages": len(module.workflow),
            "Boundary": module.boundary,
        }
        for module in modules
    ]),
    height=520,
    key="step128_hub_matrix",
)

st.markdown("### Step 132 scientific intelligence workspaces")
links = [
    ("Scientific Intelligence Hub", "pages/194_Scientific_Intelligence_Hub.py"),
    ("Multi-Scale Visual Intelligence Studio", "pages/196_Multi_Scale_Scientific_Visual_Intelligence_Studio.py"),
    ("Cross-Module Evidence Board", "pages/190_Cross_Module_Evidence_Board.py"),
    ("Scenario & Sensitivity Lab", "pages/191_Scientific_Scenario_Sensitivity_Lab.py"),
    ("Validation Cohort Manager", "pages/192_Validation_Cohort_Manager.py"),
    ("Visual Review & Approval Center", "pages/193_Visual_Review_Approval_Center.py"),
]
columns = st.columns(len(links))
for column, (label, path) in zip(columns, links):
    with column:
        st.page_link(path, label=label)

st.info("External proprietary weights, licensed reference databases and clinical or wet-lab evidence are not presented as bundled. Each module exposes its scientific boundary and readiness requirements.")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='next_generation_biomedical_hub', title='Next-Generation Biomedical Modules Hub', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
