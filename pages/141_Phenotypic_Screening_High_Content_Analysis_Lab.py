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

st.set_page_config(page_title='Phenotypic Screening & High-Content Analysis Lab' + " · BioIntel AI", page_icon='🧫', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('phenotypic_screening', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'phenotypic_screening', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("high_content", key_prefix="step116_141_Phenotypic_Screening_High_Content_Analysis_Lab_high_content_1", expanded=False)
render_nextgen_module('phenotypic_screening')
# Step 180 final-five scientific qualification
from biointel.target_modules_v180.ui import render_step180_module_upgrade
render_step180_module_upgrade('phenotypic_screening', expanded=False)

# Step 181 real external scientific evidence qualification
from biointel.external_readiness_v181.ui import render_step181_external_readiness
render_step181_external_readiness('phenotypic_screening', expanded=False)


# Step 115 non-chart visual: microscopy_editor
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("microscopy_editor", key_prefix="step115_141_Phenotypic_Screening_High_Content_Analysis_Lab_microscopy_editor", expanded=False)

# Step 115 non-chart visual: plate_map_editor
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("plate_map_editor", key_prefix="step115_141_Phenotypic_Screening_High_Content_Analysis_Lab_plate_map_editor", expanded=False)


# Step 182 synthetic demo evidence files
from biointel.external_demo_v182.ui import render_step182_demo_evidence
render_step182_demo_evidence('phenotypic_screening', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("phenotypic_screening", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("phenotypic_screening", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('phenotypic_screening', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('phenotypic_screening', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('phenotypic_screening', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('phenotypic_screening', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('phenotypic_screening', expanded=False)

