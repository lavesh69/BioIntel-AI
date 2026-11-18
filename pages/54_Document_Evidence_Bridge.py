from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.bridge import import_table_as_evidence, register_table_as_dataset
from biointel.documents.history import list_runs
from biointel.documents.service import load_processed_document
from biointel.ui.components import smart_json
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Document Evidence Bridge · BioIntel AI", page_icon="🌉", layout="wide")
apply_theme()
hero("🌉 Document → Dataset & Evidence Bridge", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Promote a reviewed extracted table into the Dataset Registry or map it into the Quality-Hardened "
    "real-evidence workflow with document, table and page/cell provenance."
)

HISTORY = ROOT / "reports" / "document_history.sqlite3"
runs = [run for run in list_runs(HISTORY, limit=2000) if run.status == "completed" and run.table_count]
if not runs:
    st.info("No completed extraction with tables is available.")
    st.stop()
labels = {run.run_id: f"{run.source_name} · {run.table_count} table(s)" for run in runs}
run_id = st.selectbox("Document run", list(labels), format_func=labels.get)
processed = load_processed_document(ROOT, run_id)
extraction = processed.extraction
table_labels = [f"{index}: {table.name} · {table.row_count} rows" for index, table in enumerate(extraction.tables)]
selected = st.selectbox("Extracted table", range(len(table_labels)), format_func=lambda value: table_labels[value])
table = extraction.tables[selected]
frame = pd.DataFrame(table.rows, columns=table.columns)
st.caption(f"Source: {table.source} · Confidence: {table.confidence}")
st.dataframe(frame.head(5000), width="stretch", hide_index=True)

dataset_tab, evidence_tab = st.tabs(["Register dataset", "Import real evidence"])
with dataset_tab:
    dataset_name = st.text_input("Dataset name", value=f"{Path(extraction.source_name).stem} - {table.name}")
    dataset_version = st.text_input("Dataset version", value="1.0")
    task_type = st.selectbox("Task type", ["unlabelled", "classification", "regression"])
    notes = st.text_area("Notes")
    if st.button("Register extracted table as dataset", type="primary"):
        try:
            result = register_table_as_dataset(
                ROOT,
                run_id=run_id,
                table_index=selected,
                dataset_name=dataset_name,
                dataset_version=dataset_version,
                task_type=task_type,
                notes=notes,
            )
            st.success("Dataset registered with document provenance.")
            smart_json(result)
        except Exception as exc:
            st.error(str(exc))

with evidence_tab:
    st.warning("Evidence import requires scientific columns and all imported rows remain review-pending.")
    columns = ["None", *map(str, frame.columns)]
    mappings = {}
    for target in ("canonical_smiles", "protein_sequence", "standard_value", "standard_units", "standard_relation", "activity_type", "assay_id", "publication_id", "uniprot_accession", "organism"):
        default = target if target in frame.columns else "None"
        choice = st.selectbox(target, columns, index=columns.index(default), key=f"map_{target}")
        if choice != "None":
            mappings[target] = choice
    provider = st.text_input("Provider/source", value="document_extraction")
    source_release = st.text_input("Source release", value="document_import")
    threshold = st.slider("Active pActivity threshold", 4.0, 10.0, 6.0, 0.25)
    if st.button("Import table into Evidence Registry"):
        try:
            result = import_table_as_evidence(
                ROOT,
                run_id=run_id,
                table_index=selected,
                column_mapping=mappings,
                provider=provider,
                source_release=source_release,
                active_threshold=threshold,
            )
            st.success("Evidence imported. Human review is required before release.")
            smart_json(result)
        except Exception as exc:
            st.error(str(exc))

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='document_evidence_bridge', title='Document Evidence Bridge', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
