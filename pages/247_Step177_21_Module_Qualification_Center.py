from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.ui.theme import apply_theme
from biointel.target_modules_v177 import qualification_matrix
st.set_page_config(page_title='Step 177 · 21-Module Qualification Center · BioIntel AI',page_icon='🧪',layout='wide');apply_theme()
st.title('Step 177 · 21-Module Qualification Center')
st.caption('Internal 10/10 contracts with fail-closed runtime, reference, authentic-model, real-cohort and external-evidence qualification.')
run=st.checkbox('Execute non-destructive engine smoke probes',False)
frame=qualification_matrix(ROOT,execute_smoke_tests=run)
a,b,c,d=st.columns(4);a.metric('Modules',len(frame));b.metric('Internal 10/10',int(frame.internal_upgrade_rating.eq(10).sum()));c.metric('Controlled-release eligible',int(frame.controlled_release_eligible.sum()));d.metric('Research-only',int(frame.decision.eq('research-only-fail-closed').sum()))
st.dataframe(frame,width="stretch",hide_index=True)
st.download_button('Download qualification matrix CSV',frame.to_csv(index=False),'step177_21_module_qualification.csv','text/csv')
st.warning('A 10/10 internal implementation does not imply real-world or clinical release. All external evidence remains fail-closed until verified on the target environment.')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
