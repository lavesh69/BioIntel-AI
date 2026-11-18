from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.components import metric_cards, smart_dataframe
from biointel.ui.nextgen_intelligence import render_visual_review_center
from biointel.ui.theme import apply_theme, hero
from biointel.ui.visual_workspace import list_all_annotations, list_all_views, list_visual_errors

st.set_page_config(page_title="Scientific Visual Workspace Studio · BioIntel AI", page_icon="🎨", layout="wide")
apply_theme()
hero(
    "Scientific Visual Workspace Studio",
    "Review saved visual states, linked scientific selections, annotations, rendering incidents and report-ready figure assets across modules.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["Linked selection", "Saved views", "Annotations", "SVG/PDF/DOCX/PPTX"],
)

views = list_all_views()
annotations = list_all_annotations()
errors = list_visual_errors()
metric_cards([
    ("Saved views", len(views), "Persistent visual configurations"),
    ("Annotations", len(annotations), "Scientific reviewer notes"),
    ("Modules represented", views["module_key"].nunique() if not views.empty else 0, "Visual workspace coverage"),
    ("Visual errors", len(errors), "Recorded rendering incidents"),
])

render_visual_review_center()

st.markdown("### Figure package workflow")
st.write(
    "Open any Step 131 next-generation module, complete an analysis and use **Scientific intelligence → Story & figures**. "
    "The generated package includes vector SVG, HTML, PDF, DOCX, PPTX, bounded result tables and a machine-readable manifest."
)
if not views.empty:
    with st.expander("Saved visual configurations", expanded=False):
        smart_dataframe(views.drop(columns=["configuration_json"], errors="ignore"), height=420, key="step130_visual_workspace_views")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scientific_visual_workspace_studio', title='Scientific Visual Workspace Studio', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
