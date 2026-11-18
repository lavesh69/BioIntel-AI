from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.target_modules_v180 import qualification_matrix
from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board

st.set_page_config(
    page_title="Step 180 Final Five Scientific Qualification · BioIntel AI",
    page_icon="🧬",
    layout="wide",
)
apply_theme()
hero(
    "Step 180 · Final Five Scientific Modules",
    "Focused scientific assurance for phenotypic screening, spatial pathology, protein generation, protein–ligand co-design and strain-resolved microbiome.",
    eyebrow="Internal implementation 10/10 · External scientific evidence fail-closed",
    chips=["5/5 modules", "80/80 portfolio internal", "Model/cohort provenance", "Wet-lab and site gates"],
)

execute = st.toggle("Run non-destructive runtime import/version probes", False)
frame = qualification_matrix(ROOT, execute)
scientific_boundary_banner(
    source_kind="final_scientific_qualification",
    release_eligible=False,
    message="Internal software qualification is distinct from authentic model weights, qualified references, independent cohorts, target-machine runtime execution, orthogonal or wet-lab confirmation and expert approval.",
)
render_metric_board(
    [
        ("Final modules", len(frame), "Focused scientific qualification set.", "info"),
        ("Internal 10/10", int(frame.internal_after_rating.eq(10).sum()), "Software-owned controls complete.", "success"),
        ("Scientific smoke passed", int(frame.deterministic_scientific_smoke_passed.sum()), "Deterministic local verification only.", "neutral"),
        ("Portfolio internal", "80/80", "Portfolio software assurance state.", "success"),
        ("Controlled release", int(frame.controlled_release_eligible.sum()), "External evidence still gates release.", "warning"),
    ]
)

matrix_tab, boundary_tab = st.tabs(["Qualification matrix", "Scientific boundary"])
with matrix_tab:
    section_title("Final-five qualification details", "📊")
    smart_dataframe(frame, height=610, key="step180_qualification")
    st.download_button(
        "Download Step 180 qualification CSV",
        frame.to_csv(index=False).encode("utf-8"),
        "step180_final_five_qualification.csv",
        "text/csv",
        width="stretch",
    )
with boundary_tab:
    st.warning(
        "Internal software qualification is 10/10. Controlled scientific release remains fail-closed until authentic model weights, qualified references, independent cohorts, target-machine runtime execution, orthogonal/wet-lab confirmation and expert approval are complete."
    )

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
