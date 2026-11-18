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

from biointel.microbiology.metagenomics import (
    approximate_ani,
    beta_diversity,
    diversity_metrics,
    kmer_profile,
    validate_abundance_frame,
)
from biointel.projects.metagenomics_pipeline import pcoa
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_csv_cached
from biointel.step121.panels import render_microbiology_isolate_upgrade
from biointel.ui.theme import apply_theme, hero, insight_callout
from biointel.ui.workflow import (
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Microbiology & Metagenomics · BioIntel AI", page_icon="🦠", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/65_Microbiology_Metagenomics.py", key_prefix="65_microbiology_metagenomics", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("microbiology", key_prefix="step116_65_Microbiology_Metagenomics_microbiology_1", expanded=False)
hero(
    "Microbiology & Metagenomics Rapid Screen",
    "Validate abundance tables, explore alpha/beta diversity and taxonomy, and screen compact genome panels with k-mer similarity and containment metrics.",
    eyebrow="BioIntel AI · Microbiology",
    chips=["Strict abundance QC", "Alpha + beta diversity", "Taxonomy aggregation", "k-mer containment"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="Rapid local screen only. Use the Professional Metagenomics Pipeline and validated classification/ANI tools for confirmatory or publication-grade analysis.",
)
render_methodology(
    method="Strict non-negative abundance validation, diversity geometry and lightweight k-mer genome screening.",
    assumptions=["Taxa are rows and selected samples are non-negative abundance measurements."],
    limitations=["This page does not classify raw reads or provide alignment-based ANI."],
    validation=["Use negative controls and metadata.", "Confirm genome similarity using FastANI, Mash or whole-genome alignment."],
)

abundance_tab, genome_tab = st.tabs(["Community abundance", "Genome comparison"])
with abundance_tab:
    upload = st.file_uploader("Taxon abundance CSV/TSV", type=["csv", "tsv"], key="microbiome_upload")
    render_upload_preflight(upload, key="microbiome_abundance", allowed_extensions=["csv", "tsv"], soft_limit_mb=25, hard_limit_mb=150)
    frame = read_uploaded_table(upload) if upload else read_csv_cached(DEMO / "demo_taxonomy.csv")
    taxon_column = st.selectbox("Taxon column", frame.columns, index=0)
    sample_columns = [column for column in frame.columns if column != taxon_column and pd.api.types.is_numeric_dtype(frame[column])]
    selected_samples = st.multiselect("Samples", sample_columns, default=sample_columns)
    if not selected_samples:
        st.warning("Select at least one sample before analysis.")
        st.stop()
    taxonomy_delimiter = st.text_input("Optional taxonomy delimiter", ";", help="Use rank aggregation for strings such as k__;p__;c__;o__;f__;g__;s__.")
    rank_level = st.selectbox("Taxonomic aggregation", ["Original label", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"])
    try:
        validated = validate_abundance_frame(frame, taxon_column=taxon_column, abundance_columns=selected_samples)
    except Exception as exc:
        st.error(f"Abundance validation failed: {exc}")
        st.stop()
    if rank_level != "Original label":
        rank_index = ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"].index(rank_level)
        split = validated[taxon_column].astype(str).str.split(taxonomy_delimiter)
        validated[taxon_column] = split.map(lambda values: values[rank_index].strip() if len(values) > rank_index and values[rank_index].strip() else f"Unclassified {rank_level}")
        validated = validated.groupby(taxon_column, as_index=False)[selected_samples].sum()
    max_total = float(validated[selected_samples].sum(axis=1).max()) if len(validated) else 0.0
    minimum_total = st.number_input("Minimum total abundance", 0.0, max(max_total, 0.0), 0.0)
    filtered = validated[validated[selected_samples].sum(axis=1) >= float(minimum_total)].copy()
    metadata_upload = st.file_uploader("Optional sample metadata CSV/TSV", type=["csv", "tsv"], key="microbiology_metadata")
    metadata = read_uploaded_table(metadata_upload) if metadata_upload else pd.DataFrame({"sample": selected_samples, "group": "All samples"})
    if "sample" not in metadata.columns:
        st.error("Metadata requires a sample column.")
        st.stop()
    with analysis_run("Calculating strict diversity metrics"):
        diversity = diversity_metrics(filtered, taxon_column=taxon_column, abundance_columns=selected_samples)
        bray = beta_diversity(filtered, taxon_column=taxon_column, abundance_columns=selected_samples, metric="braycurtis")
        jaccard = beta_diversity(filtered, taxon_column=taxon_column, abundance_columns=selected_samples, metric="jaccard")
        ordination, variance = pcoa(bray)
        ordination = ordination.merge(metadata, on="sample", how="left")
    metric_cards([
        ("Samples", len(selected_samples), None),
        ("Retained taxa", len(filtered), None),
        ("Median Shannon", f"{diversity['shannon'].median():.3f}", None),
        ("PCoA explained", f"{variance.get('PCoA1', 0) + variance.get('PCoA2', 0):.1f}%", None),
    ])
    smart_dataframe(diversity, height=280)
    color = "group" if "group" in ordination.columns else None
    st.plotly_chart(px.scatter(ordination, x="PCoA1", y="PCoA2", color=color, hover_name="sample", title="Bray–Curtis PCoA"), width="stretch")
    distance_choice = st.radio("Distance matrix", ["Bray-Curtis", "Jaccard"], horizontal=True)
    chosen_distance = bray if distance_choice == "Bray-Curtis" else jaccard
    st.plotly_chart(px.imshow(chosen_distance, text_auto=".2f", aspect="auto", title=f"{distance_choice} distance"), width="stretch")
    top_n = st.slider("Top taxa", 5, max(5, min(100, len(filtered))), min(20, max(5, len(filtered))))
    top = filtered.assign(total=filtered[selected_samples].sum(axis=1)).nlargest(min(top_n, len(filtered)), "total")
    long = top.melt(id_vars=[taxon_column], value_vars=selected_samples, var_name="sample", value_name="abundance")
    st.plotly_chart(px.bar(long, x="sample", y="abundance", color=taxon_column, title=f"Top taxa · {rank_level}"), width="stretch")
    smart_dataframe(filtered, height=400)
    st.download_button("Download validated abundance table", filtered.to_csv(index=False), "microbiology_abundance_validated.csv", "text/csv", width="stretch")
    insight_callout("Next step", "Use the Professional Metagenomics Pipeline for compositional transforms, PERMANOVA, contamination controls, covariates and reproducibility bundles.", "info")

with genome_tab:
    default_fasta = ">Genome_A\n" + "ATGCGTACGTAGCTAGCTAGCGGATCCGATCGATCGATCGATCG" * 3 + "\n>Genome_B\n" + "ATGCGTACGTAGCTAGCTAGCGGATCCGATCGATCGTTTGATCG" * 3
    with st.form("genome_compare_form"):
        fasta_text = st.text_area("Genome/contig FASTA panel", default_fasta, height=240)
        k = st.slider("k-mer size", 3, 31, 15)
        run = st.form_submit_button("Compare genome panel", type="primary", width="stretch")
    if run:
        try:
            records = parse_sequences_text(fasta_text)
            if len(records) < 2:
                raise ValueError("Provide at least two FASTA records.")
            if len(records) > 30:
                raise ValueError("Rapid screen supports at most 30 sequences per run.")
            rows = []
            with analysis_run("Calculating pairwise k-mer containment and ANI proxies"):
                for left_index, left in enumerate(records):
                    for right in records[left_index + 1 :]:
                        rows.append({"sequence_a": left.identifier, "sequence_b": right.identifier, **approximate_ani(left.sequence, right.sequence, k=int(k))})
            comparisons = pd.DataFrame(rows)
            smart_dataframe(comparisons, height=440)
            matrix = pd.DataFrame(1.0, index=[record.identifier for record in records], columns=[record.identifier for record in records])
            for row in rows:
                matrix.loc[row["sequence_a"], row["sequence_b"]] = matrix.loc[row["sequence_b"], row["sequence_a"]] = row["jaccard"]
            st.plotly_chart(px.imshow(matrix, text_auto=".2f", aspect="auto", title="Pairwise k-mer Jaccard similarity"), width="stretch")
            profiles = pd.DataFrame([{"sequence": record.identifier, "length": len(record.sequence), "distinct_kmers": len(kmer_profile(record.sequence, k=int(k)))} for record in records])
            smart_dataframe(profiles, height=260)
            st.download_button("Download genome comparison", comparisons.to_csv(index=False), "microbiology_genome_screen.csv", "text/csv", width="stretch")
        except Exception as exc:
            st.error(f"Genome comparison could not run: {exc}")
render_microbiology_isolate_upgrade(key_prefix="step121_microbiology_isolate")

# STEP127_SCIENTIFIC_DEPTH_MICROBIOLOGY_METAGENOMICS
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('microbiology_metagenomics', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='microbiology_metagenomics', title='Microbiology & Metagenomics', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='microbiology_metagenomics', title='Microbiology & Metagenomics', category='Lab Analytics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
