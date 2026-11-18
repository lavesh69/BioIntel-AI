from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.dti.feature_cache import FeatureCache
from biointel.jobs.local_queue import LocalJobQueue
from biointel.step101.background import BackgroundJobService
from biointel.step101.performance import PerformanceRegistry, process_memory_mb, release_memory
from biointel.ui.components import filterable_dataframe, metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import analysis_run

st.set_page_config(page_title="Background Jobs & Performance · BioIntel AI", page_icon="⚙️", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('background_jobs_core', expanded=False)
hero(
    "Real Background Job Engine",
    "Run long scientific tasks outside Streamlit reruns with a persistent worker, pause/resume, checkpoints, retries, dependencies, artifacts, recovery and resource requests.",
    eyebrow="BioIntel AI 10.1 · Persistent Execution",
    chips=["Independent worker", "Pause/resume", "Crash recovery", "ETA", "Resource requests", "Artifacts"],
)
scientific_boundary_banner(
    source_kind="operational",
    release_eligible=False,
    message="A completed compute job is not automatically a scientifically validated result. Evidence and release gates remain independent.",
)

queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
cache = FeatureCache(ROOT / "reports" / "feature_cache.sqlite3")
performance = PerformanceRegistry(ROOT / "reports" / "performance.sqlite3")
service = BackgroundJobService(ROOT, python_executable=sys.executable)
service_state = service.status()
summary = queue.orchestration_summary()
cache_stats = cache.stats()

metric_cards(
    [
        ("Worker", "Running" if service_state.running else "Stopped", f"PID {service_state.pid}" if service_state.running else "Start from this page or app launcher"),
        ("Queued", summary["statuses"].get("queued", 0), None),
        ("Running", summary["statuses"].get("running", 0), None),
        ("Paused", summary["statuses"].get("paused", 0), None),
        ("Artifacts", summary["artifacts"], "Checksum-bound job outputs"),
        ("Process RAM", f"{process_memory_mb():.1f} MB", "Current UI process"),
    ]
)

service_tab, submit_tab, portfolio_tab, timeline_tab, performance_tab = st.tabs(
    ["Worker service", "Submit job", "Job portfolio", "Timeline & control", "Performance"]
)

with service_tab:
    st.subheader("Persistent worker service")
    smart_json(asdict(service_state), title="Background worker service")
    cols = st.columns(4)
    if cols[0].button("Start worker", type="primary", disabled=service_state.running, width="stretch"):
        with st.spinner("Starting persistent worker…"):
            state = service.start()
        st.success(f"Worker started with PID {state.pid}.")
        st.rerun()
    if cols[1].button("Stop worker", disabled=not service_state.running, width="stretch"):
        with st.spinner("Stopping worker safely…"):
            service.stop()
        st.success("Worker stopped. Running jobs will be recovered from their last checkpoint.")
        st.rerun()
    if cols[2].button("Restart worker", width="stretch"):
        with st.spinner("Restarting worker…"):
            service.restart()
        st.success("Worker restarted.")
        st.rerun()
    if cols[3].button("Recover stale jobs", width="stretch"):
        result = service.recover()
        st.success(f"Recovered {result['recovered']} stale running job(s).")
        st.rerun()
    workers = pd.DataFrame(queue.workers())
    if workers.empty:
        st.info("No worker heartbeat has been recorded yet.")
    else:
        smart_dataframe(workers, height=360, key="step101_workers")

with submit_tab:
    section_title("Submit a background task", "➕")
    supported = {
        "System diagnostics": "system_diagnostics",
        "Database optimization": "database_optimize",
        "ChEMBL scientific sync": "scientific_sync_chembl",
        "UniProt scientific sync": "scientific_sync_uniprot",
        "UI regression suite": "ui_regression_run",
        "UI performance audit": "ui_performance_audit",
        "Unified scientific report": "unified_report_generate",
        "Reference asset verification": "reference_asset_verify",
        "Discovery batch triage": "discovery_batch_triage",
    }
    existing = queue.list(limit=500)
    with st.form("step101_submit_job"):
        left, middle, right = st.columns(3)
        label = left.selectbox("Job type", list(supported))
        priority = middle.number_input("Priority", 1, 10_000, 100, help="Lower values run first.")
        max_attempts = right.number_input("Maximum attempts", 1, 10, 3)
        cpu, ram, gpu = st.columns(3)
        cpu_count = cpu.number_input("Requested CPU threads", 1, 128, 2)
        ram_gb = ram.number_input("Requested RAM (GB)", 1, 1024, 4)
        gpu_required = gpu.checkbox("GPU required", value=False)
        dependency_ids = st.multiselect(
            "Dependencies",
            [job.job_id for job in existing],
            format_func=lambda value: next((f"{j.job_type} · {j.status} · {value[-8:]}" for j in existing if j.job_id == value), value),
        )
        estimated = st.number_input("Initial ETA estimate (seconds)", 0, 7 * 24 * 3600, 60)
        payload_text = st.text_area(
            "Payload JSON",
            value=json.dumps({"mode": "static", "title": "BioIntel AI Unified Scientific Report"}, indent=2),
            height=180,
        )
        submitted = st.form_submit_button("Submit to background engine", type="primary", width="stretch")
    if submitted:
        try:
            payload = json.loads(payload_text or "{}")
            record = queue.submit(
                supported[label],
                payload,
                priority=int(priority),
                max_attempts=int(max_attempts),
                dependencies=dependency_ids,
                stages=["prepare", "execute", "validate", "finalize"],
                resources={"cpu_threads": int(cpu_count), "ram_gb": int(ram_gb), "gpu_required": bool(gpu_required)},
                estimated_seconds=float(estimated) if estimated else None,
            )
        except Exception as exc:
            st.error(f"Job submission failed: {exc}")
        else:
            st.success(f"Submitted {record.job_id}. Status: {record.status}.")
            if not service.status().running:
                st.warning("The worker is stopped. Start it from the Worker service tab.")
            st.rerun()

with portfolio_tab:
    jobs = queue.list(limit=2000)
    frame = pd.DataFrame([asdict(job) for job in jobs])
    if frame.empty:
        st.info("No persistent jobs are available.")
    else:
        counts = frame.groupby("status").size().reset_index(name="jobs")
        st.plotly_chart(px.bar(counts, x="status", y="jobs", text="jobs", title="Persistent queue status"), width="stretch")
        display = frame.copy()
        display["resources"] = display["resources"].map(lambda value: json.dumps(value or {}, sort_keys=True))
        display["checkpoint"] = display["checkpoint"].map(lambda value: json.dumps(value or {}, sort_keys=True))
        filterable_dataframe(
            display,
            key="step101_job_portfolio",
            search_columns=["job_id", "job_type", "status", "current_stage", "worker_id"],
            status_column="status",
            height=560,
        )
        st.download_button("Export queue CSV", display.to_csv(index=False).encode("utf-8-sig"), "biointel_background_jobs.csv", "text/csv", width="stretch")

with timeline_tab:
    jobs = queue.list(limit=2000)
    if not jobs:
        st.info("No job timeline is available.")
    else:
        lookup = {job.job_id: job for job in jobs}
        selected = st.selectbox(
            "Job",
            list(lookup),
            format_func=lambda value: f"{lookup[value].job_type} · {lookup[value].status} · {value[-8:]}",
        )
        timeline = queue.timeline(selected)
        job = timeline["job"]
        metric_cards(
            [
                ("Status", job["status"], None),
                ("Progress", f"{job['progress_percent']:.1f}%", None),
                ("Stage", job.get("current_stage") or "Not started", None),
                ("ETA", f"{job.get('estimated_seconds', 0):.0f}s" if job.get("estimated_seconds") is not None else "Unknown", None),
                ("Attempts", f"{job['attempts']}/{job['max_attempts']}", None),
                ("Worker", job.get("worker_id") or "Unassigned", None),
            ]
        )
        actions = st.columns(5)
        if actions[0].button("Pause", disabled=job["status"] not in {"queued", "blocked", "running"}, width="stretch"):
            queue.request_pause(selected)
            st.rerun()
        if actions[1].button("Resume", disabled=job["status"] != "paused", width="stretch"):
            queue.resume(selected)
            st.rerun()
        if actions[2].button("Cancel", disabled=job["status"] in {"completed", "cancelled", "failed"}, width="stretch"):
            queue.request_cancel(selected)
            st.rerun()
        if actions[3].button("Retry", disabled=job["status"] not in {"failed", "cancelled"}, width="stretch"):
            queue.retry(selected)
            st.rerun()
        if actions[4].button("Refresh", width="stretch"):
            st.rerun()
        tabs = st.tabs(["Events", "Stages", "Dependencies", "Artifacts", "Payload", "Checkpoint"])
        for index, key in enumerate(["events", "stages", "dependencies", "artifacts"]):
            with tabs[index]:
                smart_dataframe(pd.DataFrame(timeline[key]), height=420, key=f"step101_{key}_{selected}")
        with tabs[4]:
            smart_json(job.get("payload", {}), title="Payload")
        with tabs[5]:
            smart_json(job.get("checkpoint", {}), title="Checkpoint")

with performance_tab:
    perf_summary = performance.summary()
    recent = pd.DataFrame(performance.recent(limit=1000))
    metric_cards(
        [
            ("Profiler events", perf_summary["event_count"], None),
            ("Cache entries", cache_stats.entries, None),
            ("Cache hits", cache_stats.total_hits, None),
            ("Cache size", f"{cache_stats.total_bytes / 1024**2:.2f} MB", None),
        ]
    )
    if not recent.empty:
        by_component = recent.groupby("component", as_index=False)["duration_ms"].mean().sort_values("duration_ms", ascending=False)
        st.plotly_chart(px.bar(by_component, x="duration_ms", y="component", orientation="h", title="Average measured operation time"), width="stretch")
        smart_dataframe(recent, height=480, key="step101_performance_events")
    else:
        st.info("Performance events will appear as optimized operations run.")
    cols = st.columns(2)
    if cols[0].button("Release unused Python memory", width="stretch"):
        st.success(f"Garbage collector released {release_memory()} object(s).")
    if cols[1].button("Prune feature cache", width="stretch"):
        with analysis_run("Pruning stale feature cache"):
            removed = cache.prune(older_than_days=90, max_entries=100_000)
        st.success(f"Removed {removed} stale cache entries.")

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("background_jobs_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("background_jobs_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("background_jobs_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('background_jobs_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('background_jobs_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('background_jobs_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('background_jobs_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('background_jobs_core', expanded=False)

