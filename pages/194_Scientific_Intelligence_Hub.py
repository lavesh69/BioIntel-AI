from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.intelligence import list_evidence_board, list_handoffs, list_run_snapshots, list_scenarios, list_validation_cohorts
from biointel.ui.components import metric_cards
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Scientific Intelligence Hub · BioIntel AI", page_icon="🧠", layout="wide")
apply_theme()
hero(
    "Scientific Intelligence Hub",
    "Central access to persistent run comparison, scenario analysis, evidence boards, validation cohorts, visual review and publication figure workflows.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["Run history", "Scenarios", "Evidence", "Cohorts", "Publication figures"],
)

runs = list_run_snapshots(ROOT)
scenarios = list_scenarios(ROOT)
evidence = list_evidence_board(ROOT)
cohorts = list_validation_cohorts(ROOT)
handoffs = list_handoffs(ROOT)
metric_cards([
    ("Persistent runs", len(runs), "Next-generation module snapshots"),
    ("Saved scenarios", len(scenarios), "Sensitivity analyses"),
    ("Evidence items", len(evidence), "Cross-module board"),
    ("Validation cohorts", len(cohorts), "Manifested cohort identities"),
    ("Handoffs", len(handoffs), "Auditable module transfers"),
])

links = [
    ("Scientific Visual Workspace Studio", "pages/189_Scientific_Visual_Workspace_Studio.py", "Saved views, annotations and publication figure workflow."),
    ("Cross-Module Evidence Board", "pages/190_Cross_Module_Evidence_Board.py", "Candidate evidence from multiple scientific modules."),
    ("Scenario & Sensitivity Lab", "pages/191_Scientific_Scenario_Sensitivity_Lab.py", "Saved threshold and assumption comparisons."),
    ("Validation Cohort Manager", "pages/192_Validation_Cohort_Manager.py", "Internal, external, blinded and prospective cohort manifests."),
    ("Visual Review & Approval Center", "pages/193_Visual_Review_Approval_Center.py", "Review views, decisions, annotations and rendering incidents."),
    ("Real-Time Scientific Canvas & Collaboration Center", "pages/195_Real_Time_Scientific_Canvas_Collaboration_Center.py", "No-rerun linked canvas, provenance, collaboration and journal layout workflows."),
    ("Multi-Scale Scientific Visual Intelligence Studio", "pages/196_Multi_Scale_Scientific_Visual_Intelligence_Studio.py", "Thirty new visual concepts for scale navigation, causal evidence, digital twins, replay and decision intelligence."),
]
for start in range(0, len(links), 3):
    columns = st.columns(3)
    for column, (title, path, description) in zip(columns, links[start:start + 3]):
        with column:
            with st.container(border=True):
                st.markdown(f"### {title}")
                st.write(description)
                st.page_link(path, label="Open workspace")

st.markdown("### Per-module intelligence")
st.write(
    "Every Step 128–132 biomedical module now includes a **Scientific intelligence** tab with linked selection, "
    "persistent run comparison, scenario simulation, review decisions, evidence-board handoff, story mode, visual QA and vector figure packages."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scientific_intelligence_hub', title='Scientific Intelligence Hub', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
