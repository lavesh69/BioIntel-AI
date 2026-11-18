from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.sequence.advanced import deduplicate_records, near_duplicate_clusters
from biointel.sequence.batch_analysis import summarize_fasta_text
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.theme import apply_theme, hero
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.workflow import read_uploaded_text, render_upload_preflight
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(page_title="Batch Sequence Analysis · BioIntel AI", page_icon="🧬", layout="wide")

apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/16_Batch_Sequence_Analysis.py", key_prefix="16_batch_sequence_analysis", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("batch_sequence", key_prefix="step116_16_Batch_Sequence_Analysis_batch_sequence_1", expanded=False)
hero(
    "🧬 Batch FASTA Summary",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
source = st.radio(
    "FASTA source",
    [
        "Coverage mixed library — 800 records",
        "Coverage DNA — 300 records",
        "Coverage RNA — 200 records",
        "Coverage protein — 300 records",
        "Upload FASTA",
    ],
    horizontal=True,
)
fasta_text = ""
if source == "Upload FASTA":
    uploaded = st.file_uploader(
        "Upload FASTA",
        type=["fasta", "fa", "fna", "faa", "txt"],
    )
    render_upload_preflight(
        uploaded,
        key="batch_fasta",
        allowed_extensions=["fasta", "fa", "fna", "faa", "txt"],
        soft_limit_mb=10,
        hard_limit_mb=50,
    )
    if uploaded is None:
        st.info("Upload up to 1,000 records.")
        st.stop()
    fasta_text = read_uploaded_text(uploaded)
else:
    sequence_path = ROOT / "data" / "coverage" / "sequence_library_800.csv"
    fasta_path = ROOT / "data" / "coverage" / "sequence_library_800.fasta"
    if not sequence_path.is_file() or not fasta_path.is_file():
        st.error("Coverage sequence pack is missing. Run SEED_COMPLETE_DATA_WINDOWS.bat.")
        st.stop()
    if source == "Coverage mixed library — 800 records":
        fasta_text = fasta_path.read_text(encoding="utf-8")
    else:
        sequence_type = "DNA" if "DNA" in source else "RNA" if "RNA" in source else "Protein"
        frame = read_csv_cached(sequence_path)
        frame = frame[frame["sequence_type"] == sequence_type]
        fasta_text = (
            "\n".join(
                f">{row.record_id}|{row.sequence_type}|{row.family}\n{row.sequence}"
                for row in frame.itertuples(index=False)
            )
            + "\n"
        )
    st.download_button(
        "Download selected FASTA",
        fasta_text,
        "selected_coverage_sequences.fasta",
        "text/plain",
    )

try:
    summary = summarize_fasta_text(fasta_text, 1000)
except Exception as exc:
    st.error(str(exc))
    st.stop()
a, b, c = st.columns(3)
a.metric("Records", len(summary))
b.metric("Total length", int(summary["length"].sum()))
c.metric("Needs review", int((summary["status"] != "ok").sum()))
st.dataframe(summary, width="stretch")
st.plotly_chart(px.histogram(summary, x="length", title="Length distribution"), width="stretch")
render_generic_visual_explorer(
    summary,
    key="batch_sequence_summary_visuals",
    heading="Batch sequence visual analytics",
)
st.download_button(
    "Download summary CSV", summary.to_csv(index=False), "batch_sequence_summary.csv", "text/csv"
)

section = st.expander("Deduplication, clustering and clean FASTA", expanded=True)
with section:
    threshold = st.slider("Near-duplicate k-mer similarity", 0.70, 1.00, 0.95, 0.01)
    input_signature = hashlib.sha256(
        (f"{float(threshold):.4f}\n" + fasta_text).encode("utf-8", errors="replace")
    ).hexdigest()
    stored = st.session_state.get("batch_sequence_advanced_result")
    if isinstance(stored, dict) and stored.get("signature") != input_signature:
        st.session_state.pop("batch_sequence_advanced_result", None)
        stored = None

    run_advanced = st.button(
        "Run deduplication and near-duplicate clustering",
        type="primary",
        width="stretch",
        key="batch_sequence_run_advanced",
    )
    if run_advanced:
        try:
            with st.spinner("Deduplicating and clustering sequences…"):
                records = parse_sequences_text(fasta_text, max_records=10000)
                duplicate_audit, unique_records = deduplicate_records(records)
                clustering = near_duplicate_clusters(
                    unique_records[:2000], identity_threshold=float(threshold)
                )
                clean_fasta = (
                    "\n".join(
                        f">{record.header}\n{record.sequence}" for record in unique_records
                    )
                    + "\n"
                )
                stored = {
                    "signature": input_signature,
                    "duplicate_audit": duplicate_audit,
                    "clustering": clustering,
                    "clean_fasta": clean_fasta,
                    "unique_count": len(unique_records),
                }
                st.session_state["batch_sequence_advanced_result"] = stored
        except Exception as exc:
            st.warning(f"Advanced batch analysis unavailable: {exc}")
            stored = None

    if not isinstance(stored, dict):
        st.info(
            "Advanced clustering is intentionally button-gated so opening this page cannot freeze "
            "the Streamlit session. Select the threshold and run it when needed."
        )
    else:
        duplicate_audit = stored["duplicate_audit"]
        clustering = stored["clustering"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Exact duplicates", int(duplicate_audit["duplicate"].sum()))
        c2.metric("Unique records", int(stored["unique_count"]))
        c3.metric(
            "Near-duplicate clusters",
            int(clustering["cluster"].nunique()) if not clustering.empty else 0,
        )
        tabs = st.tabs(["Duplicate audit", "Clusters", "Exports"])
        with tabs[0]:
            st.dataframe(duplicate_audit, width="stretch", hide_index=True)
        with tabs[1]:
            st.dataframe(clustering, width="stretch", hide_index=True)
            render_generic_visual_explorer(
                clustering,
                key="batch_sequence_cluster_visuals",
                heading="Cluster visual analytics",
            )
        with tabs[2]:
            st.download_button(
                "Download deduplicated FASTA",
                stored["clean_fasta"],
                "deduplicated_sequences.fasta",
                "text/plain",
            )
            st.download_button(
                "Download duplicate audit",
                duplicate_audit.to_csv(index=False),
                "sequence_duplicate_audit.csv",
                "text/csv",
            )
            st.download_button(
                "Download cluster assignments",
                clustering.to_csv(index=False),
                "sequence_clusters.csv",
                "text/csv",
            )

# STEP127_SCIENTIFIC_DEPTH_BATCH_SEQUENCE
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('batch_sequence', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='batch_sequence', title='Batch Sequence Analysis', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='batch_sequence', title='Batch Sequence Analysis', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
