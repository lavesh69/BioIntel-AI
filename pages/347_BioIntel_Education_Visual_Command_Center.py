from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.visual_command_ui import render_education_visual_command_center
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Education Visual Command Center",
    page_icon=":material/space_dashboard:",
    layout="wide",
)
apply_theme()
render_education_visual_command_center(ROOT)
