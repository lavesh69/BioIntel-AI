from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.synthetic.ui import render_synthetic_demo_workspace

st.set_page_config(
    page_title="Synthetic Demo Data Workspace | BioIntel AI",
    page_icon=":material/science:",
    layout="wide",
)
render_synthetic_demo_workspace(ROOT)