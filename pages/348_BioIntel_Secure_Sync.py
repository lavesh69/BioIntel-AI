from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase32_35.ui import render_secure_sync

st.set_page_config(page_title="BioIntel Secure Sync", page_icon=":material/sync:", layout="wide")
render_secure_sync(ROOT)
