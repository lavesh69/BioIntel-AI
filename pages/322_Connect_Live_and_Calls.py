from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.connect.complete_ui import render_live_calls
st.set_page_config(page_title="Live and calls · BioIntel AI", page_icon=":material/video_call:", layout="wide")
render_live_calls(ROOT)
