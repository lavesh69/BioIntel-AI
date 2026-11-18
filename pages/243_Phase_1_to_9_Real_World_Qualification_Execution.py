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

from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES  # noqa: E402
from biointel.realworld_v174 import (  # noqa: E402
    Step174ExecutionRegistry,
    automatic_environment_probe,
    phase_catalog,
    prepare_execution_workspace,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.operational_canvas import render_operational_canvas  # noqa: E402
from biointel.proof_gates_v10.ui import render_priority_upgrade_center  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.visual_polish import render_metric_board  # noqa: E402

st.set_page_config(page_title="Phase 1–9 Qualification Execution · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
registry = Step174ExecutionRegistry(ROOT)
matrix = registry.latest(refresh=False)
phases = phase_catalog()

hero(
    "Phase 1–9 Real-World Qualification Execution Center",
    "Execute and verify the final path from physical scientific environment through specialist engines, production references, authentic models and cohorts, independent benchmarks, wet-lab confirmation, expert approval, operating history and formal controlled release.",
    eyebrow="Step 174 · version 14.6.0 · external execution orchestration",
    chips=["9 executable phases", "80 module workspaces", "Evidence-bound", "No fabricated completion"],
)
scientific_boundary_banner(
    source_kind="real_world_qualification_execution",
    release_eligible=bool(matrix["controlled_release_eligible"].all()) if not matrix.empty else False,
    message=(
        "All software automation, schemas, workspaces and verification controls are complete at 10/10. "
        "Physical Windows/GPU/instrument tests, provider access, real cohorts, laboratory outcomes, expert identities and operating history must come from genuine execution."
    ),
)

registry_status = registry.status()
render_metric_board(
    [
        ("Automation ready", f"{int(matrix['all_phase_software_automation_available'].sum())}/80", "Available local execution controls.", "success"),
        ("External phases complete", f"{int(matrix['completed_phases'].sum())}/{int(matrix['required_phases'].sum())}", "Genuine external progress only.", "warning"),
        ("Average practical", f"{matrix['actual_practical_readiness_rating'].mean():.2f}/10", "Evidence-bound practical readiness.", "info"),
        ("Release eligible", f"{int(matrix['controlled_release_eligible'].sum())}/80", "Controlled release remains fail-closed.", "warning"),
        ("Audit chain", "PASS" if registry_status["audit_chain_valid"] else "REVIEW", "Local evidence-chain verification.", "success" if registry_status["audit_chain_valid"] else "danger"),
    ]
)

portfolio_tab, phase_tab, module_tab, workspace_tab, environment_tab, priority_tab = st.tabs([
    "Portfolio execution", "Nine phases", "Module work plan", "Evidence workspaces", "Environment probe", "P0/P1 priority upgrades"
])

with portfolio_tab:
    section_title("All-module Phase 1–9 matrix", "📊")
    smart_dataframe(matrix, height=700, key="step174_execution_matrix")
    st.download_button(
        "Download Phase 1–9 execution matrix",
        matrix.to_csv(index=False).encode(),
        "step174_phase1_to_9_execution_matrix.csv",
        "text/csv",
        width="stretch",
    )

with phase_tab:
    section_title("Ordered qualification phases", "🧭")
    smart_dataframe(phases, height=650, key="step174_phase_catalog")
    st.code(
        "RUN_STEP174_PHASE1_TO_9_WINDOWS.bat\n"
        "VERIFY_STEP174_WINDOWS.bat\n"
        "RUN_STEP174_RELEASE_DOCTOR_WINDOWS.bat",
        language="bat",
    )

with module_tab:
    module_key = st.selectbox("Module", ALL_MODULES, format_func=lambda key: f"{FINAL_PROFILES[key].module_title} · {key}")
    row = matrix.loc[matrix["module_key"] == module_key].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed phases", f"{row['completed_phases']}/{row['required_phases']}")
    c2.metric("Next phase", int(row["next_phase"]))
    c3.metric("Practical readiness", f"{row['actual_practical_readiness_rating']:.2f}/10")
    c4.metric("Release", "ELIGIBLE" if row["controlled_release_eligible"] else "BLOCKED")
    insight_callout("Next executable command", str(row["next_command"]), tone="success" if row["controlled_release_eligible"] else "warning")
    st.markdown("**Current phase blockers**")
    st.write(row["phase_blockers"] or "None")
    module_phase_rows = []
    for phase in range(1, 10):
        module_phase_rows.append({
            "Phase": phase,
            "Applicable": bool(row.get(f"phase_{phase}_applicable", True)),
            "Complete": bool(row[f"phase_{phase}_complete"]),
            "Title": phases.loc[phases["phase_number"] == phase, "title"].iloc[0],
        })
    smart_dataframe(pd.DataFrame(module_phase_rows), height=440, key="step174_module_phases")

with workspace_tab:
    section_title("Prepare evidence workspaces", "📁")
    selected = st.selectbox("Workspace module", ["ALL"] + list(ALL_MODULES), key="step174_workspace_module")
    force = st.checkbox("Refresh template files", value=False)
    if st.button("Prepare workspace", type="primary", width="stretch"):
        written = prepare_execution_workspace(ROOT, None if selected == "ALL" else selected, force=force)
        st.success(f"Prepared {len(written)} files. Existing evidence was preserved unless refresh was selected.")
    user_data = Path.cwd() / "UserData" / "step174" / "execution_workspaces"
    st.code(str(user_data), language="text")
    st.info("Template generation does not count as external evidence. Only genuine completed artifacts with matching hashes can advance the module.")

with environment_tab:
    section_title("Build-host automatic probe", "🖥️")
    probe = automatic_environment_probe(ROOT)
    render_operational_canvas(
        "Build-host probe",
        probe,
        workflow=("Operating system", "Runtime", "Storage", "Target qualification"),
    )
    insight_callout(
        "Target-machine boundary",
        "This probe describes the current build host only. Run RUN_STEP174_LOCAL_ENVIRONMENT_QUALIFICATION_WINDOWS.bat on every real Windows/GPU/instrument site.",
        tone="warning",
    )

with priority_tab:
    section_title("P0/P1 remediation and proof-gate queue", "🧩")
    render_priority_upgrade_center(ROOT, key_prefix="step174_p0p1")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
