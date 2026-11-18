from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.target_modules_v178 import qualification_matrix
from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board

st.set_page_config(
    page_title="Step 178 · 19-Module Assurance Center · BioIntel AI",
    page_icon="🛡️",
    layout="wide",
)
apply_theme()
hero(
    "Step 178 · 19-Module Assurance Center",
    "A focused view of clinical, operational, privacy and ML assurance controls with transparent internal and external-readiness separation.",
    eyebrow="Internal assurance · evidence-bound external qualification",
    chips=["19 modules", "Runtime checks", "Privacy & ML", "Fail-closed release"],
)
scientific_boundary_banner(
    source_kind="module_assurance",
    release_eligible=False,
    message="Internal 10/10 describes local software controls. Licensed assets, prospective cohorts, wet-lab validation, independent review and controlled release remain separate evidence requirements.",
)

run = st.toggle("Run non-destructive engine smoke probes", value=False)
frame = qualification_matrix(ROOT, execute_smoke_tests=run)
render_metric_board(
    [
        ("Modules", len(frame), "Included assurance modules.", "info"),
        ("Internal 10/10", int(frame.internal_after_rating.eq(10).sum()), "Software-owned contract completion.", "success"),
        ("Average before", f"{frame.baseline_rating.mean():.2f}/10", "Baseline implementation state.", "neutral"),
        ("Average after", f"{frame.internal_after_rating.mean():.2f}/10", "Internal assurance result.", "success"),
        ("Controlled release", int(frame.controlled_release_eligible.sum()), "Evidence-gated release decisions.", "warning"),
    ]
)

matrix_tab, guidance_tab = st.tabs(["Qualification matrix", "Evidence boundary"])
with matrix_tab:
    section_title("Module qualification matrix", "📊")
    smart_dataframe(frame, height=650, key="step178_qualification")
    st.download_button(
        "Download qualification matrix CSV",
        frame.to_csv(index=False),
        "step178_19_module_qualification.csv",
        "text/csv",
        width="stretch",
    )
with guidance_tab:
    section_title("What remains evidence-bound", "🧭")
    st.info(
        "Use this screen to plan evidence collection and technical remediation. It never promotes a module based only on a local template, smoke probe or displayed score."
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
