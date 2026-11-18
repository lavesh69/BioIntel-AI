from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.bioinformatics_upgrades import CONTEXT_LABELS, render_bioinformatics_upgrade_panel
from biointel.ui.components import scientific_boundary_banner
from biointel.ui.theme import apply_theme, hero
from biointel.module_runtime_v207.portfolio_ui import render_step207_portfolio_panel

st.set_page_config(page_title="Bioinformatics Feature Upgrade Center · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()
hero(
    "🧬 Bioinformatics Feature Upgrade Center",
    "Run the Step 112 shared QC, study-design and reproducibility upgrades used across sequence, FASTQ, variants, transcriptomics, proteins, phylogeny, metagenomics, pangenomes and long-read workflows.",
    eyebrow="Bioinformatics · Shared Scientific Infrastructure",
    chips=["Batch sequence QC", "Extended FASTQ", "VCF QC", "Design matrices", "Reproducible plans"],
)
scientific_boundary_banner(source_kind="reference", release_eligible=False, message="Built-in analyses are transparent screening and QC aids. Production claims require appropriate specialist engines, reference databases and independent validation.")
st.page_link(
    "pages/168_Synthetic_Demo_Data_Workspace.py",
    label="Open Synthetic Demo Data Workspace",
    icon=":material/science:",
    width="stretch",
)

render_step207_portfolio_panel("Bioinformatics", expanded=True)

context = st.selectbox("Upgrade workspace", list(CONTEXT_LABELS), format_func=lambda key: f"{key.replace('_', ' ').title()} · {CONTEXT_LABELS[key]}")
render_bioinformatics_upgrade_panel(context, expanded=True)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='bioinformatics_upgrade_center', title='Bioinformatics Feature Upgrade Center', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='bioinformatics_upgrade_center', title='Bioinformatics Feature Upgrade Center', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
