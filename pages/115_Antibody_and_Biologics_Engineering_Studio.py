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

st.set_page_config(page_title='Antibody & Biologics Engineering Studio' + " · BioIntel AI", page_icon='🧫', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('antibody_biologics', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'antibody_biologics', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("antibody", key_prefix="step116_115_Antibody_and_Biologics_Engineering_Studio_antibody_1", expanded=False)
render_expansion_module('antibody_biologics')

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("molecular_3d", key_prefix="step110_115_Antibody_and_Biologics_Engineering_Studio_molecular_3d")

# Step 115 non-chart visual: molecular_scene
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("molecular_scene", key_prefix="step115_115_Antibody_and_Biologics_Engineering_Studio_molecular_scene", expanded=False)

# Step 115 non-chart visual: sequence_feature_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("sequence_feature_track", key_prefix="step115_115_Antibody_and_Biologics_Engineering_Studio_sequence_feature_track", expanded=False)

# Step 115 module-specific non-chart workspace: antibody
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("antibody", key_prefix="step115_115_Antibody_and_Biologics_Engineering_Studio_antibody", expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='antibody_biologics', title='Antibody & Biologics Engineering Studio', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='antibody_biologics', title='Antibody & Biologics Engineering Studio', category='Discovery')

# STEP176_TARGET_MODULE_OPERATIONAL_EXCELLENCE
from biointel.target_modules_v176.ui import render_target_module_upgrade as _render_step176_target_module_upgrade
_render_step176_target_module_upgrade('antibody_biologics', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("antibody_biologics", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("antibody_biologics", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('antibody_biologics', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('antibody_biologics', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('antibody_biologics', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('antibody_biologics', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('antibody_biologics', expanded=False)

