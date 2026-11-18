from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.expansion.renderer import render_expansion_module

from biointel.ui.theme import apply_theme

st.set_page_config(page_title='LIMS, ELN & Sample Chain-of-Custody Hub' + " · BioIntel AI", page_icon='🧾', layout="wide")
apply_theme()
render_expansion_module('lims_eln_chain')

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("freezer_map", key_prefix="step110_126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub_freezer_map")

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='lims_eln_chain', title='LIMS, ELN & Sample Chain-of-Custody Hub', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='lims_eln_chain', title='LIMS, ELN & Sample Chain-of-Custody Hub', category='Lab Analytics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
