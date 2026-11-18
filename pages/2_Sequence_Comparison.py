from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.sequence.advanced import (
    alignment_event_table,
    auto_orient_alignment,
    semiglobal_alignment,
)
from biointel.sequence.parser import parse_sequence_text
from biointel.sequence.validators import (
    SequenceType,
    validate_for_type,
)
from biointel.ui.theme import apply_theme, hero
from biointel.ui.scientific_visuals import build_sequence_alignment_visuals, render_visual_collection
from biointel.utils.exceptions import InvalidSequenceError
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title="Sequence Comparison · BioIntel AI",
    page_icon="🔬",
    layout="wide",
)

apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/2_Sequence_Comparison.py", key_prefix="2_sequence_comparison", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("sequence_comparison", key_prefix="step116_2_Sequence_Comparison_sequence_comparison_1", expanded=False)
hero(
    "🔬 Sequence Comparison",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption("Global or local pairwise alignment using the BioIntel Sequence Intelligence Engine.")

coverage_pairs_path = ROOT / "data" / "coverage" / "sequence_comparison_pairs_180.csv"
coverage_pairs = (
    read_csv_cached(coverage_pairs_path) if coverage_pairs_path.is_file() else pd.DataFrame()
)
input_source = st.radio(
    "Comparison source",
    ["Coverage pair library — 180 pairs", "Custom sequences"],
    horizontal=True,
)
first_default = ""
second_default = ""
default_type = "DNA"
default_mode = "global"
if input_source == "Coverage pair library — 180 pairs" and not coverage_pairs.empty:
    pair_type = st.selectbox(
        "Pair type",
        ["DNA", "RNA", "Protein"],
    )
    filtered_pairs = coverage_pairs[coverage_pairs["sequence_type"] == pair_type]
    pair_id = st.selectbox(
        "Ready comparison pair",
        filtered_pairs["pair_id"].tolist(),
        format_func=lambda value: next(
            (
                f"{value} · mutation {float(row.mutation_rate) * 100:.0f}%"
                for row in filtered_pairs.itertuples(index=False)
                if row.pair_id == value
            ),
            value,
        ),
    )
    pair_row = filtered_pairs.loc[filtered_pairs["pair_id"] == pair_id].iloc[0]
    first_default = f">{pair_row['query_id']}\n{pair_row['query_sequence']}"
    second_default = f">{pair_row['target_id']}\n{pair_row['target_sequence']}"
    default_type = str(pair_row["sequence_type"])
    default_mode = str(pair_row["recommended_mode"])

left, right = st.columns(2)
with left:
    first = st.text_area(
        "Sequence 1",
        height=180,
        value=first_default,
        placeholder=">query\nATG...",
    )
with right:
    second = st.text_area(
        "Sequence 2",
        height=180,
        value=second_default,
        placeholder=">target\nATG...",
    )

sequence_type = SequenceType(
    st.radio(
        "Sequence type",
        ["DNA", "RNA", "Protein"],
        index=["DNA", "RNA", "Protein"].index(default_type),
        horizontal=True,
    )
)
alignment_modes = ["global", "local", "semi-global"]
mode = st.radio(
    "Alignment mode",
    alignment_modes,
    index=alignment_modes.index(default_mode) if default_mode in alignment_modes else 0,
    horizontal=True,
)

with st.expander("Scoring settings"):
    c1, c2, c3, c4 = st.columns(4)
    match = c1.number_input("Match", value=2.0)
    mismatch = c2.number_input("Mismatch", value=-1.0)
    gap_open = c3.number_input("Gap open", value=-2.0)
    gap_extend = c4.number_input(
        "Gap extension",
        value=-0.5,
    )
    substitution_matrix = "BLOSUM62"
    if sequence_type == SequenceType.PROTEIN:
        substitution_matrix = st.selectbox(
            "Protein substitution matrix",
            ["BLOSUM62", "PAM250"],
        )

if st.button("Run alignment", type="primary"):
    try:
        query = parse_sequence_text(first)
        target = parse_sequence_text(second)
    except InvalidSequenceError as exc:
        st.error(str(exc))
        st.stop()

    for label, parsed in (
        ("Sequence 1", query),
        ("Sequence 2", target),
    ):
        invalid = validate_for_type(
            parsed.sequence,
            sequence_type,
        )
        if invalid:
            st.error(
                f"{label} has invalid symbols for "
                f"{sequence_type.value}: "
                + ", ".join(f"{character} at {position}" for position, character in invalid[:20])
            )
            st.stop()

    try:
        if mode == "semi-global":
            result = semiglobal_alignment(
                query.sequence,
                target.sequence,
                match_score=float(match),
                mismatch_score=float(mismatch),
                gap_open=float(gap_open),
                gap_extend=float(gap_extend),
            )
        else:
            result = auto_orient_alignment(
                query.sequence,
                target.sequence,
                sequence_type=sequence_type.value,
                mode=mode,
                match_score=float(match),
                mismatch_score=float(mismatch),
                gap_open=float(gap_open),
                gap_extend=float(gap_extend),
                substitution_matrix=substitution_matrix,
            )
    except Exception as exc:
        st.error(f"Alignment failed: {exc}")
        st.stop()

    metrics = st.columns(6)
    metrics[0].metric("Score", f"{result['score']:.2f}")
    metrics[1].metric(
        "Alignment length",
        result["alignment_length"],
    )
    metrics[2].metric("Identities", result["identities"])
    metrics[3].metric(
        "Identity %",
        f"{result['identity_percent']:.2f}",
    )
    similarity = result["similarity_percent"]
    metrics[4].metric(
        "Similarity %",
        (f"{similarity:.2f}" if similarity is not None else "N/A"),
    )
    metrics[5].metric(
        "Gap columns",
        result["gap_columns"],
    )

    coverage_left, coverage_right = st.columns(2)
    coverage_left.metric(
        "Query coverage",
        f"{result['query_coverage_percent']:.2f}%",
    )
    coverage_right.metric(
        "Target coverage",
        f"{result['target_coverage_percent']:.2f}%",
    )

    st.code(
        result["formatted_alignment"],
        language=None,
    )
    if result["mismatch_positions"]:
        st.caption(
            "Mismatch positions in displayed alignment: "
            + ", ".join(map(str, result["mismatch_positions"][:100]))
        )

    events = pd.DataFrame()
    if result.get("aligned_query") and result.get("aligned_target"):
        events = alignment_event_table(result["aligned_query"], result["aligned_target"])
        st.subheader("Coordinate-mapped substitution and indel events")
        st.dataframe(events, width="stretch", hide_index=True)
        st.download_button(
            "Download event table", events.to_csv(index=False), "alignment_events.csv", "text/csv"
        )
    if result.get("orientation"):
        st.info(f"Selected query orientation: {result['orientation']}")

    excluded = {
        "formatted_alignment",
        "aligned_query",
        "aligned_target",
        "mismatch_positions",
    }
    summary = {key: value for key, value in result.items() if key not in excluded}
    summary_df = pd.DataFrame([summary])
    st.dataframe(
        summary_df,
        width="stretch",
        hide_index=True,
    )
    render_visual_collection(
        build_sequence_alignment_visuals(result, events),
        key="sequence_comparison_visuals",
        heading="Alignment visual analytics",
    )

    st.download_button(
        "Download alignment TXT",
        result["formatted_alignment"],
        "alignment.txt",
        "text/plain",
    )
    st.download_button(
        "Download metrics CSV",
        summary_df.to_csv(index=False),
        "alignment_metrics.csv",
        "text/csv",
    )
    st.download_button(
        "Download alignment JSON",
        json.dumps(result, indent=2, default=str),
        "alignment.json",
        "application/json",
    )

# STEP127_SCIENTIFIC_DEPTH_SEQUENCE_COMPARISON
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('sequence_comparison', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='sequence_comparison', title='Sequence Comparison', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='sequence_comparison', title='Sequence Comparison', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
