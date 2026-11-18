from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuro_cns.ui import render_neuro_cns_studio
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="Neuro/CNS Intelligence Studio · BioIntel AI",
    page_icon="🧠",
    layout="wide",
)
apply_theme()
render_neuro_cns_studio(ROOT)
