from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.research_planning.burden_budget import BudgetItem, BurdenItem, calculate_participant_burden, simulate_budget, site_workload_simulation
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Research Budget & Participant Burden Studio · BioIntel AI", page_icon="RB", layout="wide")
apply_theme()
hero(
    "Research Budget & Participant Burden Studio",
    "Quantify participant time, travel, procedures, blood volume, digital-access burden, site workload and probabilistic study cost.",
    eyebrow="BioIntel Research Planning · Feasibility",
    chips=["Participant burden", "Probabilistic budget", "Site capacity", "Scenario export"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Cost and burden estimates are planning aids. Local prices, ethics requirements, participant consultation and operational validation remain necessary.",
)

burden_tab, budget_tab, site_tab, export_tab = st.tabs(["Participant burden", "Research budget", "Site workload", "Export"])

with burden_tab:
    section_title("Participant burden model", "person")
    default_burden = pd.DataFrame([
        {"activity": "Screening visit", "visits": 1, "minutes_per_visit": 90.0, "travel_minutes_per_visit": 60.0, "blood_ml_per_visit": 20.0, "questionnaire_minutes_per_visit": 20.0, "digital_access_required": False, "discomfort_score": 3.0},
        {"activity": "Treatment visit", "visits": 4, "minutes_per_visit": 120.0, "travel_minutes_per_visit": 60.0, "blood_ml_per_visit": 15.0, "questionnaire_minutes_per_visit": 15.0, "digital_access_required": False, "discomfort_score": 4.0},
        {"activity": "Remote follow-up", "visits": 6, "minutes_per_visit": 20.0, "travel_minutes_per_visit": 0.0, "blood_ml_per_visit": 0.0, "questionnaire_minutes_per_visit": 15.0, "digital_access_required": True, "discomfort_score": 1.0},
    ])
    edited = pd.DataFrame(st.data_editor(default_burden, num_rows="dynamic", width="stretch", key="rp_burden_editor"))
    try:
        items = [BurdenItem(**row) for row in edited.to_dict(orient="records")]
        burden, burden_summary = calculate_participant_burden(items)
        st.session_state["rp_burden_table"] = burden
        st.session_state["rp_burden_summary"] = burden_summary
        metric_cards([
            ("Burden score", burden_summary["total_burden_score"], burden_summary["risk_level"]),
            ("Visits", burden_summary["total_visits"], None),
            ("Participant time", f"{burden_summary['total_time_hours']:.1f} h", None),
            ("Blood volume", f"{burden_summary['total_blood_ml']:.1f} mL", None),
        ])
        st.plotly_chart(px.bar(burden, x="activity", y="burden_score", color="digital_access_required", title="Burden contribution by activity"), width="stretch")
        smart_dataframe(burden, height=360, key="rp_burden_table")
    except Exception as exc:
        st.error(f"Participant burden calculation stopped safely: {exc}")

with budget_tab:
    section_title("Probabilistic study budget", "money")
    default_budget = pd.DataFrame([
        {"category": "Study start-up", "unit": "study", "quantity": 1.0, "unit_cost": 250000.0, "uncertainty_fraction": 0.08, "owner": "Sponsor"},
        {"category": "Sites", "unit": "site", "quantity": 10.0, "unit_cost": 18000.0, "uncertainty_fraction": 0.15, "owner": "Operations"},
        {"category": "Participants", "unit": "participant", "quantity": 220.0, "unit_cost": 3800.0, "uncertainty_fraction": 0.20, "owner": "Operations"},
        {"category": "Laboratory assays", "unit": "sample", "quantity": 440.0, "unit_cost": 210.0, "uncertainty_fraction": 0.18, "owner": "Laboratory"},
        {"category": "Data management and analysis", "unit": "study", "quantity": 1.0, "unit_cost": 160000.0, "uncertainty_fraction": 0.12, "owner": "Data"},
    ])
    edited_budget = pd.DataFrame(st.data_editor(default_budget, num_rows="dynamic", width="stretch", key="rp_budget_editor"))
    c1, c2 = st.columns(2)
    contingency = c1.slider("Contingency fraction", 0.0, 0.50, 0.12, 0.01)
    iterations = c2.slider("Monte Carlo iterations", 500, 25_000, 5000, 500)
    try:
        items = [BudgetItem(**row) for row in edited_budget.to_dict(orient="records")]
        budget, distribution, budget_summary = simulate_budget(items, iterations, 142, contingency)
        st.session_state["rp_budget_table"] = budget
        st.session_state["rp_budget_distribution"] = distribution
        st.session_state["rp_budget_summary"] = budget_summary
        metric_cards([
            ("Base total", f"{budget_summary['base_total']:,.0f}", None),
            ("Median with contingency", f"{budget_summary['median_total']:,.0f}", None),
            ("P90 total", f"{budget_summary['p90_total']:,.0f}", None),
            ("Contingency", f"{100*budget_summary['contingency_fraction']:.0f}%", None),
        ])
        st.plotly_chart(px.bar(budget, x="category", y="median_cost", error_y=budget["p90_cost"]-budget["median_cost"], error_y_minus=budget["median_cost"]-budget["p10_cost"], title="Budget by category with uncertainty"), width="stretch")
        st.plotly_chart(px.histogram(distribution, x="total_with_contingency", nbins=60, title="Total budget uncertainty distribution"), width="stretch")
        smart_dataframe(budget, height=360, key="rp_budget_table")
    except Exception as exc:
        st.error(f"Budget simulation stopped safely: {exc}")

with site_tab:
    section_title("Participant and site workload simulator", "site")
    site_default = pd.DataFrame([
        {"site": "Site A", "participants": 40, "staff_fte": 1.5, "working_hours_per_month": 140},
        {"site": "Site B", "participants": 30, "staff_fte": 1.0, "working_hours_per_month": 140},
        {"site": "Site C", "participants": 55, "staff_fte": 1.2, "working_hours_per_month": 140},
    ])
    sites = pd.DataFrame(st.data_editor(site_default, num_rows="dynamic", width="stretch", key="rp_site_editor"))
    c1, c2 = st.columns(2)
    visits = c1.number_input("Visits per participant", 1, 100, 6)
    minutes = c2.number_input("Staff minutes per visit", 1.0, 1440.0, 75.0)
    try:
        workload = site_workload_simulation(sites, int(visits), float(minutes))
        st.session_state["rp_site_workload"] = workload
        st.plotly_chart(px.bar(workload, x="site", y="utilization", color="status", title="Site workload utilization"), width="stretch")
        smart_dataframe(workload, height=360, key="rp_site_table")
    except Exception as exc:
        st.error(f"Site workload simulation stopped safely: {exc}")

with export_tab:
    package = {
        "participant_burden": st.session_state.get("rp_burden_table", pd.DataFrame()).to_dict(orient="records"),
        "participant_burden_summary": st.session_state.get("rp_burden_summary", {}),
        "budget": st.session_state.get("rp_budget_table", pd.DataFrame()).to_dict(orient="records"),
        "budget_summary": st.session_state.get("rp_budget_summary", {}),
        "site_workload": st.session_state.get("rp_site_workload", pd.DataFrame()).to_dict(orient="records"),
    }
    smart_json(package, title="Budget and burden planning manifest", download_name="research_budget_burden.json", key="rp_budget_manifest")
    st.download_button("Download complete budget and burden JSON", json.dumps(package, indent=2, default=str).encode(), "research_budget_participant_burden.json", "application/json", type="primary", width="stretch")


# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='research_budget_burden', title='Research Budget Participant Burden Studio', category='Research Planning')


st.divider()
section_title("Peak Budget & Burden Feature Lab", "analysis")
from biointel.research_planning.feature_density_renderer import render_peak_feature_lab
render_peak_feature_lab("research_budget_participant_burden", None, key_prefix="rp_peak_budget_burden")

st.divider()
section_title("Full Research Lifecycle Readiness", "network")
from biointel.research_planning.lifecycle_renderer import render_lifecycle_readiness_panel
render_lifecycle_readiness_panel("research_budget_participant_burden", context=st.session_state.get("biointel_master_research_plan", {}), key_prefix="rp_lifecycle_budget")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
