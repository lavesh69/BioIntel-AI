from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.ui.components import metric_cards
from biointel.ui.module_experience_2_9 import (
    GROUP_LABELS,
    MODULE_EXPERIENCE_CATALOG,
    render_module_experience_hub,
)
from biointel.ui.theme import apply_theme
from biointel.ui.workbench import compact_module_header

st.set_page_config(
    page_title="Interactive Module Experience Hub · BioIntel AI",
    page_icon="🧭",
    layout="wide",
)
apply_theme()
compact_module_header(
    title="Interactive Module Experience Hub",
    summary=(
        "Open the non-chart scientific workspaces added across recommendation sections 2–9: sequence and genomics, "
        "pathogen and long-read, omics and spatial biology, protein and discovery, analytical imaging, wet-lab design, "
        "AI/model lifecycle, and data/evidence governance."
    ),
    icon="🧭",
    category="Scientific Intelligence",
    tags=("Entity Passport", "Decision Replay", "Cross-module handoff", "Scientific notebook", "Readiness matrix"),
    boundary=(
        "The workspaces organize inspection, review and reproducibility. They do not replace specialist scientific engines, "
        "independent validation, provider licences or regulated clinical interpretation."
    ),
)

metric_cards(
    [
        ("Module workspaces", len(MODULE_EXPERIENCE_CATALOG), "Integrated into sections 2–9"),
        ("Scientific groups", len(GROUP_LABELS), "Eight domain families"),
        ("Core interactions", "5", "Canvas, passport, replay, handoff and notebook"),
        ("Network dependency", "None", "Deterministic offline UI layer"),
    ]
)

render_module_experience_hub()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='module_experience_2_9', title='Interactive Module Experience Hub', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
