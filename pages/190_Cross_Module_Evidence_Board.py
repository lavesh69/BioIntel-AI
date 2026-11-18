from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.nextgen_intelligence import render_global_evidence_board
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Cross-Module Evidence Board · BioIntel AI", page_icon="🧾", layout="wide")
apply_theme()
hero(
    "Cross-Module Evidence Board",
    "Combine candidate-level claims, confidence, source runs and evidence status from the fifteen next-generation biomedical modules.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["Cross-module evidence", "Candidate lineage", "Confidence filters", "CSV export"],
)
render_global_evidence_board()
st.warning("Evidence-board confidence is a transparent screening score. It is not a substitute for external validation, clinical evidence or regulatory review.")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='cross_module_evidence_board', title='Cross-Module Evidence Board', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
