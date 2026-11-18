from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase32_35.twin_ui import render_digital_twin_lab

st.set_page_config(
    page_title="Biomedical Digital Twin Learning Lab",
    page_icon=":material/model_training:",
    layout="wide",
)
render_digital_twin_lab(ROOT)
