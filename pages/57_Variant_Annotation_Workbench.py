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

from biointel.genomics.annotations import annotation_summary, overlap_features, parse_gff
from biointel.genomics.variant_advanced import (
    annotate_feature_context,
    genome_build_audit,
    normalize_variant_frame,
    parse_fasta_reference,
    structural_variant_table,
    trio_mendelian_audit,
    validate_reference_alleles,
)
from biointel.genomics.variants import (
    decode_vcf_bytes,
    filter_variants,
    genotype_matrix,
    mask_low_quality_genotypes,
    parse_vcf,
    sample_summary,
    variant_summary,
)
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_text_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Variant & Annotation Workbench · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/57_Variant_Annotation_Workbench.py", key_prefix="57_variant_annotation_workbench", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("variant_workbench", key_prefix="step116_57_Variant_Annotation_Workbench_variant_workbench_1", expanded=False)
hero(
    "Variant & Annotation Workbench",
    "Inspect plain or gzip-compressed VCF files, sample call rates, genotype matrices, INFO-derived depth/frequency, chromosome distributions, and overlapping GFF/GTF features.",
    eyebrow="Quality-Hardened · Production Genomics Workbench",
    chips=["VCF.gz", "Multi-sample genotypes", "INFO fields", "GFF/GTF", "Interval queries"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False)

render_methodology(
    method="Allele-aware VCF profiling, genotype QC and GFF/GTF feature inspection.",
    assumptions=[
        "Genome build and chromosome naming are internally consistent.",
        "FILTER, FORMAT and INFO fields follow VCF conventions.",
    ],
    limitations=[
        "No clinical interpretation or full transcript consequence engine is implied.",
        "Indexed region querying is preferred for very large callsets.",
    ],
    validation=[
        "Normalize variants against the declared reference build.",
        "Confirm consequences with a versioned annotation pipeline.",
    ],
)

vcf_tab, gff_tab = st.tabs(["VCF variants", "Genome annotations"])
with vcf_tab:
    with st.form("vcf_load_form"):
        uploaded = st.file_uploader("VCF / VCF.gz", type=["vcf", "gz"], key="step33_vcf")
        vcf_upload_profile = render_upload_preflight(
            uploaded,
            key="variant_vcf",
            allowed_extensions=["vcf", "vcf.gz", "gz"],
            soft_limit_mb=50,
            hard_limit_mb=500,
        )
        controls = st.columns(3)
        maximum_variants = controls[0].number_input(
            "Maximum variants to load", 1_000, 1_000_000, 250_000, 1_000
        )
        genome_build = controls[1].selectbox(
            "Declared genome build", ["GRCh38", "GRCh37", "GRCm39"]
        )
        normalize_variants = controls[2].toggle("Normalize alleles", value=True)
        reference_upload = st.file_uploader(
            "Optional matching reference FASTA for REF validation and repeat-aware left alignment",
            type=["fa", "fasta", "fna"],
            key="step59_variant_reference",
        )
        load_vcf = st.form_submit_button(
            "Load, normalize and profile VCF", type="primary", width="stretch"
        )
    if load_vcf or "step33_vcf_data" not in st.session_state:
        try:
            text = (
                decode_vcf_bytes(uploaded.getvalue(), filename=uploaded.name)
                if uploaded
                else read_text_cached(DEMO / "demo_variants.vcf")
            )
            with analysis_run("Parsing, normalizing and profiling VCF"):
                frame = parse_vcf(text, max_variants=int(maximum_variants))
                references = None
                if reference_upload is not None:
                    references = parse_fasta_reference(
                        reference_upload.getvalue().decode("utf-8-sig")
                    )
                if normalize_variants:
                    frame, normalization_audit = normalize_variant_frame(
                        frame, reference_sequences=references
                    )
                else:
                    normalization_audit = pd.DataFrame()
                build_audit = genome_build_audit(frame, genome_build)
                if references is not None:
                    reference_audit, reference_summary = validate_reference_alleles(
                        frame, references
                    )
                else:
                    reference_audit, reference_summary = pd.DataFrame(), None
                summary = variant_summary(frame)
            st.session_state["step33_vcf_data"] = frame
            st.session_state["step33_vcf_summary"] = summary
            st.session_state["step59_vcf_normalization_audit"] = normalization_audit
            st.session_state["step59_vcf_build_audit"] = build_audit
            st.session_state["step59_vcf_reference_audit"] = reference_audit
            st.session_state["step59_vcf_reference_summary"] = reference_summary
            st.session_state["step59_vcf_build"] = genome_build
        except (OSError, ValueError) as exc:
            st.error(str(exc))

    frame = st.session_state.get("step33_vcf_data")
    summary = st.session_state.get("step33_vcf_summary")
    if frame is not None and summary is not None:
        metric_cards(
            [
                ("Variants", f"{summary.variants:,}", None),
                ("SNPs", f"{summary.snps:,}", None),
                ("Indels", f"{summary.indels:,}", "Insertions, deletions and complex alleles"),
                ("PASS", f"{summary.pass_variants:,}", None),
                ("Mean QUAL", f"{summary.mean_quality:.1f}", None),
                ("Samples", f"{summary.samples:,}", None),
            ]
        )
        with st.form("variant_filter_form"):
            cols = st.columns(3)
            quality = cols[0].slider("Minimum QUAL", 0, 500, 20)
            minimum_depth = cols[1].number_input("Minimum INFO/DP", 0, 1_000_000, 0)
            maximum_af = cols[2].number_input("Maximum INFO/AF", 0.0, 1.0, 1.0, 0.01)
            cols = st.columns(3)
            require_pass = cols[0].toggle("Require PASS", value=True)
            variant_types = cols[1].multiselect(
                "Variant types", sorted(frame["variant_type"].dropna().unique()), default=[]
            )
            chromosomes = cols[2].multiselect(
                "Chromosomes", sorted(frame["chrom"].astype(str).unique()), default=[]
            )
            call_filters = st.columns(3)
            minimum_sample_dp = call_filters[0].number_input("Minimum FORMAT/DP", 0, 10000, 0)
            minimum_gq = call_filters[1].number_input("Minimum FORMAT/GQ", 0.0, 999.0, 0.0, 1.0)
            minimum_alt_depth = call_filters[2].number_input(
                "Minimum alternate FORMAT/AD", 0, 10000, 0
            )
            apply_filters = st.form_submit_button("Apply filters", type="primary", width="stretch")
        filtered = filter_variants(
            frame,
            minimum_quality=float(quality),
            require_pass=require_pass,
            minimum_depth=int(minimum_depth) or None,
            maximum_allele_frequency=float(maximum_af) if maximum_af < 1 else None,
            variant_types=variant_types or None,
            chromosomes=chromosomes or None,
        )
        filtered = mask_low_quality_genotypes(
            filtered,
            minimum_sample_depth=int(minimum_sample_dp) or None,
            minimum_genotype_quality=float(minimum_gq) or None,
            minimum_alt_depth=int(minimum_alt_depth) or None,
        )
        if "source_multiallelic" in frame and bool(frame["source_multiallelic"].any()):
            st.info(
                f"Multiallelic source records were split into allele-specific rows. "
                f"Original multiallelic records: {summary.multiallelic:,}."
            )

        charts = st.columns(3)
        variant_counts = frame.groupby("variant_type").size().reset_index(name="Count")
        charts[0].plotly_chart(
            px.bar(variant_counts, x="variant_type", y="Count", title="Variant types"),
            width="stretch",
        )
        charts[1].plotly_chart(
            px.histogram(frame, x="quality", nbins=35, title="QUAL distribution"), width="stretch"
        )
        chrom_counts = frame.groupby("chromosome").size().reset_index(name="Count").head(40)
        charts[2].plotly_chart(
            px.bar(chrom_counts, x="chromosome", y="Count", title="Variants by chromosome"),
            width="stretch",
        )

        result_tabs = st.tabs(
            [
                "Filtered variants",
                "Samples",
                "Genotype matrix",
                "INFO fields",
                "Normalization & reference",
                "Structural variants",
                "Feature context",
            ]
        )
        with result_tabs[0]:
            section_title(f"Filtered variants · {len(filtered):,}", "🔎")
            display_columns = [
                "chrom",
                "pos",
                "id",
                "ref",
                "alt",
                "variant_type",
                "qual",
                "filter",
                "depth",
                "allele_frequency",
            ]
            smart_dataframe(
                filtered[[column for column in display_columns if column in filtered]], height=500
            )
            st.download_button(
                "Download filtered variants",
                filtered.to_csv(index=False),
                "filtered_variants.csv",
                "text/csv",
                width="stretch",
            )
        with result_tabs[1]:
            samples = sample_summary(filtered)
            if samples.empty:
                st.info("This VCF contains no sample genotype columns.")
            else:
                smart_dataframe(samples, height=420)
                st.plotly_chart(
                    px.bar(
                        samples,
                        x="sample",
                        y="call_rate_percent",
                        title="Sample call rate",
                        range_y=[0, 100],
                    ),
                    width="stretch",
                )
        with result_tabs[2]:
            available_samples = sorted(
                {name for sample_map in filtered["samples"] for name in (sample_map or {})}
            )
            selected_samples = st.multiselect(
                "Samples to display",
                available_samples,
                default=available_samples[: min(8, len(available_samples))],
            )
            matrix = genotype_matrix(filtered.head(5_000), sample_names=selected_samples)
            smart_dataframe(matrix, height=500)
            st.download_button(
                "Download genotype matrix",
                matrix.to_csv(index=False),
                "genotype_matrix.csv",
                "text/csv",
                width="stretch",
            )
        with result_tabs[3]:
            info_rows = []
            for row in filtered.head(5_000).itertuples():
                for key, value in (row.info or {}).items():
                    info_rows.append(
                        {"chrom": row.chrom, "pos": row.pos, "field": key, "value": value}
                    )
            smart_dataframe(pd.DataFrame(info_rows), height=500)
        with result_tabs[4]:
            normalization_audit = st.session_state.get(
                "step59_vcf_normalization_audit", pd.DataFrame()
            )
            build_audit = st.session_state.get("step59_vcf_build_audit", pd.DataFrame())
            reference_audit = st.session_state.get("step59_vcf_reference_audit", pd.DataFrame())
            reference_summary = st.session_state.get("step59_vcf_reference_summary")
            if reference_summary is not None:
                metric_cards(
                    [
                        (
                            "REF matches",
                            f"{reference_summary.reference_matches:,}",
                            f"{reference_summary.match_percent:.2f}%",
                        ),
                        (
                            "REF mismatches",
                            f"{reference_summary.reference_mismatches:,}",
                            "Review build/reference",
                        ),
                        ("Missing contigs", f"{reference_summary.missing_contigs:,}", None),
                        ("Out of range", f"{reference_summary.out_of_range:,}", None),
                    ]
                )
            if not normalization_audit.empty:
                st.caption(
                    f"Normalized rows changed: {int(normalization_audit['changed'].sum()):,}"
                )
                smart_dataframe(normalization_audit, height=300)
            smart_dataframe(build_audit, height=260)
            if not reference_audit.empty:
                smart_dataframe(reference_audit, height=320)
        with result_tabs[5]:
            sv = structural_variant_table(filtered)
            if sv.empty:
                st.info("No symbolic or INFO/SVTYPE structural variants were detected.")
            else:
                smart_dataframe(sv, height=500)
                st.download_button(
                    "Download structural variants",
                    sv.to_csv(index=False),
                    "structural_variants.csv",
                    "text/csv",
                    width="stretch",
                )
        with result_tabs[6]:
            annotations = st.session_state.get("step33_gff_data")
            if annotations is None:
                st.info(
                    "Load a GFF/GTF in the Genome annotations tab, then rerun to annotate variant feature context."
                )
            else:
                context = annotate_feature_context(filtered.head(100_000), annotations)
                smart_dataframe(context, height=500)
                st.download_button(
                    "Download feature-context annotation",
                    context.to_csv(index=False),
                    "variant_feature_context.csv",
                    "text/csv",
                    width="stretch",
                )

        available_samples = sorted(
            {name for sample_map in filtered["samples"] for name in (sample_map or {})}
        )
        if len(available_samples) >= 3:
            with st.expander("Trio Mendelian consistency screen"):
                trio_cols = st.columns(3)
                child = trio_cols[0].selectbox("Child", available_samples, key="trio_child")
                mother = trio_cols[1].selectbox(
                    "Mother",
                    available_samples,
                    index=min(1, len(available_samples) - 1),
                    key="trio_mother",
                )
                father = trio_cols[2].selectbox(
                    "Father",
                    available_samples,
                    index=min(2, len(available_samples) - 1),
                    key="trio_father",
                )
                if len({child, mother, father}) < 3:
                    st.warning("Select three different samples.")
                else:
                    trio = trio_mendelian_audit(
                        filtered.head(100_000), child=child, mother=mother, father=father
                    )
                    smart_dataframe(trio, height=360)
                    st.download_button(
                        "Download trio audit",
                        trio.to_csv(index=False),
                        "trio_mendelian_audit.csv",
                        "text/csv",
                        width="stretch",
                    )

with gff_tab:
    with st.form("gff_load_form"):
        annotation_source = st.radio(
            "Annotation source",
            ["Bundled demonstration annotation", "Upload GFF/GTF"],
            horizontal=True,
        )
        uploaded = st.file_uploader(
            "GFF3 or GTF",
            type=["gff", "gff3", "gtf"],
            key="step33_gff",
            disabled=annotation_source != "Upload GFF/GTF",
        )
        gff_upload_profile = render_upload_preflight(
            uploaded,
            key="variant_gff",
            allowed_extensions=["gff", "gff3", "gtf"],
            soft_limit_mb=50,
            hard_limit_mb=500,
        )
        load_gff = st.form_submit_button("Load genome annotation", type="primary", width="stretch")
    if load_gff:
        try:
            if annotation_source == "Upload GFF/GTF" and uploaded is None:
                raise ValueError("Choose a GFF/GTF file before loading the annotation.")
            text = (
                read_uploaded_text(uploaded)
                if annotation_source == "Upload GFF/GTF" and uploaded is not None
                else read_text_cached(DEMO / "demo_annotations.gff3")
            )
            with analysis_run("Parsing genome annotations"):
                frame = parse_gff(text)
                summary = annotation_summary(frame)
            st.session_state["step33_gff_data"] = frame
            st.session_state["step33_gff_summary"] = summary
        except (OSError, ValueError) as exc:
            st.error(str(exc))
    elif "step33_gff_data" not in st.session_state:
        st.info(
            "Genome annotations are loaded only after you press the button. This prevents a large "
            "GFF/GTF audit from running automatically when the page opens."
        )
    frame = st.session_state.get("step33_gff_data")
    summary = st.session_state.get("step33_gff_summary")
    if frame is not None and summary is not None:
        metric_cards(
            [
                ("Features", f"{summary.features:,}", None),
                ("Genes", f"{summary.genes:,}", None),
                ("Transcripts", f"{summary.transcripts:,}", None),
                ("Exons", f"{summary.exons:,}", None),
                ("CDS", f"{summary.cds:,}", None),
                ("Sequences", f"{summary.sequence_regions:,}", None),
            ]
        )
        feature_counts = (
            frame.groupby("type")
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
        )
        st.plotly_chart(
            px.bar(
                feature_counts.head(30), x="type", y="Count", title="Annotation feature composition"
            ),
            width="stretch",
        )
        with st.form("interval_query"):
            cols = st.columns(3)
            seqid = cols[0].selectbox(
                "Sequence / chromosome", sorted(frame["seqid"].astype(str).unique())
            )
            maximum_end = int(frame.loc[frame["seqid"].astype(str) == str(seqid), "end"].max())
            start = cols[1].number_input("Start", 1, maximum_end, 1)
            end = cols[2].number_input("End", 1, maximum_end, min(100_000, maximum_end))
            query = st.form_submit_button(
                "Find overlapping features", type="primary", width="stretch"
            )
        overlap = overlap_features(frame, seqid, int(start), int(end)) if query else frame.head(500)
        smart_dataframe(overlap, height=480)
        st.download_button(
            "Download annotation table",
            frame.to_csv(index=False),
            "genome_annotations.csv",
            "text/csv",
            width="stretch",
        )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("genome_browser", key_prefix="step110_57_Variant_Annotation_Workbench_genome_browser")


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("variant", expanded=False)

# Step 115 non-chart visual: genome_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("genome_track", key_prefix="step115_57_Variant_Annotation_Workbench_genome_track", expanded=False)

# Step 115 module-specific non-chart workspace: variant
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("variant", key_prefix="step115_57_Variant_Annotation_Workbench_variant", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_VARIANT_ANNOTATION
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('variant_annotation', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='variant_annotation', title='Variant & Annotation Workbench', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='variant_annotation', title='Variant & Annotation Workbench', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
