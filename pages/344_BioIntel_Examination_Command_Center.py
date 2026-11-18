from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.education.ui import render_examinations
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Examination Command Center",
    page_icon=":material/assignment_turned_in:",
    layout="wide",
)
apply_theme()
render_examinations(ROOT)
