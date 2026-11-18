from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.connect.advanced_ui import render_events_mentorship
st.set_page_config(page_title='Events and mentorship - BioIntel AI',page_icon=':material/event:',layout='wide')
render_events_mentorship(ROOT)
