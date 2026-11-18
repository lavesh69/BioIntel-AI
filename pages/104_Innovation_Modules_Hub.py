from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.excellence_ui import render_innovation_hub_excellence
from biointel.innovation.professional_ui import render_innovation_hub_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402

TEMPLATE_PACK = ROOT / "data" / "innovation_templates" / "BIOINTEL_INNOVATION_TEMPLATE_PACK.zip"

from biointel.ui.navigation import PAGE_BY_KEY  # noqa: E402
from biointel.ui.theme import feature_card  # noqa: E402

st.set_page_config(page_title="Innovation Modules Hub · BioIntel AI", page_icon="✨", layout="wide")
apply_theme()
hero("Innovation Modules Hub", "Ten upgraded scientific workbenches with deeper analytics, reproducibility controls, real-data import paths, uncertainty reporting and execution-aware workflows.", eyebrow="BioIntel AI Step 99", chips=["10 Pro modules", "Nested validation", "Real-data imports", "Execution-aware", "Transparent boundaries"])
modules = [
    ("pangenome_graph", "GFA1/GFA2 topology, bubbles and path comparison", "🧬"),
    ("long_read_assembly", "FASTQ.GZ QC, executable plans and T2T signals", "🧵"),
    ("protein_design_lab", "BLOSUM62, Pareto mutation ranking and PDB context", "🧫"),
    ("crispr_perturbseq", "Replicate-aware FDR and Perturb-seq UMAP/DE", "✂️"),
    ("pathogen_outbreak", "SNP-time-space clustering and MST review", "🦠"),
    ("synthetic_biology_designer", "Synthesis QC, Gibson, codon optimization and GenBank", "🧩"),
    ("rare_disease_board", "VCF/CNV research prioritization with ACMG assistance", "🔎"),
    ("knowledge_graph_copilot", "Importable evidence graph, paths, conflicts and gaps", "🕸️"),
    ("multiomics_biomarker", "Nested CV, CIs, permutation and external validation", "📈"),
    ("visual_workflow_builder", "Editable DAG with resume and real local run history", "🔗"),
]
for start in range(0, len(modules), 3):
    cols = st.columns(3)
    for column, (key, copy, icon) in zip(cols, modules[start:start+3], strict=False):
        with column:
            page = PAGE_BY_KEY[key]
            feature_card(page.title, copy, icon)
            st.page_link(page.path, label="Open module", width="stretch")
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message="Every module clearly separates demonstrator analytics from validated scientific evidence. Import real data and complete independent validation before publication, clinical or regulated use.")

# Step 99 module excellence layer
render_innovation_hub_excellence()

# Step 100 professional integration and optimization layer
render_innovation_hub_professional()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='innovation_modules_hub', title='Innovation Modules Hub', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
