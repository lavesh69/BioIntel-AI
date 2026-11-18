from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.intelligence_ui import render_education_intelligence_hub
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Education Intelligence Hub",
    page_icon=":material/psychology:",
    layout="wide",
)
apply_theme()
render_education_intelligence_hub(ROOT)
