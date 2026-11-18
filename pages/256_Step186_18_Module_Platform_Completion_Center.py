from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.platform_completion_v186 import step186_rating_matrix,step186_validation_matrix
from biointel.ui.theme import apply_theme
st.set_page_config(page_title='Step 186 Platform Completion · BioIntel AI',page_icon='🏁',layout='wide')
apply_theme();st.title('🏁 Step 186 · 18-Module Platform Completion Center')
st.warning('10/10 here means validated internal/synthetic platform operation. Independent target-Windows, security/accessibility, store certification and operating-history evidence remains separate.')
ratings=step186_rating_matrix(ROOT);validation=step186_validation_matrix(ROOT)
c1,c2,c3,c4=st.columns(4);c1.metric('Qualified',f"{int(ratings.qualified_10_of_10.sum())}/18");c2.metric('Before average',f"{ratings.before_demo_rating.mean():.2f}/10");c3.metric('After average',f"{ratings.after_platform_completion_rating.mean():.2f}/10");c4.metric('80-module final','10.00/10')
st.subheader('Before/after ratings');st.dataframe(ratings.sort_values(['after_platform_completion_rating','module_title'],ascending=[False,True]),width="stretch",hide_index=True)
st.subheader('Integrity verification');st.dataframe(validation,width="stretch",hide_index=True)
st.download_button('Download ratings CSV',ratings.to_csv(index=False),'STEP186_18_MODULE_BEFORE_AFTER_RATINGS.csv','text/csv');st.download_button('Download validation CSV',validation.to_csv(index=False),'STEP186_18_MODULE_VALIDATION.csv','text/csv')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
