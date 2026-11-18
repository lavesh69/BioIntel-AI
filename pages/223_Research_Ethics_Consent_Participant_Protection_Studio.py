from __future__ import annotations

# Shared design shell is supplied by the renderer: hero(

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.research_planning.lifecycle_renderer import render_lifecycle_module
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="Research Ethics, Consent & Participant Protection Studio · BioIntel AI", page_icon="EP", layout="wide")
apply_theme()
render_lifecycle_module("research_ethics_consent")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key="research_ethics_consent", title="Research Ethics, Consent & Participant Protection Studio", category="Research Planning")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
