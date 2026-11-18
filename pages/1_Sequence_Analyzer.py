from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.reports.pdf_report import build_summary_pdf
from biointel.sequence.additional_analysis import dna_oligo_properties, kmer_frequency
from biointel.sequence.advanced import motif_search_both_strands, sequence_qc_profile
from biointel.sequence.dna_analysis import (
    codon_usage,
    cumulative_gc_skew,
    dna_transformations,
    nucleotide_statistics,
    six_frame_translation,
    sliding_gc,
)
from biointel.sequence.motif_analysis import (
    find_exact_motif,
    find_regex_motif,
)
from biointel.sequence.orf_analysis import find_orfs
from biointel.sequence.parser import parse_sequences_text
from biointel.sequence.protein_analysis import (
    hydropathy_profile,
    protein_statistics,
)
from biointel.sequence.restriction_analysis import (
    COMMON_ENZYMES,
    analyze_restriction_sites,
)
from biointel.sequence.validators import (
    SequenceType,
    detect_sequence_type,
    validate_for_type,
)
from biointel.ui.workflow import read_uploaded_text, render_upload_preflight
from biointel.utils.exceptions import InvalidSequenceError

MAX_SEQUENCE_LENGTH = 200_000

from biointel.ui.components import smart_json
from biointel.ui.theme import apply_theme, hero
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(
    page_title="Sequence Analyzer · BioIntel AI",
    page_icon="🧬",
    layout="wide",
)

apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/1_Sequence_Analyzer.py", key_prefix="1_sequence_analyzer", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("sequence_analyzer", key_prefix="step116_1_Sequence_Analyzer_sequence_analyzer_1", expanded=False)
hero(
    "🧬 Sequence Analyzer",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption("DNA, RNA and protein analysis with explicit validation and downloadable results.")

EXAMPLES = {
    "DNA example": (">example_dna\nATGAAACCCGGGTTTAAATGCGTATCGATCGTACGATCGATGCTAGCTAGCTAA"),
    "Protein example": (">example_protein\nMKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"),
    "Multi-record FASTA": (">record_1\nATGAAATAA\n>record_2\nATGCCCTAG"),
}

coverage_sequence_path = ROOT / "data" / "coverage" / "sequence_library_800.csv"
coverage_sequences = (
    read_csv_cached(coverage_sequence_path) if coverage_sequence_path.is_file() else pd.DataFrame()
)

input_tab, upload_tab = st.tabs(["Paste sequence", "Upload file"])
imported_sequence = st.session_state.pop("imported_sequence", "")
raw_text = imported_sequence

with input_tab:
    input_source = st.radio(
        "Sequence source",
        [
            "Coverage library — 800 records",
            "Built-in examples",
            "Paste custom",
        ],
        horizontal=True,
    )
    text_value = imported_sequence
    if input_source == "Coverage library — 800 records" and not coverage_sequences.empty:
        sequence_type_filter = st.selectbox(
            "Library type",
            ["DNA", "RNA", "Protein"],
        )
        filtered_library = coverage_sequences[
            coverage_sequences["sequence_type"] == sequence_type_filter
        ]
        selected_record_id = st.selectbox(
            "Library record",
            filtered_library["record_id"].tolist(),
            format_func=lambda value: next(
                (
                    f"{value} · {row.family} · {int(row.length):,} characters"
                    for row in filtered_library.itertuples(index=False)
                    if row.record_id == value
                ),
                value,
            ),
        )
        selected_row = filtered_library.loc[
            filtered_library["record_id"] == selected_record_id
        ].iloc[0]
        text_value = (
            f">{selected_row['record_id']}|"
            f"{selected_row['sequence_type']}|"
            f"{selected_row['family']}\n"
            f"{selected_row['sequence']}"
        )
        st.download_button(
            "Download complete 800-record FASTA",
            (ROOT / "data" / "coverage" / "sequence_library_800.fasta").read_bytes(),
            "sequence_library_800.fasta",
            "text/plain",
        )
    elif input_source == "Built-in examples":
        example = st.selectbox(
            "Load an example",
            ["None", *EXAMPLES],
        )
        text_value = imported_sequence or EXAMPLES.get(
            example,
            "",
        )

    raw_text = st.text_area(
        "Raw sequence or FASTA",
        value=text_value,
        height=190,
        help=(f"Maximum selected sequence length: {MAX_SEQUENCE_LENGTH:,} characters."),
    )

with upload_tab:
    uploaded = st.file_uploader(
        "FASTA/FA/FNA/FAA/TXT",
        type=["fasta", "fa", "fna", "faa", "txt"],
    )

render_upload_preflight(
    uploaded,
    key="sequence_analyzer",
    allowed_extensions=["fasta", "fa", "fna", "faa", "txt"],
    soft_limit_mb=2,
    hard_limit_mb=5,
)

if uploaded is not None:
    if uploaded.size > 5 * 1024 * 1024:
        st.error("Uploaded text file exceeds the 5 MB limit.")
        st.stop()
    try:
        raw_text = read_uploaded_text(uploaded)
    except UnicodeDecodeError:
        st.error("The uploaded file is not valid UTF-8 text.")
        st.stop()

if not raw_text.strip():
    st.info("Paste a sequence or upload a file to begin.")
    st.stop()

try:
    records = parse_sequences_text(raw_text)
except InvalidSequenceError as exc:
    st.error(str(exc))
    st.stop()

if len(records) > 1:
    st.success(f"Detected {len(records)} FASTA records.")
    selected_index = st.selectbox(
        "Select record to analyse",
        range(len(records)),
        format_func=lambda index: (
            f"{index + 1}. {records[index].header} ({len(records[index].sequence):,} chars)"
        ),
    )
    parsed = records[int(selected_index)]
else:
    parsed = records[0]

if len(parsed.sequence) > MAX_SEQUENCE_LENGTH:
    st.error(f"Selected sequence exceeds the {MAX_SEQUENCE_LENGTH:,}-character limit.")
    st.stop()

detection = detect_sequence_type(parsed.sequence)
st.write(f"**Header:** {parsed.header}")
st.write(f"**Automatic detection:** {detection.detected_type.value} — {detection.message}")

options = [
    SequenceType.DNA.value,
    SequenceType.RNA.value,
    SequenceType.PROTEIN.value,
]
default_index = {
    SequenceType.RNA: 1,
    SequenceType.PROTEIN: 2,
}.get(detection.detected_type, 0)

selected = st.radio(
    "Analyse as",
    options,
    index=default_index,
    horizontal=True,
)
sequence_type = SequenceType(selected)
invalid = validate_for_type(parsed.sequence, sequence_type)
if invalid:
    st.error(
        "Invalid symbols for the selected type: "
        + ", ".join(f"{character} at {position}" for position, character in invalid[:50])
    )
    if len(invalid) > 50:
        st.caption(f"Showing first 50 of {len(invalid)} invalid positions.")
    st.stop()

stats: dict[str, object]

if sequence_type in (
    SequenceType.DNA,
    SequenceType.RNA,
):
    stats = nucleotide_statistics(
        parsed.sequence,
        is_rna=sequence_type == SequenceType.RNA,
    )
    metric_columns = st.columns(6)
    metric_values = [
        ("Length", f"{stats['length']:,}"),
        ("GC %", f"{stats['gc_percent']:.2f}"),
        ("AT/AU %", f"{stats['at_percent']:.2f}"),
        ("Ambiguous", stats["ambiguous_count"]),
        ("Entropy", f"{stats['entropy_bits']:.3f}"),
        (
            "GC:AT ratio",
            (f"{stats['gc_at_ratio']:.3f}" if stats["gc_at_ratio"] is not None else "Undefined"),
        ),
    ]
    for column, (name, value) in zip(metric_columns, metric_values, strict=True):
        column.metric(name, value)

    counts_df = pd.DataFrame(
        {
            "Base": list(stats["counts"].keys()),
            "Count": list(stats["counts"].values()),
        }
    )
    chart_left, chart_right = st.columns(2)
    chart_left.plotly_chart(
        px.bar(
            counts_df,
            x="Base",
            y="Count",
            title="Nucleotide composition",
        ),
        width="stretch",
    )
    chart_right.plotly_chart(
        px.pie(
            pd.DataFrame(
                {
                    "Class": ["GC", "AT/AU"],
                    "Percent": [
                        stats["gc_percent"],
                        stats["at_percent"],
                    ],
                }
            ),
            names="Class",
            values="Percent",
            title="Canonical-base composition",
        ),
        width="stretch",
    )

    if sequence_type == SequenceType.DNA:
        transformations = dna_transformations(parsed.sequence)
        with st.expander(
            "Complement, reverse complement and transcription",
            expanded=True,
        ):
            st.text_area(
                "Complement",
                transformations["complement"],
                height=90,
            )
            st.text_area(
                "Reverse complement",
                transformations["reverse_complement"],
                height=90,
            )
            st.text_area(
                "mRNA",
                transformations["mrna"],
                height=90,
            )

        genetic_table = st.number_input(
            "NCBI genetic-code table",
            min_value=1,
            max_value=33,
            value=1,
        )
        frame_rows = six_frame_translation(
            parsed.sequence,
            table=int(genetic_table),
        )
        st.subheader("Six-frame translation")
        st.dataframe(
            pd.DataFrame(frame_rows),
            width="stretch",
            hide_index=True,
        )

        orf_left, orf_right = st.columns(2)
        min_orf = orf_left.number_input(
            "Minimum ORF length (nt)",
            min_value=6,
            max_value=10000,
            value=30,
            step=3,
        )
        include_partial = orf_right.checkbox(
            "Include 3′ partial ORFs",
            value=False,
        )
        orfs = find_orfs(
            parsed.sequence,
            min_length_nt=int(min_orf),
            table=int(genetic_table),
            include_partial=include_partial,
        )
        st.subheader("Six-frame ORFs")
        orf_df = pd.DataFrame(orfs)
        if orf_df.empty:
            st.info("No ORF met the selected settings.")
        else:
            st.dataframe(
                orf_df,
                width="stretch",
                hide_index=True,
            )
            st.plotly_chart(
                px.bar(
                    orf_df,
                    x="orf",
                    y="nt_length",
                    color="strand",
                    pattern_shape="complete",
                    title="ORF lengths",
                ),
                width="stretch",
            )
            st.download_button(
                "Download ORFs CSV",
                orf_df.to_csv(index=False),
                "orfs.csv",
                "text/csv",
            )

        codon_df = pd.DataFrame(codon_usage(parsed.sequence))
        st.subheader("Codon usage")
        st.dataframe(
            codon_df,
            width="stretch",
            hide_index=True,
        )
        if not codon_df.empty:
            st.plotly_chart(
                px.bar(
                    codon_df,
                    x="codon",
                    y="count",
                    title="Observed codon frequency",
                ),
                width="stretch",
            )

        window = st.slider(
            "Sliding GC window",
            3,
            max(3, min(500, len(parsed.sequence))),
            min(50, max(3, len(parsed.sequence))),
        )
        gc_df = pd.DataFrame(sliding_gc(parsed.sequence, window))
        skew_df = pd.DataFrame(cumulative_gc_skew(parsed.sequence))
        gc_left, gc_right = st.columns(2)
        if not gc_df.empty:
            gc_left.plotly_chart(
                px.line(
                    gc_df,
                    x="position",
                    y="gc_percent",
                    title="Sliding-window GC content",
                ),
                width="stretch",
            )
        gc_right.plotly_chart(
            px.line(
                skew_df,
                x="position",
                y="cumulative_gc_skew",
                title="Cumulative GC skew",
            ),
            width="stretch",
        )

        with st.expander("Restriction-site analysis"):
            enzymes = st.multiselect(
                "Restriction enzymes",
                list(COMMON_ENZYMES),
                default=list(COMMON_ENZYMES[:6]),
            )
            if enzymes:
                restriction_df = pd.DataFrame(analyze_restriction_sites(parsed.sequence, enzymes))
                st.dataframe(
                    restriction_df,
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    "Download restriction sites CSV",
                    restriction_df.to_csv(index=False),
                    "restriction_sites.csv",
                    "text/csv",
                )

    st.subheader("Motif search")
    motif_mode = st.selectbox(
        "Motif mode",
        [
            "Exact",
            "IUPAC nucleotide",
            "Advanced regex",
        ],
    )
    motif_strands = st.radio("Motif strand", ["Both", "Forward", "Reverse"], horizontal=True)
    motif = st.text_input("Motif/pattern")
    if motif:
        try:
            if motif_mode == "Exact":
                motif_rows = motif_search_both_strands(
                    parsed.sequence, motif, mode="exact", strands=motif_strands.lower()
                ).to_dict("records")
            elif motif_mode == "IUPAC nucleotide":
                motif_rows = motif_search_both_strands(
                    parsed.sequence, motif, mode="iupac", strands=motif_strands.lower()
                ).to_dict("records")
            else:
                motif_rows = find_regex_motif(parsed.sequence, motif)
            st.dataframe(
                pd.DataFrame(motif_rows),
                width="stretch",
                hide_index=True,
            )
            st.caption("Coordinates are one-based and inclusive.")
        except ValueError as exc:
            st.error(str(exc))

else:
    stats = protein_statistics(parsed.sequence)
    metric_columns = st.columns(5)
    metric_values = [
        ("Length", stats["length"]),
        (
            "Molecular weight",
            (
                f"{stats['molecular_weight']:.2f}"
                if stats.get("molecular_weight") is not None
                else "Unavailable"
            ),
        ),
        (
            "Theoretical pI",
            (
                f"{stats['isoelectric_point']:.2f}"
                if stats.get("isoelectric_point") is not None
                else "Unavailable"
            ),
        ),
        (
            "GRAVY",
            (f"{stats['gravy']:.3f}" if stats.get("gravy") is not None else "Unavailable"),
        ),
        (
            "Instability",
            (
                f"{stats['instability_index']:.2f}"
                if stats.get("instability_index") is not None
                else "Unavailable"
            ),
        ),
    ]
    for column, (name, value) in zip(metric_columns, metric_values, strict=True):
        column.metric(name, value)

    if stats.get("warning"):
        st.warning(stats["warning"])

    composition_df = pd.DataFrame(
        [
            {"Amino acid": amino_acid, **values}
            for amino_acid, values in stats["composition"].items()
        ]
    )
    group_df = pd.DataFrame(
        {
            "Group": list(stats["groups_percent"].keys()),
            "Percentage": list(stats["groups_percent"].values()),
        }
    )
    protein_left, protein_right = st.columns(2)
    protein_left.plotly_chart(
        px.bar(
            composition_df,
            x="Amino acid",
            y="count",
            title="Amino-acid composition",
        ),
        width="stretch",
    )
    protein_right.plotly_chart(
        px.bar(
            group_df,
            x="Group",
            y="Percentage",
            title="Amino-acid groups",
        ),
        width="stretch",
    )

    hydro_window = st.slider(
        "Kyte–Doolittle window",
        3,
        max(3, min(51, len(parsed.sequence))),
        min(9, max(3, len(parsed.sequence))),
    )
    hydro_df = pd.DataFrame(hydropathy_profile(parsed.sequence, hydro_window))
    if not hydro_df.empty:
        hydro_figure = px.line(
            hydro_df,
            x="position",
            y="hydropathy",
            title="Hydropathy profile",
        )
        hydro_figure.add_hline(
            y=1.6,
            line_dash="dash",
            annotation_text="Potential hydrophobic region",
        )
        st.plotly_chart(hydro_figure, width="stretch")
        st.caption("Hydrophobic peaks are screening signals, not confirmed transmembrane domains.")

    motif_mode = st.selectbox(
        "Protein motif mode",
        ["Exact", "Advanced regex"],
    )
    motif = st.text_input("Protein motif/pattern")
    if motif:
        try:
            motif_rows = (
                find_exact_motif(parsed.sequence, motif)
                if motif_mode == "Exact"
                else find_regex_motif(parsed.sequence, motif)
            )
            st.dataframe(
                pd.DataFrame(motif_rows),
                width="stretch",
                hide_index=True,
            )
        except ValueError as exc:
            st.error(str(exc))

st.subheader("Sequence quality & complexity")
try:
    qc_profile = sequence_qc_profile(parsed.sequence)
    qc_frame = pd.DataFrame([qc_profile.__dict__])
    st.dataframe(qc_frame, width="stretch", hide_index=True)
    if qc_profile.dust_like_fraction > 0.35:
        st.warning(
            "A high low-complexity fraction was detected; consider masking before homology or motif analysis."
        )
except ValueError as exc:
    st.info(str(exc))

st.subheader("K-mer profile")
kmer_left, kmer_right = st.columns(2)
k_value = kmer_left.slider("k-mer size", 1, 6, 3)
top_kmers = kmer_right.slider("Top k-mers", 5, 100, 25, 5)
kmer_df = pd.DataFrame(kmer_frequency(parsed.sequence, k=int(k_value), top_n=int(top_kmers)))
if kmer_df.empty:
    st.info("Sequence is shorter than the selected k-mer size.")
else:
    st.dataframe(kmer_df, width="stretch", hide_index=True)
    st.plotly_chart(
        px.bar(
            kmer_df,
            x="kmer",
            y="frequency",
            title=f"Top {len(kmer_df)} overlapping {k_value}-mers",
        ),
        width="stretch",
    )
    st.download_button(
        "Download k-mer CSV",
        kmer_df.to_csv(index=False),
        f"kmer_{k_value}_profile.csv",
        "text/csv",
    )

if sequence_type == SequenceType.DNA and len(parsed.sequence) <= 500:
    with st.expander("DNA oligo properties"):
        sodium = st.number_input(
            "Sodium concentration (mM)",
            min_value=0.1,
            value=50.0,
        )
        concentration = st.number_input(
            "Strand concentration (nM)",
            min_value=0.1,
            value=250.0,
        )
        try:
            oligo = dna_oligo_properties(
                parsed.sequence,
                sodium_millimolar=float(sodium),
                strand_concentration_nanormolar=float(concentration),
            )
            smart_json(oligo)
            st.caption(
                "Melting temperatures are estimates and depend on salt, "
                "strand concentration, sequence context and laboratory conditions."
            )
        except ValueError as exc:
            st.warning(str(exc))

st.divider()
st.download_button(
    "Download summary JSON",
    json.dumps(stats, indent=2, default=str),
    "sequence_summary.json",
    "application/json",
)
st.download_button(
    "Download cleaned FASTA",
    f">{parsed.header}\n{parsed.sequence}\n",
    "cleaned_sequence.fasta",
    "text/plain",
)
st.download_button(
    "Download PDF summary",
    build_summary_pdf(
        f"BioIntel AI — {sequence_type.value} Summary",
        stats,
    ),
    "sequence_summary.pdf",
    "application/pdf",
)
st.info("Local mode processes inputs on this computer and does not intentionally retain them.")
st.caption("Research use only. Verify results with curated databases and laboratory methods.")


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("sequence", expanded=False)

# Step 115 non-chart visual: sequence_feature_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("sequence_feature_track", key_prefix="step115_1_Sequence_Analyzer_sequence_feature_track", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_SEQUENCE_ANALYZER
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('sequence_analyzer', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='sequence_analyzer', title='Sequence Analyzer', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='sequence_analyzer', title='Sequence Analyzer', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
