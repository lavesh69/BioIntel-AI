from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES, Step173Registry, profile_matrix  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.operational_canvas import render_operational_canvas  # noqa: E402
from biointel.proof_gates_v10.ui import render_priority_upgrade_center  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.visual_polish import render_metric_board  # noqa: E402

st.set_page_config(page_title="Final All-Module 10/10 · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
registry = Step173Registry(ROOT)
matrix = registry.latest(refresh=False)

hero(
    "Final All-Module 10/10 Command Center",
    "One evidence-bound view of all 80 modules across internal software quality, native scientific depth, specialist runtime/reference qualification, authentic models and cohorts, external confirmation, physical qualification and controlled release.",
    eyebrow="Step 173 · version 14.5.0 · unified final qualification",
    chips=["80/80 internal 10/10", "Evidence-bound ratings", "Immutable snapshots", "Fail-closed release"],
)
scientific_boundary_banner(
    source_kind="unified_release_readiness",
    release_eligible=bool(matrix["controlled_release_eligible"].all()) if not matrix.empty else False,
    message=(
        "Internal software, native depth and qualification framework are complete at 10/10. Actual practical readiness remains evidence-bound: "
        "specialist engines, production references, authentic models/cohorts, external confirmations, physical testing, expert signatures and release approvals are never inferred."
    ),
)

registry_status = registry.status()
render_metric_board(
    [
        ("Internal 10/10", f"{int(matrix['internal_10of10_complete'].sum())}/80", "Software-owned quality status.", "success"),
        ("Average practical", f"{matrix['actual_practical_readiness_rating'].mean():.2f}/10", "Evidence-bound practical readiness.", "info"),
        ("Release eligible", f"{int(matrix['controlled_release_eligible'].sum())}/80", "Controlled release remains fail-closed.", "warning"),
        ("Remaining blockers", int(matrix["blocker_count"].sum()), "Outstanding evidence or control requirements.", "danger"),
        ("Registry integrity", "PASS" if registry_status["audit_chain_valid"] else "REVIEW", "Local audit-chain verification.", "success" if registry_status["audit_chain_valid"] else "warning"),
    ]
)

ratings_tab, module_tab, stages_tab, execution_tab, governance_tab, priority_tab = st.tabs([
    "All-module ratings", "Module action plan", "Readiness stages", "One-command execution", "Rating governance", "P0/P1 priority upgrades"
])

with ratings_tab:
    section_title("Honest final ratings", "📊")
    filters = st.columns(3)
    maximum = filters[0].slider("Maximum practical rating", 0.0, 10.0, 10.0, 0.25)
    stage = filters[1].selectbox("Readiness stage", ["All"] + sorted(matrix["readiness_stage"].unique().tolist()))
    decision = filters[2].selectbox("Decision", ["All"] + sorted(matrix["decision"].unique().tolist()))
    shown = matrix[matrix["actual_practical_readiness_rating"] <= maximum]
    if stage != "All":
        shown = shown[shown["readiness_stage"] == stage]
    if decision != "All":
        shown = shown[shown["decision"] == decision]
    smart_dataframe(shown, height=680, key="step173_ratings")
    st.download_button("Download final 80-module ratings", matrix.to_csv(index=False).encode(), "step173_final_all_module_ratings.csv", "text/csv")

with module_tab:
    module_key = st.selectbox("Module", ALL_MODULES, format_func=lambda key: f"{FINAL_PROFILES[key].module_title} · {key}")
    row = matrix.loc[matrix["module_key"] == module_key].iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Internal software", f"{row['internal_software_rating']:.1f}/10")
    m2.metric("Native depth", f"{row['native_research_depth_rating']:.1f}/10")
    m3.metric("Framework", f"{row['qualification_framework_rating']:.1f}/10")
    m4.metric("Actual practical", f"{row['actual_practical_readiness_rating']:.2f}/10")
    insight_callout("Current stage", str(row["readiness_stage"]), tone="success" if row["controlled_release_eligible"] else "warning")
    st.markdown("**Remaining blockers**")
    st.write(row["remaining_blockers"] or "None")
    st.markdown("**Next executable actions**")
    for action in str(row["next_actions"]).split(" | "):
        st.write(f"- {action}")
    package = ROOT / "data" / "step173" / "module_packages" / module_key
    st.code(str(package), language="text")

with stages_tab:
    section_title("Portfolio readiness stages", "🚦")
    stage_summary = matrix.groupby("readiness_stage", dropna=False).agg(
        modules=("module_key", "count"),
        average_practical_rating=("actual_practical_readiness_rating", "mean"),
        blockers=("blocker_count", "sum"),
        controlled_release_eligible=("controlled_release_eligible", "sum"),
    ).reset_index()
    smart_dataframe(stage_summary, height=420, key="step173_stage_summary")
    st.caption("S0 means internally complete but external qualification has not started. S4 means every controlled-release gate has passed with genuine evidence.")

with execution_tab:
    section_title("Full qualification sequence", "⚙️")
    st.code(
        "RUN_STEP173_FULL_QUALIFICATION_WINDOWS.bat\n"
        "VERIFY_STEP173_WINDOWS.bat\n"
        "RUN_STEP173_RELEASE_DOCTOR_WINDOWS.bat",
        language="bat",
    )
    insight_callout(
        "External work remains a real-world activity",
        "The orchestration script executes every software-controlled check. It cannot manufacture patient cohorts, wet-lab measurements, site qualification, expert credentials or release committee decisions.",
        tone="warning",
    )

with governance_tab:
    section_title("Rating and claim policy", "🛡️")
    smart_dataframe(pd.DataFrame([
        {"Axis": "Internal software", "Maximum": 10.0, "Rule": "Source, tests, stability, UI, workflow, provenance and fail-closed controls"},
        {"Axis": "Native scientific depth", "Maximum": 10.0, "Rule": "Transparent local methods, QC, uncertainty and research outputs"},
        {"Axis": "Qualification framework", "Maximum": 10.0, "Rule": "Runtime, reference, model, cohort, evidence, expert and release verification"},
        {"Axis": "Actual practical readiness", "Maximum": 10.0, "Rule": "Only checksum-valid external artifacts and completed operating evidence increase this score"},
        {"Axis": "Controlled release", "Maximum": "Eligible/Blocked", "Rule": "Every required gate must pass; no averaging can override a failed gate"},
    ]), height=360, key="step173_rating_policy")
    status = registry.status()
    render_operational_canvas(
        "Registry integrity",
        status,
        workflow=("Audit chain", "Rating snapshots", "Evidence gates", "Release state"),
    )

with priority_tab:
    section_title("P0/P1 priority upgrade centre", "🧩")
    render_priority_upgrade_center(ROOT, key_prefix="step173_p0p1")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
