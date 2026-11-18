from __future__ import annotations

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

from biointel.transcriptomics.advanced import (
    ma_plot_table,
    negative_binomial_de,
    residualize_batch,
    sample_diagnostics,
)
from biointel.transcriptomics.expression import (
    collapse_duplicate_genes,
    differential_expression,
    expression_summary,
    filter_low_count_genes,
    median_ratio_normalize,
    normalize_cpm,
    pca_samples,
)
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Transcriptomics Expression Lab · BioIntel AI", page_icon="📈", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("transcriptomics", key_prefix="step116_59_Transcriptomics_Expression_Lab_transcriptomics_1", expanded=False)
hero(
    "Transcriptomics Expression Lab",
    "Configure sample groups, normalization, comparisons and thresholds before differential-expression and PCA analysis.",
    eyebrow="BioIntel AI · Omics Workbench",
    chips=["Negative-binomial GLM", "Editable design", "Batch adjustment", "Sample QC", "PCA"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="The bundled matrix is simulated. For publication-grade RNA-seq, use raw-count QC, a validated design matrix and a specialist method such as DESeq2/edgeR.",
)

render_methodology(
    method="Count-matrix QC, selectable normalization, exploratory PCA and statistical differential-expression screening.",
    assumptions=[
        "Rows are genes and sample columns contain non-negative measurements.",
        "Metadata groups and batches are correctly assigned.",
    ],
    limitations=[
        "The internal negative-binomial GLM is transparent and local; final regulated/publication workflows should still reproduce results in a validated specialist stack.",
        "Low replicate counts reduce variance and FDR reliability.",
    ],
    validation=[
        "Re-run final contrasts with DESeq2/edgeR/limma-voom as appropriate.",
        "Validate gene identifiers, covariates and reference levels.",
    ],
)

uploaded = st.file_uploader("Gene-count matrix CSV", type=["csv", "tsv"])
expression_upload_profile = render_upload_preflight(
    uploaded,
    key="transcriptomics_counts",
    allowed_extensions=["csv", "tsv"],
    soft_limit_mb=40,
    hard_limit_mb=250,
)
frame = (
    read_uploaded_table(uploaded)
    if uploaded
    else read_csv_cached(DEMO / "demo_expression_counts.csv")
)
duplicate_gene_rows = (
    int(frame["gene"].astype(str).duplicated(keep=False).sum()) if "gene" in frame.columns else 0
)
duplicate_report = None
if duplicate_gene_rows:
    st.warning(f"Detected {duplicate_gene_rows:,} rows belonging to duplicated gene identifiers.")
    duplicate_controls = st.columns([1.2, 1.0])
    collapse_duplicates = duplicate_controls[0].toggle(
        "Collapse duplicate genes before analysis", value=True
    )
    duplicate_method = duplicate_controls[1].selectbox(
        "Duplicate aggregation", ["sum", "mean", "max"], index=0
    )
    if collapse_duplicates:
        frame, duplicate_report = collapse_duplicate_genes(frame, method=duplicate_method)
        st.caption(
            f"Collapsed {duplicate_report['duplicate_gene_ids']:,} duplicated identifiers "
            f"using {duplicate_report['method']}; {duplicate_report['output_rows']:,} unique genes remain."
        )
    else:
        st.error("Duplicate gene identifiers must be resolved before analysis.")
        st.stop()
summary = expression_summary(frame)
metric_cards(
    [
        ("Genes", f"{summary.genes:,}", None),
        ("Samples", f"{summary.samples:,}", None),
        ("Total counts", f"{summary.total_counts:,.0f}", None),
        ("Zero fraction", f"{summary.zero_fraction * 100:.2f}%", None),
    ]
)

sample_columns = [column for column in frame.columns if column != "gene"]
default_metadata = pd.DataFrame(
    {
        "sample": sample_columns,
        "group": [
            "Control" if str(column).upper().startswith("CTRL") else "Treatment"
            for column in sample_columns
        ],
        "batch": ["Batch 1"] * len(sample_columns),
        "include": [True] * len(sample_columns),
    }
)
section_title("Experimental design", "🧾")
metadata = st.data_editor(
    default_metadata, width="stretch", hide_index=True, num_rows="fixed", key="expression_design"
)
metadata = metadata[metadata["include"] == True].copy()  # noqa: E712
valid_samples = [sample for sample in metadata["sample"] if sample in frame.columns]
analysis_frame = frame[["gene", *valid_samples]].copy()
groups = dict(zip(metadata["sample"], metadata["group"]))
unique_groups = list(dict.fromkeys(metadata["group"].astype(str)))

with st.form("expression_analysis_form"):
    controls = st.columns(5)
    analysis_method = controls[0].selectbox(
        "DE model", ["Negative-binomial GLM", "Welch / batch-adjusted OLS"]
    )
    normalization = controls[1].selectbox("Exploratory normalization", ["Log2 CPM", "Median ratio"])
    group_a = controls[2].selectbox("Reference group", unique_groups, index=0)
    comparison_options = [group for group in unique_groups if group != group_a]
    group_b = controls[3].selectbox(
        "Comparison group", comparison_options or ["Add another group in the design"]
    )
    fdr_threshold = controls[4].slider("FDR threshold", 0.001, 0.25, 0.05, 0.001)
    filtering = st.columns(4)
    minimum_count = filtering[0].number_input("Minimum count", 0.0, 10000.0, 10.0, 1.0)
    minimum_samples = filtering[1].number_input(
        "Minimum samples above count",
        1,
        max(len(valid_samples), 1),
        min(2, max(len(valid_samples), 1)),
    )
    use_batch_adjustment = filtering[2].toggle("Adjust for batch", value=True)
    min_abs_log2fc = filtering[3].slider("Minimum absolute log2 fold change", 0.0, 5.0, 1.0, 0.1)
    run = st.form_submit_button(
        "Run transcriptomics analysis",
        type="primary",
        width="stretch",
        disabled=len(unique_groups) < 2,
    )

if run:
    with analysis_run("Filtering genes, normalizing counts and running comparisons"):
        filtered_frame = filter_low_count_genes(
            analysis_frame,
            minimum_count=float(minimum_count),
            minimum_samples=int(minimum_samples),
        )
        normalized = (
            normalize_cpm(filtered_frame)
            if normalization == "Log2 CPM"
            else median_ratio_normalize(filtered_frame)
        )
        batches = dict(zip(metadata["sample"], metadata["batch"])) if use_batch_adjustment else None
        if analysis_method == "Negative-binomial GLM":
            de, design_audit = negative_binomial_de(
                filtered_frame,
                groups,
                reference_group=group_a,
                comparison_group=group_b,
                batches=batches,
            )
            de["batch_adjusted"] = bool(batches)
        else:
            de = differential_expression(
                normalized,
                groups,
                group_a=group_a,
                group_b=group_b,
                values_are_log2=normalization == "Log2 CPM",
                batches=batches,
            )
            design_audit = None
        pca = pca_samples(normalized, values_are_log2=normalization == "Log2 CPM")
        sample_qc, sample_correlation, sample_distance = sample_diagnostics(filtered_frame)
        batch_corrected = residualize_batch(
            normalized,
            batches or {sample: "Batch 1" for sample in valid_samples},
            values_are_log2=normalization == "Log2 CPM",
        )
        pca["group"] = pca["sample"].map(groups)
        pca["batch"] = pca["sample"].map(dict(zip(metadata["sample"], metadata["batch"])))
        fdr_col = (
            "fdr_bh"
            if "fdr_bh" in de
            else "fdr"
            if "fdr" in de
            else "adjusted_p_value"
            if "adjusted_p_value" in de
            else None
        )
        logfc_col = "log2_fold_change" if "log2_fold_change" in de else "log2fc"
        if fdr_col:
            de["significant"] = (pd.to_numeric(de[fdr_col], errors="coerce") <= fdr_threshold) & (
                pd.to_numeric(de[logfc_col], errors="coerce").abs() >= min_abs_log2fc
            )
        else:
            de["significant"] = (
                pd.to_numeric(de[logfc_col], errors="coerce").abs() >= min_abs_log2fc
            )
    metric_cards(
        [
            ("Input genes", f"{len(analysis_frame):,}", None),
            ("Retained genes", f"{len(filtered_frame):,}", None),
            ("Comparison", f"{group_b} vs {group_a}", None),
            ("Batch adjusted", "Yes" if bool(de["batch_adjusted"].iloc[0]) else "No", None),
        ]
    )
    tabs = st.tabs(
        [
            "Counts",
            "Filtered",
            "Normalized",
            "Differential expression",
            "Volcano",
            "MA plot",
            "PCA",
            "Sample QC",
            "Correlation",
            "Batch-corrected",
            "Design audit",
        ]
    )
    with tabs[0]:
        smart_dataframe(analysis_frame, height=500)
    with tabs[1]:
        smart_dataframe(filtered_frame, height=500)
    with tabs[2]:
        smart_dataframe(normalized, height=500)
    with tabs[3]:
        smart_dataframe(de.sort_values(fdr_col or logfc_col).head(5000), height=520)
    with tabs[4]:
        if fdr_col:
            volcano = de.copy()
            volcano["minus_log10_fdr"] = -np.log10(
                pd.to_numeric(volcano[fdr_col], errors="coerce").clip(lower=1e-300)
            )
            st.plotly_chart(
                px.scatter(
                    volcano,
                    x=logfc_col,
                    y="minus_log10_fdr",
                    color="significant",
                    hover_data=["gene"],
                    title=f"{group_b} vs {group_a}",
                ),
                width="stretch",
            )
        else:
            st.info("Adjusted p-values are unavailable for this analysis backend.")
    with tabs[5]:
        if "base_mean" in de.columns:
            ma = ma_plot_table(de)
            st.plotly_chart(
                px.scatter(
                    ma,
                    x="mean_expression_log10",
                    y="log2_fold_change",
                    color="significant",
                    hover_data=["gene"],
                    title="MA plot",
                ),
                width="stretch",
            )
        else:
            st.info("MA plot requires base mean values from the negative-binomial model.")
    with tabs[6]:
        st.plotly_chart(
            px.scatter(
                pca,
                x="PC1",
                y="PC2",
                color="group",
                symbol="batch",
                text="sample",
                title="Sample PCA",
            ),
            width="stretch",
        )
    with tabs[7]:
        smart_dataframe(sample_qc, height=420)
        if sample_qc["review_sample"].any():
            st.warning(
                f"{int(sample_qc['review_sample'].sum())} sample(s) triggered robust outlier review flags."
            )
    with tabs[8]:
        st.plotly_chart(
            px.imshow(sample_correlation, text_auto=".2f", title="Sample Pearson correlation"),
            width="stretch",
        )
        st.plotly_chart(
            px.imshow(sample_distance, title="Sample Euclidean distance"), width="stretch"
        )
    with tabs[9]:
        smart_dataframe(batch_corrected, height=500)
        st.download_button(
            "Download batch-residualized matrix",
            batch_corrected.to_csv(index=False),
            "batch_corrected_expression.csv",
            "text/csv",
            width="stretch",
        )
    with tabs[10]:
        if design_audit is None:
            st.info("Design audit is available for the negative-binomial GLM.")
        else:
            smart_dataframe(pd.DataFrame([design_audit.__dict__]), height=220)
    st.download_button(
        "Download differential-expression results",
        de.to_csv(index=False),
        "differential_expression.csv",
        "text/csv",
        width="stretch",
    )
else:
    st.info(
        "Configure the sample design and run the analysis. Input changes do not trigger expensive recalculation until submission."
    )


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("transcriptomics", expanded=False)

# Step 115 module-specific non-chart workspace: transcriptomics
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("transcriptomics", key_prefix="step115_59_Transcriptomics_Expression_Lab_transcriptomics", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_TRANSCRIPTOMICS
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('transcriptomics', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='transcriptomics_expression', title='Transcriptomics Expression Lab', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='transcriptomics_expression', title='Transcriptomics Expression Lab', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
