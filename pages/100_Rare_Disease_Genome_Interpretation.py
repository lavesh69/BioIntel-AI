from __future__ import annotations

import gzip
import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.engines import demo_variants
from biointel.innovation.advanced_engines import parse_vcf_extended, prioritize_variants_advanced, trio_segregation_assessment
from biointel.tools.runtime import run_tool_audited, verified_tool_status
from biointel.innovation.excellence_ui import render_rare_disease_excellence
from biointel.innovation.professional_ui import render_rare_disease_professional
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="Rare Disease Genome Interpretation Board · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("rare_disease", key_prefix="step116_100_Rare_Disease_Genome_Interpretation_rare_disease_1", expanded=False)
hero(
    "Rare Disease Genome Interpretation Board Pro",
    "Prioritize SNVs/indels and review CNV evidence with phenotype, rarity, consequence, computational evidence, inheritance consistency and transparent ACMG-assistance criteria.",
    eyebrow="Step 99 · Audited research interpretation",
    chips=["Multi-sample VCF", "Trio segregation", "HPO", "ACMG assistance", "VEP/SnpEff", "CNV review"],
)
scientific_boundary_banner(source_kind="research_use_only", release_eligible=False, message="Research use only. The module does not diagnose disease, issue ACMG classifications or replace validated annotation, clinical laboratory review, genetic counselling and multidisciplinary case evaluation.")

variant_tab, cnv_tab, tools_tab, evidence_tab = st.tabs(["SNV/indel prioritization", "CNV/SV review", "Annotation tools", "Evidence checklist"])
with variant_tab:
    source = st.radio("Variant source", ["Deterministic demo", "Upload VCF", "Upload CSV/TSV"], horizontal=True)
    upload = st.file_uploader("Variant file", type=["vcf", "vcf.gz", "csv", "tsv", "xlsx", "xlsm"], disabled=source == "Deterministic demo")
    render_upload_preflight(upload, key="rare_disease_variants", allowed_extensions=["vcf", "vcf.gz", "csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=50, hard_limit_mb=500)
    cols = st.columns(3)
    hpo_text = cols[0].text_input("HPO terms", "HP:0001250, HP:0001263")
    inheritance = cols[1].selectbox("Inheritance model", ["Any model", "De novo dominant", "Autosomal dominant", "Autosomal recessive", "X-linked"])
    max_af = cols[2].selectbox("Maximum population AF", [0.05, 0.01, 0.001, 0.0001], index=2, format_func=lambda value: f"{value:g}")
    try:
        if upload is None:
            variants = demo_variants()
            variants["cadd"] = [32, 25, 12, 18, 4][:len(variants)] if len(variants) <= 5 else np.nan
            variants["revel"] = [0.91, 0.76, 0.25, 0.61, 0.05][:len(variants)] if len(variants) <= 5 else np.nan
            variants["spliceai"] = np.nan
        elif upload.name.lower().endswith((".vcf", ".vcf.gz")):
            payload = upload.getvalue()
            if upload.name.lower().endswith(".gz"):
                try:
                    payload = gzip.decompress(payload)
                except (OSError, EOFError) as exc:
                    raise ValueError("The VCF.GZ file is corrupt or incomplete.") from exc
            variants = parse_vcf_extended(payload.decode("utf-8-sig", errors="replace"))
        else:
            variants = read_uploaded_table(upload)
        variants["gnomad_af"] = pd.to_numeric(variants.get("gnomad_af", 0), errors="coerce").fillna(0)
        if "sample_genotypes" in variants.columns and variants["sample_genotypes"].astype(str).str.len().gt(2).any():
            try:
                sample_names = sorted(json.loads(str(variants["sample_genotypes"].iloc[0])).keys())
            except Exception:
                sample_names = []
            if len(sample_names) >= 3:
                st.markdown("#### Trio segregation")
                use_trio = st.checkbox("Apply explicit trio segregation assessment", value=True)
                if use_trio:
                    trio_cols = st.columns(3)
                    proband = trio_cols[0].selectbox("Proband", sample_names, index=0)
                    mother = trio_cols[1].selectbox("Mother", sample_names, index=min(1, len(sample_names) - 1))
                    father = trio_cols[2].selectbox("Father", sample_names, index=min(2, len(sample_names) - 1))
                    if len({proband, mother, father}) < 3:
                        raise ValueError("Proband, mother and father must be different samples.")
                    variants = trio_segregation_assessment(variants, proband=proband, mother=mother, father=father)
        filtered = variants[variants["gnomad_af"] <= float(max_af)].copy()
        ranked = prioritize_variants_advanced(filtered, [term.strip() for term in hpo_text.split(",") if term.strip()], inheritance)
    except Exception as exc:
        st.error(f"Variant prioritization failed: {exc}")
        st.stop()
    metric_cards([
        ("Input variants", len(variants), None), ("After AF filter", len(ranked), None),
        ("Genes", ranked["gene"].nunique() if not ranked.empty else 0, None),
        ("High priority", int((ranked["evidence_tier"] == "High").sum()) if not ranked.empty else 0, None),
        ("Phenotype matches", int(ranked["phenotype_match"].sum()) if not ranked.empty else 0, None),
        ("Inheritance matches", int(ranked["inheritance_match"].sum()) if not ranked.empty else 0, None),
    ])
    if ranked.empty:
        st.warning("No variants remain after filtering.")
    else:
        plot = ranked.copy()
        plot["plot_af"] = pd.to_numeric(plot["gnomad_af"], errors="coerce").fillna(0).clip(lower=1e-8)
        st.plotly_chart(px.scatter(plot, x="plot_af", y="priority_score", color="evidence_tier", size="acmg_points_proxy", hover_name="gene", hover_data=["consequence", "clinvar", "acmg_criteria"], log_x=True, title="Rarity–evidence prioritization landscape"), width="stretch")
        smart_dataframe(ranked, height=500, key="rare_disease_ranked_pro")
        render_generic_visual_explorer(
            ranked,
            key="rare_disease_ranked_visuals",
            heading="Variant prioritisation visual analytics",
        )
        selected_index = st.selectbox("Review candidate evidence card", list(range(len(ranked))), format_func=lambda i: f"{ranked.iloc[i]['gene']} · {ranked.iloc[i].get('chrom','?')}:{ranked.iloc[i].get('pos','?')} · {ranked.iloc[i]['acmg_assist_tier']}")
        selected = ranked.iloc[int(selected_index)].to_dict()
        smart_json(selected, key="rare_disease_evidence_card_pro")
        st.download_button("Export prioritized variants", ranked.to_csv(index=False).encode(), "rare_disease_prioritized_variants_pro.csv", "text/csv")

with cnv_tab:
    st.caption("Upload a research CNV/SV table with chrom, start, end, type, genes and optional inheritance/frequency fields.")
    cnv_upload = st.file_uploader("CNV/SV CSV, TSV or Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="cnv_upload")
    render_upload_preflight(cnv_upload, key="rare_disease_cnv", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=30, hard_limit_mb=250)
    if cnv_upload:
        try:
            cnv = read_uploaded_table(cnv_upload)
            required = {"chrom", "start", "end", "type"}
            missing = required - set(cnv.columns)
            if missing:
                raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
            cnv["size_bp"] = pd.to_numeric(cnv["end"], errors="coerce") - pd.to_numeric(cnv["start"], errors="coerce") + 1
            cnv["frequency"] = pd.to_numeric(cnv.get("frequency", 0), errors="coerce").fillna(0)
            cnv["gene_count"] = cnv.get("genes", "").astype(str).apply(lambda value: len([x for x in value.replace(";", ",").split(",") if x.strip()]))
            cnv["review_score"] = np.log10(cnv["size_bp"].clip(lower=1)) + 1.5 * (cnv["frequency"] <= 1e-3) + 0.25 * cnv["gene_count"].clip(upper=20)
            cnv = cnv.sort_values("review_score", ascending=False)
            metric_cards([("Events", len(cnv), None), ("Rare events", int((cnv["frequency"] <= 1e-3).sum()), None), ("Largest event", f"{cnv['size_bp'].max():,.0f} bp", None), ("Genes represented", int(cnv["gene_count"].sum()), None)])
            st.plotly_chart(px.scatter(cnv, x="size_bp", y="review_score", color="type", size="gene_count", hover_data=["chrom", "start", "end", "genes"] if "genes" in cnv else ["chrom", "start", "end"], log_x=True, title="CNV/SV review landscape"), width="stretch")
            smart_dataframe(cnv, height=480, key="rare_disease_cnv_review")
            render_generic_visual_explorer(
                cnv,
                key="rare_disease_cnv_visuals",
                heading="CNV and structural-variant visual analytics",
            )
        except Exception as exc:
            st.error(str(exc))
    else:
        st.info("CNV/SV review is available after upload; no clinical classification is generated.")

with tools_tab:
    section_title("Audited annotation and normalization adapters", "⚙")
    st.caption("Executables and reference databases are resolved through the versioned Advanced Tools Manager. Every run writes command, logs, timings and executable evidence.")
    status = pd.DataFrame([verified_tool_status(name) for name in ["bcftools", "vep", "snpeff"]])
    smart_dataframe(status, height=260, key="rare_disease_tool_status")
    with st.form("rare_disease_tool_run"):
        selected_tool = st.selectbox("Tool", ["bcftools", "vep", "snpeff"])
        source_path_text = st.text_input("Local VCF path")
        output_path_text = st.text_input("Output path", str(ROOT / "reports" / "tool_runs" / "rare_disease" / "annotated.vcf"))
        reference_or_cache = st.text_input("Reference/cache/database option", help="For bcftools enter reference FASTA; for VEP enter cache directory; for SnpEff enter database name.")
        extra_arguments = st.text_input("Additional arguments")
        run_annotation = st.form_submit_button("Run audited annotation", width="stretch")
    if run_annotation:
        source_path = Path(source_path_text).expanduser()
        output_path = Path(output_path_text).expanduser()
        if not source_path.is_file():
            st.error("Choose an existing VCF file.")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if selected_tool == "bcftools":
                    if not Path(reference_or_cache).expanduser().is_file():
                        raise ValueError("bcftools normalization requires an existing reference FASTA.")
                    arguments = ["norm", "-f", str(Path(reference_or_cache).expanduser()), "-m", "-any", "-Ov", "-o", str(output_path), str(source_path)]
                elif selected_tool == "vep":
                    cache_path = Path(reference_or_cache).expanduser()
                    arguments = ["--input_file", str(source_path), "--output_file", str(output_path), "--offline", "--cache", "--dir_cache", str(cache_path), "--everything", "--force_overwrite", "--vcf"]
                else:
                    database_name = reference_or_cache.strip()
                    if not database_name:
                        raise ValueError("Enter the installed SnpEff genome database name.")
                    arguments = [database_name, str(source_path)]
                arguments.extend(shlex.split(extra_arguments, posix=False))
                execution = run_tool_audited(
                    selected_tool,
                    arguments,
                    run_directory=output_path.parent / "evidence",
                    cwd=source_path.parent,
                    timeout_seconds=10800,
                )
                st.success(f"{selected_tool} completed. Review the output and immutable evidence before interpretation.")
                smart_json(execution.to_dict(), key="100_execution_manifest")
                st.download_button("Download execution manifest", Path(execution.manifest_path).read_bytes(), Path(execution.manifest_path).name, "application/json")
            except Exception as exc:
                st.error(str(exc))

with evidence_tab:
    checklist = pd.DataFrame([
        ("Variant identity", "Genome build, transcript, HGVS and left-normalization verified"),
        ("Population evidence", "Ancestry-appropriate frequency and technical quality reviewed"),
        ("Functional consequence", "Validated transcript consequence, splicing and gene mechanism reviewed"),
        ("Phenotype", "HPO terms curated and phenotype specificity considered"),
        ("Inheritance", "Pedigree, segregation, mosaicism and de novo status confirmed"),
        ("Clinical evidence", "ClinVar assertions, primary literature and expert-panel evidence inspected"),
        ("Confirmation", "Orthogonal confirmation and multidisciplinary sign-out completed where required"),
    ], columns=["Evidence gate", "Required review"])
    smart_dataframe(checklist, height=430, key="rare_disease_checklist")
    insight_callout("ACMG boundary", "Displayed criteria are transparent review prompts and a prioritization aid. They are not an automated ACMG/AMP classification and must not be reported as one.", tone="warning")

# Step 99 module excellence layer
render_rare_disease_excellence(ranked, [term.strip() for term in hpo_text.split(",") if term.strip()], variants)

# Step 100 professional integration and optimization layer
render_rare_disease_professional(ranked, [term.strip() for term in hpo_text.split(",") if term.strip()], variants)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("pedigree", key_prefix="step110_100_Rare_Disease_Genome_Interpretation_pedigree")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("rare_variant_family", None, key_prefix="step114_rare_variant_family", expanded=False)

# Step 115 non-chart visual: pedigree_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("pedigree_canvas", key_prefix="step115_100_Rare_Disease_Genome_Interpretation_pedigree_canvas", expanded=False)

# Step 115 module-specific non-chart workspace: rare_disease
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("rare_disease", key_prefix="step115_100_Rare_Disease_Genome_Interpretation_rare_disease", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_RARE_DISEASE
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('rare_disease', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='rare_disease_board', title='Rare Disease Genome Interpretation Board', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='rare_disease_board', title='Rare Disease Genome Interpretation Board', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
