from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.expansion.renderer import render_expansion_module

from biointel.ui.theme import apply_theme

st.set_page_config(page_title='Spatial Omics & Digital Pathology Studio' + " · BioIntel AI", page_icon='🗺️', layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/118_Spatial_Omics_and_Digital_Pathology_Studio.py", key_prefix="118_spatial_omics_and_digital_pathology_studio", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('spatial_omics_pathology', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'spatial_omics_pathology', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("spatial_omics", key_prefix="step116_118_Spatial_Omics_and_Digital_Pathology_Studio_spatial_omics_1", expanded=False)
render_expansion_module('spatial_omics_pathology')
# Step 180 final-five scientific qualification
from biointel.target_modules_v180.ui import render_step180_module_upgrade
render_step180_module_upgrade('spatial_omics_pathology', expanded=False)

# Step 181 real external scientific evidence qualification
from biointel.external_readiness_v181.ui import render_step181_external_readiness
render_step181_external_readiness('spatial_omics_pathology', expanded=False)


# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("pathology", key_prefix="step110_118_Spatial_Omics_and_Digital_Pathology_Studio_pathology")

# Step 115 non-chart visual: pathology_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("pathology_canvas", key_prefix="step115_118_Spatial_Omics_and_Digital_Pathology_Studio_pathology_canvas", expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='spatial_omics_pathology', title='Spatial Omics & Digital Pathology Studio', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='spatial_omics_pathology', title='Spatial Omics & Digital Pathology Studio', category='Bioinformatics')


# Step 182 synthetic demo evidence files
from biointel.external_demo_v182.ui import render_step182_demo_evidence
render_step182_demo_evidence('spatial_omics_pathology', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("spatial_omics_pathology", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("spatial_omics_pathology", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('spatial_omics_pathology', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('spatial_omics_pathology', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('spatial_omics_pathology', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('spatial_omics_pathology', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('spatial_omics_pathology', expanded=False)

