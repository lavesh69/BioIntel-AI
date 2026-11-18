from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v169 import final_consolidation_matrix
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Final Consolidation 10/10 · BioIntel AI", page_icon="F10", layout="wide")
apply_theme()
hero(
    "Final Consolidation 10/10 Center",
    "Unified Step 159–169 assurance, checksum-verified evidence registry, version consistency and controlled-release qualification for all 80 scientific modules.",
    eyebrow="BioIntel AI · Step 169 · v14.1.0",
    chips=["80/80 internal 10/10", "Registry-verified evidence", "Metadata cannot unlock release", "Fail closed"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message=(
        "Internal software, native scientific depth and release workflows are consolidated at 10/10. "
        "Controlled release is unlocked only by checksum-valid evidence artifacts, qualified operating history "
        "and a verified formal release decision. Demo flags or caller metadata cannot unlock release."
    ),
)
frame = final_consolidation_matrix(ROOT)
eligible = int(frame["controlled_release_eligible"].sum())
metric_cards([
    ("Modules", "80/80", "Consolidated"),
    ("Internal quality", "10/10", "Software-owned"),
    ("Version", "14.1.0", "Runtime aligned"),
    ("Controlled release", f"{eligible}/80", "Verified evidence only"),
])
section_title("Final all-module consolidation matrix", "Registry-derived release state")
smart_dataframe(frame, height=620, key="step169_final_matrix")
st.download_button(
    "Download final consolidation matrix",
    frame.to_csv(index=False).encode(),
    "biointel_step169_final_consolidation_matrix.csv",
    "text/csv",
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
