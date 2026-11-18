from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.history import list_runs
from biointel.documents.service import process_documents
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import indeterminate_loader, render_upload_collection_preflight

st.set_page_config(page_title="Batch Document Processor · BioIntel AI", page_icon="📚", layout="wide")
apply_theme()
hero("📚 Batch Document Processor", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Process multiple supported documents with duplicate detection, optional OCR, scientific "
    "entity extraction and searchable history. Combined input is limited to 100 MB per batch."
)


DEMO_DIR = ROOT / "data" / "examples" / "demo_workspace"
demo_files = [
    path for path in sorted(DEMO_DIR.iterdir())
    if path.suffix.lower() in {".pdf", ".docx", ".xlsx", ".csv", ".md", ".txt", ".json", ".html"}
]
existing_demo_runs = [
    run for run in list_runs(ROOT / "reports" / "document_history.sqlite3", limit=500)
    if "demo" in run.tags or run.project_code.startswith("DEMO-")
]
metrics = st.columns(3)
metrics[0].metric("Preloaded documents", len(demo_files))
metrics[1].metric("Existing demo runs", len(existing_demo_runs))
metrics[2].metric("Available formats", len({path.suffix.lower() for path in demo_files}))
st.dataframe(
    pd.DataFrame([
        {"File": path.name, "Type": path.suffix.upper().lstrip("."), "Size KB": round(path.stat().st_size / 1024, 1)}
        for path in demo_files
    ]),
    width="stretch",
    hide_index=True,
)
if st.button("Run preloaded demonstration batch", width="stretch"):
    with indeterminate_loader("Loading preloaded documents through the batch engine..."):
        result = process_documents(
            [(path.name, path.read_bytes()) for path in demo_files],
            project_root=ROOT,
            keep_source=False,
            ocr_mode="off",
            duplicate_policy="reuse",
            tags=["demo", "preloaded", "batch"],
            project_code="DEMO-BATCH-28",
            notes="Preloaded Quality-Hardened batch demonstration.",
        )
    st.session_state["step27_batch_result"] = result

st.divider()
uploads = st.file_uploader(
    "Documents",
    type=[
        "pdf", "xlsx", "xls", "xlsm", "docx", "csv", "tsv", "txt", "md",
        "html", "htm", "json", "xml", "yaml", "yml", "pptx", "odt", "ods",
    ],
    accept_multiple_files=True,
)
render_upload_collection_preflight(
    uploads,
    key="document_batch",
    allowed_extensions=["pdf", "xlsx", "xls", "xlsm", "docx", "csv", "tsv", "txt", "md", "html", "htm", "json", "xml", "yaml", "yml", "pptx", "odt", "ods"],
    per_file_soft_limit_mb=25,
    per_file_hard_limit_mb=100,
    combined_hard_limit_mb=100,
)
left, middle, right = st.columns(3)
ocr_mode = left.selectbox("OCR mode", ["off", "auto", "force"], index=1)
duplicate_policy = middle.selectbox("Duplicate policy", ["warn", "reuse", "force"])
redact_sensitive = right.checkbox("Redact possible sensitive values in exports", value=False)
keep_source = st.checkbox("Keep local source copies", value=False)

if uploads:
    total_size = sum(item.size for item in uploads)
    st.info(f"{len(uploads)} document(s) selected · {total_size / (1024 * 1024):.2f} MB")
    if total_size > 100 * 1024 * 1024:
        st.error("Combined upload exceeds the 100 MB batch safety limit.")
    elif st.button("Run batch extraction", type="primary"):
        progress = st.progress(0.0)
        status = st.empty()

        def update(done: int, total: int, filename: str) -> None:
            progress.progress(done / max(total, 1))
            status.caption(f"{done}/{total} · {filename}")

        with indeterminate_loader("Processing document batch..."):
            result = process_documents(
                [(item.name, item.getvalue()) for item in uploads],
                project_root=ROOT,
                progress_callback=update,
                keep_source=keep_source,
                ocr_mode=ocr_mode,
                duplicate_policy=duplicate_policy,
                redact_sensitive=redact_sensitive,
            )
        st.session_state["step27_batch_result"] = result

result = st.session_state.get("step27_batch_result")
if result:
    metrics = st.columns(4)
    metrics[0].metric("Batch ID", result.batch_id[:12])
    metrics[1].metric("Total", result.total)
    metrics[2].metric("Completed", result.completed)
    metrics[3].metric("Failed", result.failed)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Run": item.run_id,
                    "File": item.extraction.source_name,
                    "Type": item.extraction.file_type,
                    "Tables": item.extraction.table_count,
                    "Entities": item.extraction.entity_count,
                    "Warnings": len(item.extraction.warnings),
                    "Reused": bool(item.reused_from_run_id),
                }
                for item in result.processed
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    if result.errors:
        st.error("Some files failed.")
        st.dataframe(pd.DataFrame(result.errors), width="stretch", hide_index=True)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
