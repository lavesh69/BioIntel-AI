from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.services.engine_license_service import render_engine_license_manager
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="Legal & Component Notices · BioIntel AI",
    page_icon=":material/license:",
    layout="wide",
)
apply_theme()
render_engine_license_manager()