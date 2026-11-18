from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.phase7_ui import render_education_phase7_desktop
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Education Desktop", page_icon=":material/desktop_windows:", layout="wide"
)
apply_theme()
render_education_phase7_desktop(ROOT)
