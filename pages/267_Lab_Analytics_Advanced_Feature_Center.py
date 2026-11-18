from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.module_features_v208.ui import render_feature_center
from biointel.ui.components import scientific_boundary_banner
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Lab Analytics Advanced Feature Center · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
hero(
    "Lab Analytics Advanced Feature Center",
    "Run microscopy QC, high-content plate review, bioprocess analytics, metagenomics controls, construct QC, primer/CRISPR review, organoid trajectories, vector QC and human-gated experiment planning.",
    eyebrow="BioIntel AI · Lab analytics maximum-potential workflows",
    chips=["Image QC", "Plate controls", "Bioprocess trends", "Human approval gates"],
)
scientific_boundary_banner(
    source_kind="research_software",
    release_eligible=False,
    message="Outputs require calibrated instruments, validated assays, biosafety review and laboratory quality-system approval.",
)
render_feature_center("Lab Analytics")
