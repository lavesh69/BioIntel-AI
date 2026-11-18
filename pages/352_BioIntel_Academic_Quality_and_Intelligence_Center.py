from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.phase14_ui import render_phase14_academic_intelligence_center
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Academic Quality & Intelligence Center",
    page_icon=":material/analytics:",
    layout="wide",
)
apply_theme()
render_phase14_academic_intelligence_center(ROOT)
