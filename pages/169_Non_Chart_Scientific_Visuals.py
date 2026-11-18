from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.ui.components import metric_cards
from biointel.ui.non_chart_scientific_visuals import (
    MODULE_NON_CHART_CONTEXTS,
    NON_CHART_VISUAL_CATALOG,
    render_non_chart_visual_hub,
)
from biointel.ui.theme import apply_theme
from biointel.ui.workbench import compact_module_header

st.set_page_config(
    page_title="Non-Chart Scientific Visuals · BioIntel AI",
    page_icon="🧭",
    layout="wide",
)
apply_theme()
compact_module_header(
    title="Non-Chart Scientific Visuals",
    summary=(
        "Inspect, select, annotate and review scientific evidence using canvases, tracks, maps, editors, "
        "plate layouts, pedigrees, process boards and readiness matrices rather than conventional charts alone."
    ),
    icon="🧭",
    category="Scientific Intelligence",
    tags=("Genome tracks", "Image overlays", "Plate maps", "Pedigree", "Workflow boards", "Review matrices"),
    boundary=(
        "These workspaces improve inspection and decision support. They do not replace validated specialist software, "
        "current reference data, independent scientific review or regulated operating procedures."
    ),
)

metric_cards(
    [
        ("Scientific canvases", len(NON_CHART_VISUAL_CATALOG), "Lazy-rendered interactive workspaces"),
        ("Module-specific boards", len(MODULE_NON_CHART_CONTEXTS), "Decision and review layouts"),
        ("Conventional charts", "Not required", "Tracks, maps, editors and matrices"),
        ("Offline-safe", "Yes", "Bundled deterministic demonstrations"),
    ]
)

render_non_chart_visual_hub()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='non_chart_scientific_visuals', title='Non-Chart Scientific Visuals', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
