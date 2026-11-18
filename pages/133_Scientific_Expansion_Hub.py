from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.expansion.catalog import EXPANSION_MODULES
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import apply_theme, feature_card, section_title
from biointel.ui.workbench import compact_module_header

st.set_page_config(page_title="Advanced Scientific Workbenches · BioIntel AI", page_icon="🚀", layout="wide")
apply_theme()
compact_module_header(
    title="Advanced Scientific Workbenches",
    summary="Explore integrated workbenches spanning epigenomics, metabolomics, biologics, spatial biology, clinical research, laboratory operations, model assurance and privacy engineering.",
    icon="🚀",
    category="Scientific Workspaces",
    tags=("21 workbenches", "Raw-file aware", "Auditable export"),
    boundary="These workbenches provide transparent exploratory analysis. Publication, clinical, manufacturing or regulated use requires validated methods, genuine evidence and independent review.",
)

section_title("Choose a scientific workspace", "✦")
st.caption("Each workspace provides active module-specific upload, a deterministic demonstration dataset, explicit run controls, cached results, quality review and a reproducible export bundle.")

for start in range(0, len(EXPANSION_MODULES), 3):
    columns = st.columns(3)
    for column, module in zip(columns, EXPANSION_MODULES[start : start + 3], strict=False):
        with column:
            page = PAGE_BY_KEY[module.key]
            feature_card(module.title, module.summary, module.icon)
            st.caption(module.category)
            st.page_link(page.path, label="Open workspace", width="stretch")

with st.expander("Workspace capabilities", expanded=False):
    st.markdown(
        """
        - Module-relevant FASTA, VCF, BED, H5AD/MTX, microscopy image, structure and mzML metadata imports.
        - Explicit **Run analysis** action with session-cached results instead of repeated hidden-tab execution.
        - Replicate-aware statistics, effect sizes, FDR and domain-specific quality checks where supported.
        - Filterable result tables, advanced auxiliary outputs and one-click ZIP evidence bundles.
        - Optional specialist-tool readiness checks without silent execution or misleading proxy claims.
        """
    )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scientific_expansion_hub', title='Advanced Scientific Workbenches', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
