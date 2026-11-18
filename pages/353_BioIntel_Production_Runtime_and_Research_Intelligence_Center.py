from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase15_ui import render_phase15_runtime_and_research_center
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Production Runtime & Research Intelligence Center",
    page_icon=":material/hub:",
    layout="wide",
)
apply_theme()
render_phase15_runtime_and_research_center(ROOT)
