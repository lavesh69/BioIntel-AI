from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase23_30.ui import render_phase23_30_platform
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="BioIntel Education & Research Enterprise",
    page_icon=":material/domain:",
    layout="wide",
)
apply_theme()
render_phase23_30_platform(ROOT)
