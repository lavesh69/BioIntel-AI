from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.connect.advanced_ui import render_docs_whiteboard
st.set_page_config(page_title='Collaborative documents and whiteboards - BioIntel AI',page_icon=':material/edit_note:',layout='wide')
render_docs_whiteboard(ROOT)
