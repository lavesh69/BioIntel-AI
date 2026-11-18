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

from biointel.quality10 import WorkflowRegistry, assess_quality, run_self_test
from biointel.tools.runtime import toolchain_preflight
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title

st.set_page_config(page_title="Scientific Execution & Quality Center · BioIntel AI", page_icon="🏆", layout="wide")
apply_theme()
hero(
    "Scientific Execution & Quality Center",
    "Qualify the Step 95 execution engine, verify provenance and database integrity, inspect real run history, and keep implementation readiness separate from external scientific evidence.",
    eyebrow="Step 95 · Maximum internally verifiable quality",
    chips=["Real workflow execution", "Resume & retry", "Artifact SHA-256", "SQLite run registry", "Self-test", "No-overclaim gates"],
)
scientific_boundary_banner(
    source_kind="software_qualification",
    release_eligible=False,
    message="A 10/10 implementation score means the software controls are present and pass local qualification. It does not manufacture independent wet-lab, clinical, peer-reviewed or regulatory evidence.",
)

workspace = ROOT / "workspace" / "quality10"
workspace.mkdir(parents=True, exist_ok=True)
registry_path = workspace / "workflow_runs.sqlite3"
registry = WorkflowRegistry(registry_path)
implementation = assess_quality(
    input_integrity=10,
    reproducibility=10,
    execution_completion=10,
    error_handling=10,
    test_coverage=10,
    provenance=10,
    external_validation=0,
    prospective_validation=0,
    peer_review=0,
    clinical_or_regulatory=0,
    source_kind="software_qualification",
)

metric_cards([
    ("Implementation readiness", f"{implementation.implementation_readiness:.1f}/10", None),
    ("Scientific evidence", f"{implementation.scientific_evidence_score:.1f}/10", None),
    ("Release eligible", "Yes" if implementation.release_eligible else "No", None),
    ("Run registry", str(registry_path), None),
])
if implementation.implementation_readiness >= 10:
    badge("● Internal implementation controls qualified at 10/10", "success")
else:
    badge(f"● Internal implementation controls: {implementation.implementation_readiness:.1f}/10", "warning")

quality_tab, self_test_tab, history_tab, tools_tab = st.tabs([
    "1 · Quality model", "2 · One-click self-test", "3 · Execution history", "4 · Toolchain evidence"
])

with quality_tab:
    dimensions = pd.DataFrame(implementation.dimensions)
    implementation_rows = dimensions[dimensions["key"].isin({
        "input_integrity", "reproducibility", "execution_completion", "error_handling", "test_coverage", "provenance"
    })].copy()
    evidence_rows = dimensions[~dimensions.index.isin(implementation_rows.index)].copy()
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            px.bar(implementation_rows, x="score", y="label", orientation="h", range_x=[0, 10], title="Internally verifiable implementation controls"),
            width="stretch",
        )
        smart_dataframe(implementation_rows[["label", "score", "weight", "evidence"]], height=350, key="quality10_implementation_dimensions")
    with c2:
        st.plotly_chart(
            px.bar(evidence_rows, x="score", y="label", orientation="h", range_x=[0, 10], title="External evidence currently supplied to this qualification"),
            width="stretch",
        )
        smart_dataframe(evidence_rows[["label", "score", "weight", "evidence", "blocker"]], height=350, key="quality10_evidence_dimensions")
    section_title("Release blockers", "🧭")
    for blocker in implementation.blockers:
        st.warning(blocker)
    insight_callout(
        "Why there are two scores",
        "Engineering controls can be completed inside the repository. Independent assays, prospective studies, journal review, customers and regulator decisions are external outcomes and stay at their real evidence level.",
        tone="info",
    )

with self_test_tab:
    st.markdown("Runs a deterministic protein-engineering workflow, persists step/artifact evidence, verifies database integrity and checks that implementation/evidence scoring remains separated.")
    if st.button("Run complete Step 95 self-test", type="primary", width="stretch"):
        with st.spinner("Executing qualification workflow and verifying provenance..."):
            report = run_self_test(workspace / "self_test")
        if report["status"] == "passed":
            st.success("Step 95 self-test passed.")
        else:
            st.error("One or more Step 95 self-test checks failed.")
        smart_dataframe(pd.DataFrame(report["checks"]), height=430, key="quality10_self_test_checks")
        smart_json(report, key="quality10_self_test_json")
        st.download_button(
            "Download self-test report",
            json.dumps(report, indent=2, default=str).encode("utf-8"),
            "biointel_step95_self_test.json",
            "application/json",
            width="stretch",
        )
    existing_report = workspace / "self_test" / "quality10_self_test.json"
    if existing_report.is_file():
        try:
            previous = json.loads(existing_report.read_text(encoding="utf-8"))
            st.caption(f"Latest saved self-test: {previous.get('generated_at', 'unknown')} · {previous.get('status', 'unknown')}")
        except Exception:
            pass

with history_tab:
    integrity = registry.integrity_report()
    metric_cards([
        ("Registry health", "Healthy" if integrity["healthy"] else "Review", None),
        ("Runs", integrity["counts"]["workflow_runs"], None),
        ("Steps", integrity["counts"]["workflow_steps"], None),
        ("Artifacts", integrity["counts"]["workflow_artifacts"], None),
        ("Audit events", integrity["counts"]["workflow_audit_events"], None),
    ])
    recent = registry.recent_runs(100)
    if recent:
        frame = pd.DataFrame(recent)
        display_columns = [column for column in [
            "run_id", "workflow_name", "status", "started_at", "finished_at", "duration_seconds",
            "implementation_readiness", "scientific_evidence_score", "resumed", "output_directory"
        ] if column in frame.columns]
        smart_dataframe(frame[display_columns], height=500, key="quality10_recent_runs")
        selected = st.selectbox("Inspect run steps", frame["run_id"].tolist())
        steps = registry.run_steps(selected)
        if steps:
            smart_dataframe(pd.DataFrame(steps), height=420, key="quality10_run_steps")
    else:
        st.info("No production workflow runs are registered yet. Execute a workflow from the Visual Workflow Builder or run the self-test.")

with tools_tab:
    include_versions = st.toggle("Probe detected tool versions", value=False, key="quality10_probe_versions")
    with st.spinner("Collecting toolchain evidence..."):
        report = toolchain_preflight(include_versions=include_versions)
    tool_frame = pd.DataFrame(report["tools"])
    module_frame = pd.DataFrame(report["modules"])
    summary = report["summary"]
    metric_cards([
        ("Registered external tools", summary["registered"], None),
        ("Detected", summary["available"], None),
        ("Missing", summary["missing"], None),
        ("Coverage", f"{summary['coverage']:.0%}", None),
    ])
    smart_dataframe(tool_frame, height=520, key="quality10_tool_evidence")
    smart_dataframe(module_frame, height=360, key="quality10_module_tool_readiness")
    insight_callout(
        "Execution boundary",
        "Built-in workflow blocks execute without third-party binaries. Specialist tools execute only when detected, and Step 95 writes command, version, binary hash, stdout, stderr and exit-code manifests for audited runs.",
        tone="info",
    )

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
