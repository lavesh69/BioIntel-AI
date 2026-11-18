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

st.set_page_config(page_title="Discovery Optimization Feature Center · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
hero(
    "Discovery Optimization Feature Center",
    "Run compound preparation, docking review, ADMET calibration, multi-objective lead ranking, protein design QC, antibody developability, neoantigen prioritization and assay planning.",
    eyebrow="BioIntel AI · Discovery deep execution",
    chips=["BioIntel molecular standardization", "Applicability domain", "Pareto ranking", "Assay controls"],
)
scientific_boundary_banner(
    source_kind="research_software",
    release_eligible=False,
    message="Screening and design outputs do not replace measured potency, selectivity, ADMET, binding, immunogenicity or safety experiments.",
)
render_feature_center("Discovery")
