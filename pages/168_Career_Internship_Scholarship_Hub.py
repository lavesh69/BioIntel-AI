"""Compatibility route for the canonical BioIntel Career Hub.

The earlier Education Universe workspace route is retained, while its record
management feature is now available inside the canonical Career workspace tab.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.career_hub_ui import render_career_hub_page
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="Career, Internship & Scholarship Hub · BioIntel AI",
    page_icon=":material/work:",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
render_career_hub_page()
