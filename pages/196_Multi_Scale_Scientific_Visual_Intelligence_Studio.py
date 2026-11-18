from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme, hero
from biointel.ui.visual_intelligence_v132 import render_global_visual_intelligence_studio

st.set_page_config(
    page_title="Multi-Scale Scientific Visual Intelligence Studio · BioIntel AI",
    page_icon="🌐",
    layout="wide",
)
apply_theme()
hero(
    "Multi-Scale Scientific Visual Intelligence Studio",
    "Explore thirty data-linked scientific visual concepts spanning biological scale, causal evidence, temporal replay, genomics, discovery, laboratory digital twins, governance and presentation.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["30 new visual concepts", "Lazy rendering", "Visual bookmarks", "Multi-monitor layouts", "Presenter mode"],
)
render_global_visual_intelligence_studio()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='multi_scale_visual_intelligence', title='Multi-Scale Scientific Visual Intelligence Studio', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
