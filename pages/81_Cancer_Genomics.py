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

from biointel.projects.cancer_advanced import (  # noqa: E402
    annotate_research_gene_pack,
    estimate_cancer_cell_fraction,
    expanded_cancer_gene_reference,
    matched_normal_population_filter,
    msi_hrd_research_screen,
    sample_specific_tmb,
    trinucleotide_signature_matrix,
    validate_cnv_table,
    validate_sv_fusion_table,
)
from biointel.projects.cancer_genomics import (  # noqa: E402
    clonality_screen,
    demo_cancer_variants,
    gene_association_screen,
    gene_cooccurrence_matrix,
    oncoprint_matrix,
    recurrent_hotspot_screen,
    run_cancer_genomics_pipeline,
    sample_mutation_similarity,
    sample_quality_tiers,
    sample_variant_qc,
    six_class_signature_exposure,
    snv_spectrum,
    threshold_sensitivity,
    vaf_confidence_intervals,
    validate_variant_table,
    variant_qc_report,
)
from biointel.projects.professional import (  # noqa: E402
    QualityGate,
    model_card_payload,
    quality_gate_table,
)
from biointel.projects.reporting import build_project_bundle, build_run_manifest  # noqa: E402
from biointel.projects.run_registry import register_run  # noqa: E402
from biointel.ui.components import (  # noqa: E402
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

PROJECT_CODE = "BIO-CANCER-GX"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"
PROJECT_NAME = "Bioinformatics Approaches to Cancer Genomics"
BOUNDARY = (
    "This workbench does not provide clinical interpretation, diagnosis, prognosis or treatment recommendations. "
    "Use accredited pipelines, current curated knowledge bases and qualified molecular-pathology review for clinical decisions."
)


st.set_page_config(page_title="Cancer Genomics · BioIntel AI", page_icon="🎗️", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/81_Cancer_Genomics.py", key_prefix="81_cancer_genomics", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('cancer_genomics_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'cancer_genomics_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("cancer_genomics", key_prefix="step116_81_Cancer_Genomics_cancer_genomics_1", expanded=False)
hero(
    PROJECT_NAME,
    "A complete research workbench for somatic-variant validation, QC sensitivity analysis, transparent candidate prioritization, sample mutation burden, allele-fraction structure, substitution spectra, oncoprints, gene co-occurrence and pathway summaries.",
    eyebrow="Biotechnology Project 04 · Professional workbench",
    chips=[
        "Variant QC",
        "Priority tiers",
        "TMB screen",
        "SNV spectrum",
        "Oncoprint",
        "Project bundle",
    ],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=BOUNDARY)

render_methodology(
    method="Somatic-variant QC, matched-normal/population screens, sample-specific TMB, research prioritization, CNV/SV/fusion audit, CCF and signature summaries.",
    assumptions=[
        "Variants are normalized and aligned to one declared genome build.",
        "Somatic status and sample identifiers are trustworthy.",
    ],
    limitations=[
        "The bundled gene/evidence layer is not a clinical knowledgebase.",
        "CCF, MSI/HRD and signature outputs are research screens and depend on supplied assay-quality inputs.",
    ],
    validation=[
        "Use versioned clinical annotation sources and matched-normal/population filters.",
        "Require molecular pathology review before any clinical interpretation.",
    ],
)

input_tab, metadata_tab, layers_tab, settings_tab = st.tabs(
    [
        "1 · Somatic variants",
        "2 · Sample metadata",
        "3 · CNV / SV / callable layers",
        "4 · Analysis settings",
    ]
)
with input_tab:
    source = st.radio(
        "Variant source", ["Deterministic demo", "Upload CSV/TSV/MAF"], horizontal=True
    )
    uploaded = st.file_uploader(
        "Somatic variant table",
        type=["csv", "tsv", "maf"],
        help="CSV/TSV/MAF accepted. Required or mapped fields: chromosome, position, ref, alt, gene, consequence, vaf, depth. Optional: sample, protein_change, filter.",
        disabled=source == "Deterministic demo",
        key="cancer_variant_upload",
    )
    variant_upload_profile = render_upload_preflight(
        uploaded,
        key="cancer_variants",
        allowed_extensions=["csv", "tsv", "maf"],
        soft_limit_mb=30,
        hard_limit_mb=200,
    )
    demo_cols = st.columns(2)
    demo_samples = demo_cols[0].slider(
        "Demo samples", 2, 30, 8, disabled=source != "Deterministic demo"
    )
    demo_variants = demo_cols[1].slider(
        "Variants per demo sample", 20, 200, 55, 5, disabled=source != "Deterministic demo"
    )
    variants = (
        read_uploaded_table(uploaded)
        if uploaded
        else demo_cancer_variants(samples=int(demo_samples), variants_per_sample=int(demo_variants))
    )
    try:
        validated_preview = validate_variant_table(variants)
        metric_cards(
            [
                ("Variant records", f"{len(validated_preview):,}", None),
                ("Samples", f"{validated_preview['sample'].nunique():,}", None),
                ("Genes", f"{validated_preview['gene'].nunique():,}", None),
                ("Input mode", "Demo" if not uploaded else "Uploaded", None),
            ]
        )
        smart_dataframe(validated_preview.head(300), height=400, key="cancer_input_preview")
    except Exception as exc:
        st.error(f"Variant input validation failed: {exc}")

with metadata_tab:
    metadata_upload = st.file_uploader(
        "Optional sample metadata",
        type=["csv", "tsv"],
        help="Required column: sample. Optional: cohort, tumor_type, batch, timepoint.",
        key="cancer_metadata_upload",
    )
    sample_metadata_profile = render_upload_preflight(
        metadata_upload,
        key="cancer_metadata",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=10,
        hard_limit_mb=50,
    )
    sample_ids = sorted(variants.get("sample", pd.Series(["Sample_1"])).astype(str).unique())
    if metadata_upload:
        sample_metadata = read_uploaded_table(metadata_upload)
    else:
        sample_metadata = pd.DataFrame(
            {
                "sample": sample_ids,
                "cohort": [
                    "Cohort A" if index < len(sample_ids) / 2 else "Cohort B"
                    for index in range(len(sample_ids))
                ],
                "tumor_type": ["Unspecified research tumor" for _ in sample_ids],
                "batch": [f"Batch_{1 + index % 2}" for index in range(len(sample_ids))],
                "purity": [0.60 for _ in sample_ids],
                "total_copy_number": [2.0 for _ in sample_ids],
                "mutant_copy_number": [1.0 for _ in sample_ids],
            }
        )
    sample_metadata = st.data_editor(
        sample_metadata,
        width="stretch",
        height=320,
        hide_index=True,
        num_rows="dynamic",
        key="cancer_metadata_editor",
    )

with layers_tab:
    layer_cols = st.columns(3)
    cnv_upload = layer_cols[0].file_uploader(
        "Optional CNV segments",
        type=["csv", "tsv"],
        key="cancer_cnv_upload",
        help="Columns: sample, chromosome, start, end; optional log2_ratio or copy_number.",
    )
    sv_upload = layer_cols[1].file_uploader(
        "Optional SV / fusion table",
        type=["csv", "tsv"],
        key="cancer_sv_upload",
        help="Columns: sample, event_type; optional gene_1, gene_2 and support.",
    )
    callable_upload = layer_cols[2].file_uploader(
        "Optional sample callable territory",
        type=["csv", "tsv"],
        key="cancer_callable_upload",
        help="Columns: sample, callable_megabases.",
    )
    cnv_profile = render_upload_preflight(
        cnv_upload,
        key="cancer_cnv",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=20,
        hard_limit_mb=100,
    )
    sv_profile = render_upload_preflight(
        sv_upload,
        key="cancer_sv",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=20,
        hard_limit_mb=100,
    )
    callable_profile = render_upload_preflight(
        callable_upload,
        key="cancer_callable",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=5,
        hard_limit_mb=20,
    )
    cnv_table = read_uploaded_table(cnv_upload) if cnv_upload else pd.DataFrame()
    sv_table = read_uploaded_table(sv_upload) if sv_upload else pd.DataFrame()
    callable_table = read_uploaded_table(callable_upload) if callable_upload else pd.DataFrame()
    smart_dataframe(
        expanded_cancer_gene_reference().head(150), height=260, key="cancer_reference_preview"
    )
    st.caption(
        "Bundled gene-role metadata is research-only and has no treatment/actionability classifications."
    )

with settings_tab:
    with st.form("cancer_equal_depth_form"):
        row1 = st.columns(4)
        min_depth = row1[0].number_input("Minimum read depth", 1, 2_000, 30)
        min_vaf = row1[1].slider("Minimum VAF", 0.01, 0.50, 0.05, 0.01)
        callable_mb = row1[2].number_input(
            "Callable panel/genome size (Mb)", 0.1, 5_000.0, 30.0, 1.0
        )
        top_genes = row1[3].slider("Top genes for oncoprint", 5, 50, 20)
        row2 = st.columns(3)
        cooccurrence_genes = row2[0].slider("Genes in co-occurrence matrix", 5, 30, 15)
        max_priority_rows = row2[1].number_input("Priority rows retained", 100, 100_000, 5_000, 100)
        include_all_variants = row2[2].toggle(
            "Include full annotated variants in bundle", value=True
        )
        row3 = st.columns(3)
        max_normal_vaf = row3[0].slider("Maximum matched-normal VAF", 0.0, 0.20, 0.02, 0.005)
        max_population_af = row3[1].number_input(
            "Maximum population AF", 0.0, 0.10, 0.001, 0.001, format="%.4f"
        )
        require_somatic_support = row3[2].toggle(
            "Apply somatic-support screens to priority view", value=True
        )
        run = st.form_submit_button(
            "Run complete cancer-genomics workbench", type="primary", width="stretch"
        )

if run:
    try:
        with analysis_run("Validating variants and building multi-sample cancer-genomics evidence"):
            qc_report = variant_qc_report(variants)
            result = run_cancer_genomics_pipeline(
                variants,
                min_depth=int(min_depth),
                min_vaf=float(min_vaf),
                callable_megabases=float(callable_mb),
            )
            research_variants = annotate_research_gene_pack(result.variants)
            research_variants, somatic_support_audit = matched_normal_population_filter(
                research_variants,
                maximum_normal_vaf=float(max_normal_vaf),
                maximum_population_af=float(max_population_af),
            )
            if require_somatic_support:
                research_variants["passes_qc"] = (
                    research_variants["passes_qc"]
                    & research_variants["passes_somatic_support_screen"]
                )
            result = type(result)(
                variants=research_variants,
                pathway_summary=result.pathway_summary,
                gene_summary=result.gene_summary,
                sample_summary=result.sample_summary,
                metrics=result.metrics,
            )
            cnv = validate_cnv_table(cnv_table)
            sv_fusions = validate_sv_fusion_table(sv_table)
            tmb_by_sample = sample_specific_tmb(
                result.variants, callable_table, default_callable_megabases=float(callable_mb)
            )
            ccf_variants = estimate_cancer_cell_fraction(
                result.variants, pd.DataFrame(sample_metadata)
            )
            signature96 = trinucleotide_signature_matrix(
                result.variants[result.variants["passes_qc"]]
            )
            msi_hrd = msi_hrd_research_screen(result.variants[result.variants["passes_qc"]], cnv)
            sample_qc = sample_variant_qc(result.variants)
            spectrum = snv_spectrum(result.variants[result.variants["passes_qc"]])
            oncoprint = oncoprint_matrix(result.variants, top_genes=int(top_genes))
            cooccurrence = gene_cooccurrence_matrix(
                result.variants, top_genes=int(cooccurrence_genes)
            )
            clonality = clonality_screen(result.variants)
            sensitivity = threshold_sensitivity(variants)
            annotated_sample_summary = (
                result.sample_summary.drop(
                    columns=["tmb_mutations_per_mb", "callable_megabases"], errors="ignore"
                )
                .merge(tmb_by_sample, on="sample", how="left")
                .merge(
                    pd.DataFrame(sample_metadata), on="sample", how="left", validate="one_to_one"
                )
            )
            parameters = {
                "minimum_depth": int(min_depth),
                "minimum_vaf": float(min_vaf),
                "callable_megabases": float(callable_mb),
                "oncoprint_genes": int(top_genes),
                "cooccurrence_genes": int(cooccurrence_genes),
                "maximum_matched_normal_vaf": float(max_normal_vaf),
                "maximum_population_af": float(max_population_af),
                "require_somatic_support": bool(require_somatic_support),
            }
            outputs = {
                "variant_qc_report": qc_report,
                "sample_variant_qc": sample_qc,
                "sample_summary": annotated_sample_summary,
                "gene_summary": result.gene_summary,
                "pathway_summary": result.pathway_summary,
                "snv_spectrum": spectrum,
                "oncoprint": oncoprint,
                "gene_cooccurrence": cooccurrence.reset_index(names="gene")
                if not cooccurrence.empty
                else pd.DataFrame(),
                "clonality_screen": clonality,
                "threshold_sensitivity": sensitivity,
                "priority_variants": result.variants.head(int(max_priority_rows)),
                "somatic_support_audit": somatic_support_audit,
                "sample_specific_tmb": tmb_by_sample,
                "ccf_estimates": ccf_variants,
                "cnv_segments": cnv,
                "sv_fusion_events": sv_fusions,
                "sbs96_context_matrix": signature96,
                "msi_hrd_research_screen": msi_hrd,
                "research_cancer_gene_reference": expanded_cancer_gene_reference(),
            }
            if include_all_variants:
                outputs["all_annotated_variants"] = result.variants
            inputs = {
                "somatic_variants": variants,
                "sample_metadata": pd.DataFrame(sample_metadata),
                "cnv_segments": cnv_table,
                "sv_fusions": sv_table,
                "callable_territory": callable_table,
            }
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes="Research tiers are transparent heuristics and are not AMP/ASCO/CAP classifications.",
            )
            vaf_intervals = vaf_confidence_intervals(result.variants)
            hotspots = recurrent_hotspot_screen(result.variants[result.variants["passes_qc"]])
            sample_similarity = sample_mutation_similarity(
                result.variants[result.variants["passes_qc"]], top_genes=max(int(top_genes), 10)
            )
            associations = gene_association_screen(
                result.variants[result.variants["passes_qc"]],
                top_genes=min(int(cooccurrence_genes), 20),
            )
            quality_tiers = sample_quality_tiers(result.variants)
            signature_exposure = six_class_signature_exposure(
                result.variants[result.variants["passes_qc"]]
            )
            outputs.update(
                {
                    "vaf_confidence_intervals": vaf_intervals,
                    "recurrent_hotspots": hotspots,
                    "sample_mutation_similarity": sample_similarity,
                    "gene_association_screen": associations,
                    "sample_quality_tiers": quality_tiers,
                    "six_class_signature_exposure": signature_exposure,
                }
            )
            qc_pass = float(result.metrics["qc_pass_percent"])
            strong_samples = (
                int((quality_tiers["quality_tier"].astype(str) == "strong").sum())
                if not quality_tiers.empty
                else 0
            )
            recurrent_sites = int((hotspots["samples"] >= 2).sum()) if not hotspots.empty else 0
            median_ci_width = (
                float(vaf_intervals["vaf_ci95_width"].median()) if not vaf_intervals.empty else 1.0
            )
            gates = quality_gate_table(
                [
                    QualityGate(
                        "CANCER-QC",
                        "Variant QC pass rate",
                        "pass" if qc_pass >= 70 else "review",
                        qc_pass,
                        f"{qc_pass:.1f}% variants pass selected thresholds",
                        "Review depth, VAF, filters and assay-specific limits.",
                    ),
                    QualityGate(
                        "CANCER-SAMPLE",
                        "Sample technical quality",
                        "pass" if strong_samples == len(quality_tiers) else "review",
                        100.0 * strong_samples / max(len(quality_tiers), 1),
                        f"{strong_samples}/{len(quality_tiers)} samples in strong tier",
                        "Investigate low-depth and low-VAF dominated samples.",
                    ),
                    QualityGate(
                        "CANCER-VAF",
                        "Allele-fraction precision",
                        "pass" if median_ci_width <= 0.20 else "review",
                        max(0.0, 100.0 * (1.0 - median_ci_width)),
                        f"Median Wilson interval width {median_ci_width:.3f}",
                        "Use validated read-level callers and orthogonal confirmation.",
                    ),
                    QualityGate(
                        "CANCER-REC",
                        "Cohort recurrence evidence",
                        "review",
                        min(100.0, recurrent_sites * 10.0),
                        f"{recurrent_sites} recurrent positions",
                        "Recurrence is descriptive and must be compared with curated cohorts.",
                    ),
                    QualityGate(
                        "CANCER-CLIN",
                        "Clinical evidence boundary",
                        "review",
                        40.0,
                        "Research tiers only; no clinical classification",
                        "Use current curated evidence and qualified molecular pathology review.",
                    ),
                ]
            )
            manifest = build_run_manifest(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
            )
            model_card = model_card_payload(
                project_code=PROJECT_CODE,
                title=PROJECT_NAME,
                intended_use="Research-only prioritization and cohort profiling of somatic variants.",
                out_of_scope=[
                    "Diagnosis",
                    "Prognosis",
                    "Treatment selection",
                    "Clinical pathogenicity/actionability classification",
                ],
                methodology=[
                    "Variant/schema QC",
                    "Transparent priority scoring",
                    "Wilson VAF intervals",
                    "Recurrence and gene-association screens",
                    "Oncoprint, sample-specific burden, CCF approximation, SBS-96 context and CNV/SV research screens",
                ],
                metrics={
                    **result.metrics,
                    "strong_quality_samples": strong_samples,
                    "recurrent_sites": recurrent_sites,
                    "median_vaf_ci_width": median_ci_width,
                },
                validation=[
                    "Threshold sensitivity",
                    "Sample-level technical tiers",
                    "VAF uncertainty",
                    "Recurrence and co-mutation review",
                ],
                limitations=[
                    BOUNDARY,
                    "Matched-normal, population, CNV/SV, CCF, MSI/HRD and signature outputs remain input-dependent research screens; no clinical actionability is inferred.",
                ],
                quality_gates=gates,
                run_fingerprint=manifest["run_fingerprint"],
            )
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs=inputs,
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes="Deep cancer-genomics research and assurance bundle.",
                quality_gates=gates,
                summary={
                    "Input variants": int(result.metrics["input_variants"]),
                    "QC-passing variants": int(result.metrics["qc_passing_variants"]),
                    "Samples": int(result.metrics["samples"]),
                    "Recurrent sites": recurrent_sites,
                    "Median VAF CI width": round(median_ci_width, 4),
                },
                methods=model_card["methodology"],
                model_card=model_card,
            )
            quality_score = float(
                gates.assign(
                    weight=gates["status"]
                    .map({"pass": 1.0, "review": 0.6, "block": 0.0})
                    .fillna(0.0)
                )
                .eval("score * weight")
                .mean()
            )
            register_run(
                RUN_REGISTRY,
                run_fingerprint=manifest["run_fingerprint"],
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                status="qualified" if (gates["status"] == "block").sum() == 0 else "blocked",
                quality_score=quality_score,
                input_rows=sum(len(frame) for frame in inputs.values()),
                output_rows=sum(len(frame) for frame in outputs.values()),
                parameters=parameters,
                metrics={
                    **result.metrics,
                    "recurrent_sites": recurrent_sites,
                    "median_vaf_ci_width": median_ci_width,
                },
            )
        st.session_state["cancer_equal_depth_result"] = {
            "result": result,
            "qc": qc_report,
            "sample_qc": sample_qc,
            "sample_summary": annotated_sample_summary,
            "spectrum": spectrum,
            "oncoprint": oncoprint,
            "cooccurrence": cooccurrence,
            "clonality": clonality,
            "sensitivity": sensitivity,
            "bundle": bundle,
            "manifest": manifest,
            "vaf_intervals": vaf_intervals,
            "hotspots": hotspots,
            "sample_similarity": sample_similarity,
            "associations": associations,
            "quality_tiers": quality_tiers,
            "signature_exposure": signature_exposure,
            "quality_gates": gates,
            "model_card": model_card,
            "somatic_support_audit": somatic_support_audit,
            "tmb_by_sample": tmb_by_sample,
            "ccf_variants": ccf_variants,
            "cnv": cnv,
            "sv_fusions": sv_fusions,
            "signature96": signature96,
            "msi_hrd": msi_hrd,
            "cancer_reference": expanded_cancer_gene_reference(),
        }
        st.toast("Cancer-genomics workbench completed", icon="✅")
    except Exception as exc:
        st.error(f"Cancer-genomics workbench could not run: {exc}")

payload = st.session_state.get("cancer_equal_depth_result")
if payload:
    result = payload["result"]
    metric_cards(
        [
            ("Input variants", f"{int(result.metrics['input_variants']):,}", None),
            (
                "QC-passing",
                f"{int(result.metrics['qc_passing_variants']):,}",
                f"{result.metrics['qc_pass_percent']:.1f}% pass",
            ),
            (
                "Cancer-gene variants",
                f"{int(result.metrics['known_cancer_gene_variants']):,}",
                None,
            ),
            ("Samples", f"{int(result.metrics['samples']):,}", None),
        ]
    )
    tabs = st.tabs(
        [
            "Executive summary",
            "Variant QC",
            "Priority variants",
            "Sample burden",
            "SNV spectrum",
            "Genes & pathways",
            "Oncoprint",
            "Clonality",
            "Threshold sensitivity",
            "Somatic & CCF",
            "CNV / SV / signatures",
            "Deep cohort assurance",
            "Exports & manifest",
        ]
    )
    with tabs[0]:
        overview = pd.DataFrame(
            [
                ("Maximum research tier", result.metrics["maximum_research_tier"]),
                ("Coding variants", result.metrics["coding_variants"]),
                ("Callable megabases", result.metrics["callable_megabases"]),
                ("Run fingerprint", payload["manifest"]["run_fingerprint"]),
            ],
            columns=["Measure", "Value"],
        )
        smart_dataframe(overview, height=260)
        st.plotly_chart(
            px.bar(
                payload["sample_summary"],
                x="sample",
                y="tmb_mutations_per_mb",
                color="high_priority_variants",
                hover_data=["passing_variants", "coding_variants", "median_vaf"],
                title="Research mutation-burden screen by sample",
            ),
            width="stretch",
        )
        insight_callout(
            "Clinical boundary",
            "TMB values depend on panel design, callable territory, filtering and validated assay-specific methods. This screen is not a clinical biomarker result.",
            "warning",
        )
    with tabs[1]:
        left, right = st.columns(2)
        with left:
            smart_dataframe(payload["qc"], height=360)
        with right:
            smart_dataframe(payload["sample_qc"], height=360)
        st.plotly_chart(
            px.scatter(
                payload["sample_qc"],
                x="median_depth",
                y="median_vaf",
                size="input_variants",
                color="pass_filter_percent",
                hover_name="sample",
                title="Sample-level variant QC",
            ),
            width="stretch",
        )
    with tabs[2]:
        passing = result.variants[result.variants["passes_qc"]].copy()
        tier_filter = st.multiselect(
            "Research tiers",
            sorted(passing["research_tier"].unique()),
            default=sorted(passing["research_tier"].unique()),
            key="cancer_tier_filter",
        )
        filtered = passing[passing["research_tier"].isin(tier_filter)]
        st.plotly_chart(
            px.scatter(
                filtered,
                x="depth",
                y="vaf",
                color="research_tier",
                size="research_priority_score",
                hover_data=["sample", "gene", "consequence", "protein_change"],
                title="Prioritized variant landscape",
            ),
            width="stretch",
        )
        smart_dataframe(filtered, height=540)
        st.download_button(
            "Download prioritized variants",
            filtered.to_csv(index=False),
            "cancer_genomics_prioritized_variants.csv",
            "text/csv",
            width="stretch",
        )
    with tabs[3]:
        smart_dataframe(payload["sample_summary"], height=380)
        st.plotly_chart(
            px.scatter(
                payload["sample_summary"],
                x="median_vaf",
                y="tmb_mutations_per_mb",
                size="passing_variants",
                color="cohort"
                if "cohort" in payload["sample_summary"]
                else "high_priority_variants",
                hover_name="sample",
                title="Sample mutation burden and allele fraction",
            ),
            width="stretch",
        )
    with tabs[4]:
        if payload["spectrum"].empty:
            st.info("No QC-passing SNVs are available for spectrum analysis.")
        else:
            st.plotly_chart(
                px.bar(
                    payload["spectrum"],
                    x="sample",
                    y="variants",
                    color="substitution_class",
                    title="Six-class SNV substitution spectrum",
                ),
                width="stretch",
            )
            smart_dataframe(payload["spectrum"], height=370)
    with tabs[5]:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                px.bar(
                    result.gene_summary.head(int(top_genes)),
                    x="variants",
                    y="gene",
                    color="pathway",
                    orientation="h",
                    title="Most altered genes",
                ),
                width="stretch",
            )
        with right:
            st.plotly_chart(
                px.bar(
                    result.pathway_summary.head(20),
                    x="variants",
                    y="pathway",
                    orientation="h",
                    title="Pathway-level variant burden",
                ),
                width="stretch",
            )
        smart_dataframe(result.gene_summary, height=430)
    with tabs[6]:
        if payload["oncoprint"].empty:
            st.info("No QC-passing variants are available for the oncoprint.")
        else:
            matrix = payload["oncoprint"].set_index("gene")
            st.plotly_chart(
                px.imshow(
                    matrix, aspect="auto", text_auto=True, title="Binary gene-by-sample oncoprint"
                ),
                width="stretch",
            )
        if not payload["cooccurrence"].empty:
            st.plotly_chart(
                px.imshow(
                    payload["cooccurrence"],
                    aspect="auto",
                    text_auto=True,
                    title="Gene co-occurrence counts",
                ),
                width="stretch",
            )
    with tabs[7]:
        smart_dataframe(payload["clonality"], height=360)
        if not payload["clonality"].empty:
            long = payload["clonality"].melt(
                id_vars=["sample", "median_vaf", "high_vaf_fraction_percent"],
                value_vars=["low_frequency", "subclonal_like", "clonal_like"],
                var_name="band",
                value_name="variants",
            )
            st.plotly_chart(
                px.bar(
                    long,
                    x="sample",
                    y="variants",
                    color="band",
                    title="Allele-fraction clonality bands",
                ),
                width="stretch",
            )
        insight_callout(
            "Clonality boundary",
            "VAF-only clonality bands ignore purity, ploidy, copy number and local allelic imbalance. Treat them as exploratory structure only.",
            "warning",
        )
    with tabs[8]:
        pivot = payload["sensitivity"].pivot(
            index="minimum_depth", columns="minimum_vaf", values="passing_variants"
        )
        st.plotly_chart(
            px.imshow(
                pivot,
                text_auto=True,
                aspect="auto",
                title="Passing variants across depth/VAF thresholds",
            ),
            width="stretch",
        )
        smart_dataframe(payload["sensitivity"], height=380)
    with tabs[9]:
        left, right = st.columns(2)
        with left:
            section_title("Matched-normal and population screens", "◫")
            smart_dataframe(payload["somatic_support_audit"], height=240)
            screen_cols = [
                column
                for column in [
                    "sample",
                    "variant_id",
                    "gene",
                    "normal_vaf_screen",
                    "population_af_screen",
                    "passes_somatic_support_screen",
                ]
                if column in result.variants.columns
            ]
            smart_dataframe(result.variants[screen_cols].head(1000), height=420)
        with right:
            section_title("Purity/copy-number-aware CCF approximation", "⌁")
            st.plotly_chart(
                px.scatter(
                    payload["ccf_variants"],
                    x="vaf",
                    y="estimated_cancer_cell_fraction",
                    color="sample",
                    hover_data=["gene", "variant_id", "purity", "total_copy_number"],
                    title="VAF versus approximate cancer-cell fraction",
                ),
                width="stretch",
            )
            smart_dataframe(payload["ccf_variants"].head(1000), height=300)
        insight_callout(
            "CCF boundary",
            "CCF estimates require validated purity, allele-specific local copy number and mutation multiplicity; values above 1 flag assumption mismatch.",
            "warning",
        )
    with tabs[10]:
        left, right = st.columns(2)
        with left:
            section_title("Copy-number and structural events", "▦")
            smart_dataframe(payload["cnv"], height=280)
            smart_dataframe(payload["sv_fusions"], height=280)
        with right:
            section_title("SBS-96 and MSI/HRD research screens", "⌁")
            if not payload["signature96"].empty:
                st.plotly_chart(
                    px.bar(
                        payload["signature96"],
                        x="channel",
                        y="fraction",
                        color="sample",
                        title="SBS-96 trinucleotide context fractions",
                    ),
                    width="stretch",
                )
            else:
                st.info(
                    "Provide a trinucleotide_context/context column to generate SBS-96 channels."
                )
            smart_dataframe(payload["msi_hrd"], height=300)
        insight_callout(
            "Assay boundary",
            "MSI/HRD, CNV, SV and fusion outputs are research triage summaries and require validated assay-specific callers and orthogonal review.",
            "warning",
        )
    with tabs[11]:
        left, right = st.columns(2)
        with left:
            section_title("Sample and VAF uncertainty", "◫")
            smart_dataframe(payload["quality_tiers"], height=280)
            smart_dataframe(payload["vaf_intervals"].head(600), height=350)
        with right:
            section_title("Recurrence and gene associations", "⌁")
            smart_dataframe(payload["hotspots"].head(300), height=300)
            smart_dataframe(payload["associations"].head(300), height=330)
        if not payload["sample_similarity"].empty:
            similarity = payload["sample_similarity"].set_index(
                payload["sample_similarity"].columns[0]
            )
            st.plotly_chart(
                px.imshow(similarity, aspect="auto", title="Sample mutation-profile similarity"),
                width="stretch",
            )
        if not payload["signature_exposure"].empty:
            st.plotly_chart(
                px.bar(
                    payload["signature_exposure"],
                    x="substitution",
                    y="exposure_percent",
                    title="Six-class substitution exposure screen",
                ),
                width="stretch",
            )
        smart_dataframe(payload["quality_gates"], height=340)
        insight_callout(
            "Clinical boundary",
            "These deeper cohort diagnostics remain research screens and do not provide clinical actionability or treatment evidence.",
            "warning",
        )
    with tabs[12]:
        smart_json(
            payload["model_card"],
            title="Cancer-genomics method card",
            download_name="cancer_genomics_method_card.json",
            key="cancer_method_card",
        )
        smart_json(
            payload["manifest"],
            title="Reproducibility manifest",
            download_name="cancer_genomics_manifest.json",
            key="cancer_manifest_download",
        )
        st.download_button(
            "Download complete cancer-genomics project bundle (.zip)",
            payload["bundle"],
            "BIO-CANCER-GX_project_bundle.zip",
            "application/zip",
            width="stretch",
            key="cancer_bundle_download",
        )
else:
    section_title("Professional capability map", "▦")
    smart_dataframe(
        pd.DataFrame(
            [
                (
                    "Input & QC",
                    "Somatic-variant schema validation, sample metadata and data-quality review",
                ),
                (
                    "Prioritization",
                    "Transparent impact/gene/VAF/depth research score and non-clinical tiers",
                ),
                (
                    "Cohort analysis",
                    "Sample-specific TMB, matched-normal/population screens, gene/pathway summaries and metadata overlays",
                ),
                (
                    "Mutation structure",
                    "Six/SBS-96 spectra, oncoprint, co-occurrence, CCF, CNV/SV/fusion and MSI/HRD research screens",
                ),
                ("Robustness", "Depth/VAF threshold sensitivity surface"),
                ("Reproducibility", "SHA-256 manifest and complete downloadable project bundle"),
            ],
            columns=["Layer", "Implemented capability"],
        ),
        height=370,
    )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("genome_browser", key_prefix="step110_81_Cancer_Genomics_genome_browser")
_render_step110_viewer("pathology", key_prefix="step110_81_Cancer_Genomics_pathology")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("cancer_genomics_core", None, key_prefix="step114_cancer_genomics_core", expanded=False)

# Step 115 non-chart visual: genome_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("genome_track", key_prefix="step115_81_Cancer_Genomics_genome_track", expanded=False)

# Step 115 non-chart visual: pathology_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("pathology_canvas", key_prefix="step115_81_Cancer_Genomics_pathology_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_CANCER_GENOMICS
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('cancer_genomics', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='cancer_genomics', title='Cancer Genomics', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='cancer_genomics', title='Cancer Genomics', category='Bioinformatics')

# STEP176_TARGET_MODULE_OPERATIONAL_EXCELLENCE
from biointel.target_modules_v176.ui import render_target_module_upgrade as _render_step176_target_module_upgrade
_render_step176_target_module_upgrade('cancer_genomics_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("cancer_genomics_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("cancer_genomics_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('cancer_genomics_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('cancer_genomics_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('cancer_genomics_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('cancer_genomics_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('cancer_genomics_core', expanded=False)

