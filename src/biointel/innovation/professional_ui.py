from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import insight_callout, section_title

from .professional_engines import (
    acmg_points_assistance,
    assembly_contamination_screen,
    assembly_iteration_compare,
    assembly_storage_guard,
    assembly_tool_plan,
    batch_center_correct,
    circuit_parameter_sensitivity,
    crispr_library_plan,
    dependency_install_plan,
    dna_assembly_plan,
    evidence_claim_highlight,
    expand_scatter_plan,
    graph_components,
    graph_gene_presence,
    graph_path_genotypes,
    graph_release_diff,
    guide_sequence_qc,
    hardware_profile,
    inheritance_model_screen,
    knowledge_contradiction_audit,
    knowledge_paths,
    knowledge_rdf_export,
    logrank_screen,
    module_dependency_matrix,
    module_next_step_recommendations,
    multi_view_latent_factors,
    optimisation_scorecard,
    outbreak_case_audit,
    outbreak_geospatial_summary,
    outbreak_temporal_signal,
    paired_guide_library,
    perturbseq_pseudobulk,
    phenotype_semantic_screen,
    protein_active_learning_queue,
    protein_mutation_library,
    protein_runtime_readiness,
    protein_structure_quality,
    runtime_capability_scan,
    sbol3_like_export,
    similarity_network_fusion_screen,
    simulate_circuit_gillespie,
    simulate_circuit_ode,
    stable_payload_hash,
    variant_normalisation_audit,
    workflow_cache_key,
    workflow_container_audit,
    workflow_resource_schedule,
    workflow_test_matrix,
)


def _download_json(label: str, payload: Any, filename: str, key: str) -> None:
    st.download_button(
        label,
        json.dumps(payload, indent=2, default=str).encode("utf-8"),
        filename,
        "application/json",
        key=key,
        width="stretch",
    )


def _read_table(upload: Any) -> pd.DataFrame:
    if upload is None:
        return pd.DataFrame()
    name = str(getattr(upload, "name", "")).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(upload)
    separator = "\t" if name.endswith((".tsv", ".txt")) else ","
    return pd.read_csv(upload, sep=separator)


def render_pangenome_professional(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    paths: pd.DataFrame,
    bubbles: pd.DataFrame,
) -> None:
    st.divider()
    section_title("Step 100 · Graph genotyping, annotations and release control", "🧬")
    component_tab, genotype_tab, annotation_tab, release_tab = st.tabs([
        "Graph topology", "Path genotypes", "Gene presence", "Release diff",
    ])
    with component_tab:
        components, report = graph_components(nodes, edges)
        metric_cards([
            ("Components", report["components"], None),
            ("Largest component", report["largest_component_nodes"], None),
            ("Singletons", report["singleton_components"], None),
            ("Connected", "Yes" if report["connected"] else "Review", None),
        ])
        smart_dataframe(components, height=360, key="step100_graph_components")
        _download_json("Download graph topology report", report, "graph_topology_report.json", "step100_graph_topology_download")
    with genotype_tab:
        genotypes = graph_path_genotypes(paths, bubbles)
        if genotypes.empty:
            st.info("Bubble and path records are required for path-level screening genotypes.")
        else:
            smart_dataframe(genotypes, height=400, key="step100_graph_genotypes")
            st.download_button("Export genotype screen", genotypes.to_csv(index=False).encode(), "path_genotype_screen.csv", "text/csv", key="step100_graph_genotype_download")
        insight_callout("Interpretation boundary", "Path-derived genotypes are a graph-path screen. Read mapping, allele balance and orthogonal confirmation remain required.", tone="warning")
    with annotation_tab:
        annotation_upload = st.file_uploader("Node-to-gene annotation table", type=["csv", "tsv", "xlsx", "xlsm"], key="step100_graph_annotations")
        annotations = _read_table(annotation_upload)
        presence = graph_gene_presence(paths, annotations)
        if annotation_upload and presence.empty:
            st.warning("Annotation table must include node and gene columns.")
        elif not presence.empty:
            smart_dataframe(presence, height=420, key="step100_gene_presence")
            st.download_button("Export gene presence matrix", presence.to_csv(index=False).encode(), "graph_gene_presence.csv", "text/csv", key="step100_gene_presence_download")
    with release_tab:
        st.caption("Compare a candidate graph release using node and edge tables.")
        c1, c2 = st.columns(2)
        candidate_nodes_upload = c1.file_uploader("Candidate nodes", type=["csv", "tsv", "xlsx"], key="step100_candidate_nodes")
        candidate_edges_upload = c2.file_uploader("Candidate edges", type=["csv", "tsv", "xlsx"], key="step100_candidate_edges")
        if candidate_nodes_upload and candidate_edges_upload:
            candidate_nodes = _read_table(candidate_nodes_upload)
            candidate_edges = _read_table(candidate_edges_upload)
            report = graph_release_diff(nodes, edges, candidate_nodes, candidate_edges)
            smart_json(report, key="step100_graph_release_diff")
            _download_json("Download release diff", report, "graph_release_diff.json", "step100_graph_release_download")


def render_long_read_professional(
    reads: pd.DataFrame,
    metrics: Mapping[str, Any],
    contigs: pd.DataFrame,
) -> None:
    st.divider()
    section_title("Step 100 · Assembly polishing, contamination and capacity guard", "🧵")
    contamination_tab, iteration_tab, resource_tab, tools_tab = st.tabs([
        "Contamination screen", "Iteration comparison", "Disk guard", "Executable plan",
    ])
    with contamination_tab:
        screened, report = assembly_contamination_screen(contigs)
        metric_cards([
            ("Contigs", report["contigs"], None),
            ("Review candidates", report["review"], None),
            ("Review fraction", f"{report.get('review_fraction', 0):.1%}", None),
            ("Input hash", report.get("contig_table_sha256", "")[:12], None),
        ])
        smart_dataframe(screened, height=420, key="step100_contamination_screen")
        insight_callout("Contamination boundary", report.get("boundary", ""), tone="warning")
    with iteration_tab:
        iteration_upload = st.file_uploader("Polishing iteration metrics", type=["csv", "tsv", "xlsx"], key="step100_polishing_iterations")
        if iteration_upload:
            comparison = assembly_iteration_compare(_read_table(iteration_upload))
            smart_dataframe(comparison, height=420, key="step100_iteration_compare")
            if not comparison.empty:
                st.plotly_chart(px.line(comparison, x="iteration", y="marginal_gain_score", markers=True, title="Marginal gain by polishing iteration"), width="stretch")
    with resource_tab:
        c1, c2, c3 = st.columns(3)
        genome_mb = c1.number_input("Genome size (Mb)", 0.01, 100000.0, 3000.0, 10.0, key="step100_assembly_genome")
        coverage = c2.number_input("Coverage (×)", 1.0, 500.0, 35.0, 1.0, key="step100_assembly_coverage")
        platform_name = c3.selectbox("Platform", ["Oxford Nanopore", "PacBio HiFi", "PacBio CLR"], key="step100_assembly_platform")
        free_disk = hardware_profile().get("disk_free_gb")
        guard = assembly_storage_guard(genome_mb, coverage, platform_name, free_disk)
        smart_json(guard, key="step100_assembly_storage_guard")
    with tools_tab:
        c1, c2, c3 = st.columns(3)
        platform_name = c1.selectbox("Chemistry", ["Oxford Nanopore", "PacBio HiFi", "PacBio CLR"], key="step100_assembly_tool_platform")
        hybrid = c2.toggle("Short-read polishing", value=False, key="step100_assembly_hybrid")
        phased = c3.toggle("Phased assembly", value=False, key="step100_assembly_phased")
        plan = assembly_tool_plan(platform_name, hybrid, phased)
        smart_dataframe(plan, height=360, key="step100_assembly_tool_plan")
        capabilities = runtime_capability_scan()
        smart_dataframe(capabilities[capabilities["capability"].str.contains("assembly|polish|completeness|validation", case=False, regex=True)], height=360, key="step100_assembly_tools")


def render_protein_design_professional(sequence: str, candidates: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 100 · Protein runtime, structure QC and active learning", "🧫")
    runtime_tab, structure_tab, library_tab, active_tab = st.tabs([
        "Model runtime", "Structure confidence", "Mutation library", "Active learning",
    ])
    with runtime_tab:
        readiness = protein_runtime_readiness()
        smart_dataframe(readiness, height=400, key="step100_protein_runtime")
        profile = hardware_profile()
        smart_json(profile, key="step100_protein_hardware")
    with structure_tab:
        plddt_text = st.text_area("pLDDT values (comma/space separated)", value="", key="step100_plddt_values")
        clashes = st.number_input("Steric-clash count (optional)", 0, 100000, 0, key="step100_clashes")
        if plddt_text.strip():
            plddt = [float(value) for value in plddt_text.replace(",", " ").split() if value]
            report = protein_structure_quality(plddt, clashes=int(clashes))
            smart_json(report, key="step100_structure_quality")
    with library_tab:
        top_n = st.slider("Top candidate mutations", 1, 50, 12, key="step100_protein_top_n")
        max_pairs = st.slider("Maximum pair designs", 0, 500, 40, key="step100_protein_max_pairs")
        library = protein_mutation_library(sequence, candidates, top_n, max_pairs)
        if library.empty:
            st.info("Valid candidate mutations such as A5V are required.")
        else:
            smart_dataframe(library, height=420, key="step100_protein_library")
            fasta = "".join(f">{row.variant_id}\n{row.sequence}\n" for row in library.itertuples(index=False))
            st.download_button("Export mutation library FASTA", fasta.encode(), "protein_mutation_library.fasta", "text/plain", key="step100_protein_fasta")
    with active_tab:
        assay_upload = st.file_uploader("Optional assay results", type=["csv", "tsv", "xlsx"], key="step100_protein_assays")
        assays = _read_table(assay_upload)
        queue = protein_active_learning_queue(candidates, assays if not assays.empty else None)
        smart_dataframe(queue, height=420, key="step100_protein_active_queue")
        insight_callout("Evidence boundary", "Acquisition ranking prioritises experiments; it is not experimental confirmation or model retraining by itself.", tone="warning")


def render_crispr_professional(
    counts: pd.DataFrame,
    gene_results: pd.DataFrame,
    expression: pd.DataFrame,
    labels: Sequence[str],
) -> None:
    st.divider()
    section_title("Step 100 · Guide design, library planning and pseudobulk", "✂")
    sequence_tab, plan_tab, pseudobulk_tab, paired_tab = st.tabs([
        "Guide sequence QC", "Library planner", "Perturb-seq pseudobulk", "Paired guides",
    ])
    with sequence_tab:
        qc = guide_sequence_qc(counts)
        smart_dataframe(qc, height=420, key="step100_guide_sequence_qc")
    with plan_tab:
        c1, c2, c3, c4 = st.columns(4)
        genes = c1.number_input("Genes", 1, 100000, 19000, 100, key="step100_crispr_genes")
        guides = c2.number_input("Guides/gene", 1, 20, 4, 1, key="step100_crispr_guides")
        controls = c3.number_input("Control guides", 0, 10000, 1000, 50, key="step100_crispr_controls")
        representation = c4.number_input("Representation", 50, 5000, 500, 50, key="step100_crispr_representation")
        reads = st.number_input("Reads per guide", 50, 100000, 500, 50, key="step100_crispr_reads")
        plan = crispr_library_plan(genes, guides, controls, representation, reads)
        smart_json(plan, key="step100_crispr_plan")
    with pseudobulk_tab:
        labels_empty = labels is None or len(labels) == 0
        if expression.empty or labels_empty:
            st.info("Perturb-seq expression and guide labels are required.")
        else:
            pseudobulk = perturbseq_pseudobulk(expression, labels)
            smart_dataframe(pseudobulk, height=420, key="step100_pseudobulk")
            st.download_button("Export pseudobulk matrix", pseudobulk.to_csv(index=False).encode(), "perturbseq_pseudobulk.csv", "text/csv", key="step100_pseudobulk_download")
    with paired_tab:
        pairs = paired_guide_library(counts, max_pairs=200)
        smart_dataframe(pairs, height=420, key="step100_paired_guides")
        insight_callout("Design boundary", "Sequence QC and pairing do not replace genome-wide off-target search, chromatin context, isoform selection or experimental guide validation.", tone="info")


def render_outbreak_professional(samples: pd.DataFrame, distances: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 100 · Temporal, geographic and case-definition audit", "🦠")
    temporal_tab, geo_tab, definition_tab, runtime_tab = st.tabs([
        "Temporal signal", "Geospatial screen", "Case definition", "Tool readiness",
    ])
    with temporal_tab:
        report = outbreak_temporal_signal(samples, distances)
        smart_json(report, key="step100_outbreak_temporal")
    with geo_tab:
        mapped, report = outbreak_geospatial_summary(samples)
        smart_json(report, key="step100_outbreak_geo_report")
        if not mapped.empty:
            st.map(mapped, latitude="latitude", longitude="longitude")
            smart_dataframe(mapped, height=300, key="step100_outbreak_geo_table")
    with definition_tab:
        organism = st.selectbox("Organism profile", ["SARS-CoV-2", "Mycobacterium tuberculosis", "Salmonella enterica", "Escherichia coli", "Klebsiella pneumoniae", "Other"], key="step100_outbreak_organism")
        audit = outbreak_case_audit(samples, organism)
        smart_dataframe(audit, height=390, key="step100_outbreak_case_audit")
    with runtime_tab:
        capabilities = runtime_capability_scan()
        selected = capabilities[capabilities["capability"].str.contains("phylogeny|recombination|AMR", case=False, regex=True)]
        smart_dataframe(selected, height=380, key="step100_outbreak_tools")
        insight_callout("Public-health boundary", "Genomic similarity alone cannot establish transmission. Epidemiology, organism-specific validation and public-health review remain mandatory.", tone="warning")


def render_synthetic_biology_professional(sequence: str, architecture: pd.DataFrame, design_name: str = "BioIntel construct") -> None:
    st.divider()
    section_title("Step 100 · ODE/stochastic simulation, sensitivity and assembly", "🧪")
    ode_tab, stochastic_tab, sensitivity_tab, assembly_tab = st.tabs([
        "ODE simulation", "Stochastic simulation", "Sensitivity", "Assembly & SBOL",
    ])
    defaults = {"inducer": 1.0, "production_rate": 5.0, "degradation_rate": 0.35, "hill_k": 0.5, "hill_n": 2.0, "burden": 0.15}
    with ode_tab:
        c1, c2, c3 = st.columns(3)
        duration = c1.number_input("Duration", 1.0, 240.0, 24.0, 1.0, key="step100_circuit_duration")
        inducer = c2.number_input("Inducer", 0.0, 100.0, defaults["inducer"], 0.1, key="step100_circuit_inducer")
        burden = c3.slider("Resource burden", 0.0, 0.95, defaults["burden"], 0.05, key="step100_circuit_burden")
        ode = simulate_circuit_ode(duration, inducer, defaults["production_rate"], defaults["degradation_rate"], defaults["hill_k"], defaults["hill_n"], burden)
        st.plotly_chart(px.line(ode, x="time", y="reporter", title="Deterministic circuit response"), width="stretch")
    with stochastic_tab:
        seed = st.number_input("Simulation seed", 0, 1_000_000, 42, key="step100_circuit_seed")
        stochastic = simulate_circuit_gillespie(duration=24, production_rate=4, degradation_rate=0.25, seed=int(seed))
        st.plotly_chart(px.line(stochastic, x="time", y="molecules", title="Gillespie stochastic trajectory"), width="stretch")
        st.caption(f"Events simulated: {int(stochastic['event_count'].iloc[-1]) if not stochastic.empty else 0}")
    with sensitivity_tab:
        params = {**defaults, "burden": burden, "inducer": inducer}
        sensitivity = circuit_parameter_sensitivity(params)
        smart_dataframe(sensitivity, height=400, key="step100_circuit_sensitivity")
        st.plotly_chart(px.bar(sensitivity, x="parameter", y="relative_change", color="direction", barmode="group", title="Endpoint sensitivity"), width="stretch")
    with assembly_tab:
        c1, c2, c3 = st.columns(3)
        method = c1.selectbox("Assembly method", ["Gibson", "Golden Gate", "MoClo"], key="step100_assembly_method")
        target_bp = c2.number_input("Target fragment bp", 200, 10000, 1500, 100, key="step100_fragment_bp")
        overlap_bp = c3.number_input("Overlap bp", 15, 80, 30, 1, key="step100_overlap_bp")
        plan = dna_assembly_plan(sequence, method, target_bp, overlap_bp)
        smart_dataframe(plan, height=380, key="step100_dna_assembly_plan")
        document = sbol3_like_export(design_name, sequence, "Unspecified chassis", architecture)
        _download_json("Export SBOL3-like JSON-LD", document, "circuit_sbol3_like.jsonld", "step100_sbol_export")
        insight_callout("Simulation boundary", "Model behaviour depends on chassis-specific measured parameters. Simulations and assembly plans require laboratory confirmation.", tone="warning")


def render_rare_disease_professional(ranked: pd.DataFrame, hpo_terms: Sequence[str], variants: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 100 · Phenotype, inheritance and ACMG decision support", "🧬")
    phenotype_tab, inheritance_tab, acmg_tab, normalize_tab = st.tabs([
        "Phenotype matching", "Inheritance models", "ACMG points", "Variant normalisation",
    ])
    with phenotype_tab:
        gene_hpo_upload = st.file_uploader("Gene–phenotype table", type=["csv", "tsv", "xlsx"], key="step100_gene_hpo")
        gene_hpo = _read_table(gene_hpo_upload)
        result = phenotype_semantic_screen(hpo_terms, gene_hpo)
        if gene_hpo_upload and result.empty:
            st.warning("Table requires gene and hpo_terms/phenotypes columns.")
        elif not result.empty:
            smart_dataframe(result, height=420, key="step100_phenotype_similarity")
    with inheritance_tab:
        sex = st.selectbox("Proband sex", ["Unknown", "Male", "Female"], key="step100_proband_sex")
        result = inheritance_model_screen(variants, sex)
        smart_dataframe(result, height=420, key="step100_inheritance_models")
    with acmg_tab:
        criteria = st.multiselect("Evidence criteria recorded after expert review", ["PVS1", "PS1", "PS2", "PS3", "PS4", "PM1", "PM2", "PM3", "PM4", "PM5", "PM6", "PP1", "PP2", "PP3", "PP4", "PP5", "BA1", "BS1", "BS2", "BS3", "BS4", "BP1", "BP2", "BP3", "BP4", "BP5", "BP6", "BP7"], key="step100_acmg_criteria")
        report = acmg_points_assistance(criteria)
        smart_json(report, key="step100_acmg_points")
    with normalize_tab:
        audit = variant_normalisation_audit(variants)
        smart_dataframe(audit, height=420, key="step100_variant_normalisation")
        insight_callout("Clinical boundary", "These tools support review. They do not issue a diagnosis or replace current database releases, laboratory confirmation, genetic counselling or authorised clinical sign-off.", tone="warning")


def render_knowledge_graph_professional(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 100 · Contradictions, graph paths and interoperable evidence", "🕸")
    conflict_tab, path_tab, rdf_tab, highlight_tab = st.tabs([
        "Conflicting evidence", "Multi-hop paths", "RDF export", "Claim passages",
    ])
    with conflict_tab:
        conflicts = knowledge_contradiction_audit(edges)
        smart_dataframe(conflicts, height=420, key="step100_knowledge_conflicts")
    with path_tab:
        node_names = sorted(set(edges.get("source", pd.Series(dtype=str)).astype(str)) | set(edges.get("target", pd.Series(dtype=str)).astype(str)))
        if len(node_names) >= 2:
            c1, c2, c3 = st.columns(3)
            start = c1.selectbox("Start entity", node_names, key="step100_path_start")
            end = c2.selectbox("End entity", node_names, index=min(1, len(node_names)-1), key="step100_path_end")
            hops = c3.slider("Maximum hops", 1, 6, 4, key="step100_path_hops")
            paths = knowledge_paths(edges, start, end, hops)
            smart_dataframe(paths, height=400, key="step100_knowledge_paths")
    with rdf_tab:
        rdf = knowledge_rdf_export(nodes, edges)
        st.code(rdf[:6000], language="turtle")
        st.download_button("Download Turtle graph", rdf.encode(), "biointel_knowledge_graph.ttl", "text/turtle", key="step100_rdf_download")
    with highlight_tab:
        claim = st.text_input("Claim to verify", value="", key="step100_claim")
        docs_upload = st.file_uploader("Evidence table with a text column", type=["csv", "tsv", "xlsx"], key="step100_claim_docs")
        docs = _read_table(docs_upload)
        if claim and not docs.empty:
            highlights = evidence_claim_highlight(claim, docs)
            smart_dataframe(highlights, height=420, key="step100_claim_highlights")
        insight_callout("Evidence boundary", "Graph paths and text matches are evidence-navigation aids, not proof of causality or clinical validity.", tone="info")


def render_biomarker_professional(data: pd.DataFrame, outcome: str, features: Sequence[str], predictions: pd.DataFrame | None = None) -> None:
    st.divider()
    section_title("Step 100 · Batch correction, multi-view factors and clinical utility", "🧬")
    batch_tab, factor_tab, fusion_tab, survival_tab = st.tabs([
        "Batch correction", "Latent factors", "Similarity fusion", "Survival screen",
    ])
    usable_features = [feature for feature in features if feature in data.columns]
    with batch_tab:
        batch_candidates = [column for column in data.columns if "batch" in str(column).lower() or "site" in str(column).lower()]
        if batch_candidates and usable_features:
            batch_column = st.selectbox("Batch/site column", batch_candidates, key="step100_batch_column")
            corrected = batch_center_correct(data[usable_features], data[batch_column])
            smart_dataframe(corrected.head(200), height=360, key="step100_batch_corrected")
            st.download_button("Export corrected feature matrix", corrected.to_csv(index=False).encode(), "multiomics_batch_corrected.csv", "text/csv", key="step100_batch_download")
        else:
            st.info("A batch/site column and numeric features are required.")
    with factor_tab:
        if usable_features:
            view_prefixes = sorted({_view_name(feature) for feature in usable_features})
            views = {prefix: data[[feature for feature in usable_features if _view_name(feature) == prefix]] for prefix in view_prefixes}
            factors, loadings = multi_view_latent_factors(views, components=3)
            metric_cards([("Views", len(views), None), ("Factors", factors.shape[1], None), ("Samples", factors.shape[0], None), ("Loadings", len(loadings), None)])
            smart_dataframe(factors.head(200), height=320, key="step100_latent_factors")
            smart_dataframe(loadings.head(300), height=320, key="step100_factor_loadings")
    with fusion_tab:
        if usable_features:
            view_prefixes = sorted({_view_name(feature) for feature in usable_features})
            views = {prefix: data[[feature for feature in usable_features if _view_name(feature) == prefix]] for prefix in view_prefixes}
            fused = similarity_network_fusion_screen(views, neighbours=min(10, max(2, len(data)-1)), iterations=5)
            if fused.size:
                heat = pd.DataFrame(fused)
                st.plotly_chart(px.imshow(heat, title="Fused sample similarity (screening)"), width="stretch")
                st.download_button("Export fused similarity", heat.to_csv(index=False).encode(), "multiomics_fused_similarity.csv", "text/csv", key="step100_fusion_download")
    with survival_tab:
        time_candidates = [column for column in data.columns if any(token in str(column).lower() for token in ("time", "survival", "followup"))]
        event_candidates = [column for column in data.columns if any(token in str(column).lower() for token in ("event", "status", "death"))]
        group_candidates = [outcome] + [column for column in data.columns if column != outcome and data[column].nunique(dropna=True) == 2]
        if time_candidates and event_candidates and group_candidates:
            c1, c2, c3 = st.columns(3)
            time_col = c1.selectbox("Time column", time_candidates, key="step100_survival_time")
            event_col = c2.selectbox("Event column", event_candidates, key="step100_survival_event")
            group_col = c3.selectbox("Two-group column", list(dict.fromkeys(group_candidates)), key="step100_survival_group")
            report = logrank_screen(data[time_col], data[event_col], data[group_col])
            smart_json(report, key="step100_survival_report")
        else:
            st.info("Time, event and binary group columns are required for the exploratory survival screen.")
        insight_callout("Validation boundary", "Batch correction, latent factors, similarity fusion and log-rank screening require locked independent-cohort validation before biomarker claims.", tone="warning")


def _view_name(feature: str) -> str:
    text = str(feature).lower()
    for prefix in ("rna", "transcript", "protein", "proteom", "metabol", "methyl", "copy", "clinical"):
        if text.startswith(prefix):
            return prefix
    return "other"


def render_workflow_professional(dag: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 100 · Containers, resources, scatter and workflow tests", "⚙")
    container_tab, schedule_tab, scatter_tab, tests_tab = st.tabs([
        "Container audit", "Resource schedule", "Scatter plan", "Test matrix",
    ])
    with container_tab:
        audit = workflow_container_audit(dag)
        smart_dataframe(audit, height=400, key="step100_workflow_containers")
    with schedule_tab:
        c1, c2, c3 = st.columns(3)
        cpu = c1.number_input("Available CPU", 1, 512, max(2, hardware_profile()["logical_cpu_count"]), key="step100_workflow_cpu")
        ram = c2.number_input("Available RAM GB", 1.0, 4096.0, 16.0, 1.0, key="step100_workflow_ram")
        gpu = c3.number_input("Available GPUs", 0, 64, 0, key="step100_workflow_gpu")
        schedule, report = workflow_resource_schedule(dag, int(cpu), float(ram), int(gpu))
        smart_json(report, key="step100_workflow_schedule_report")
        smart_dataframe(schedule, height=400, key="step100_workflow_schedule")
    with scatter_tab:
        expanded = expand_scatter_plan(dag)
        smart_dataframe(expanded, height=420, key="step100_workflow_scatter")
        st.caption("Add a scatter_values column such as sampleA,sampleB to generate independent planned tasks.")
    with tests_tab:
        matrix = workflow_test_matrix(dag)
        smart_dataframe(matrix, height=420, key="step100_workflow_tests")
        cache_preview = []
        for _, row in dag.head(20).iterrows():
            cache_preview.append({"id": row.get("id"), "cache_key": workflow_cache_key(row.to_dict(), ["input-example"], "environment-example")})
        smart_dataframe(pd.DataFrame(cache_preview), height=260, key="step100_workflow_cache")
        insight_callout("Execution boundary", "Local scheduling and provenance are implemented. SLURM, Kubernetes and cloud workers require separately configured execution backends.", tone="info")


def render_innovation_hub_professional() -> None:
    st.divider()
    section_title("Step 100 · Dependency intelligence and system optimization", "🚀")
    readiness_tab, plan_tab, optimize_tab, next_tab = st.tabs([
        "Module readiness", "Setup plan", "Optimization", "Recommended next module",
    ])
    matrix = module_dependency_matrix()
    with readiness_tab:
        smart_dataframe(matrix, height=480, key="step100_module_dependency_matrix")
        st.download_button("Export dependency matrix", matrix.to_csv(index=False).encode(), "innovation_dependency_matrix.csv", "text/csv", key="step100_dependency_matrix_download")
    with plan_tab:
        module_name = st.selectbox("Module", matrix["module"].tolist(), key="step100_dependency_module")
        plan = dependency_install_plan(module_name, matrix)
        smart_dataframe(plan, height=400, key="step100_dependency_plan")
    with optimize_tab:
        scorecard = optimisation_scorecard()
        smart_dataframe(scorecard, height=380, key="step100_optimisation_scorecard")
        smart_json(hardware_profile(), key="step100_hardware_profile")
    with next_tab:
        role = st.selectbox("Working role", ["Bioinformatician", "ML Scientist", "Clinical Researcher", "Wet-Lab Scientist"], key="step100_innovation_role")
        recommendations = module_next_step_recommendations(matrix, role)
        smart_dataframe(recommendations, height=450, key="step100_next_modules")
        _download_json("Download readiness snapshot", {"role": role, "modules": recommendations.to_dict("records"), "sha256": stable_payload_hash(recommendations.to_dict("records"))}, "innovation_readiness_snapshot.json", "step100_readiness_download")
