from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.history import list_entities, list_runs, search_content
from biointel.documents.knowledge import ask_document_history, compare_document_runs
from biointel.ui.components import smart_json
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Document Knowledge Search · BioIntel AI", page_icon="🧠", layout="wide")
apply_theme()
hero("🧠 Document Knowledge Search", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Search indexed paragraphs and tables, inspect scientific entities, ask extractive cited "
    "questions and compare two document runs without sending data to an external service."
)

HISTORY = ROOT / "reports" / "document_history.sqlite3"
search_tab, entity_tab, qa_tab, compare_tab = st.tabs(
    ["Full-text search", "Scientific entities", "Cited Q&A", "Compare documents"]
)

with search_tab:
    query = st.text_input("Search extracted content")
    if query:
        results = search_content(HISTORY, query, limit=200)
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)

with entity_tab:
    entity_types = ["all", "gene_or_protein", "drug_or_compound", "disease", "organism", "mutation", "assay_endpoint", "activity_measurement", "publication_identifier"]
    entity_type = st.selectbox("Entity type", entity_types)
    entity_query = st.text_input("Entity search")
    entities = list_entities(HISTORY, entity_type=entity_type, query=entity_query, limit=5000)
    st.dataframe(pd.DataFrame(entities), width="stretch", hide_index=True)

with qa_tab:
    question = st.text_area("Question", placeholder="Which targets and activity values are reported?")
    if st.button("Answer from indexed documents", type="primary") and question.strip():
        result = ask_document_history(ROOT, question, maximum_documents=15, maximum_citations=8)
        st.session_state["step27_document_answer"] = result
    result = st.session_state.get("step27_document_answer")
    if result:
        st.markdown(result["answer"])
        st.dataframe(pd.DataFrame(result["citations"]), width="stretch", hide_index=True)
        st.caption("Answer is extractive and grounded only in stored document passages.")

with compare_tab:
    runs = [run for run in list_runs(HISTORY, limit=2000) if run.status == "completed"]
    if len(runs) < 2:
        st.info("At least two completed document runs are required.")
    else:
        labels = {run.run_id: f"{run.source_name} · {run.started_at_utc}" for run in runs}
        left, right = st.columns(2)
        left_id = left.selectbox("Left document", list(labels), format_func=labels.get)
        right_id = right.selectbox("Right document", list(labels), index=1, format_func=labels.get)
        if st.button("Compare documents"):
            st.session_state["step27_comparison"] = compare_document_runs(ROOT, left_id, right_id)
        comparison = st.session_state.get("step27_comparison")
        if comparison:
            smart_json(comparison)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='document_knowledge_search', title='Document Knowledge Search', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
