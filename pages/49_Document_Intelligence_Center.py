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
from biointel.documents.service import (
    load_processed_document,
    process_document,
    resolve_document_path,
)
from biointel.ui.components import smart_json
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import indeterminate_loader, render_upload_preflight

st.set_page_config(page_title="Document Intelligence Center · BioIntel AI", page_icon="📄", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('document_intelligence_core', expanded=False)
hero("📄 Document Intelligence Center", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Extract PDF, Office, structured and text documents with optional OCR, page/cell "
    "provenance, scientific entities, sensitive-data review and six download formats."
)


HISTORY = ROOT / "reports" / "document_history.sqlite3"
preloaded_runs = [run for run in list_runs(HISTORY, limit=200) if run.status == "completed"]
if preloaded_runs:
    labels = {run.run_id: f"{run.source_name} · {run.file_type.upper()} · {run.table_count} table(s)" for run in preloaded_runs}
    demo_col, open_col = st.columns([4, 1])
    demo_run_id = demo_col.selectbox("Open a preloaded extraction", list(labels), format_func=labels.get)
    if open_col.button("Open demo", width="stretch"):
        st.session_state["step27_processed_document"] = load_processed_document(ROOT, demo_run_id)
    st.caption("Preloaded documents are demonstration/reference content and can be explored immediately.")

uploaded = st.file_uploader(
    "Upload a document",
    type=[
        "pdf", "xlsx", "xls", "xlsm", "docx", "csv", "tsv", "txt", "md",
        "html", "htm", "json", "xml", "yaml", "yml", "pptx", "odt", "ods",
    ],
    help="Maximum size is 100 MB. Active content and unsafe embedded objects are blocked.",
)
render_upload_preflight(
    uploaded,
    key="document_intelligence",
    allowed_extensions=["pdf", "xlsx", "xls", "xlsm", "docx", "csv", "tsv", "txt", "md", "html", "htm", "json", "xml", "yaml", "yml", "pptx", "odt", "ods"],
    soft_limit_mb=50,
    hard_limit_mb=100,
)

left, middle, right = st.columns(3)
password = left.text_input("PDF password", type="password")
ocr_mode = middle.selectbox("OCR mode", ["off", "auto", "force"], index=1)
ocr_language = right.text_input("OCR language", value="eng")

left, middle, right = st.columns(3)
max_rows = left.number_input("Maximum rows per table", 100, 250_000, 50_000, 1_000)
max_columns = middle.number_input("Maximum columns", 10, 2_000, 256, 10)
duplicate_policy = right.selectbox("Duplicate policy", ["warn", "reuse", "force"])

left, middle, right = st.columns(3)
keep_source = left.checkbox("Keep local source copy", value=False)
allow_xlsm = middle.checkbox("Allow XLSM reading; macros never execute", value=False)
redact_sensitive = right.checkbox("Redact possible sensitive values in exports", value=False)

project_code = st.text_input("Project code (optional)")
tags = st.text_input("Tags, comma-separated")
notes = st.text_area("Extraction notes")

if uploaded is not None:
    st.info(
        f"Selected: {uploaded.name} · {uploaded.size / (1024 * 1024):.2f} MB · local processing"
    )
    if st.button("Extract and build downloads", type="primary"):
        try:
            with indeterminate_loader("Extracting, indexing and generating output packages..."):
                processed = process_document(
                    uploaded.name,
                    uploaded.getvalue(),
                    project_root=ROOT,
                    password=password or None,
                    keep_source=keep_source,
                    max_rows_per_table=int(max_rows),
                    max_columns=int(max_columns),
                    allow_macro_workbooks=allow_xlsm,
                    ocr_mode=ocr_mode,
                    ocr_language=ocr_language.strip() or "eng",
                    redact_sensitive=redact_sensitive,
                    duplicate_policy=duplicate_policy,
                    project_code=project_code,
                    tags=[value.strip() for value in tags.split(",") if value.strip()],
                    notes=notes,
                )
            st.session_state["step27_processed_document"] = processed
        except Exception as exc:
            st.error(str(exc))

processed = st.session_state.get("step27_processed_document")
if processed is None and preloaded_runs:
    processed = load_processed_document(ROOT, preloaded_runs[0].run_id)
if processed is None:
    st.markdown(
        """
### Quality-Hardened extraction capabilities

- **PDF:** layout-aware text, tables, normalized bounding boxes and reviewed OCR.
- **Excel:** formulas plus cached values, hidden rows/columns, merged ranges, comments,
  hyperlinks, validation rules and named ranges.
- **DOCX/PPTX:** headings, tables, headers/footers, notes, comments, tracked changes,
  images and layout metadata.
- **Structured/text:** CSV, TSV, TXT, Markdown, HTML, JSON, XML, YAML, ODT and ODS.
- **Intelligence:** scientific entities, research-paper sections, PII/secret warnings,
  full-text indexing and document-to-evidence provenance.
"""
    )
    st.stop()

extraction = processed.extraction
summary = extraction.summary()
metrics = st.columns(7)
metrics[0].metric("Type", extraction.file_type.upper())
metrics[1].metric("Pages / sheets", summary["page_count"] or summary["sheet_count"])
metrics[2].metric("Tables", summary["table_count"])
metrics[3].metric("Rows", f"{summary['row_count']:,}")
metrics[4].metric("Regions", f"{summary['region_count']:,}")
metrics[5].metric("Entities", f"{summary['entity_count']:,}")
metrics[6].metric("Warnings", summary["warning_count"])

if processed.reused_from_run_id:
    st.success(f"Duplicate result reused from run {processed.reused_from_run_id}.")
for warning in extraction.warnings:
    st.warning(warning)

preview_tab, tables_tab, entities_tab, provenance_tab, metadata_tab, downloads_tab = st.tabs(
    ["Text", "Tables", "Scientific entities", "Provenance", "Metadata", "Downloads"]
)
with preview_tab:
    if extraction.sections:
        names = [section.name for section in extraction.sections]
        selected = st.selectbox("Section", names)
        section = extraction.sections[names.index(selected)]
        st.caption(f"Source: {section.source} · Confidence: {section.confidence}")
        st.text_area("Extracted text", section.text, height=420)
    else:
        st.text_area("Extracted text", extraction.text, height=420)

with tables_tab:
    if extraction.tables:
        names = [table.name for table in extraction.tables]
        selected = st.selectbox("Table", names)
        table = extraction.tables[names.index(selected)]
        st.caption(
            f"Source: {table.source} · {table.row_count:,} rows · "
            f"{table.column_count} columns · Confidence: {table.confidence}"
        )
        st.dataframe(pd.DataFrame(table.rows, columns=table.columns).head(5_000), width="stretch", hide_index=True)
        smart_json(table.metadata)
    else:
        st.info("No structured table was detected.")

with entities_tab:
    st.dataframe(
        pd.DataFrame([entity.to_dict() for entity in extraction.entities]),
        width="stretch",
        hide_index=True,
    )
    smart_json(extraction.structured_fields)

with provenance_tab:
    st.dataframe(
        pd.DataFrame([region.to_dict() for region in extraction.regions]).head(20_000),
        width="stretch",
        hide_index=True,
    )

with metadata_tab:
    smart_json(
        {
            "run_id": processed.run_id,
            "summary": summary,
            "metadata": extraction.metadata,
            "source_saved": bool(processed.source_saved_path),
            "output_directory": processed.output_directory,
        }
    )

with downloads_tab:
    columns = st.columns(3)
    mime_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "json": "application/json",
        "csv_zip": "application/zip",
        "bundle_zip": "application/zip",
    }
    for index, output in enumerate(processed.outputs):
        path = resolve_document_path(ROOT, output.path)
        if path.is_file():
            column = columns[index % 3]
            column.download_button(
                f"Download {output.format.replace('_', ' ').upper()}",
                data=path.read_bytes(),
                file_name=output.filename,
                mime=mime_types.get(output.format, "application/octet-stream"),
                key=f"step27_download_{processed.run_id}_{output.output_id}",
                width="stretch",
            )
            column.caption(f"{output.size_bytes / 1024:.1f} KB · {output.sha256[:12]}…")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("document_intelligence_core", None, key_prefix="step114_document_intelligence_core", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='document_intelligence', title='Document Intelligence Center', category='Data')

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("document_intelligence_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("document_intelligence_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("document_intelligence_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('document_intelligence_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('document_intelligence_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('document_intelligence_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('document_intelligence_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('document_intelligence_core', expanded=False)

