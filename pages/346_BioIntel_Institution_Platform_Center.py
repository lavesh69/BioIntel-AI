from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.institution_ui import render_education_institution_center
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Institution Platform Center", page_icon=":material/domain:", layout="wide"
)
apply_theme()
render_education_institution_center(ROOT)
