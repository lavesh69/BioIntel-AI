from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.history import (
    delete_run,
    get_run,
    history_summary,
    list_events,
    list_outputs,
    list_runs,
    restore_run,
    soft_delete_run,
    update_run_organization,
    verify_output,
)
from biointel.documents.service import resolve_document_path
from biointel.ui.components import smart_json
from biointel.ui.performance import read_sql_cached
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Document Extraction History · BioIntel AI", page_icon="🕘", layout="wide")
apply_theme()
hero("🕘 Document Extraction History", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Search, tag, verify, trash, restore and re-download previous extractions. Full-text and "
    "scientific entity search are available in Document Knowledge Search."
)

HISTORY = ROOT / "reports" / "document_history.sqlite3"
summary = history_summary(HISTORY)
metrics = st.columns(7)
metrics[0].metric("Runs", summary["total_runs"])
metrics[1].metric("Completed", summary["completed_runs"])
metrics[2].metric("Failed", summary["failed_runs"])
metrics[3].metric("Trash", summary["trashed_runs"])
metrics[4].metric("Tables", f"{summary['total_tables']:,}")
metrics[5].metric("Indexed records", f"{summary['indexed_content_records']:,}")
metrics[6].metric("Entities", f"{summary['scientific_entities']:,}")

query_col, type_col, status_col, trash_col = st.columns([2, 1, 1, 1])
query = query_col.text_input("Search filename, hash or notes")
file_type = type_col.selectbox(
    "Type",
    ["all", "pdf", "xlsx", "xls", "xlsm", "docx", "csv", "tsv", "txt", "md", "html", "json", "xml", "yaml", "pptx", "odt", "ods"],
)
status = status_col.selectbox("Status", ["all", "completed", "failed", "running"])
include_deleted = trash_col.checkbox("Show trash", value=False)
registry_version_rows = read_sql_cached(
    HISTORY,
    "SELECT run_id,registry_version,verification_status,last_verified_at_utc FROM document_registry_versions",
)
registry_versions = {
    str(row.run_id): {
        "registry_version": row.registry_version,
        "verification_status": row.verification_status,
        "last_verified_at_utc": row.last_verified_at_utc,
    }
    for row in registry_version_rows.itertuples(index=False)
}

runs = list_runs(
    HISTORY,
    query=query,
    file_type=file_type,
    status=status,
    include_deleted=include_deleted,
    limit=5000,
)
if not runs:
    st.info("No history matches the filters.")
    st.stop()

st.dataframe(
    pd.DataFrame(
        [
            {
                "Run": run.run_id,
                "Started": run.started_at_utc,
                "File": run.source_name,
                "Type": run.file_type.upper(),
                "Status": run.status,
                "Project": run.project_code,
                "Tags": ", ".join(run.tags),
                "Tables": run.table_count,
                "Rows": run.row_count,
                "Warnings": run.warning_count,
                "Engine": run.engine_version,
                "Registry": registry_versions.get(run.run_id, {}).get("registry_version", "not verified"),
                "Integrity": registry_versions.get(run.run_id, {}).get("verification_status", "unknown"),
                "Deleted": run.deleted_at_utc,
                "SHA-256": run.source_sha256,
            }
            for run in runs
        ]
    ),
    width="stretch",
    hide_index=True,
)
labels = {run.run_id: f"{run.started_at_utc} · {run.source_name} · {run.status}" for run in runs}
run_id = st.selectbox("Open run", list(labels), format_func=labels.get)
run = get_run(HISTORY, run_id)
outputs = list_outputs(HISTORY, run_id)
events = list_events(HISTORY, run_id)

details_tab, organize_tab, outputs_tab, events_tab, lifecycle_tab = st.tabs(
    ["Details", "Organize", "Downloads & integrity", "Events", "Trash / restore"]
)
with details_tab:
    version_info = registry_versions.get(run_id, {})
    version_metrics = st.columns(3)
    version_metrics[0].metric("Extraction engine", run.engine_version)
    version_metrics[1].metric("Registry version", version_info.get("registry_version", "not verified"))
    version_metrics[2].metric("Output integrity", version_info.get("verification_status", "unknown"))
    st.caption("Historical engine versions are preserved; registry verification is tracked separately.")
    smart_json(asdict(run))
    for warning in run.warnings:
        st.warning(warning)

with organize_tab:
    tags = st.text_input("Tags", value=", ".join(run.tags))
    project = st.text_input("Project code", value=run.project_code)
    notes = st.text_area("Notes", value=run.notes)
    if st.button("Save organization"):
        update_run_organization(
            HISTORY,
            run_id,
            tags=[value.strip() for value in tags.split(",") if value.strip()],
            project_code=project,
            notes=notes,
        )
        st.success("Organization updated.")
        st.rerun()

with outputs_tab:
    columns = st.columns(3)
    for index, output in enumerate(outputs):
        column = columns[index % 3]
        path = resolve_document_path(ROOT, output.path)
        if path.is_file():
            column.download_button(
                f"Download {output.format.replace('_', ' ').upper()}",
                path.read_bytes(),
                file_name=output.filename,
                key=f"history_{output.output_id}",
                width="stretch",
            )
            if column.button("Verify integrity", key=f"verify_{output.output_id}"):
                column.json(verify_output(HISTORY, output.output_id))
        else:
            column.error(f"Missing: {output.filename}")

with events_tab:
    st.dataframe(pd.DataFrame(events), width="stretch", hide_index=True)

with lifecycle_tab:
    if run.deleted_at_utc:
        if st.button("Restore from trash", type="primary"):
            restore_run(HISTORY, run_id)
            st.success("Run restored.")
            st.rerun()
        st.warning("Permanent purge removes records and generated files.")
        confirm = st.checkbox("Permanently purge this run")
        if st.button("Purge permanently", disabled=not confirm):
            delete_run(HISTORY, run_id, delete_files=True)
            st.success("Run permanently purged.")
            st.rerun()
    else:
        st.info("Move this run to trash. Files remain available until permanent purge.")
        if st.button("Move to trash"):
            soft_delete_run(HISTORY, run_id)
            st.success("Run moved to trash.")
            st.rerun()

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
