from __future__ import annotations

import platform
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.integrations.cache import ExternalResponseCache
from biointel.integrations.http_client import (
    DEFAULT_CACHE_DIRECTORY,
    DEFAULT_CACHE_TTL_SECONDS,
)
from biointel.intelligence.data_intelligence import (
    all_database_health,
    optimize_all_databases,
)
from biointel.training.model_artifact import (
    clear_model_artifact_cache,
    model_artifact_cache_info,
)
from biointel.ui.components import smart_dataframe
from biointel.ui.performance import clear_ui_caches
from biointel.ui.runtime_guard import runtime_diagnostic_bundle, runtime_error_reports
from biointel.ui.theme import apply_theme, hero
from biointel.utils.diagnostics import (
    diagnostic_summary,
    run_diagnostics,
)
from biointel.utils.integrity_cache import clear_integrity_cache
from biointel.utils.runtime_cache import (
    clear_runtime_caches,
    runtime_cache_info,
)
from biointel.utils.structured_integrity import scan_structured_assets

st.set_page_config(
    page_title="System Diagnostics · BioIntel AI",
    page_icon="🩺",
    layout="wide",
)

apply_theme()
hero(
    "🩺 System Diagnostics & Offline Cache",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption(
    "Check dependencies, model compatibility, writable folders "
    "and cached scientific-database responses."
)


@st.cache_data(ttl=300, show_spinner=False)
def _quick_diagnostics(root_text: str):
    return run_diagnostics(root_text, profile="quick")


@st.cache_data(ttl=300, show_spinner=False)
def _database_health(root_text: str):
    return all_database_health(root_text)


if st.button("Run full diagnostics", type="primary"):
    with st.spinner("Running complete dependency, model, data and database checks…"):
        st.session_state["diagnostic_checks"] = run_diagnostics(ROOT, profile="full")
        st.session_state["diagnostic_profile"] = "full"

if "diagnostic_checks" not in st.session_state:
    st.session_state["diagnostic_checks"] = _quick_diagnostics(str(ROOT))
    st.session_state["diagnostic_profile"] = "quick"
checks = st.session_state["diagnostic_checks"]
st.caption(
    f"Active diagnostic profile: {st.session_state.get('diagnostic_profile', 'quick').title()}"
)
summary = diagnostic_summary(checks)

columns = st.columns(4)
columns[0].metric("Overall", summary["overall"])
columns[1].metric("Passed", summary["PASS"])
columns[2].metric("Warnings", summary["WARN"])
columns[3].metric("Failed", summary["FAIL"])

diagnostic_table = pd.DataFrame([check.to_dict() for check in checks])
smart_dataframe(diagnostic_table, height=420, key="diagnostic_checks_table")

if summary["FAIL"]:
    if platform.system() == "Windows":
        st.error(
            "One or more checks failed. Run REPAIR_WINDOWS.bat "
            "from the extracted project folder."
        )
    else:
        st.warning(
            "One or more Windows-targeted checks are unavailable in this source/build environment. "
            "Review the diagnostic table; installed Windows runs can use DIAGNOSE_WINDOWS.bat and REPAIR_WINDOWS.bat."
        )
elif summary["WARN"]:
    st.warning("The application can run, but one or more optional checks need attention.")
else:
    st.success("All diagnostic checks passed.")

st.divider()
st.subheader("Structured asset integrity")
st.caption("Validate JSON, YAML, CSV/TSV, SQLite and ZIP assets without loading large files into the UI.")
if st.button("Scan structured assets", width="stretch", key="scan_structured_assets"):
    with st.spinner("Checking structured assets and archive integrity…"):
        st.session_state["structured_asset_scan"] = scan_structured_assets(ROOT)
asset_scan = st.session_state.get("structured_asset_scan")
if asset_scan:
    asset_columns = st.columns(3)
    asset_columns[0].metric("Checked", asset_scan["checked"])
    asset_columns[1].metric("Passed", asset_scan["passed"])
    asset_columns[2].metric("Failed", asset_scan["failed"])
    if asset_scan["failed"]:
        st.error("One or more structured assets need repair.")
        smart_dataframe(pd.DataFrame(asset_scan["failures"]), height=320, key="structured_asset_failures")
    else:
        st.success("All scanned structured assets passed parsing and integrity checks.")

st.divider()
st.subheader("Professional database fabric")
database_health = _database_health(str(ROOT))
db_columns = st.columns(4)
db_columns[0].metric(
    "Databases",
    database_health["database_count"],
)
db_columns[1].metric(
    "Healthy",
    database_health["healthy_count"],
)
db_columns[2].metric(
    "Indexed rows",
    f"{database_health['total_rows']:,}",
)
db_columns[3].metric(
    "Indices",
    database_health["total_indices"],
)

database_rows = []
for key, item in database_health["databases"].items():
    database_rows.append(
        {
            "Database": key.title(),
            "Integrity": item["integrity"],
            "Journal": item["journal_mode"],
            "Tables": item["table_count"],
            "Indices": item["index_count"],
            "Rows": item["row_count"],
            "Size MB": round(
                item["size_bytes"] / (1024 * 1024),
                3,
            ),
        }
    )
smart_dataframe(pd.DataFrame(database_rows), height=460, key="database_health_table")

database_actions = st.columns(2)
vacuum_databases = database_actions[0].checkbox(
    "Compact with VACUUM",
    value=False,
)
if database_actions[1].button(
    "Optimize all databases",
    width="stretch",
):
    result = optimize_all_databases(
        ROOT,
        vacuum=vacuum_databases,
    )
    _database_health.clear()
    _quick_diagnostics.clear()
    st.session_state.pop("diagnostic_checks", None)
    st.success(f"Optimized {len(result['results'])} database systems.")
    st.rerun()

st.divider()
st.subheader("External database offline cache")

cache = ExternalResponseCache(DEFAULT_CACHE_DIRECTORY)
entries = cache.list_entries()
cache_columns = st.columns(3)
cache_columns[0].metric("Cached responses", len(entries))
cache_columns[1].metric(
    "Cache size",
    f"{cache.total_size_bytes() / 1024:.1f} KB",
)
cache_columns[2].metric(
    "Default freshness",
    f"{DEFAULT_CACHE_TTL_SECONDS // 3600} hours",
)

if entries:
    cache_table = pd.DataFrame(
        [
            {
                "URL": entry.url,
                "Content type": entry.content_type,
                "Size KB": round(entry.size_bytes / 1024, 2),
                "Age hours": round(
                    entry.age_seconds() / 3600,
                    2,
                ),
                "Fresh": entry.is_fresh(DEFAULT_CACHE_TTL_SECONDS),
            }
            for entry in entries
        ]
    )
    smart_dataframe(cache_table, height=360, key="external_cache_table")
else:
    st.info("No cached UniProt or ChEMBL responses are available yet.")

cache_left, cache_right = st.columns(2)
if cache_left.button(
    "Remove expired cache entries",
    width="stretch",
):
    removed = cache.remove_expired(DEFAULT_CACHE_TTL_SECONDS)
    st.success(f"Removed {removed} expired cache entries.")
    st.rerun()

confirm_clear = cache_right.checkbox(
    "Confirm complete cache clear",
    key="confirm_cache_clear",
)
if cache_right.button(
    "Clear entire external cache",
    disabled=not confirm_clear,
    width="stretch",
):
    removed_files = cache.clear()
    st.success(f"Removed {removed_files} cache files.")
    st.rerun()

st.info(
    "When UniProt or ChEMBL is temporarily unavailable, BioIntel can "
    "use a previously cached response. Cached records should still be "
    "verified before scientific use."
)


st.divider()
st.subheader("Runtime optimization caches")
file_cache = runtime_cache_info()
model_cache = model_artifact_cache_info()
cache_stats = pd.DataFrame(
    [{"Cache": name, **values} for name, values in file_cache.items()]
    + [{"Cache": "models", **model_cache}]
)
smart_dataframe(cache_stats, height=260, key="runtime_cache_table")

cache_actions = st.columns(3)
if cache_actions[0].button(
    "Clear file caches",
    width="stretch",
):
    clear_runtime_caches()
    st.success("CSV, JSON and text caches cleared.")
    st.rerun()

if cache_actions[1].button(
    "Clear model cache",
    width="stretch",
):
    clear_model_artifact_cache()
    st.success("Cached model objects cleared.")
    st.rerun()

if cache_actions[2].button(
    "Rebuild integrity cache",
    width="stretch",
):
    removed_data = clear_integrity_cache(
        ROOT,
        cache_name=".data_pack_integrity_cache.json",
    )
    removed_coverage = clear_integrity_cache(
        ROOT,
        cache_name=".coverage_integrity_cache.json",
    )
    st.session_state.pop("diagnostic_checks", None)
    st.success(
        "Integrity cache cleared."
        if removed_data or removed_coverage
        else "Integrity cache was already empty."
    )
    st.rerun()

st.caption(
    "Caches invalidate automatically when a file modification time or size "
    "changes. Manual clearing is only needed after maintenance or debugging."
)


st.divider()
st.subheader("Interactive workflow state")
latest_run = st.session_state.get("_bio_latest_run")
state_columns = st.columns(4)
state_columns[0].metric("Session keys", len(st.session_state))
state_columns[1].metric(
    "Latest run", latest_run.get("status", "None") if isinstance(latest_run, dict) else "None"
)
state_columns[2].metric(
    "Latest workflow", latest_run.get("workflow", "—") if isinstance(latest_run, dict) else "—"
)
state_columns[3].metric(
    "Elapsed",
    f"{float(latest_run.get('elapsed_seconds') or 0):.2f}s"
    if isinstance(latest_run, dict)
    else "—",
)
if isinstance(latest_run, dict):
    st.download_button(
        "Download latest interactive run trace",
        __import__("json").dumps(latest_run, indent=2, sort_keys=True, default=str),
        "biointel_latest_run_trace.json",
        "application/json",
        width="stretch",
        key="diagnostics_latest_run_trace",
    )

workflow_actions = st.columns(2)
if workflow_actions[0].button("Clear Streamlit data/resource caches", width="stretch"):
    clear_ui_caches()
    st.success("Interactive data and resource caches cleared.")
    st.rerun()
confirm_transient = workflow_actions[1].checkbox(
    "Confirm transient result reset", key="confirm_transient_reset"
)
if workflow_actions[1].button(
    "Reset transient analysis results", disabled=not confirm_transient, width="stretch"
):
    protected_prefixes = ("ui_", "_bio_", "confirm_")
    removed = 0
    for key in list(st.session_state):
        if not str(key).startswith(protected_prefixes):
            del st.session_state[key]
            removed += 1
    st.success(
        f"Removed {removed} transient analysis/session values. Interface preferences were retained."
    )
    st.rerun()

st.caption(
    "Use transient reset when a page retains an outdated uploaded file or result. It does not delete datasets, reports, models or databases from disk."
)


st.divider()
st.subheader("Interaction reliability and crash recovery")
runtime_reports = runtime_error_reports(limit=100)
reliability_columns = st.columns(3)
reliability_columns[0].metric("Recorded runtime stops", len(runtime_reports))
reliability_columns[1].metric(
    "Latest reference", runtime_reports[0].get("error_id", "None") if runtime_reports else "None"
)
reliability_columns[2].metric("Friendly crash boundary", "Active")
if runtime_reports:
    report_frame = pd.DataFrame(
        [
            {
                "Reference": item.get("error_id"),
                "Time UTC": item.get("timestamp_utc"),
                "Context": item.get("context"),
                "Type": item.get("exception_type"),
                "Message": item.get("message"),
            }
            for item in runtime_reports
        ]
    )
    smart_dataframe(report_frame, height=360, key="runtime_error_reports_table")
else:
    st.success("No runtime error reports are present in this clean workspace.")
st.download_button(
    "Download interaction diagnostics bundle",
    runtime_diagnostic_bundle(limit=100),
    file_name="biointel_interaction_diagnostics.json",
    mime="application/json",
    width="stretch",
    key="download_interaction_diagnostics",
)
st.caption(
    "Uncaught page errors are converted into a safe stop with a local reference ID instead of exposing Streamlit's red exception panel."
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
