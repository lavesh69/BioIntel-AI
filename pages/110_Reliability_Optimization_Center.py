from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.io.uploads import UploadReadError, read_uploaded_table_bytes
from biointel.stability_v145.cache import cache_registry_snapshot
from biointel.stability_v145.maintenance import run_overall_maintenance
from biointel.stability_v145.runtime import startup_preflight
from biointel.ui.performance import clear_ui_caches
from biointel.ui.workflow import render_upload_preflight, stage_streamlit_upload
from biointel.ui.runtime_guard import runtime_diagnostic_bundle, runtime_error_reports
from biointel.ui.theme import apply_theme, hero
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics
from biointel.utils.runtime_cache import clear_runtime_caches

st.set_page_config(page_title="Reliability & Optimization · BioIntel AI", page_icon="⚡", layout="wide")
apply_theme()
hero(
    "⚡ Reliability & Optimization Center",
    "Overall app stability, guarded startup, database maintenance, job recovery, upload protection and bounded caching in one place.",
    eyebrow="BioIntel AI Step 145 · Overall Stability",
    chips=["Guarded startup", "Database lock recovery", "Orphan job recovery", "Bounded caches"],
)

@st.cache_data(ttl=300, show_spinner=False)
def _quick_checks(root: str):
    return run_diagnostics(root, profile="quick")

checks = _quick_checks(str(ROOT))
summary = diagnostic_summary(checks)
user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or ROOT)
free = shutil.disk_usage(user_data if user_data.exists() else ROOT).free
model_files = tuple(sorted((ROOT / "models").glob("*.joblib")))
reports = runtime_error_reports(limit=25)

metrics = st.columns(5)
metrics[0].metric("Startup checks", summary["overall"])
metrics[1].metric("Dependencies", f"{summary['PASS']}/{len(checks)}")
metrics[2].metric("Local model files", len(model_files))
metrics[3].metric("Recent safe stops", len(reports))
metrics[4].metric("Free disk", f"{free / 1024**3:.1f} GB")

st.subheader("Overall app stability")

@st.cache_data(ttl=60, show_spinner=False)
def _step145_preflight(root_text: str) -> dict[str, object]:
    return startup_preflight(Path(root_text), clean_stale_temp=False)

stability = _step145_preflight(str(ROOT))
stability_metrics = st.columns(5)
stability_metrics[0].metric("Startup state", "PASS" if stability.get("passed") else "BLOCKED")
stability_metrics[1].metric("Blocking checks", len(stability.get("failures", [])))
stability_metrics[2].metric("Advisories", len(stability.get("warnings", [])))
stability_metrics[3].metric("Protected caches", len(cache_registry_snapshot()))
stability_metrics[4].metric("Temp files cleaned", int(stability.get("temp_cleanup", {}).get("removed_files", 0)))

if stability.get("failures"):
    st.error("Large analyses are blocked until the failed startup checks are repaired.")
    st.dataframe(pd.DataFrame(stability["failures"]), width="stretch", hide_index=True)
elif stability.get("warnings"):
    st.warning("The application is usable, but large workflows should be reviewed against these advisory checks.")
    st.dataframe(pd.DataFrame(stability["warnings"]), width="stretch", hide_index=True)
else:
    st.success("Startup, writable workspace, disk and memory guards are ready.")

maintenance_options = st.columns(4)
maintain_databases = maintenance_options[0].checkbox("Maintain databases", value=True)
recover_jobs = maintenance_options[1].checkbox("Recover stale jobs", value=True)
clear_caches = maintenance_options[2].checkbox("Clear bounded caches", value=True)
prune_logs = maintenance_options[3].checkbox("Prune old logs/temp", value=True)

if st.button("Run safe overall optimization", type="primary", width="stretch"):
    with st.spinner("Running protected maintenance across the application..."):
        try:
            maintenance = run_overall_maintenance(
                ROOT,
                database_maintenance=maintain_databases,
                recover_jobs=recover_jobs,
                clear_caches=clear_caches,
                prune_old_logs=prune_logs,
            )
        except Exception as exc:
            st.error(f"Overall maintenance stopped safely: {type(exc).__name__}: {exc}")
        else:
            st.session_state["step145_maintenance_result"] = maintenance
            _quick_checks.clear()
            _step145_preflight.clear()
            if maintenance.get("passed"):
                st.success("Overall app optimization completed successfully.")
            else:
                st.warning("Maintenance completed with one or more items requiring review.")

maintenance_result = st.session_state.get("step145_maintenance_result")
if isinstance(maintenance_result, dict):
    result_metrics = st.columns(5)
    result_metrics[0].metric("Databases passed", int(maintenance_result.get("databases", {}).get("passed_count", 0)))
    result_metrics[1].metric("Database failures", int(maintenance_result.get("databases", {}).get("failed_count", 0)))
    result_metrics[2].metric("Recovered jobs", int(maintenance_result.get("jobs", {}).get("recovered_jobs", 0)))
    result_metrics[3].metric("Caches cleared", int(maintenance_result.get("registered_caches_cleared", 0)))
    result_metrics[4].metric("Duration", f"{float(maintenance_result.get('duration_seconds', 0.0)):.2f}s")
    st.download_button(
        "Download Step 145 maintenance report",
        json.dumps(maintenance_result, indent=2, default=str).encode("utf-8"),
        "biointel_step145_overall_maintenance.json",
        "application/json",
        width="stretch",
    )

st.subheader("Universal upload validator")
st.caption("Validate CSV, TSV, TXT, gzip, Excel, ODS or a single-table ZIP before running a scientific workflow.")
uploaded = st.file_uploader(
    "Choose a table",
    type=["csv", "tsv", "txt", "tab", "maf", "gz", "xlsx", "xlsm", "xls", "ods", "zip"],
    key="step97_universal_upload_validator",
)
if uploaded is not None:
    allowed_extensions = ["csv", "tsv", "txt", "tab", "maf", "gz", "xlsx", "xlsm", "xls", "ods", "zip"]
    profile = render_upload_preflight(
        uploaded,
        key="step113_reliability_upload",
        allowed_extensions=allowed_extensions,
        soft_limit_mb=100,
        hard_limit_mb=1024,
        block_large_files=False,
        module_key="reliability_optimization",
    )
    if profile is not None and profile.size_mb > 100:
        st.warning(
            "This file is larger than the 100 MB interactive parsing boundary. It will be staged atomically for a background workflow instead of being copied into page memory."
        )
        if st.button("Stage large upload safely", type="primary", width="stretch"):
            try:
                stage_root = user_data / "workspace" / "staged_uploads"
                safe_name = Path(uploaded.name).name
                staged = stage_streamlit_upload(uploaded, stage_root / safe_name, max_bytes=1024**3)
                st.success(f"Staged {staged['size_bytes'] / 1024**2:.1f} MB safely.")
                st.code(json.dumps(staged, indent=2), language="json")
            except Exception as exc:
                st.error(f"Large-file staging failed: {exc}")
    elif profile is not None:
        try:
            payload = uploaded.getvalue()
            table = read_uploaded_table_bytes(
                payload, uploaded.name, max_rows=100_000, max_columns=1_000, max_cells=5_000_000
            )
        except UploadReadError as exc:
            st.error(str(exc))
        else:
            st.success(f"Upload validated: {table.frame.shape[0]:,} rows × {table.frame.shape[1]:,} columns")
            info = st.columns(4)
            info[0].metric("Format", table.detected_extension.lstrip(".").upper())
            info[1].metric("Encoding", table.encoding or "binary")
            info[2].metric("Delimiter", repr(table.separator) if table.separator else "n/a")
            info[3].metric("SHA-256", profile.sha256[:12] + "…")
            st.dataframe(table.frame.head(200), width="stretch", hide_index=True)
            st.download_button(
                "Download normalized preview CSV",
                table.frame.head(100_000).to_csv(index=False).encode("utf-8"),
                "biointel_validated_upload.csv",
                "text/csv",
                width="stretch",
            )

st.divider()
st.subheader("Runtime recovery")
left, middle, right = st.columns(3)
if left.button("Clear scientific file caches", width="stretch"):
    clear_runtime_caches()
    st.success("File caches cleared safely.")
if middle.button("Clear UI data/resource caches", width="stretch"):
    clear_ui_caches()
    st.success("Streamlit caches cleared safely.")
if right.button("Refresh startup checks", width="stretch"):
    _quick_checks.clear()
    st.rerun()

if reports:
    st.warning("Safe-stop reports are available. No project data is removed by the crash boundary.")
    st.dataframe(
        pd.DataFrame(
            {
                "Reference": item.get("error_id"),
                "Time UTC": item.get("timestamp_utc"),
                "Context": item.get("context"),
                "Type": item.get("exception_type"),
            }
            for item in reports
        ),
        width="stretch",
        hide_index=True,
    )
else:
    st.success("No runtime safe-stop reports are present.")

st.download_button(
    "Download support diagnostics",
    runtime_diagnostic_bundle(limit=100),
    "biointel_step113_support_diagnostics.json",
    "application/json",
    width="stretch",
)

with st.expander("Startup check detail"):
    st.dataframe(pd.DataFrame([item.to_dict() for item in checks]), width="stretch", hide_index=True)

st.info(
    "Large analyses remain run-on-demand. Uploaded files are parsed with size, encoding, archive-path, column and cell-count guards before model execution."
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
