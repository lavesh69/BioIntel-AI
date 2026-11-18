from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.models_v171 import Step171Registry, qualification_matrix
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Authentic Models & Benchmarks · BioIntel AI", page_icon="M171", layout="wide")
apply_theme()
hero(
    "Authentic Models, Real Cohorts & Independent Benchmarks",
    "Checksum-bound model packages, verified public or official cohorts, locked holdout predictions and fail-closed domain release controls for every module that requires a predictive model.",
    eyebrow="BioIntel AI · Step 171 · v14.3.0",
    chips=["12 applicable modules", "8 authentic research packages", "4 acquisition plans", "No synthetic substitution"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message=(
        "An untouched holdout from a public cohort is a reproducible research benchmark, not an independent hospital, laboratory or prospective validation. "
        "Full controlled release still requires a genuinely external cohort or site, signed domain-expert review and a formal release decision."
    ),
)
registry = Step171Registry(ROOT)
status = registry.status()
matrix = qualification_matrix(ROOT)
metric_cards([
    ("Applicable modules", "12/12", "Qualification contracts"),
    ("Authentic packages", f"{status['authentic_research_packages']}/12", "Real public/official evidence"),
    ("Locked benchmarks", str(status["locked_benchmarks"]), "Predictions + hashes"),
    ("External-site complete", str(status["independent_external_sites"]), "Not inferred"),
])

qualified, pending = st.tabs(["Qualified research benchmarks", "External acquisition required"])
with qualified:
    section_title("Research benchmark qualification", "Real-cohort packages with transparent task boundaries")
    smart_dataframe(matrix[matrix["research_benchmark_qualified"]], height=570, key="step171_qualified")
with pending:
    section_title("Pending domain model acquisition", "No demo or wrong-domain model is substituted")
    smart_dataframe(matrix[~matrix["research_benchmark_qualified"]], height=420, key="step171_pending")

st.download_button(
    "Download all-module model qualification matrix",
    matrix.to_csv(index=False).encode(),
    "biointel_step171_model_qualification_matrix.csv",
    "text/csv",
    width="stretch",
)
st.info("Run BUILD_STEP171_MODEL_BENCHMARK_ASSETS_WINDOWS.bat to reproduce packages and VERIFY_STEP171_WINDOWS.bat to verify every model, cohort, prediction and checksum.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
