from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.priority_v168 import priority_matrix, universal_evidence_matrix
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
st.set_page_config(page_title='Remaining Modules & External Evidence · BioIntel AI',page_icon='E10',layout='wide')
apply_theme()
hero('Remaining Modules & External Evidence 10/10 Center','Focused scientific and operational assurance for the remaining 35 modules, plus universal evidence-intake and physical-qualification workflows for all 80 modules.',eyebrow='BioIntel AI · Step 168',chips=['35/35 software 10/10','80/80 evidence workflows','620 validation assets','Fail closed'])
scientific_boundary_banner(source_kind='reference',release_eligible=False,message='Step 168 completes software-owned analysis, intake, validation, review and release workflows. Genuine production references, independent studies, prospective/wet-lab evidence, expert decisions, operating history and physical tests must still be supplied by real providers, sites and reviewers.')
focused=priority_matrix(ROOT); universal=universal_evidence_matrix()
metric_cards([('Focused modules','35/35','Software + native depth'),('Universal modules','80/80','Evidence operations'),('Framework score','10/10','Software-owned'),('External completion','0/80','Real evidence required')])
section_title('Remaining-module excellence matrix','35 focused modules')
smart_dataframe(focused,height=560,key='step168_focused_matrix')
st.download_button('Download focused matrix',focused.to_csv(index=False).encode(),'biointel_step168_priority_module_matrix.csv','text/csv',width="stretch")
section_title('Universal evidence and physical qualification matrix','All 80 scientific modules')
smart_dataframe(universal,height=560,key='step168_universal_matrix')
st.download_button('Download universal matrix',universal.to_csv(index=False).encode(),'biointel_step168_universal_evidence_matrix.csv','text/csv',width="stretch")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
