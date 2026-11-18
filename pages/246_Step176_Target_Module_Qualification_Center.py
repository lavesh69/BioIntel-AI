from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.target_modules_v176 import TARGET_MODULES, TARGET_PROFILES, qualification_matrix
from biointel.target_modules_v176.ui import render_target_module_upgrade
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="17-Module Qualification Center · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()
st.title("17-Module Operational Qualification Center")
st.caption("Step 176 · Internal software completion separated from runtime, reference and external scientific evidence.")

matrix = qualification_matrix(ROOT)
cols = st.columns(4)
cols[0].metric("Target modules", len(matrix))
cols[1].metric("Internal 10/10", int(matrix["internal_upgrade_rating"].eq(10.0).sum()))
cols[2].metric("Full runtime discovery", int(matrix["engine_discovery_fraction"].eq(1.0).sum()))
cols[3].metric("Controlled release", int(matrix["controlled_release_eligible"].sum()))

st.dataframe(
    matrix[[
        "module_title", "internal_upgrade_rating", "engine_discovery_fraction",
        "reference_qualification_fraction", "controlled_release_eligible", "decision"
    ]],
    width="stretch",
    hide_index=True,
)

selected = st.selectbox("Open module qualification workspace", TARGET_MODULES, format_func=lambda key: TARGET_PROFILES[key].title)
render_target_module_upgrade(selected, expanded=True)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
