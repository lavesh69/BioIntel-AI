from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.evidence_registry import (
    evidence_readiness,
    list_evidence_links,
    record_review,
    registry_summary,
)
from biointel.ui.components import smart_json
from biointel.ui.performance import read_sql_cached
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Evidence Review Queue · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()
hero("✅ Evidence Review Queue", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption("Human review is mandatory before real experimental rows become release-eligible. Decisions are append-only review records with reviewer and comments.")

DB = ROOT / "reports" / "evidence.sqlite3"
summary = registry_summary(DB)
smart_json(summary)
all_links = list_evidence_links(DB, limit=5000)
available_hashes = sorted({str(item["dataset_sha256"]) for item in all_links})
if available_hashes:
    dataset_hash = st.selectbox(
        "Dataset SHA-256",
        available_hashes,
        format_func=lambda value: f"{value[:16]}… · {sum(item['dataset_sha256'] == value for item in all_links)} rows",
    )
else:
    dataset_hash = st.text_input("Dataset SHA-256")
st.info(
    "The preloaded queue is demonstration/reference data. Review decisions show workflow behavior "
    "and are not scientific approvals."
)
status = st.selectbox("Review status", ["pending", "accepted", "rejected", "edited", "all"])
if dataset_hash.strip():
    links = list_evidence_links(DB, dataset_sha256=dataset_hash.strip(), review_status=None if status == "all" else status, limit=5000)
    frame = pd.DataFrame(links)
    st.dataframe(frame, width="stretch", hide_index=True)
    if not frame.empty:
        evidence_key = st.selectbox("Evidence row", frame["evidence_key"].tolist())
        decision = st.selectbox("Decision", ["accepted", "rejected", "edited", "pending"])
        reviewer = st.text_input("Reviewer")
        comment = st.text_area("Scientific review comment")
        if st.button("Record review decision", type="primary"):
            try:
                record_review(DB, dataset_sha256=dataset_hash.strip(), evidence_key=evidence_key, decision=decision, reviewer=reviewer, comment=comment)
                st.success("Review recorded.")
                smart_json(evidence_readiness(DB, dataset_hash.strip()))
            except Exception as exc:
                st.error(str(exc))
    try:
        contexts = read_sql_cached(
            DB,
            "SELECT * FROM evidence_assay_context WHERE dataset_sha256=? LIMIT 1000",
            params=(dataset_hash.strip(),),
        ).to_dict("records")
        replicates = read_sql_cached(
            DB,
            "SELECT * FROM evidence_replicates WHERE dataset_sha256=? LIMIT 3000",
            params=(dataset_hash.strip(),),
        ).to_dict("records")
    except sqlite3.OperationalError:
        contexts = replicates = []
    context_tab,replicate_tab=st.tabs(["Assay context","Replicate measurements"])
    with context_tab:
        st.dataframe(pd.DataFrame(contexts),width="stretch",hide_index=True) if contexts else st.info("No assay-context records.")
    with replicate_tab:
        st.dataframe(pd.DataFrame(replicates),width="stretch",hide_index=True) if replicates else st.info("No replicate records.")
    readiness = evidence_readiness(DB, dataset_hash.strip())
    st.subheader("Release readiness")
    smart_json(readiness)
    st.download_button("Download readiness manifest", json.dumps(readiness, indent=2), "step25_evidence_readiness.json", "application/json")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
