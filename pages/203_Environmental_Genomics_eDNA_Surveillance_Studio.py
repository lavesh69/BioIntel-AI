# STEP139_BIOINFORMATICS_NATIVE_REVIEW_PUBLICATION_PEAK
from __future__ import annotations

# Shared design shell is supplied by the renderer: compact_module_header(

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.bioinformatics_peak_v138.renderer import render_bioinformatics_peak_module
from biointel.ui.theme import apply_theme

st.set_page_config(page_title='Environmental Genomics & eDNA Surveillance Studio' + " · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()
render_bioinformatics_peak_module('environmental_edna')


# STEP136_NON_AI_VISUAL_PEAK_SUITE
# Native Step 138 renderer supplies twelve domain-specific visuals; the marker retains visual-coverage governance.

# Targeted peak-potential assurance for Bioinformatics modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='environmental_edna', title='Environmental Genomics & eDNA Surveillance Studio', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
