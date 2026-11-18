from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.nextgen_intelligence import render_visual_review_center
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Visual Review & Approval Center · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()
hero(
    "Visual Review & Approval Center",
    "Review saved views, visual annotations, candidate decisions and recorded rendering failures from one auditable workspace.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["Review queue", "Annotations", "Decision history", "Visual diagnostics"],
)
render_visual_review_center()

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
