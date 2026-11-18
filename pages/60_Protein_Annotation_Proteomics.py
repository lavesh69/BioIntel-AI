from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.proteomics.advanced import (
    differential_protein_abundance,
    enzyme_class_hints,
    peptide_sequence_coverage,
    proteomics_summary,
    reference_similarity_search,
    scan_domain_signatures,
    tryptic_digest,
    validate_quantitative_proteomics,
)
from biointel.proteomics.annotation import annotate_protein, annotation_dict
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.components import (
    metric_cards,
    result_summary,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_text_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_table,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Protein Annotation & Proteomics · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/60_Protein_Annotation_Proteomics.py", key_prefix="60_protein_annotation_proteomics", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("protein_annotation", key_prefix="step116_60_Protein_Annotation_Proteomics_protein_annotation_1", expanded=False)
hero(
    "Protein Annotation & Proteomics",
    "Inspect sequence-level properties, topology heuristics, motif hints and batch annotation outputs with clear positional context.",
    eyebrow="BioIntel AI · Protein Workbench",
    chips=["FASTA upload", "Batch annotation", "Topology tracks", "CSV export"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="Signal peptide, transmembrane and disorder calls are lightweight screening heuristics. Confirm with InterPro/Pfam/DeepTMHMM or equivalent specialist tools.",
)

render_methodology(
    method="Sequence-composition, motif and topology heuristics over uploaded or bundled protein FASTA records.",
    assumptions=[
        "Sequences use valid amino-acid symbols and identifiers are unique.",
    ],
    limitations=[
        "Motif and topology calls are heuristic and database-free.",
        "No peptide-spectrum or quantitative proteomics inference is performed.",
    ],
    validation=[
        "Confirm domains and topology with versioned specialist predictors.",
        "Review isoform and organism context before interpretation.",
    ],
)

uploaded = st.file_uploader("Protein FASTA", type=["fasta", "fa", "faa"])
protein_upload_profile = render_upload_preflight(
    uploaded,
    key="protein_fasta",
    allowed_extensions=["fasta", "fa", "faa"],
    soft_limit_mb=15,
    hard_limit_mb=100,
)
text = (
    read_uploaded_text(uploaded)
    if uploaded
    else read_text_cached(DEMO / "demo_protein_panel.fasta")
)
records = parse_sequences_text(text, max_records=10_000)
labels = [record.header or f"protein_{index + 1}" for index, record in enumerate(records)]

controls = st.columns([2, 1, 1])
selected_index = controls[0].selectbox(
    "Protein record", list(range(len(records))), format_func=lambda index: labels[index]
)
batch_limit = controls[1].number_input(
    "Batch rows", 1, min(1000, len(records)), min(200, len(records))
)
show_sequence = controls[2].toggle("Show sequence", value=True)
sequence = records[selected_index].sequence

with analysis_run("Annotating selected protein and scanning local references"):
    selected = annotation_dict(annotate_protein(sequence))
    domain_hints = scan_domain_signatures(sequence)
    enzyme_hints = enzyme_class_hints(sequence)
    digest = tryptic_digest(sequence, missed_cleavages=1)
    reference_text = read_text_cached(ROOT / "data" / "libraries" / "protein_library_160.fasta")
    reference_records = parse_sequences_text(reference_text, max_records=500)
    similarity_hits = reference_similarity_search(sequence, reference_records, maximum_hits=10)
metric_cards(
    [
        ("Reference proteins", f"{len(records):,}", None),
        ("Selected length", f"{len(sequence):,} aa", None),
        ("Molecular weight", f"{selected.get('molecular_weight', 0):,.1f}", None),
        ("pI", f"{selected.get('isoelectric_point', 0):.2f}", None),
    ]
)
if show_sequence:
    st.code(sequence, language="text")

section_title("Selected-protein interpretation", "🔬")
selected_tabs = st.tabs(
    [
        "Core annotation",
        "Domain & enzyme hints",
        "Local homology",
        "Tryptic digest",
        "Peptide coverage",
    ]
)
with selected_tabs[0]:
    result_summary(selected, title=labels[selected_index])
with selected_tabs[1]:
    smart_dataframe(domain_hints, height=320)
    smart_dataframe(enzyme_hints, height=220)
    st.caption(
        "Domain/enzyme calls are local motif screens. Confirm final assignments with a versioned profile-HMM/domain database."
    )
with selected_tabs[2]:
    smart_dataframe(similarity_hits, height=420)
    st.download_button(
        "Download local similarity hits",
        similarity_hits.to_csv(index=False),
        "protein_similarity_hits.csv",
        "text/csv",
        width="stretch",
    )
with selected_tabs[3]:
    smart_dataframe(digest, height=420)
    st.download_button(
        "Download in-silico tryptic peptides",
        digest.to_csv(index=False),
        "tryptic_digest.csv",
        "text/csv",
        width="stretch",
    )
with selected_tabs[4]:
    peptide_text = st.text_area(
        "Observed peptide sequences (one per line)", "", key="protein_peptide_coverage"
    )
    peptides = [value.strip() for value in peptide_text.splitlines() if value.strip()]
    if peptides:
        peptide_hits, coverage_summary = peptide_sequence_coverage(sequence, peptides)
        result_summary(coverage_summary, title="Sequence coverage")
        smart_dataframe(peptide_hits, height=320)

track_rows = []
for key, value in selected.items():
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                track_rows.append({"Feature": key, **item})
            else:
                track_rows.append({"Feature": key, "Position / value": item})
if track_rows:
    smart_dataframe(track_rows, height=330)

with st.form("protein_batch_form"):
    st.caption("Batch annotation is limited intentionally so large FASTA files remain responsive.")
    run_batch = st.form_submit_button(
        f"Annotate first {int(batch_limit)} proteins", type="primary", width="stretch"
    )
if run_batch:
    with analysis_run("Running batch protein annotation"):
        rows = []
        for label, record in zip(labels[: int(batch_limit)], records[: int(batch_limit)]):
            payload = annotation_dict(annotate_protein(record.sequence))
            rows.append(
                {
                    "Protein": label,
                    "Length": len(record.sequence),
                    "Molecular weight": payload.get("molecular_weight"),
                    "pI": payload.get("isoelectric_point"),
                    "Signal peptide": bool(payload.get("signal_peptide")),
                    "TM regions": len(payload.get("transmembrane_regions", []) or []),
                    "Disorder regions": len(payload.get("disorder_regions", []) or []),
                    "PTM sites": len(payload.get("ptm_sites", []) or []),
                }
            )
        batch = pd.DataFrame(rows)
    smart_dataframe(batch, height=520)
    render_generic_visual_explorer(
        batch,
        key="protein_batch_visuals",
        heading="Protein annotation visual analytics",
    )
    charts = st.columns(2)
    charts[0].plotly_chart(
        px.histogram(batch, x="Length", nbins=30, title="Protein-length distribution"),
        width="stretch",
    )
    charts[1].plotly_chart(
        px.scatter(
            batch,
            x="Length",
            y="Molecular weight",
            color="Signal peptide",
            hover_data=["Protein"],
            title="Length vs molecular weight",
        ),
        width="stretch",
    )
    st.download_button(
        "Download batch annotation",
        batch.to_csv(index=False),
        "protein_annotations.csv",
        "text/csv",
        width="stretch",
    )


section_title("Quantitative proteomics", "📊")
quant_upload = st.file_uploader(
    "Long-format protein intensity table (protein, sample, intensity)",
    type=["csv", "tsv"],
    key="quantitative_proteomics",
)
if quant_upload is not None:
    try:
        quant = read_uploaded_table(quant_upload)
        quant = validate_quantitative_proteomics(quant)
        quant_summary = proteomics_summary(quant)
        metric_cards(
            [
                ("Proteins", quant_summary.proteins, None),
                ("Samples", quant_summary.samples, None),
                ("Quantified values", quant_summary.quantified_values, None),
                ("Missing fraction", f"{quant_summary.missing_fraction * 100:.2f}%", None),
            ]
        )
        samples = sorted(quant["sample"].astype(str).unique())
        default_groups = pd.DataFrame(
            {
                "sample": samples,
                "group": [
                    "Group A" if index < max(2, len(samples) // 2) else "Group B"
                    for index in range(len(samples))
                ],
            }
        )
        metadata = st.data_editor(
            default_groups, hide_index=True, width="stretch", key="proteomics_design"
        )
        groups = list(dict.fromkeys(metadata["group"].astype(str)))
        if len(groups) >= 2 and st.button("Run differential protein abundance", type="primary"):
            with analysis_run("Running protein-abundance comparison"):
                abundance = differential_protein_abundance(
                    quant, metadata, group_a=groups[0], group_b=groups[1]
                )
            smart_dataframe(abundance, height=500)
            render_generic_visual_explorer(
                abundance,
                key="proteomics_abundance_visuals",
                heading="Differential proteomics visual analytics",
            )
            st.plotly_chart(
                px.scatter(
                    abundance,
                    x="log2_fold_change",
                    y=-pd.to_numeric(abundance["fdr_bh"], errors="coerce")
                    .clip(lower=1e-300)
                    .map(lambda value: __import__("math").log10(value)),
                    hover_data=["protein"],
                    title=f"{groups[1]} vs {groups[0]}",
                ),
                width="stretch",
            )
            st.download_button(
                "Download differential proteins",
                abundance.to_csv(index=False),
                "differential_proteins.csv",
                "text/csv",
                width="stretch",
            )
    except Exception as exc:
        st.error(f"Quantitative proteomics analysis stopped: {exc}")

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("mass_spectrometry", key_prefix="step110_60_Protein_Annotation_Proteomics_mass_spectrometry")
_render_step110_viewer("sequence_track", key_prefix="step110_60_Protein_Annotation_Proteomics_sequence_track")


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("protein", expanded=False)

# Step 115 non-chart visual: mass_spectrum_inspector
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("mass_spectrum_inspector", key_prefix="step115_60_Protein_Annotation_Proteomics_mass_spectrum_inspector", expanded=False)

# Step 115 non-chart visual: sequence_feature_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("sequence_feature_track", key_prefix="step115_60_Protein_Annotation_Proteomics_sequence_feature_track", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_PROTEIN_ANNOTATION_PROTEOMICS
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('protein_annotation_proteomics', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='protein_annotation', title='Protein Annotation & Proteomics', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='protein_annotation', title='Protein Annotation & Proteomics', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
