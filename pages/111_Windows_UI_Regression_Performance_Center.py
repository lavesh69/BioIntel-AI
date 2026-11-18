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

from biointel.jobs.local_queue import LocalJobQueue
from biointel.step101.performance import PerformanceRegistry, audit_ui_source, process_memory_mb, release_memory
from biointel.step101.ui_regression import discover_pages, run_ui_regression
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Windows UI Regression & Performance · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()
hero(
    "Windows UI Regression & Performance Center",
    "Audit every Streamlit page, run AppTest interaction smoke checks, export machine-readable failure reports and profile UI structure without freezing the workspace.",
    eyebrow="BioIntel AI 10.1 · UI Qualification",
    chips=["All-page audit", "AppTest", "Performance budget", "Failure artifacts", "Background execution"],
)

pages = discover_pages(ROOT)
registry = PerformanceRegistry(ROOT / "reports" / "performance.sqlite3")
queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
audit = audit_ui_source(ROOT)
metric_cards(
    [
        ("Pages", len(pages), "Home plus multipage screens"),
        ("Pages using cache", audit["cached_pages"], None),
        ("Forms", audit["forms"], "Reduced rerun risk"),
        ("Upload controls", audit["uploaders"], None),
        ("UI process RAM", f"{process_memory_mb():.1f} MB", None),
    ]
)

run_tab, audit_tab, results_tab, budget_tab = st.tabs(["Run regression", "Static performance audit", "Results", "Performance budget"])
with run_tab:
    with st.form("step101_ui_regression"):
        mode = st.selectbox("Regression mode", ["static", "apptest", "full"], index=0)
        selected = st.multiselect("Pages (empty = all pages)", [page.name for page in pages])
        timeout = st.slider("Timeout per page (seconds)", 5, 120, 30)
        execution = st.radio("Execution", ["Run now", "Queue in background"], horizontal=True)
        submitted = st.form_submit_button("Run UI regression", type="primary", width="stretch")
    if submitted:
        if execution == "Queue in background":
            record = queue.submit(
                "ui_regression_run",
                {"mode": mode, "selected_pages": selected, "timeout_seconds": timeout},
                stages=["discover", "compile", "apptest", "report"],
                resources={"cpu_threads": 2, "ram_gb": 4, "gpu_required": False},
                estimated_seconds=max(30, len(selected or pages) * timeout / 3),
            )
            st.success(f"Regression queued as {record.job_id}.")
        else:
            with st.spinner("Running UI regression checks…"):
                result = run_ui_regression(ROOT, mode=mode, selected_pages=selected or None, timeout_seconds=timeout)
            st.session_state["step101_ui_regression_result"] = result
            if result["failed"]:
                st.error(f"Regression completed with {result['failed']} failed check(s).")
            else:
                st.success(f"Regression passed: {result['passed']}/{result['checks']} checks.")

with audit_tab:
    frame = pd.DataFrame(audit["pages"])
    if not frame.empty:
        st.plotly_chart(px.scatter(frame, x="lines", y="dataframes", hover_name="page", size="uploaders", title="Page complexity and table usage"), width="stretch")
        smart_dataframe(frame, height=560, key="step101_static_ui_audit")
        st.download_button("Export UI audit CSV", frame.to_csv(index=False).encode("utf-8-sig"), "biointel_ui_performance_audit.csv", "text/csv", width="stretch")

with results_tab:
    result = st.session_state.get("step101_ui_regression_result")
    report_dir = ROOT / "reports" / "ui_regression"
    reports = sorted(report_dir.glob("ui-regression-*.json"), reverse=True) if report_dir.exists() else []
    if result is None and reports:
        result = json.loads(reports[0].read_text(encoding="utf-8"))
    if result is None:
        st.info("No UI regression report is available yet.")
    else:
        metric_cards([("Passed", result["passed"], None), ("Failed", result["failed"], None), ("Warnings", result["warnings"], None), ("Checks", result["checks"], None)])
        smart_dataframe(pd.DataFrame(result["results"]), height=600, key="step101_ui_results")
        smart_json(result.get("artifacts", {}), title="Report artifacts")

with budget_tab:
    section_title("Recommended runtime budgets", "⏱️")
    budgets = pd.DataFrame(
        [
            {"Operation": "Initial page shell", "Target": "< 2.0 s", "Action": "Cache static metadata and defer heavy scans"},
            {"Operation": "Normal control interaction", "Target": "< 300 ms", "Action": "Use forms and debounced actions"},
            {"Operation": "Table preview", "Target": "< 1.5 s", "Action": "Bound rows and columns"},
            {"Operation": "Large scientific run", "Target": "No UI blocking", "Action": "Queue in background engine"},
            {"Operation": "Reference verification", "Target": "Checkpointed", "Action": "Background hash and index jobs"},
        ]
    )
    st.dataframe(budgets, width="stretch", hide_index=True)
    events = pd.DataFrame(registry.recent(500))
    if not events.empty:
        st.plotly_chart(px.box(events, x="component", y="duration_ms", points="outliers", title="Measured operation durations"), width="stretch")
    if st.button("Release unused UI memory", width="stretch"):
        st.success(f"Released {release_memory()} object(s).")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
