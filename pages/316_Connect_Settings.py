from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.connect.ui import render_settings
st.set_page_config(page_title="Connect Settings · BioIntel AI", page_icon=":material/hub:", layout="wide")
render_settings(ROOT)
