from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.research_planning.advanced_renderer import ASSUMPTIONS_DB, COLLAB_DB, THREAD_DB, _safe_payload
from biointel.research_planning.assumptions import AssumptionRegistry
from biointel.research_planning.collaboration import PlanningCollaborationStore
from biointel.research_planning.command_center import build_command_center, recommended_actions
from biointel.research_planning.digital_thread import ResearchDigitalThreadStore
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Research Planning Command Center · BioIntel AI", page_icon="RP", layout="wide")
apply_theme()
hero(
    "Research Planning Command Center",
    "Connect protocol, endpoints, sample size, eligibility, CRFs, SAP, recruitment, risks, budgets and preregistration into one traceable planning system.",
    eyebrow="BioIntel Research Planning · Connected Operating System",
    chips=["24 planning modules", "Digital thread", "Standards readiness", "Consistency audit", "Decision traceability"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="This command center provides local planning-readiness and traceability support. It does not certify regulatory compliance, ethical approval or study validity.",
)

plan = st.session_state.setdefault("biointel_master_research_plan", _safe_payload("research_planning_command_center", None))

with st.expander("Master study context", expanded=False):
    c1, c2, c3 = st.columns(3)
    plan["protocol_id"] = c1.text_input("Protocol ID", value=str(plan.get("protocol_id", "BIOINTEL-PLAN-001")))
    plan["protocol_version"] = c2.text_input("Protocol version", value=str(plan.get("protocol_version", "0.1-draft")))
    plan["primary_endpoint"] = c3.text_input("Primary endpoint", value=str(plan.get("primary_endpoint", "Primary outcome")))
    c4, c5, c6 = st.columns(3)
    plan["protocol_sample_size"] = int(c4.number_input("Protocol sample size", 1, 10_000_000, int(plan.get("protocol_sample_size", 200))))
    plan["power_sample_size"] = int(c5.number_input("Power result sample size", 1, 10_000_000, int(plan.get("power_sample_size", 200))))
    plan["estimated_eligible_population"] = int(c6.number_input("Estimated eligible population", 0, 100_000_000, int(plan.get("estimated_eligible_population", 500))))
    st.session_state["biointel_master_research_plan"] = plan

with st.expander("Research lifecycle readiness assumptions", expanded=False):
    l1, l2, l3, l4 = st.columns(4)
    plan["ethics_consent_score"] = float(l1.slider("Ethics and consent readiness", 0, 100, int(plan.get("ethics_consent_score", 70))))
    plan["fair_data_score"] = float(l2.slider("FAIR data readiness", 0, 100, int(plan.get("fair_data_score", 70))))
    plan["monitoring_readiness_score"] = float(l3.slider("Interim monitoring readiness", 0, 100, int(plan.get("monitoring_readiness_score", 60))))
    plan["dissemination_readiness_score"] = float(l4.slider("Dissemination readiness", 0, 100, int(plan.get("dissemination_readiness_score", 55))))
    st.session_state["biointel_master_research_plan"] = plan

try:
    assumptions = AssumptionRegistry(ASSUMPTIONS_DB).list()
except Exception:
    assumptions = pd.DataFrame()
try:
    threads = PlanningCollaborationStore(COLLAB_DB).threads()
except Exception:
    threads = pd.DataFrame()
reviews = pd.DataFrame()
readiness, blockers, standards, summary = build_command_center(plan, assumptions, reviews, threads)

metric_cards([
    ("Overall planning readiness", f"{summary['overall_readiness']:.1f}%", None),
    ("Critical blockers", summary["critical_blockers"], None),
    ("Open blockers", summary["open_blockers"], None),
    ("Assumption quality", f"{summary['assumption_quality']:.1f}%", None),
])

left, right = st.columns([1.2, 1])
with left:
    fig = go.Figure(go.Scatterpolar(r=readiness["score"].tolist() + [readiness["score"].iloc[0]], theta=readiness["dimension"].tolist() + [readiness["dimension"].iloc[0]], fill="toself"))
    fig.update_layout(title="Research planning readiness", polar={"radialaxis": {"range": [0, 100], "visible": True}}, showlegend=False)
    st.plotly_chart(fig, width="stretch")
with right:
    st.plotly_chart(px.bar(readiness.sort_values("score"), x="score", y="dimension", orientation="h", range_x=[0, 100], title="Readiness by planning dimension"), width="stretch")

section_title("Blockers and recommended actions", "alert")
if blockers.empty:
    st.success("No open readiness or consistency blockers were detected in the current master context.")
else:
    smart_dataframe(blockers, height=330, key="rp_command_blockers")
smart_dataframe(recommended_actions(blockers), height=300, key="rp_command_actions")

section_title("Standards-readiness matrix", "shield")
smart_dataframe(standards, height=420, key="rp_command_standards")

section_title("Full research lifecycle modules", "network")
l1, l2, l3, l4 = st.columns(4)
l1.page_link("pages/223_Research_Ethics_Consent_Participant_Protection_Studio.py", label="Ethics & consent")
l2.page_link("pages/224_Research_Data_Management_FAIR_Planning_Studio.py", label="FAIR data planning")
l3.page_link("pages/225_Data_Monitoring_Interim_Review_Safety_Studio.py", label="Interim monitoring")
l4.page_link("pages/226_Publication_Dissemination_Knowledge_Translation_Studio.py", label="Publication & dissemination")

section_title("Digital-thread health", "network")
try:
    thread_store = ResearchDigitalThreadStore(THREAD_DB)
    nodes = thread_store.nodes()
    links = thread_store.links()
    orphans = thread_store.orphan_report()
    metric_cards([
        ("Thread entities", len(nodes), None),
        ("Traceability links", len(links), None),
        ("Orphan entities", len(orphans), None),
        ("Audit events", len(thread_store.audit(5000)), None),
    ])
    tabs = st.tabs(["Entities", "Links", "Orphan review", "Audit"])
    with tabs[0]:
        smart_dataframe(nodes.drop(columns=["payload_json", "payload"], errors="ignore"), height=330, key="rp_command_nodes")
    with tabs[1]:
        smart_dataframe(links, height=330, key="rp_command_links")
    with tabs[2]:
        smart_dataframe(orphans, height=330, key="rp_command_orphans")
    with tabs[3]:
        smart_dataframe(thread_store.audit(), height=330, key="rp_command_audit")
except Exception as exc:
    st.error(f"Digital-thread health could not be loaded: {exc}")

export = {
    "summary": summary,
    "master_plan": plan,
    "readiness": readiness.to_dict(orient="records"),
    "blockers": blockers.to_dict(orient="records"),
    "recommended_actions": recommended_actions(blockers).to_dict(orient="records"),
}
smart_json(export, title="Planning command-center manifest", download_name="research_planning_command_center.json", key="rp_command_manifest")
st.download_button("Download planning command-center JSON", json.dumps(export, indent=2, default=str).encode(), "research_planning_command_center.json", "application/json", type="primary", width="stretch")


# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='research_planning_command_center', title='Research Planning Command Center', category='Research Planning')


st.divider()
section_title("Peak Portfolio Feature Lab", "analysis")
from biointel.research_planning.feature_density_renderer import render_peak_feature_lab
render_peak_feature_lab("research_planning_command_center", None, plan=plan, key_prefix="rp_peak_command_center")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
