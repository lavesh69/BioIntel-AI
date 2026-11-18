from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.ui.advanced_scientific_viewers import ADVANCED_VIEWER_CATALOG, render_advanced_viewer_hub
from biointel.ui.components import metric_cards
from biointel.ui.theme import apply_theme
from biointel.ui.workbench import compact_module_header

st.set_page_config(
    page_title="Advanced Scientific Viewers · BioIntel AI",
    page_icon="🔭",
    layout="wide",
)
apply_theme()
compact_module_header(
    title="Advanced Scientific Viewers",
    summary=(
        "Inspect genomic tracks, molecular structures, tissue and microscopy overlays, flow gates, spectra, "
        "trees, plate maps, pedigrees, outbreak geography, pangenome graphs, single-cell embeddings and "
        "operational scientific canvases in one optimized local workspace."
    ),
    icon="🔭",
    category="Scientific Intelligence",
    tags=("Genome", "3D structure", "Microscopy", "Flow cytometry", "Spectra", "Spatial"),
    boundary=(
        "Built-in viewers support local exploration and evidence review. Clinical, diagnostic, regulated or "
        "vendor-certified interpretation still requires validated methods, current reference data and specialist review."
    ),
)

metric_cards(
    [
        ("Advanced viewers", len(ADVANCED_VIEWER_CATALOG), "Optimized interactive canvases"),
        ("Scientific domains", 15, "Genomics through laboratory operations"),
        ("Rendering mode", "Lazy", "Only the selected view is built"),
        ("Offline operation", "Supported", "No network required for bundled demonstrations"),
    ]
)

render_advanced_viewer_hub()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='advanced_scientific_viewers', title='Advanced Scientific Viewers', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
