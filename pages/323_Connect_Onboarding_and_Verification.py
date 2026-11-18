from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.connect.complete_ui import render_onboarding_verification
st.set_page_config(page_title="Onboarding and verification · BioIntel AI", page_icon=":material/verified:", layout="wide")
render_onboarding_verification(ROOT)
