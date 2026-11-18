# STEP139_BIOINFORMATICS_NATIVE_REVIEW_PUBLICATION_PEAK
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

st.set_page_config(page_title='Proteogenomics & Neoantigen Discovery Studio' + " · BioIntel AI", page_icon='🧬', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('proteogenomics_neoantigen', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'proteogenomics_neoantigen', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("proteogenomics", key_prefix="step116_124_Proteogenomics_and_Neoantigen_Discovery_Studio_proteogenomics_1", expanded=False)
render_expansion_module('proteogenomics_neoantigen')

# Step 115 non-chart visual: mass_spectrum_inspector
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("mass_spectrum_inspector", key_prefix="step115_124_Proteogenomics_and_Neoantigen_Discovery_Studio_mass_spectrum_inspector", expanded=False)

# Step 115 non-chart visual: multiomics_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("multiomics_canvas", key_prefix="step115_124_Proteogenomics_and_Neoantigen_Discovery_Studio_multiomics_canvas", expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='proteogenomics_neoantigen', title='Proteogenomics & Neoantigen Discovery Studio', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='proteogenomics_neoantigen', title='Proteogenomics & Neoantigen Discovery Studio', category='Discovery')


# STEP137_BIOINFORMATICS_PEAK_EXPANSION (superseded by Step 138)
# STEP138_BIOINFORMATICS_DEEP_EXCELLENCE
from biointel.bioinformatics_peak_v138.renderer import render_bioinformatics_peak_module as _render_bioinformatics_peak_v138
_render_bioinformatics_peak_v138('proteogenomics_peak', embedded=True)

# STEP176_TARGET_MODULE_OPERATIONAL_EXCELLENCE
from biointel.target_modules_v176.ui import render_target_module_upgrade as _render_step176_target_module_upgrade
_render_step176_target_module_upgrade('proteogenomics_neoantigen', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("proteogenomics_neoantigen", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("proteogenomics_neoantigen", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('proteogenomics_neoantigen', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('proteogenomics_neoantigen', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('proteogenomics_neoantigen', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('proteogenomics_neoantigen', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('proteogenomics_neoantigen', expanded=False)

