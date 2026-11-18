from __future__ import annotations

import streamlit as st

from biointel.nextgen.renderer import render_nextgen_module

from biointel.ui.theme import apply_theme

st.set_page_config(page_title='Instrument Integration Hub 2' + " · BioIntel AI", page_icon='🔌', layout="wide")
apply_theme()
render_nextgen_module('instrument_integration_v2')

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("bioprocess_live", key_prefix="step110_157_Instrument_Integration_Hub_2_bioprocess_live")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
