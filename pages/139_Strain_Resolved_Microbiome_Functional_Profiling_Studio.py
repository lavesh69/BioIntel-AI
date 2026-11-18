from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.renderer import render_nextgen_module

from biointel.ui.theme import apply_theme

st.set_page_config(page_title='Strain-Resolved Microbiome & Functional Profiling Studio' + " · BioIntel AI", page_icon='🦠', layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/139_Strain_Resolved_Microbiome_Functional_Profiling_Studio.py", key_prefix="139_strain_resolved_microbiome_functional_profiling_studio", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('strain_microbiome', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'strain_microbiome', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("strain_microbiome", key_prefix="step116_139_Strain_Resolved_Microbiome_Functional_Profiling_Studio_strain_microbiome_1", expanded=False)
render_nextgen_module('strain_microbiome')
# Step 180 final-five scientific qualification
from biointel.target_modules_v180.ui import render_step180_module_upgrade
render_step180_module_upgrade('strain_microbiome', expanded=False)

# Step 181 real external scientific evidence qualification
from biointel.external_readiness_v181.ui import render_step181_external_readiness
render_step181_external_readiness('strain_microbiome', expanded=False)



# Step 182 synthetic demo evidence files
from biointel.external_demo_v182.ui import render_step182_demo_evidence
render_step182_demo_evidence('strain_microbiome', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("strain_microbiome", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("strain_microbiome", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('strain_microbiome', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('strain_microbiome', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('strain_microbiome', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('strain_microbiome', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('strain_microbiome', expanded=False)

