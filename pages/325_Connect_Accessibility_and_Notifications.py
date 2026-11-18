from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.connect.complete_ui import render_accessibility_notifications
st.set_page_config(page_title="Accessibility and notifications · BioIntel AI", page_icon=":material/accessibility_new:", layout="wide")
render_accessibility_notifications(ROOT)
