from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.target_modules_v179 import qualification_matrix
from biointel.ui.theme import apply_theme,hero
st.set_page_config(page_title='Step 179 Platform/Core Assurance · BioIntel AI',page_icon='🛡️',layout='wide');apply_theme()
hero('Step 179 · 18 Platform/Core Modules','Deterministic platform assurance for job execution, workspaces, evidence, plugins, provenance, reference lifecycle, reports, file safety, Windows release and workflow orchestration.',eyebrow='Internal implementation 10/10 · External evidence fail-closed',chips=['18/18 modules','Golden/adverse fixtures','Security & rollback','Windows qualification'])
execute=st.toggle('Run non-destructive component probes',False)
frame=qualification_matrix(ROOT,execute);a,b,c,d=st.columns(4);a.metric('Modules',len(frame));b.metric('Internal 10/10',int(frame.internal_after_rating.eq(10).sum()));c.metric('Built-in smoke passed',int(frame.deterministic_smoke_passed.sum()));d.metric('Controlled release',int(frame.controlled_release_eligible.sum()))
st.dataframe(frame,width="stretch",hide_index=True)
st.download_button('Download qualification CSV',frame.to_csv(index=False).encode(),'step179_18_platform_core_qualification.csv','text/csv')
st.warning('Controlled release stays fail-closed until real target-Windows component/reference/fixture/governance/external evidence is complete.')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
