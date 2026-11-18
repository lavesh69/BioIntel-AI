from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.connect.advanced_ui import render_marketplace_equipment
st.set_page_config(page_title='Marketplace and equipment - BioIntel AI',page_icon=':material/precision_manufacturing:',layout='wide')
render_marketplace_equipment(ROOT)
