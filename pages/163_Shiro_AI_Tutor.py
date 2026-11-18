from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.shiro.ui.page import render_page
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="Shiro AI Tutor · BioIntel AI", page_icon=":material/school:", layout="wide")
apply_theme()
render_page(ROOT)
