from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.education.ui import render_classroom
st.set_page_config(page_title='BioIntel Classroom',page_icon=':material/school:',layout='wide');render_classroom(ROOT)

