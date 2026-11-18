from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.ui import render_pulse
from biointel.ui.brand import branded_page_title
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title=branded_page_title("Science Plus"),
    page_icon=":material/biotech:",
    layout="wide",
)

apply_theme()
render_pulse(ROOT)
