from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.environment_v175 import (  # noqa: E402
    Step175Registry,
    automatic_host_probe,
    engine_execution_catalog,
    environment_groups,
    environment_summary,
    execution_matrix,
    reference_execution_catalog,
    target_profiles,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.operational_canvas import render_operational_canvas  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.visual_polish import render_metric_board  # noqa: E402

st.set_page_config(page_title="Target Environment Qualification · BioIntel AI", page_icon="◆", layout="wide")
apply_theme()
summary = environment_summary(ROOT)
matrix = execution_matrix(ROOT)
registry = Step175Registry(ROOT)

hero(
    "Target Environment, Engine & Reference Qualification",
    "Provision and qualify the physical Windows/WSL2/GPU environment, 53 specialist scientific engines and 26 production reference groups with transactional installation, resume, rollback, licence capture and checksum-bound verification.",
    eyebrow="Step 175 · version 14.7.0 · operational scientific environment",
    chips=["53 engines", "26 references", "12 isolated environments", "Fail-closed"],
)
scientific_boundary_banner(
    source_kind="target_environment_qualification",
    release_eligible=bool(summary["controlled_environment_ready"]),
    message=(
        "The installation and qualification framework is complete at 10/10. Actual qualification requires execution on the target Windows/WSL2/GPU machine, "
        "provider-authorized downloads, captured licence text, executable/reference hashes and completed integration checks."
    ),
)

environment_ready = bool(summary["controlled_environment_ready"])
render_metric_board(
    [
        ("Framework", "10/10", "Local qualification framework coverage.", "success"),
        ("Qualified hosts", summary["target_hosts_qualified"], "Verified target-host records.", "info"),
        ("Engines target-qualified", f"{summary['engines_target_qualified']}/53", "Requires actual target-machine execution.", "warning"),
        ("References target-qualified", f"{summary['references_target_qualified']}/26", "Requires authorised reference acquisition.", "warning"),
        ("Environment", "READY" if environment_ready else "BLOCKED", "Controlled environment state.", "success" if environment_ready else "danger"),
    ]
)

overview, engines_tab, refs_tab, groups_tab, host_tab, commands_tab = st.tabs([
    "Execution matrix", "Engines", "References", "Environment groups", "Host qualification", "Windows commands"
])

with overview:
    section_title("Combined installation and qualification matrix", "📊")
    smart_dataframe(matrix, height=700, key="step175_execution_matrix")
    st.download_button("Download matrix", matrix.to_csv(index=False).encode(), "step175_target_environment_matrix.csv", "text/csv", width="stretch")

with engines_tab:
    engines = engine_execution_catalog()
    section_title("53 specialist engines", "🧬")
    smart_dataframe(engines, height=700, key="step175_engine_catalog")
    st.caption("Automatic installation eligibility does not bypass licence review, golden fixtures, negative controls or native module integration.")

with refs_tab:
    refs = reference_execution_catalog()
    section_title("26 production reference groups", "🗄️")
    smart_dataframe(refs, height=700, key="step175_reference_catalog")
    st.metric("Approximate complete storage", f"{refs['approximate_size_gb'].sum():,.1f} GB")

with groups_tab:
    section_title("Isolated runtime environments", "🧩")
    smart_dataframe(environment_groups(), height=600, key="step175_environment_groups")
    section_title("Target profiles", "🖥️")
    smart_dataframe(target_profiles(), height=360, key="step175_target_profiles")

with host_tab:
    section_title("Current build-host probe", "🔍")
    render_operational_canvas(
        "Build-host probe",
        automatic_host_probe(ROOT),
        workflow=("System scan", "Runtime checks", "Storage checks", "Target handoff"),
    )
    render_operational_canvas(
        "Qualification registry",
        registry.status(),
        workflow=("Inventory", "Verification", "Evidence state", "Qualification decision"),
    )
    insight_callout(
        "Physical target boundary",
        "Run the Step 175 PowerShell workflow on every actual Windows/GPU site. A Linux build host cannot certify Windows drivers, WSL2, antivirus, sleep/resume or instrument connectivity.",
        tone="warning",
    )

with commands_tab:
    section_title("Execution commands", "▶")
    st.code(
        "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat\n"
        "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat --execute-open\n"
        "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat --resume\n"
        "VERIFY_STEP175_WINDOWS.bat\n"
        "RUN_STEP175_RELEASE_DOCTOR_WINDOWS.bat",
        language="bat",
    )
    st.info("Default mode is planning only. Restricted licences, provider credentials and manual distributions are never silently accepted or stored.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
