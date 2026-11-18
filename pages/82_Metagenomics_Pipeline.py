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

from biointel.projects.metagenomics_advanced import (  # noqa: E402
    contamination_screen,
    covariate_adjusted_clr_association,
    faith_phylogenetic_diversity,
    functional_profile_summary,
    longitudinal_alpha_change,
    nmds_ordination,
    pcoa_diagnostics,
    restricted_permanova,
    unifrac_distance,
)
from biointel.projects.metagenomics_pipeline import (  # noqa: E402
    aitchison_distance,
    alpha_group_summary,
    beta_dispersion,
    beta_dispersion_permutation_test,
    composition_long,
    core_microbiome,
    demo_metagenomics_data,
    differential_abundance_permutation,
    indicator_taxa,
    leave_one_out_pcoa_stability,
    normalize_abundance_input,
    permanova_screen,
    prevalence_sensitivity,
    rarefaction_curve,
    run_metagenomics_pipeline,
    sample_quality_flags,
    taxon_prevalence,
    validate_abundance_table,
)
from biointel.projects.metagenomics_raw_reads import (  # noqa: E402
    build_raw_read_plan,
    execute_raw_read_plan,
    plan_table,
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

PROJECT_CODE = "BIO-META-PIPE"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"
PROJECT_NAME = "Development of a Bioinformatics Pipeline for Metagenomics"
BOUNDARY = (
    "This abundance-table workflow is for exploration and software validation. Publication-grade metagenomics requires "
    "validated taxonomic classification, negative controls, contamination review, compositional statistics and study-specific covariate modelling."
)


st.set_page_config(page_title="Metagenomics Pipeline · BioIntel AI", page_icon="🦠", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/82_Metagenomics_Pipeline.py", key_prefix="82_metagenomics_pipeline", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('metagenomics_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'metagenomics_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("metagenomics", key_prefix="step116_82_Metagenomics_Pipeline_metagenomics_1", expanded=False)
hero(
    PROJECT_NAME,
    "A complete metagenomics workbench for abundance-table validation, sample QC, prevalence filtering, compositional summaries, alpha/beta diversity, Bray–Curtis and Aitchison geometry, PCoA, PERMANOVA screening, rarefaction, core microbiome and differential-taxa review.",
    eyebrow="Biotechnology Project 05 · Professional workbench",
    chips=["Sample QC", "Composition", "Alpha + beta diversity", "PERMANOVA", "Core microbiome", "Project bundle"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=BOUNDARY)

template_pack = ROOT / "data" / "lab_templates" / "LAB_ANALYTICS_TEMPLATE_PACK.zip"
if template_pack.exists():
    st.download_button(
        "Download Lab Analytics input-template pack",
        template_pack.read_bytes(),
        "LAB_ANALYTICS_TEMPLATE_PACK.zip",
        "application/zip",
        width="stretch",
        key="metagenomics_template_pack",
    )
storms_checklist = ROOT / "data" / "lab_templates" / "storms_reporting_checklist.csv"
if storms_checklist.exists():
    st.download_button(
        "Download STORMS-oriented reporting checklist",
        storms_checklist.read_bytes(),
        "storms_reporting_checklist.csv",
        "text/csv",
        width="stretch",
        key="metagenomics_storms_checklist",
    )

render_methodology(
    method='Taxon-table QC, compositional transforms, diversity, PERMANOVA-style screening and differential-abundance exploration.',
    assumptions=[
        'Input type, sample totals and metadata group labels are correctly declared.',
    ],
    limitations=[
        'Precomputed abundance tables cannot reconstruct read-level classification uncertainty.',
        'Simple permutation/CLR workflows may not address repeated measures or zero inflation.',
    ],
    validation=[
        'Use negative controls and covariate-aware confirmatory models.',
        'Retain classifier/database versions and raw-read provenance.',
    ],
)

input_tab, metadata_tab, settings_tab, raw_reads_tab = st.tabs(["1 · Abundance table", "2 · Sample design", "3 · Pipeline settings", "4 · Raw-read plan"])
with input_tab:
    source = st.radio("Abundance source", ["Upload CSV/TSV", "Deterministic demo"], index=1, horizontal=True)
    abundance_upload = None
    abundance_upload_profile = None
    demo_taxa = 90
    demo_samples_per_group = 8
    if source == "Upload CSV/TSV":
        st.caption("Maximum 1 GB per file. Files above 100 MB should be processed through the background-job workflow to avoid RAM spikes.")
        abundance_upload = st.file_uploader(
            "Taxon abundance table",
            type=["csv", "tsv"],
            help="Required first column: taxon. Remaining columns are samples with non-negative counts.",
            key="meta_abundance_upload",
        )
        abundance_upload_profile = render_upload_preflight(
            abundance_upload, key="meta_abundance", allowed_extensions=["csv", "tsv"], soft_limit_mb=100, hard_limit_mb=1024
        )
        if abundance_upload is None:
            st.info("Upload an abundance table to continue, or switch to deterministic demo data.")
            st.stop()
        if int(getattr(abundance_upload, "size", 0) or 0) > 100 * 1024 * 1024:
            st.warning("This file is larger than 100 MB. Use the Background Job Center for disk-backed processing; interactive parsing is intentionally blocked.")
            st.stop()
        abundance = read_uploaded_table(abundance_upload)
        demo_metadata = None
    else:
        demo_cols = st.columns(2)
        demo_taxa = demo_cols[0].slider("Demo taxa", 30, 300, 90, 10)
        demo_samples_per_group = demo_cols[1].slider("Demo samples per group", 3, 25, 8)
        abundance, demo_metadata = demo_metagenomics_data(taxa=int(demo_taxa), samples_per_group=int(demo_samples_per_group))
    declared_input_kind = st.selectbox(
        "Abundance value type",
        ["Auto detect", "Raw counts", "Relative fraction", "Relative percent", "Continuous abundance"],
        help="Raw counts support classical rarefaction. Relative/continuous inputs remain valid for compositional summaries but do not support read rarefaction.",
    )
    abundance_input_profile = {
        "detected_input_kind": "raw_counts",
        "supports_classical_rarefaction": True,
        "recommended_minimum_total": 10.0,
    }
    try:
        normalized_kind = declared_input_kind.lower().replace(" ", "_")
        abundance, abundance_input_profile = normalize_abundance_input(
            abundance,
            input_kind="auto" if normalized_kind == "auto_detect" else normalized_kind,
        )
        validated_preview = validate_abundance_table(abundance)
        metric_cards(
            [
                ("Taxa", f"{len(validated_preview):,}", None),
                ("Samples", f"{len(validated_preview.columns) - 1:,}", None),
                (
                    "Total reads" if abundance_input_profile["supports_classical_rarefaction"] else "Total abundance",
                    f"{validated_preview.drop(columns=['taxon']).to_numpy().sum():,.2f}",
                    None,
                ),
                ("Input mode", "Demo" if not abundance_upload else "Uploaded", None),
                ("Value type", str(abundance_input_profile["detected_input_kind"]).replace("_", " ").title(), None),
            ]
        )
        smart_dataframe(validated_preview.head(180), height=380, key="meta_abundance_preview")
    except Exception as exc:
        st.error(f"Abundance-table validation failed: {exc}")
        st.stop()

with raw_reads_tab:
    st.info("Generate a reproducible raw-read processing plan. Steps become executable when the declared specialist tools and reference databases are installed locally.")
    with st.form("meta_raw_read_plan_form"):
        raw_cols = st.columns(3)
        raw_sample = raw_cols[0].text_input("Sample ID", "Sample_001")
        raw_threads = raw_cols[1].number_input("Threads", 1, 256, 4)
        paired_end = raw_cols[2].toggle("Paired-end reads", value=True)
        read_1 = st.text_input("Read 1 path", "reads/Sample_001_R1.fastq.gz")
        read_2 = st.text_input("Read 2 path", "reads/Sample_001_R2.fastq.gz", disabled=not paired_end)
        host_index = st.text_input("Optional Bowtie2 host index prefix", "")
        kraken_database = st.text_input("Optional BioIntel taxonomy database path", "")
        metaphlan_database = st.text_input("Optional MetaPhlAn database path", "")
        provenance_cols = st.columns(3)
        database_release = provenance_cols[0].text_input("Database release/version", "")
        database_checksum = provenance_cols[1].text_input("Database SHA-256/checksum", "")
        container_image = provenance_cols[2].text_input("Container image + digest", "")
        raw_output_directory = st.text_input("Output directory", "metagenomics_output")
        raw_plan_run = st.form_submit_button("Build raw-read pipeline plan", type="primary", width="stretch")
    if raw_plan_run:
        try:
            raw_plan = build_raw_read_plan(
                sample_id=raw_sample,
                read_1=read_1,
                read_2=read_2 if paired_end else None,
                host_index=host_index or None,
                kraken_database=kraken_database or None,
                metaphlan_database=metaphlan_database or None,
                database_release=database_release or None,
                database_checksum=database_checksum or None,
                container_image=container_image or None,
                output_directory=raw_output_directory,
                threads=int(raw_threads),
            )
            st.session_state["meta_raw_read_plan"] = raw_plan
            raw_plan_frame = pd.DataFrame(plan_table(raw_plan))
            smart_dataframe(raw_plan_frame, height=420)
            for warning in raw_plan.warnings:
                st.warning(warning)
            st.download_button("Download pipeline command plan", raw_plan_frame.to_csv(index=False), "metagenomics_raw_read_plan.csv", "text/csv", width="stretch")
        except Exception as exc:
            st.error(f"Raw-read plan could not be generated: {exc}")
    stored_plan = st.session_state.get("meta_raw_read_plan")
    if stored_plan is not None:
        st.divider()
        st.subheader("Reviewed local execution")
        all_available = all(step.available for step in stored_plan.steps)
        if not all_available:
            st.warning("Install all declared executables before running the plan. The generated command plan remains downloadable and auditable.")
        acknowledge = st.checkbox(
            "I reviewed input paths, database licences/releases, expected outputs and compute resources.",
            key="meta_raw_execution_ack",
        )
        stop_on_error = st.toggle("Stop execution after the first failed step", value=True, key="meta_raw_stop_on_error")
        resume_existing = st.toggle("Resume from verified existing outputs", value=True, key="meta_raw_resume")
        if st.button("Execute reviewed raw-read plan locally", disabled=not (all_available and acknowledge), key="meta_execute_raw_plan"):
            try:
                with analysis_run("Executing specialist raw-read pipeline steps"):
                    execution = pd.DataFrame(execute_raw_read_plan(stored_plan, stop_on_error=stop_on_error, resume=resume_existing))
                smart_dataframe(execution, height=420)
                st.download_button("Download execution log", execution.to_csv(index=False), "metagenomics_raw_read_execution.csv", "text/csv", width="stretch")
            except Exception as exc:
                st.error(f"Raw-read execution could not complete: {exc}")

sample_columns = [column for column in abundance.columns if column != "taxon"]
with metadata_tab:
    metadata_upload = st.file_uploader(
        "Sample metadata",
        type=["csv", "tsv"],
        help="Required columns: sample and group. Optional: batch, site, subject, timepoint.",
        key="meta_metadata_upload",
    )
    design_upload_profile = render_upload_preflight(
        metadata_upload, key="meta_design", allowed_extensions=["csv", "tsv"], soft_limit_mb=10, hard_limit_mb=50
    )
    if metadata_upload:
        metadata = read_uploaded_table(metadata_upload)
    elif demo_metadata is not None:
        metadata = demo_metadata
    else:
        metadata = pd.DataFrame(
            {
                "sample": sample_columns,
                "group": ["Group A" if index < len(sample_columns) / 2 else "Group B" for index in range(len(sample_columns))],
                "batch": [f"Batch_{1 + index % 2}" for index in range(len(sample_columns))],
            }
        )
    metadata = st.data_editor(
        metadata,
        width="stretch",
        height=340,
        hide_index=True,
        num_rows="dynamic",
        key="meta_metadata_editor",
        column_config={
            "sample": st.column_config.TextColumn("Sample", required=True),
            "group": st.column_config.TextColumn("Group", required=True),
        },
    )
    functional_upload = st.file_uploader(
        "Optional functional profile CSV/TSV",
        type=["csv", "tsv"],
        help="Required columns: feature and pathway. Remaining numeric columns should match sample identifiers.",
        key="meta_functional_upload",
    )
    functional_profile = read_uploaded_table(functional_upload) if functional_upload else None
    phylogenetic_upload = st.file_uploader(
        "Optional rooted/unrooted Newick phylogenetic tree",
        type=["nwk", "newick", "tree", "txt"],
        help="Terminal names must match the taxon column. Enables Faith PD and weighted/unweighted UniFrac.",
        key="meta_phylogenetic_tree",
    )
    phylogenetic_tree_text = phylogenetic_upload.getvalue().decode("utf-8-sig") if phylogenetic_upload else ""

groups = list(dict.fromkeys(pd.DataFrame(metadata).get("group", pd.Series(dtype=str)).astype(str)))
with settings_tab:
    with st.form("meta_equal_depth_form"):
        row1 = st.columns(4)
        prevalence = row1[0].slider("Minimum prevalence %", 0.0, 100.0, 10.0, 2.5)
        count_filter_label = (
            "Minimum total count"
            if abundance_input_profile["supports_classical_rarefaction"]
            else "Minimum total abundance"
        )
        recommended_total = float(abundance_input_profile.get("recommended_minimum_total", 10.0))
        total_count = row1[1].number_input(
            count_filter_label,
            0.0,
            1_000_000.0,
            recommended_total,
            1.0 if abundance_input_profile["supports_classical_rarefaction"] else 0.001,
            format="%.3f" if not abundance_input_profile["supports_classical_rarefaction"] else "%.0f",
            help=(
                "Taxa below this total read count are removed."
                if abundance_input_profile["supports_classical_rarefaction"]
                else "Taxa below this summed abundance threshold are removed; this is not a read-count filter."
            ),
        )
        group_a = row1[2].selectbox("Reference group", groups or ["Group A"], index=0)
        group_b = row1[3].selectbox("Comparison group", groups or ["Group B"], index=min(1, max(len(groups) - 1, 0)))
        row2 = st.columns(4)
        top_taxa = row2[0].slider("Taxa in composition view", 5, 50, 15)
        core_prevalence = row2[1].slider("Core prevalence %", 25.0, 100.0, 75.0, 5.0)
        core_abundance = row2[2].slider("Core abundance %", 0.01, 5.0, 0.10, 0.01)
        permutations = row2[3].select_slider("PERMANOVA permutations", options=[49, 99, 199, 499, 999], value=199)
        row3 = st.columns(3)
        rarefaction_steps = row3[0].slider("Rarefaction depth steps", 6, 20, 12)
        random_state = row3[1].number_input("Random seed", 1, 9999, 42)
        include_distance_matrices = row3[2].toggle("Include distance matrices in bundle", value=True)
        optional_metadata_columns = [column for column in pd.DataFrame(metadata).columns if column not in {"sample", "group"}]
        row4 = st.columns(3)
        strata_column = row4[0].selectbox("Restricted-permutation strata", ["None", *optional_metadata_columns])
        covariates = row4[1].multiselect("CLR association covariates", optional_metadata_columns)
        control_column = row4[2].selectbox("Negative-control label column", ["None", *optional_metadata_columns])
        row5 = st.columns(3)
        subject_column = row5[0].selectbox("Longitudinal subject column", ["None", *optional_metadata_columns])
        time_column = row5[1].selectbox("Longitudinal time column", ["None", *optional_metadata_columns])
        run_nmds = row5[2].toggle("Calculate NMDS", value=True)
        run = st.form_submit_button("Run complete metagenomics workbench", type="primary", width="stretch")

if len(groups) < 2:
    st.warning("At least two sample groups are required for comparative screening.")
    st.stop()

if run:
    if group_a == group_b:
        st.error("Reference and comparison groups must be different.")
    else:
        try:
            with analysis_run("Filtering taxa, calculating diversity and testing community structure"):
                selected_metadata = pd.DataFrame(metadata).copy()
                selected_metadata["sample"] = selected_metadata["sample"].astype(str)
                selected_metadata["group"] = selected_metadata["group"].astype(str)
                selected_metadata = selected_metadata[selected_metadata["group"].isin([str(group_a), str(group_b)])].copy()
                result = run_metagenomics_pipeline(
                    abundance,
                    selected_metadata,
                    minimum_prevalence_percent=float(prevalence),
                    minimum_total_count=float(total_count),
                    group_a=str(group_a),
                    group_b=str(group_b),
                )
                qc_flags = sample_quality_flags(result.qc)
                prevalence_table = taxon_prevalence(result.filtered_counts)
                core = core_microbiome(
                    result.relative_abundance,
                    prevalence_threshold_percent=float(core_prevalence),
                    abundance_threshold_percent=float(core_abundance),
                )
                composition = composition_long(result.relative_abundance, selected_metadata, top_n=int(top_taxa))
                alpha_summary = alpha_group_summary(result.alpha_diversity, selected_metadata)
                aitchison = aitchison_distance(result.relative_abundance)
                pcoa_coordinates, pcoa_eigenvalues, pcoa_diagnostic = pcoa_diagnostics(result.distance_matrix)
                pcoa_coordinates = pcoa_coordinates.merge(selected_metadata, on="sample", how="left")
                permanova_bray = permanova_screen(
                    result.distance_matrix,
                    selected_metadata,
                    group_column="group",
                    permutations=int(permutations),
                    random_state=int(random_state),
                )
                permanova_aitchison = permanova_screen(
                    aitchison,
                    selected_metadata,
                    group_column="group",
                    permutations=int(permutations),
                    random_state=int(random_state),
                )
                if bool(abundance_input_profile["supports_classical_rarefaction"]):
                    rarefaction = rarefaction_curve(
                        result.filtered_counts,
                        steps=int(rarefaction_steps),
                        random_state=int(random_state),
                    )
                else:
                    rarefaction = pd.DataFrame(
                        columns=["sample", "sampling_depth", "mean_observed_taxa", "standard_deviation"]
                    )
                permanova_table = pd.DataFrame(
                    [
                        {"distance": "Bray-Curtis", **permanova_bray},
                        {"distance": "Aitchison", **permanova_aitchison},
                    ]
                )
                restricted = restricted_permanova(
                    result.distance_matrix,
                    selected_metadata,
                    group_column="group",
                    strata_column=None if strata_column == "None" else str(strata_column),
                    permutations=int(permutations),
                    random_state=int(random_state),
                )
                restricted_table = pd.DataFrame([restricted.__dict__])
                if run_nmds:
                    nmds, nmds_diagnostics = nmds_ordination(
                        result.distance_matrix,
                        random_state=int(random_state),
                    )
                    nmds = nmds.merge(selected_metadata, on="sample", how="left")
                else:
                    nmds = pd.DataFrame()
                    nmds_diagnostics = {}
                contaminants = contamination_screen(
                    result.relative_abundance,
                    selected_metadata,
                    control_column=str(control_column),
                ) if control_column != "None" else pd.DataFrame()
                covariate_da = covariate_adjusted_clr_association(
                    result.relative_abundance,
                    selected_metadata,
                    group_column="group",
                    reference_group=str(group_a),
                    comparison_group=str(group_b),
                    covariates=list(covariates),
                )
                alpha_with_metadata = result.alpha_diversity.merge(selected_metadata, on="sample", how="left")
                longitudinal = longitudinal_alpha_change(
                    result.alpha_diversity,
                    selected_metadata,
                    subject_column=str(subject_column),
                    time_column=str(time_column),
                ) if subject_column != "None" and time_column != "None" else pd.DataFrame()
                if functional_profile is not None:
                    functional_features, functional_pathways = functional_profile_summary(functional_profile)
                else:
                    functional_features, functional_pathways = pd.DataFrame(), pd.DataFrame()
                faith_pd = pd.DataFrame()
                unweighted_unifrac = pd.DataFrame()
                weighted_unifrac = pd.DataFrame()
                if phylogenetic_tree_text.strip():
                    faith_pd = faith_phylogenetic_diversity(result.filtered_counts, phylogenetic_tree_text)
                    unweighted_unifrac = unifrac_distance(result.filtered_counts, phylogenetic_tree_text, weighted=False)
                    weighted_unifrac = unifrac_distance(result.filtered_counts, phylogenetic_tree_text, weighted=True)
                parameters = {
                    "minimum_prevalence_percent": float(prevalence),
                    "minimum_total_count": float(total_count),
                    "reference_group": str(group_a),
                    "comparison_group": str(group_b),
                    "core_prevalence_percent": float(core_prevalence),
                    "core_abundance_percent": float(core_abundance),
                    "permanova_permutations": int(permutations),
                    "random_seed": int(random_state),
                    "abundance_input_kind": str(abundance_input_profile["detected_input_kind"]),
                    "classical_rarefaction_supported": bool(abundance_input_profile["supports_classical_rarefaction"]),
                    "restricted_permutation_strata": None if strata_column == "None" else str(strata_column),
                    "covariates": list(covariates),
                    "negative_control_column": None if control_column == "None" else str(control_column),
                    "longitudinal_subject_column": None if subject_column == "None" else str(subject_column),
                    "longitudinal_time_column": None if time_column == "None" else str(time_column),
                }
                outputs = {
                    "sample_qc": qc_flags,
                    "filtered_abundance": result.filtered_counts,
                    "relative_abundance": result.relative_abundance,
                    "taxon_prevalence": prevalence_table,
                    "core_microbiome": core,
                    "alpha_diversity": result.alpha_diversity,
                    "alpha_group_summary": alpha_summary,
                    "ordination": result.ordination,
                    "pcoa_coordinates_diagnostic": pcoa_coordinates,
                    "pcoa_eigenvalues": pcoa_eigenvalues,
                    "permanova_screen": permanova_table,
                    "rarefaction": rarefaction,
                    "differential_taxa": result.differential_taxa,
                    "composition_long": composition,
                    "restricted_permanova": restricted_table,
                    "nmds_ordination": nmds,
                    "contamination_screen": contaminants,
                    "covariate_adjusted_clr_association": covariate_da,
                    "longitudinal_alpha_change": longitudinal,
                    "functional_features": functional_features,
                    "functional_pathways": functional_pathways,
                    "faith_phylogenetic_diversity": faith_pd,
                }
                if not unweighted_unifrac.empty:
                    outputs["unweighted_unifrac"] = unweighted_unifrac.reset_index(names="sample")
                    outputs["weighted_unifrac"] = weighted_unifrac.reset_index(names="sample")
                if include_distance_matrices:
                    outputs["bray_curtis_distance"] = result.distance_matrix.reset_index(names="sample")
                    outputs["aitchison_distance"] = aitchison.reset_index(names="sample")
                inputs = {"taxon_abundance": abundance, "sample_metadata": selected_metadata}
                if functional_profile is not None:
                    inputs["functional_profile"] = functional_profile
                bundle = build_project_bundle(
                    project_code=PROJECT_CODE,
                    project_name=PROJECT_NAME,
                    parameters=parameters,
                    inputs=inputs,
                    outputs=outputs,
                    scientific_boundary=BOUNDARY,
                    notes="Includes restricted permutations, FDR-controlled screens, covariate-aware CLR association and explicit scientific-boundary reporting.",
                )
                permutation_da = differential_abundance_permutation(
                    result.relative_abundance,
                    selected_metadata,
                    group_column="group",
                    group_a=str(group_a),
                    group_b=str(group_b),
                    permutations=max(99, int(permutations)),
                    random_state=int(random_state),
                )
                dispersion = beta_dispersion(result.distance_matrix, selected_metadata, group_column="group")
                dispersion_test = beta_dispersion_permutation_test(
                    dispersion,
                    group_column="group",
                    permutations=max(99, int(permutations)),
                    random_state=int(random_state),
                )
                indicators = indicator_taxa(result.relative_abundance, selected_metadata, group_column="group")
                prevalence_screen = prevalence_sensitivity(abundance)
                loo_stability = leave_one_out_pcoa_stability(result.distance_matrix)
                outputs.update({
                    "permutation_differential_abundance": permutation_da,
                    "beta_dispersion": dispersion,
                    "beta_dispersion_test": pd.DataFrame([dispersion_test]),
                    "indicator_taxa": indicators,
                    "prevalence_sensitivity": prevalence_screen,
                    "leave_one_out_pcoa_stability": loo_stability,
                    "restricted_permanova": restricted_table,
                    "nmds_ordination": nmds,
                    "contamination_screen": contaminants,
                    "covariate_adjusted_clr_association": covariate_da,
                    "longitudinal_alpha_change": longitudinal,
                    "functional_features": functional_features,
                    "functional_pathways": functional_pathways,
                })
                min_depth_count = int((qc_flags["qc_status"].astype(str) != "Pass").sum())
                bray_p = float(permanova_bray.get("permutation_p_value", 1.0))
                dispersion_cv = float(dispersion.groupby("group")["distance_to_group_centroid_proxy"].mean().std() / max(dispersion["distance_to_group_centroid_proxy"].mean(), 1e-12)) if not dispersion.empty and "group" in dispersion.columns else 0.0
                dispersion_p = float(dispersion_test.get("permutation_p_value", 1.0))
                loo_mean = float(loo_stability["pairwise_geometry_correlation"].mean()) if not loo_stability.empty else 0.0
                significant_taxa = int(permutation_da["screening_significant"].sum()) if not permutation_da.empty else 0
                gates = quality_gate_table([
                    QualityGate("META-QC", "Sample sequencing depth", "pass" if min_depth_count == 0 else "review", 100.0 * (1 - min_depth_count / max(len(qc_flags), 1)), f"{min_depth_count} samples carry low-quality flags", "Review library size, dominance and negative controls."),
                    QualityGate("META-FILTER", "Filtering robustness", "pass" if int(prevalence_screen.iloc[-1]["retained_taxa"]) >= 5 else "review", min(100.0, 20.0 * int(prevalence_screen.iloc[-1]["retained_taxa"])), f"{int(prevalence_screen.iloc[-1]['retained_taxa'])} taxa retained at 50% prevalence", "Report sensitivity across prevalence thresholds."),
                    QualityGate("META-PERM", "Community structure screen", "pass" if bray_p <= 0.05 else "review", 100.0 * (1.0 - min(bray_p, 1.0)), f"Bray-Curtis permutation p={bray_p:.4f}", "Interpret with effect size, design and dispersion diagnostics."),
                    QualityGate("META-DISP", "Beta-dispersion balance", "pass" if dispersion_p > 0.05 else "review", max(0.0, 100.0 * dispersion_p), f"Dispersion permutation p={dispersion_p:.4f}; group CV {dispersion_cv:.3f}", "A significant dispersion test can confound PERMANOVA interpretation."),
                    QualityGate("META-STAB", "Ordination leave-one-out stability", "pass" if loo_mean >= 0.85 else "review", 100.0 * max(0.0, loo_mean), f"Mean geometry correlation {loo_mean:.3f}", "Inspect influential samples and alternative transformations."),
                ])
                manifest = build_run_manifest(project_code=PROJECT_CODE, project_name=PROJECT_NAME, parameters=parameters, inputs=inputs, outputs=outputs, scientific_boundary=BOUNDARY)
                model_card = model_card_payload(
                    project_code=PROJECT_CODE, title=PROJECT_NAME, intended_use="Explore taxonomic abundance tables with transparent compositional and diversity screens.",
                    out_of_scope=["Clinical microbiome interpretation", "Causal claims", "Validated taxonomic classification from raw reads"],
                    methodology=["Sample and taxon QC", "Prevalence sensitivity", "Relative abundance and robust CLR/Aitchison geometry", "Restricted PERMANOVA and beta-dispersion review", "Permutation/FDR and covariate-adjusted CLR association", "Negative-control and longitudinal screening"],
                    metrics={"samples": len(result.qc), "retained_taxa": len(result.filtered_counts), "bray_permanova_p_value": bray_p, "dispersion_cv": dispersion_cv, "dispersion_permutation_p_value": dispersion_p, "ordination_loo_stability": loo_mean, "screening_significant_taxa": significant_taxa},
                    validation=["Bray-Curtis and Aitchison comparison", "Dispersion diagnostics", "Leave-one-out ordination stability", "Permutation/FDR differential screen", "Prevalence-threshold sensitivity"],
                    limitations=[BOUNDARY, "Raw-read commands require separately installed specialist tools and versioned databases.", "Covariate-adjusted CLR and longitudinal slope screens are not substitutes for study-specific confirmatory mixed/compositional models."],
                    quality_gates=gates, run_fingerprint=manifest["run_fingerprint"],
                )
                bundle = build_project_bundle(project_code=PROJECT_CODE, project_name=PROJECT_NAME, parameters=parameters, inputs=inputs, outputs=outputs, scientific_boundary=BOUNDARY, notes="Deep metagenomics and compositional-assurance bundle.", quality_gates=gates, summary={"Samples": len(result.qc), "Retained taxa": len(result.filtered_counts), "Bray-Curtis p-value": round(bray_p, 5), "Dispersion CV": round(dispersion_cv, 4), "Ordination stability": round(loo_mean, 4), "Screening-significant taxa": significant_taxa}, methods=model_card["methodology"], model_card=model_card)
                quality_score = float(gates.assign(weight=gates["status"].map({"pass": 1.0, "review": 0.6, "block": 0.0}).fillna(0.0)).eval("score * weight").mean())
                register_run(RUN_REGISTRY, run_fingerprint=manifest["run_fingerprint"], project_code=PROJECT_CODE, project_name=PROJECT_NAME, status="qualified" if (gates["status"] == "block").sum() == 0 else "blocked", quality_score=quality_score, input_rows=sum(len(frame) for frame in inputs.values()), output_rows=sum(len(frame) for frame in outputs.values()), parameters=parameters, metrics={"bray_permanova_p_value": bray_p, "dispersion_cv": dispersion_cv, "dispersion_permutation_p_value": dispersion_p, "ordination_loo_stability": loo_mean, "screening_significant_taxa": significant_taxa})
            st.session_state["meta_equal_depth_result"] = {
                "result": result,
                "qc": qc_flags,
                "prevalence": prevalence_table,
                "core": core,
                "composition": composition,
                "alpha_summary": alpha_summary,
                "aitchison": aitchison,
                "permanova": permanova_table,
                "rarefaction": rarefaction,
                "bundle": bundle,
                "manifest": manifest,
                "permutation_da": permutation_da,
                "dispersion": dispersion,
                "indicators": indicators,
                "prevalence_screen": prevalence_screen,
                "loo_stability": loo_stability,
                "quality_gates": gates,
                "model_card": model_card,
                "metadata": selected_metadata,
                "restricted_permanova": restricted_table,
                "nmds": nmds,
                "nmds_diagnostics": nmds_diagnostics,
                "contaminants": contaminants,
                "covariate_da": covariate_da,
                "longitudinal": longitudinal,
                "functional_pathways": functional_pathways,
                "pcoa_coordinates": pcoa_coordinates,
                "pcoa_eigenvalues": pcoa_eigenvalues,
                "pcoa_diagnostics": pcoa_diagnostic,
                "faith_pd": faith_pd,
                "unweighted_unifrac": unweighted_unifrac,
                "weighted_unifrac": weighted_unifrac,
            }
            st.toast("Metagenomics workbench completed", icon="✅")
        except Exception as exc:
            st.error(f"Metagenomics workbench could not run: {exc}")

payload = st.session_state.get("meta_equal_depth_result")
if payload:
    result = payload["result"]
    metric_cards(
        [
            ("Input taxa", f"{int(result.summary['input_taxa']):,}", None),
            ("Retained taxa", f"{int(result.summary['retained_taxa']):,}", f"{result.summary['taxa_retention_percent']:.1f}% retained"),
            ("Samples", f"{int(result.summary['samples']):,}", None),
            ("Screening taxa", f"{int(result.summary['screening_taxa']):,}", None),
        ]
    )
    overview_tab, quality_tab, diversity_tab, assurance_tab, export_tab = st.tabs(["Overview", "Quality & composition", "Diversity & inference", "Advanced assurance", "Export"])
    with overview_tab:
        smart_dataframe(payload["alpha_summary"], height=260)
        st.plotly_chart(px.scatter(result.ordination, x="PCoA1", y="PCoA2", color="group", hover_name="sample", title="Bray–Curtis community ordination"), width="stretch")
        insight_callout("Interpretation boundary", "Community separation can reflect biology, batch, depth, contamination or processing differences. Review design and controls before biological conclusions.", "warning")

    with quality_tab:
        view = st.selectbox("Workspace view", ['Sample QC', 'Community composition', 'Core microbiome'], key="meta_quality_view")
        if view == 'Sample QC':
            st.plotly_chart(px.scatter(payload["qc"], x="total_reads", y="observed_taxa", color="qc_status", size="dominant_taxon_percent", hover_name="sample", title="Sample quality-control landscape"), width="stretch")
            smart_dataframe(payload["qc"], height=460)
        elif view == 'Community composition':
            sort_mode = st.radio("Sample ordering", ["Input order", "Group"], horizontal=True, key="meta_composition_order")
            composition = payload["composition"].copy()
            if sort_mode == "Group" and "group" in composition.columns:
                composition = composition.sort_values(["group", "sample"])
            st.plotly_chart(px.bar(composition, x="sample", y="relative_abundance_percent", color="taxon", hover_data=[column for column in ["group", "batch"] if column in composition.columns], title="Top-taxon community composition"), width="stretch")
            smart_dataframe(payload["prevalence"].head(200), height=410)
        elif view == 'Core microbiome':
            st.plotly_chart(px.scatter(payload["core"], x="prevalence_percent", y="mean_relative_abundance_percent", color="core_member", hover_name="taxon", title="Core microbiome screen"), width="stretch")
            smart_dataframe(payload["core"], height=460)

    with diversity_tab:
        view = st.selectbox("Workspace view", ['Alpha diversity', 'Beta diversity', 'PERMANOVA', 'Rarefaction', 'Differential taxa'], key="meta_diversity_view")
        if view == 'Alpha diversity':
            alpha = result.alpha_diversity.merge(payload["metadata"], on="sample", how="left")
            metric_choice = st.selectbox("Alpha-diversity metric", ["shannon", "simpson", "observed_taxa", "pielou_evenness"], key="meta_alpha_metric")
            st.plotly_chart(px.box(alpha, x="group", y=metric_choice, points="all", hover_name="sample", title=f"{metric_choice.replace('_', ' ').title()} by group"), width="stretch")
            smart_dataframe(alpha, height=390)
        elif view == 'Beta diversity':
            distance_choice = st.radio("Distance geometry", ["Bray-Curtis", "Aitchison"], horizontal=True)
            matrix = result.distance_matrix if distance_choice == "Bray-Curtis" else payload["aitchison"]
            st.plotly_chart(px.imshow(matrix, text_auto=".2f", aspect="auto", title=f"{distance_choice} sample distance"), width="stretch")
            st.plotly_chart(px.scatter(result.ordination, x="PCoA1", y="PCoA2", color="group", hover_name="sample", title="Bray–Curtis PCoA"), width="stretch")
            with st.expander("PCoA eigenvalue diagnostics", expanded=False):
                smart_json(payload["pcoa_diagnostics"], title="PCoA geometry audit", key="meta_pcoa_diagnostics")
                smart_dataframe(payload["pcoa_eigenvalues"].head(20), height=300)
                if payload["pcoa_diagnostics"].get("correction_recommended"):
                    st.warning("Negative eigenvalue mass is material; consider a Lingoes/Cailliez correction or NMDS for confirmatory interpretation.")
            if not payload["faith_pd"].empty:
                section_title("Phylogenetic diversity and UniFrac", "🌿")
                smart_dataframe(payload["faith_pd"], height=280)
                unifrac_choice = st.radio("UniFrac matrix", ["Unweighted", "Weighted"], horizontal=True, key="meta_unifrac_choice")
                unifrac_matrix = payload["unweighted_unifrac"] if unifrac_choice == "Unweighted" else payload["weighted_unifrac"]
                st.plotly_chart(px.imshow(unifrac_matrix, text_auto=".2f", aspect="auto", title=f"{unifrac_choice} UniFrac distance"), width="stretch")
        elif view == 'PERMANOVA':
            smart_dataframe(payload["permanova"], height=250)
            st.plotly_chart(px.bar(payload["permanova"], x="distance", y="pseudo_f", color="permutation_p_value", title="PERMANOVA screening statistics"), width="stretch")
            insight_callout("Statistical boundary", "This simple permutation screen tests group separation only. It does not model repeated measures, stratification, dispersion differences or confounders.", "warning")
        elif view == 'Rarefaction':
            if payload["rarefaction"].empty:
                st.info("Classical read rarefaction is available only for raw integer count inputs. Relative or continuous abundance tables are not resampled as synthetic reads.")
            else:
                st.plotly_chart(px.line(payload["rarefaction"], x="sampling_depth", y="mean_observed_taxa", color="sample", title="Rarefaction screening curves"), width="stretch")
                smart_dataframe(payload["rarefaction"], height=420)
        elif view == 'Differential taxa':
            review_only = st.toggle("Show review-flagged taxa only", value=False, key="meta_diff_review_only")
            differential = result.differential_taxa[result.differential_taxa["screening_flag"] == "Review"] if review_only else result.differential_taxa
            st.plotly_chart(px.scatter(differential, x="log2_fold_change", y="screening_effect_score", color="screening_flag", hover_name="taxon", title=f"Differential-taxa screen · {group_a} vs {group_b}"), width="stretch")
            smart_dataframe(differential, height=510)
            st.download_button("Download differential-taxa screen", result.differential_taxa.to_csv(index=False), "metagenomics_differential_taxa.csv", "text/csv", width="stretch")

    with assurance_tab:
        view = st.selectbox("Workspace view", ['Matrices', 'Deep microbiome assurance', 'Advanced design'], key="meta_assurance_view")
        if view == 'Matrices':
            matrix_choice = st.radio("Data matrix", ["Filtered counts", "Relative abundance", "Bray-Curtis distance", "Aitchison distance"], horizontal=True)
            if matrix_choice == "Filtered counts":
                smart_dataframe(result.filtered_counts, height=520)
            elif matrix_choice == "Relative abundance":
                smart_dataframe(result.relative_abundance, height=520)
            elif matrix_choice == "Bray-Curtis distance":
                smart_dataframe(result.distance_matrix.reset_index(names="sample"), height=520)
            else:
                smart_dataframe(payload["aitchison"].reset_index(names="sample"), height=520)
        elif view == 'Deep microbiome assurance':
            left, right = st.columns(2)
            with left:
                section_title("Permutation/FDR abundance evidence", "◫")
                st.plotly_chart(px.scatter(payload["permutation_da"], x="log2_fold_change", y="fdr_q_value", color="screening_significant", hover_name="taxon", title="Permutation differential-abundance screen"), width="stretch")
                smart_dataframe(payload["permutation_da"], height=350)
            with right:
                section_title("Dispersion and ordination robustness", "⌁")
                st.plotly_chart(px.box(payload["dispersion"], x="group", y="distance_to_group_centroid_proxy", points="all", title="Within-group beta dispersion"), width="stretch")
                smart_dataframe(payload["loo_stability"], height=300)
            st.plotly_chart(px.line(payload["prevalence_screen"], x="minimum_prevalence", y=["retained_taxa", "retained_total_counts_percent"], markers=True, title="Prevalence-filter sensitivity"), width="stretch")
            section_title("Indicator taxa", "◎")
            smart_dataframe(payload["indicators"].head(300), height=340)
            smart_dataframe(payload["quality_gates"], height=340)
            insight_callout("Inference boundary", "Permutation/FDR and dispersion checks improve screening discipline but do not replace study-specific covariate-aware compositional models.", "warning")
        elif view == 'Advanced design':
            section_title("Restricted permutations and covariate-aware CLR association", "◈")
            smart_dataframe(payload["restricted_permanova"], height=220)
            smart_dataframe(payload["covariate_da"], height=420)
            if not payload["nmds"].empty:
                st.plotly_chart(px.scatter(payload["nmds"], x="NMDS1", y="NMDS2", color="group", hover_name="sample", title=f"NMDS · stress {payload['nmds_diagnostics'].get('stress', 0):.4f}"), width="stretch")
            if not payload["contaminants"].empty:
                section_title("Negative-control contamination screen", "⚠")
                st.plotly_chart(px.scatter(payload["contaminants"], x="biological_prevalence", y="negative_prevalence", color="contaminant_flag", hover_name="taxon", title="Control-vs-biological prevalence"), width="stretch")
                smart_dataframe(payload["contaminants"], height=330)
            if not payload["longitudinal"].empty:
                section_title("Longitudinal alpha-diversity slopes", "↗")
                smart_dataframe(payload["longitudinal"], height=300)
            if not payload["functional_pathways"].empty:
                section_title("Functional pathway profile", "⌘")
                smart_dataframe(payload["functional_pathways"], height=380)
            insight_callout("Inference boundary", "Restricted permutations, covariate-adjusted CLR models and control screens improve design awareness but still require study-specific validation and current specialist methods.", "warning")

    with export_tab:
        smart_json(payload["model_card"], title="Metagenomics method card", download_name="metagenomics_method_card.json", key="meta_method_card")
        smart_json(payload["manifest"], title="Reproducibility manifest", download_name="metagenomics_manifest.json", key="meta_manifest_download")
        st.download_button("Download complete metagenomics project bundle (.zip)", payload["bundle"], "BIO-META-PIPE_project_bundle.zip", "application/zip", width="stretch", key="meta_bundle_download")
        insight_callout(
            "Reporting recommendation",
            "Complete the STORMS-oriented checklist and retain sample collection, extraction, controls, library preparation, classifier/database release, checksums, covariates and statistical decisions with the project bundle.",
            "info",
        )

else:
    section_title("Professional capability map", "▦")
    smart_dataframe(
        pd.DataFrame(
            [
                ("Input & QC", "Taxon-by-sample validation, editable metadata and sample quality flags"),
                ("Preprocessing", "Prevalence/count filtering and relative-abundance normalization"),
                ("Composition", "Top-taxon profiles, prevalence and core-microbiome screening"),
                ("Diversity", "Observed richness, Shannon, Simpson, evenness, Bray–Curtis and Aitchison distances"),
                ("Inference", "PCoA, permutation-based PERMANOVA screen, rarefaction and differential-taxa review"),
                ("Reproducibility", "SHA-256 manifest, matrices and complete downloadable project bundle"),
            ],
            columns=["Layer", "Implemented capability"],
        ),
        height=370,
    )


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("metagenomics", expanded=False)

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("metagenomics_core", None, key_prefix="step114_metagenomics_core", expanded=False)

# Step 115 non-chart visual: phylogeny_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("phylogeny_canvas", key_prefix="step115_82_Metagenomics_Pipeline_phylogeny_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_METAGENOMICS_PIPELINE
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('metagenomics_pipeline', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='metagenomics_pipeline', title='Metagenomics Pipeline', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='metagenomics_pipeline', title='Metagenomics Pipeline', category='Lab Analytics')

# STEP176_TARGET_MODULE_OPERATIONAL_EXCELLENCE
from biointel.target_modules_v176.ui import render_target_module_upgrade as _render_step176_target_module_upgrade
_render_step176_target_module_upgrade('metagenomics_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("metagenomics_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("metagenomics_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('metagenomics_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('metagenomics_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('metagenomics_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('metagenomics_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('metagenomics_core', expanded=False)

