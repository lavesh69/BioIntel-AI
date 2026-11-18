from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.services.pdf_rag_service import DocumentExtractionError, PDFRAGService
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Lab PDF & Notebook RAG Studio · BioIntel AI", page_icon=":material/document_search:", layout="wide")
apply_theme()
hero(
    "Lab PDF & Notebook RAG Studio",
    "Extract real page-preserving text from PDFs, text, Markdown, and notebooks for local evidence retrieval.",
    eyebrow="Lab Analytics · Retrieval",
    chips=["Real PDF parser", "Page citations", "Local retrieval", "No fabricated chunks"],
)
st.session_state.setdefault("lab_rag_service", PDFRAGService())
service: PDFRAGService = st.session_state["lab_rag_service"]
upload, query_column = st.columns(2)
with upload:
    section_title("Upload lab documents", "Upload")
    files = st.file_uploader(
        "PDF, TXT, Markdown, or Jupyter notebook",
        type=["pdf", "txt", "md", "ipynb"],
        accept_multiple_files=True,
        key="rag_document_uploader",
    )
    if files and st.button("Validate and index files", icon=":material/library_add:", type="primary"):
        for file in files:
            try:
                chunks = service.index_bytes(file.getvalue(), file.name)
                if chunks:
                    st.success(f"Indexed {file.name}: {len(chunks)} real chunks.")
                else:
                    st.warning(f"{file.name}: no extractable text was indexed.")
                for warning in service.last_warnings:
                    st.warning(warning)
            except DocumentExtractionError as exc:
                st.error(f"{file.name}: {exc}")
    sources = sorted({chunk.source_name for chunk in service.chunks})
    st.info(f"Indexed chunks: **{len(service.chunks)}** · sources: **{len(sources)}**")
with query_column:
    section_title("Evidence retrieval", "Search")
    with st.form("rag_query", border=False):
        query = st.text_input(
            "Scientific question or search term",
            placeholder="What protocol was used for cell lysis?",
        )
        submitted = st.form_submit_button("Retrieve evidence", icon=":material/search:", type="primary")
    if submitted:
        result = service.query(query)
        if result.evidence_found:
            st.markdown(result.answer)
            st.caption(f"Synthesis state: {result.synthesis}")
            with st.expander("Retrieved excerpts and scores", on_change="rerun"):
                for index, (chunk, score) in enumerate(zip(result.chunks, result.scores), start=1):
                    st.caption(
                        f"Match {index} · score {score} · {chunk.source_name} · page/cell {chunk.page_number}"
                    )
                    st.code(chunk.content, language="markdown")
        else:
            st.warning(result.answer)
