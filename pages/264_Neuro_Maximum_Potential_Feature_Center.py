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

st.set_page_config(page_title="Neuro Maximum-Potential Feature Center · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
hero(
    "Neuro Maximum-Potential Feature Center",
    "Run advanced local neuroscience workflows for signals, imaging, genetics, expression, omics, stratification, PK, evidence, trials and eight additional neurological research domains.",
    eyebrow="BioIntel AI · Neuro/CNS deep execution",
    chips=["17 executable workflows", "Local-first", "Calculated visuals", "Fail-closed boundaries"],
)
scientific_boundary_banner(
    source_kind="research_software",
    release_eligible=False,
    message="These workflows support de-identified research and software qualification only. They are not diagnostic, therapeutic or medical-device outputs.",
)
render_feature_center("Neuro/CNS")
