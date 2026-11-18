from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"src"
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.operational_assurance_v185 import step185_rating_matrix,step185_validation_matrix
from biointel.ui.theme import apply_theme
st.set_page_config(page_title="Step 185 Operational Assurance · BioIntel AI",page_icon="🛡️",layout="wide")
apply_theme(); st.title("🛡️ Step 185 · 19-Module Operational Assurance Center")
st.warning("10/10 here means validated synthetic-demo operation. Real clinical, wet-lab, instrument and controlled-release evidence remains separate.")
ratings=step185_rating_matrix(ROOT); validation=step185_validation_matrix(ROOT)
c1,c2,c3,c4=st.columns(4); c1.metric("Qualified",f"{int(ratings.qualified_10_of_10.sum())}/19"); c2.metric("Before average",f"{ratings.before_demo_rating.mean():.2f}/10"); c3.metric("After average",f"{ratings.after_operational_assurance_rating.mean():.2f}/10"); c4.metric("Controlled release","0/19")
st.subheader("Before/after ratings"); st.dataframe(ratings.sort_values(["after_operational_assurance_rating","module_title"],ascending=[False,True]),width="stretch",hide_index=True)
st.subheader("Integrity verification"); st.dataframe(validation,width="stretch",hide_index=True)
st.download_button("Download ratings CSV",ratings.to_csv(index=False),"STEP185_19_MODULE_BEFORE_AFTER_RATINGS.csv","text/csv")
st.download_button("Download validation CSV",validation.to_csv(index=False),"STEP185_19_MODULE_VALIDATION.csv","text/csv")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
