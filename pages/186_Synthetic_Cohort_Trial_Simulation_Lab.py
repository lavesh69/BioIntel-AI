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

st.set_page_config(page_title='Synthetic Cohort & Trial Simulation Lab' + " · BioIntel AI", page_icon='🧪', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('synthetic_cohort_trial', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'synthetic_cohort_trial', expanded=False)
# STEP178_19_MODULE_CLINICAL_OPERATIONAL_PRIVACY_ML_ASSURANCE
from biointel.target_modules_v178.ui import render_step178_module_upgrade
render_step178_module_upgrade('synthetic_cohort_trial', expanded=False)

render_nextgen_module('synthetic_cohort_trial')

st.divider()
from biointel.ui.theme import section_title as _rp_section_title
from biointel.research_planning.advanced_renderer import render_connected_planning_os as _render_connected_planning_os
_rp_section_title("Connected Research Planning OS", "network")
_render_connected_planning_os("synthetic_cohort_trial", None, key_prefix="rp_os_synthetic_cohort_trial")


st.divider()
_rp_section_title("Peak Feature Lab", "analysis")
from biointel.research_planning.feature_density_renderer import render_peak_feature_lab as _render_peak_feature_lab
_render_peak_feature_lab("synthetic_cohort_trial", None, key_prefix="rp_peak_synthetic_cohort_trial")

st.divider()
_rp_section_title("Full Research Lifecycle Readiness", "network")
from biointel.research_planning.lifecycle_renderer import render_lifecycle_readiness_panel as _render_lifecycle_readiness_panel
_render_lifecycle_readiness_panel("synthetic_cohort_trial", context=st.session_state.get("biointel_master_research_plan", {}), key_prefix="rp_lifecycle_synthetic")

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("synthetic_cohort_trial", expanded=False)


# Step 185 operational assurance panel (synthetic/demo boundary preserved)
try:
    from biointel.operational_assurance_v185.ui import render_step185_operational_assurance as _render_step185_operational_assurance
    _render_step185_operational_assurance("synthetic_cohort_trial")
except Exception as _step185_exc:
    try:
        import streamlit as st
        st.info(f"Step 185 assurance panel unavailable: {_step185_exc}")
    except Exception:
        pass

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('synthetic_cohort_trial', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('synthetic_cohort_trial', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('synthetic_cohort_trial', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('synthetic_cohort_trial', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('synthetic_cohort_trial', expanded=False)

