from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase32_35.discovery_ui import render_discovery_ecosystem

st.set_page_config(
    page_title="Scientific Discovery Agents",
    page_icon=":material/neurology:",
    layout="wide",
)
render_discovery_ecosystem(ROOT)
