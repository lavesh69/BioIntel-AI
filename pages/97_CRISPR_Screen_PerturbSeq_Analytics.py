from __future__ import annotations

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

from biointel.innovation.engines import demo_crispr_counts, demo_perturbseq, deterministic_rng
from biointel.innovation.advanced_engines import crispr_pathway_enrichment, crispr_replicate_analysis, perturbseq_advanced
from biointel.tools.runtime import run_tool_audited, verified_tool_status
from biointel.innovation.excellence_ui import render_crispr_excellence
from biointel.innovation.professional_ui import render_crispr_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="CRISPR Screen & Perturb-seq Analytics · BioIntel AI", page_icon="✂️", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("perturbseq", key_prefix="step116_97_CRISPR_Screen_PerturbSeq_Analytics_perturbseq_1", expanded=False)
hero(
    "CRISPR Screen & Perturb-seq Analytics Pro",
    "Run replicate-aware guide QC, gene-level FDR ranking, effect-consistency checks and UMAP/PCA-linked perturbation differential analysis.",
    eyebrow="Step 99 · Statistical functional genomics upgrade",
    chips=["Replicates", "FDR", "Guide consistency", "UMAP", "Differential markers", "Exportable hits"],
)
scientific_boundary_banner(source_kind="synthetic", release_eligible=False, message="Research-use analytics only. Screen claims require biological replicates, validated count models, orthogonal guides, rescue experiments and study-specific multiple-testing decisions.")

pooled_tab, perturb_tab, pathway_tab, tools_tab, validation_tab = st.tabs(["Pooled CRISPR screen", "Perturb-seq", "Pathway enrichment", "MAGeCK adapter", "Validation planner"])
with pooled_tab:
    source = st.radio("Count source", ["Replicate demo", "Upload CSV/TSV"], horizontal=True)
    upload = st.file_uploader("Guide table with guide, gene and control*/treated* replicate columns", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source == "Replicate demo")
    render_upload_preflight(upload, key="crispr_guide_counts", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=40, hard_limit_mb=300)
    try:
        if upload:
            counts = read_uploaded_table(upload)
        else:
            base = demo_crispr_counts()
            rng = deterministic_rng(94)
            counts = base[["guide", "gene"]].copy()
            for replicate in range(1, 4):
                counts[f"control_{replicate}"] = np.maximum(0, np.rint(base["control"] * rng.lognormal(0, 0.10, len(base)))).astype(int)
                counts[f"treated_{replicate}"] = np.maximum(0, np.rint(base["treated"] * rng.lognormal(0, 0.12, len(base)))).astype(int)
        control_columns = [c for c in counts.columns if c.lower().startswith("control")]
        treated_columns = [c for c in counts.columns if c.lower().startswith("treated")]
        guide, gene, metrics = crispr_replicate_analysis(counts, control_columns, treated_columns)
    except Exception as exc:
        st.error(f"CRISPR analysis failed: {exc}")
        st.stop()
    metric_cards([
        ("Guides", metrics["guides"], None), ("Genes", metrics["genes"], None),
        ("Control replicates", metrics["control_replicates"], None), ("Treated replicates", metrics["treated_replicates"], None),
        ("Guide QC pass", f"{metrics['qc_pass_rate']:.1%}", None), ("Negative hits", metrics["negative_hits"], None),
        ("Positive hits", metrics["positive_hits"], None), ("Median library", f"{metrics['median_library_size']:,.0f}", None),
    ])
    fig = px.scatter(gene, x="median_log2_fc", y="minus_log10_fdr", color="hit_class", size="guides", hover_name="gene", hover_data=["guide_consistency", "fdr"], title="Replicate-aware gene hit landscape")
    fig.add_vline(x=-0.5, line_dash="dash")
    fig.add_vline(x=0.5, line_dash="dash")
    fig.add_hline(y=-np.log10(0.05), line_dash="dot")
    st.plotly_chart(fig, width="stretch")
    g1, g2 = st.tabs(["Guide-level QC", "Gene-level ranking"])
    with g1:
        smart_dataframe(guide, height=440, key="crispr_guide_replicate_qc")
    with g2:
        smart_dataframe(gene, height=440, key="crispr_gene_fdr_ranking")
    st.download_button("Export FDR-ranked gene hits", gene.to_csv(index=False).encode(), "crispr_gene_hits_fdr.csv", "text/csv")

with perturb_tab:
    source = st.radio("Perturb-seq source", ["Deterministic demo", "Upload expression CSV"], horizontal=True, key="perturb_source")
    upload_expr = st.file_uploader("Expression matrix: one perturbation column plus numeric markers", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source == "Deterministic demo")
    render_upload_preflight(upload_expr, key="perturbseq_expression", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=60, hard_limit_mb=500)
    try:
        if upload_expr:
            table = read_uploaded_table(upload_expr)
            label_column = st.selectbox("Perturbation label column", table.columns)
            labels = table[label_column].astype(str)
            expression = table.drop(columns=[label_column])
        else:
            expression, labels = demo_perturbseq()
        control_label = st.selectbox("Control label", sorted(pd.Series(labels).astype(str).unique()), index=0)
        result = perturbseq_advanced(expression, labels, control_label)
    except Exception as exc:
        st.error(f"Perturb-seq analysis failed: {exc}")
        st.stop()
    embedding = result["embedding"]
    metric_cards([
        ("Cells", len(embedding), None), ("Perturbations", embedding["perturbation"].nunique(), None),
        ("Features", expression.select_dtypes(include=[np.number]).shape[1], None),
        ("Embedding", result["embedding_method"], None), ("Control", result["control_label"], None),
    ])
    st.plotly_chart(px.scatter(embedding, x="UMAP1", y="UMAP2", color="perturbation", opacity=0.75, title=f"{result['embedding_method']} perturbation embedding"), width="stretch")
    differential = result["differential"]
    if not differential.empty:
        selected = st.selectbox("Differential marker review", sorted(differential["perturbation"].unique()))
        subset = differential[differential["perturbation"] == selected].sort_values("fdr").head(50)
        st.plotly_chart(px.scatter(subset, x="mean_shift", y="minus_log10_fdr", hover_name="feature", title=f"Differential markers · {selected}"), width="stretch")
        smart_dataframe(subset, height=400, key="perturbseq_differential")
        st.download_button("Export Perturb-seq differential table", differential.to_csv(index=False).encode(), "perturbseq_differential.csv", "text/csv")

with pathway_tab:
    section_title("Gene-set enrichment for ranked CRISPR hits", "◎")
    gene_set_source = st.radio("Gene-set source", ["Deterministic example", "Upload pathway/gene table"], horizontal=True, key="crispr_gene_set_source")
    gene_set_upload = st.file_uploader("Gene sets table with pathway and gene columns", type=["csv", "tsv", "xlsx", "xlsm"], disabled=gene_set_source == "Deterministic example", key="crispr_gene_sets")
    render_upload_preflight(gene_set_upload, key="crispr_gene_sets_profile", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=10, hard_limit_mb=100)
    if gene_set_upload:
        gene_sets = read_uploaded_table(gene_set_upload)
    else:
        background = gene["gene"].astype(str).tolist() if "gene" in locals() and not gene.empty else [f"GENE_{i}" for i in range(1, 31)]
        gene_sets = pd.DataFrame([
            {"pathway": "Cell survival", "gene": value} for value in background[: max(3, len(background) // 3)]
        ] + [
            {"pathway": "DNA damage response", "gene": value} for value in background[len(background) // 4: len(background) // 2 + 3]
        ] + [
            {"pathway": "Signal transduction", "gene": value} for value in background[len(background) // 2:]
        ])
    if "gene" in locals() and not gene.empty:
        fdr_threshold = st.slider("Hit FDR threshold", 0.001, 0.25, 0.05, 0.001, key="crispr_pathway_fdr")
        hit_genes = gene.loc[(gene["fdr"] <= fdr_threshold) & (gene["hit_class"] != "Background"), "gene"].astype(str).tolist()
        if not hit_genes:
            hit_genes = gene.head(min(10, len(gene)))["gene"].astype(str).tolist()
            st.info("No genes met the selected FDR/hit-class criteria; enrichment is shown for the top-ranked genes as an exploratory fallback.")
        try:
            enrichment = crispr_pathway_enrichment(hit_genes, gene_sets, gene["gene"].astype(str).tolist())
            metric_cards([("Hit genes", len(hit_genes), None), ("Gene sets", int(gene_sets["pathway"].nunique()), None), ("Enriched pathways", len(enrichment), None), ("FDR ≤ 0.05", int((enrichment["fdr"] <= 0.05).sum()) if not enrichment.empty else 0, None)])
            if enrichment.empty:
                st.info("No overlapping pathways were found.")
            else:
                st.plotly_chart(px.bar(enrichment.head(25).sort_values("fold_enrichment"), x="fold_enrichment", y="pathway", color="fdr", orientation="h", title="CRISPR hit pathway enrichment"), width="stretch")
                smart_dataframe(enrichment, height=430, key="crispr_pathway_enrichment")
                st.download_button("Export pathway enrichment", enrichment.to_csv(index=False).encode(), "crispr_pathway_enrichment.csv", "text/csv")
        except Exception as exc:
            st.error(f"Pathway enrichment failed: {exc}")
    else:
        st.info("Run pooled CRISPR analysis first.")
    insight_callout("Statistical boundary", "The local guide model uses a transparent negative-binomial Wald approximation and weighted gene aggregation. Confirm key results with a specialist method such as MAGeCK/edgeR/DESeq2 and independent guides.", tone="info")

with tools_tab:
    section_title("Audited MAGeCK execution", "⚙")
    smart_dataframe(pd.DataFrame([verified_tool_status("mageck")]), height=180, key="mageck_tool_status")
    with st.form("mageck_run_form"):
        count_table_path = st.text_input("MAGeCK count table path")
        treatment_labels = st.text_input("Treatment sample labels", help="Comma-separated labels matching the count table header.")
        control_labels = st.text_input("Control sample labels", help="Comma-separated labels matching the count table header.")
        output_prefix = st.text_input("Output prefix", str(ROOT / "reports" / "tool_runs" / "crispr" / "mageck_result"))
        extra_args = st.text_input("Additional arguments")
        run_mageck = st.form_submit_button("Run MAGeCK test with audit evidence", width="stretch")
    if run_mageck:
        count_path = Path(count_table_path).expanduser()
        prefix = Path(output_prefix).expanduser()
        if not count_path.is_file():
            st.error("Choose an existing MAGeCK count table.")
        elif not treatment_labels.strip() or not control_labels.strip():
            st.error("Treatment and control sample labels are required.")
        else:
            prefix.parent.mkdir(parents=True, exist_ok=True)
            try:
                args = ["test", "-k", str(count_path), "-t", treatment_labels.strip(), "-c", control_labels.strip(), "-n", str(prefix)]
                args.extend(shlex.split(extra_args, posix=False))
                execution = run_tool_audited("mageck", args, run_directory=prefix.parent / "evidence", cwd=count_path.parent, timeout_seconds=10800)
                st.success("MAGeCK completed with command, logs, timings and executable evidence retained.")
                smart_json(execution.to_dict(), key="97_execution_manifest")
                st.download_button("Download execution manifest", Path(execution.manifest_path).read_bytes(), Path(execution.manifest_path).name, "application/json")
            except Exception as exc:
                st.error(str(exc))

with validation_tab:
    checklist = pd.DataFrame([
        ("Screen design", "Multiple biological replicates; adequate library representation; prespecified contrasts"),
        ("Guide QC", "Low-count filtering, guide mapping rate, non-targeting controls and replicate correlation"),
        ("Statistics", "Replicate-aware count model, FDR control and sensitivity analyses"),
        ("Biological confirmation", "Independent guides, rescue experiment and orthogonal assay"),
        ("Perturb-seq", "Doublet removal, guide assignment confidence, batch correction and cell-state covariates"),
    ], columns=["Gate", "Required evidence"])
    smart_dataframe(checklist, height=340, key="crispr_validation_checklist")
    insight_callout("Upgrade boundary", "The module now performs replicate-aware FDR analysis and perturbation differential testing. It does not claim MAGeCK equivalence or clinical-grade single-cell interpretation without externally validated workflows.", tone="info")

# Step 99 module excellence layer
render_crispr_excellence(counts, control_columns, treated_columns, gene, expression, labels)

# Step 100 professional integration and optimization layer
render_crispr_professional(counts, gene, expression, labels)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("single_cell", key_prefix="step110_97_CRISPR_Screen_PerturbSeq_Analytics_single_cell")

# Step 115 non-chart visual: single_cell_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("single_cell_canvas", key_prefix="step115_97_CRISPR_Screen_PerturbSeq_Analytics_single_cell_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_CRISPR_SCREEN
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('crispr_screen', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='crispr_perturbseq', title='CRISPR Screen & Perturb-seq Analytics', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='crispr_perturbseq', title='CRISPR Screen & Perturb-seq Analytics', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
