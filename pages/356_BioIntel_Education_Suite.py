"""Canonical BioIntel Education Suite page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.ui import render_classroom
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="BioIntel Education Suite", page_icon=":material/auto_stories:", layout="wide")
apply_theme()
st.session_state["classroom-workspace-section"] = "Education suite"
render_classroom(ROOT)
