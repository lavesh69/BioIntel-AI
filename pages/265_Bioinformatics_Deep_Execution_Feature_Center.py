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

st.set_page_config(page_title="Bioinformatics Deep Execution Center · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
hero(
    "Bioinformatics Deep Execution Center",
    "Inspect native-format readiness, genomic cohorts, sparse single-cell data, spatial omics, multi-omics batches, microbiome controls, specialist tools and reproducibility manifests.",
    eyebrow="BioIntel AI · Bioinformatics maximum-potential workflows",
    chips=["1 GB staged ingestion", "Sparse-aware QC", "Tool discovery", "Reproducibility"],
)
scientific_boundary_banner(
    source_kind="research_software",
    release_eligible=False,
    message="QC and interoperability outputs require protocol-specific review, approved references and independent scientific validation.",
)
render_feature_center("Bioinformatics")
