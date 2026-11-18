from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.nextgen.renderer import render_nextgen_module

from biointel.step121.panels import render_citation_upgrade
from biointel.ui.theme import apply_theme

st.set_page_config(page_title='Scientific Evidence & Citation Engine' + " · BioIntel AI", page_icon='📚', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('evidence_citation_engine', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("evidence_citation", key_prefix="step116_155_Scientific_Evidence_Citation_Engine_evidence_citation_1", expanded=False)
render_nextgen_module('evidence_citation_engine')
render_citation_upgrade(key_prefix="step121_citation_engine")

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("evidence_citation_engine", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("evidence_citation_engine", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("evidence_citation_engine", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('evidence_citation_engine', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('evidence_citation_engine', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('evidence_citation_engine', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('evidence_citation_engine', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('evidence_citation_engine', expanded=False)

