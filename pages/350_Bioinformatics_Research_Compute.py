from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase32_35.compute_ui import render_research_compute

st.set_page_config(
    page_title="BioIntel Research Compute",
    page_icon=":material/biotech:",
    layout="wide",
)
render_research_compute(ROOT)
