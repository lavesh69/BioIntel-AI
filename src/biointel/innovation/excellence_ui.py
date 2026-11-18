from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.innovation.engines import WORKFLOW_BLOCKS
from biointel.tools.runtime import verified_tool_status
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import insight_callout, section_title

from .excellence_engines import (
    biomarker_selection_stability,
    chassis_burden_estimate,
    claim_evidence_bundle,
    construct_manufacturability,
    crispr_copy_number_adjustment,
    crispr_design_matrix,
    crispr_library_qc,
    decision_curve_analysis,
    exact_evidence_retrieval,
    formal_acmg_assistance,
    harmonize_multiomics_columns,
    innovation_readiness,
    innovation_recommendations,
    long_read_platform_qc,
    long_read_resource_plan,
    marketplace_trust_score,
    multiomics_missingness,
    normalize_biomedical_entities,
    normalize_hpo_terms,
    outbreak_epidemiology_audit,
    outbreak_profile,
    outbreak_recombination_screen,
    outbreak_reporting_checklist,
    pangenome_bubble_support,
    pangenome_core_accessory,
    pangenome_graph_integrity,
    pangenome_path_presence,
    pangenome_resource_estimate,
    perturbseq_cell_qc,
    phenotype_gene_similarity,
    polishing_workflow,
    protein_design_consensus,
    protein_design_validation_plan,
    protein_pair_designs,
    protein_sequence_developability,
    rare_disease_reanalysis_plan,
    sbol_like_document,
    score_evidence_edges,
    simulate_genetic_circuit,
    t2t_completeness_audit,
    variant_spectrum_audit,
    workflow_critical_path,
    workflow_schema_audit,
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


def render_pangenome_excellence(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    paths: pd.DataFrame,
    bubbles: pd.DataFrame,
    quality: Mapping[str, Any],
) -> None:
    st.divider()
    section_title("Step 99 · Cohort-scale graph excellence", "◈")
    core_tab, support_tab, scale_tab = st.tabs(["Core/accessory genome", "Bubble support & integrity", "Scale planner"])
    with core_tab:
        prevalence = pangenome_core_accessory(paths, nodes)
        presence = pangenome_path_presence(paths)
        if prevalence.empty:
            st.info("Path prevalence requires P or W path records.")
        else:
            metric_cards([
                ("Core segments", int((prevalence["class"] == "Core").sum()), None),
                ("Accessory segments", int((prevalence["class"] == "Accessory").sum()), None),
                ("Rare segments", int((prevalence["class"] == "Rare").sum()), None),
                ("Path matrix", f"{presence.shape[0]} × {max(0, presence.shape[1]-1)}", None),
            ])
            st.plotly_chart(px.histogram(prevalence, x="path_prevalence", color="class", nbins=20, title="Segment prevalence across graph paths"), width="stretch")
            smart_dataframe(prevalence, height=400, key="step99_pangenome_prevalence")
            st.download_button("Export path-presence matrix", presence.to_csv(index=False).encode(), "pangenome_path_presence.csv", "text/csv", key="step99_pangenome_presence_download")
    with support_tab:
        integrity = pangenome_graph_integrity(nodes, edges, paths)
        support = pangenome_bubble_support(bubbles, paths)
        c1, c2 = st.columns(2)
        with c1:
            smart_dataframe(integrity, height=330, key="step99_graph_integrity")
        with c2:
            if support.empty:
                st.info("No bubble candidates are available for path-support review.")
            else:
                smart_dataframe(support, height=330, key="step99_bubble_support")
        insight_callout("Graph-call boundary", "Bubble support and prevalence identify review priorities. They do not replace graph-aware genotyping, cohort QC, or orthogonal variant confirmation.", tone="warning")
    with scale_tab:
        target = st.number_input("Target cohort size", 1, 100000, max(10, int(quality.get("paths", 1))), 10, key="step99_pangenome_target_samples")
        estimate = pangenome_resource_estimate(int(quality.get("nodes", len(nodes))), int(quality.get("edges", len(edges))), int(quality.get("paths", len(paths))), int(quality.get("sequence_bp", 0)), int(target))
        smart_json(estimate, key="step99_pangenome_resources")
        _download_json("Download scale plan", estimate, "pangenome_scale_plan.json", "step99_pangenome_scale_download")


def render_long_read_excellence(
    reads: pd.DataFrame,
    metrics: Mapping[str, Any],
    contigs: pd.DataFrame,
    summary: Mapping[str, Any],
) -> None:
    st.divider()
    section_title("Step 99 · Platform-aware assembly excellence", "🧵")
    platform_tab, t2t_tab, resource_tab = st.tabs(["Platform QC", "T2T completion audit", "Resources & polishing"])
    with platform_tab:
        platform = st.selectbox("Long-read chemistry", ["Oxford Nanopore", "PacBio HiFi", "PacBio CLR"], key="step99_lr_platform")
        checks, report = long_read_platform_qc(reads, metrics, platform)
        metric_cards([
            ("Checks passed", f"{report['checks_passed']}/{report['checks_total']}", None),
            ("Ultra-long ≥100 kb", f"{report['ultralong_fraction_100kb']:.1%}", None),
            ("Low-quality reads", f"{report['low_quality_fraction']:.1%}", None),
            ("Input hash", report["read_table_sha256"][:12], None),
        ])
        smart_dataframe(checks, height=300, key="step99_lr_platform_checks")
    with t2t_tab:
        audited, report = t2t_completeness_audit(contigs, summary)
        metric_cards([
            ("T2T screening score", f"{report['t2t_readiness_score']}/100", None),
            ("Gap-free contigs", report["gap_free_contigs"], None),
            ("Two-end telomere", report["two_end_telomere_contigs"], None),
            ("Chromosome candidates", report["chromosome_candidates"], None),
        ])
        smart_dataframe(audited, height=400, key="step99_t2t_audit")
        insight_callout("T2T boundary", report["boundary"], tone="warning")
    with resource_tab:
        c1, c2, c3, c4 = st.columns(4)
        genome_size = c1.number_input("Genome size Mb", 0.01, 100000.0, 5.0, 0.5, key="step99_lr_genome")
        coverage = c2.number_input("Coverage ×", 1.0, 500.0, 35.0, 1.0, key="step99_lr_cov")
        platform = c3.selectbox("Platform", ["Oxford Nanopore", "PacBio HiFi", "PacBio CLR"], key="step99_lr_resource_platform")
        genome_type = c4.selectbox("Genome type", ["Bacterial/microbial", "Fungal", "Plant", "Human/animal", "Metagenome"], key="step99_lr_resource_type")
        plan = long_read_resource_plan(genome_size, coverage, platform, genome_type)
        polish = polishing_workflow(platform, st.toggle("Hybrid short-read polishing available", value=False, key="step99_lr_hybrid"))
        smart_dataframe(plan, height=300, key="step99_lr_resources")
        smart_dataframe(polish, height=260, key="step99_lr_polish")


def render_protein_design_excellence(
    sequence: str,
    candidates: pd.DataFrame,
    objective: str,
) -> None:
    st.divider()
    section_title("Step 99 · Multi-objective protein design excellence", "🧫")
    consensus_tab, liability_tab, validation_tab = st.tabs(["Consensus & pair designs", "Developability map", "Experimental validation plan"])
    with consensus_tab:
        if candidates.empty:
            st.info("Generate mutation candidates first.")
        else:
            consensus = protein_design_consensus(candidates)
            pairs = protein_pair_designs(sequence, consensus)
            metric_cards([
                ("Top consensus", int((consensus["review_priority"] == "Top consensus").sum()), None),
                ("Pair candidates", len(pairs), None),
                ("Low epistasis risk", int((pairs.get("epistasis_risk", pd.Series(dtype=str)) == "Low").sum()), None),
                ("Structure review", int(pairs.get("requires_structure_review", pd.Series(dtype=bool)).sum()), None),
            ])
            smart_dataframe(consensus, height=380, key="step99_protein_consensus")
            smart_dataframe(pairs, height=330, key="step99_protein_pairs")
    with liability_tab:
        liability = protein_sequence_developability(sequence)
        st.plotly_chart(px.line(liability.sort_values("start"), x="start", y="developability_risk", color="risk_class", markers=True, title="Sliding-window developability risk"), width="stretch")
        smart_dataframe(liability.head(100), height=380, key="step99_protein_liabilities")
    with validation_tab:
        plan = protein_design_validation_plan(objective, len(candidates))
        smart_dataframe(plan, height=320, key="step99_protein_validation_plan")
        insight_callout("Design evidence", "Computational consensus is a prioritization method. Expression, stability, activity, specificity, aggregation and orthogonal confirmation remain required.", tone="warning")


def render_crispr_excellence(
    counts: pd.DataFrame,
    control_columns: Sequence[str],
    treated_columns: Sequence[str],
    gene: pd.DataFrame,
    expression: pd.DataFrame,
    labels: Sequence[str],
) -> None:
    st.divider()
    section_title("Step 99 · Screen and Perturb-seq excellence", "✂")
    library_tab, cn_tab, cell_tab, design_tab = st.tabs(["Library QC", "Copy-number correction", "Cell QC", "Design matrix"])
    with library_tab:
        guide_qc, metrics = crispr_library_qc(counts, control_columns, treated_columns)
        metric_cards([
            ("Median count", f"{metrics['median_count']:.0f}", None),
            ("Dropout fraction", f"{metrics['dropout_fraction']:.1%}", None),
            ("Low-count fraction", f"{metrics['low_count_fraction']:.1%}", None),
            ("Replicate Spearman", f"{metrics['median_replicate_spearman']:.2f}", None),
        ])
        smart_dataframe(guide_qc, height=390, key="step99_crispr_library_qc")
    with cn_tab:
        st.caption("Optional table columns: gene and copy_number/cn/log2_cn/segment_mean.")
        cn_upload = st.file_uploader("Copy-number table", type=["csv", "tsv"], key="step99_crispr_cn")
        cn = None
        if cn_upload:
            separator = "\t" if cn_upload.name.lower().endswith(".tsv") else ","
            cn = pd.read_csv(cn_upload, sep=separator)
        adjusted = crispr_copy_number_adjustment(gene, cn)
        smart_dataframe(adjusted, height=400, key="step99_crispr_cn_adjusted")
    with cell_tab:
        cell_qc, metrics = perturbseq_cell_qc(expression, labels)
        metric_cards([
            ("Cell QC pass", f"{metrics['pass_fraction']:.1%}", None),
            ("Doublet candidates", f"{metrics['doublet_candidate_fraction']:.1%}", None),
            ("Low complexity", f"{metrics['low_complexity_fraction']:.1%}", None),
            ("Guide review", f"{metrics['guide_review_fraction']:.1%}", None),
        ])
        smart_dataframe(cell_qc, height=390, key="step99_perturbseq_cell_qc")
    with design_tab:
        demo_meta = pd.DataFrame({"condition": ["control", "treated", "control", "treated"], "batch": ["A", "A", "B", "B"], "timepoint": [0, 0, 24, 24]})
        design = crispr_design_matrix(demo_meta, "condition", ["batch", "timepoint"])
        smart_dataframe(design, height=250, key="step99_crispr_design_matrix")
        insight_callout("Specialist-model boundary", "Copy-number correction and cell QC are transparent screening steps. MAGeCK, BAGEL/JACKS, CRISPRcleanR, pseudobulk models and orthogonal guide validation remain study-specific.", tone="info")


def render_outbreak_excellence(samples: pd.DataFrame, distances: pd.DataFrame, links: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 99 · Epidemiology-aware outbreak excellence", "🦠")
    profile_tab, epi_tab, recomb_tab, report_tab = st.tabs(["Organism profile", "Epidemiology links", "Recombination screen", "Reporting checklist"])
    with profile_tab:
        name = st.selectbox("Threshold evidence profile", ["Generic exploratory", "SARS-CoV-2", "Mycobacterium tuberculosis", "Listeria monocytogenes", "Salmonella enterica"], key="step99_outbreak_profile")
        profile = outbreak_profile(name)
        smart_json(profile, key="step99_outbreak_profile_json")
        insight_callout("Threshold boundary", profile["note"], tone="warning")
    with epi_tab:
        audited, metrics = outbreak_epidemiology_audit(samples, links)
        metric_cards([
            ("Links", metrics["links"], None),
            ("High priority", metrics["high_priority"], None),
            ("Same location", f"{metrics.get('same_location_fraction', 0):.1%}", None),
            ("Median link score", f"{metrics.get('median_epidemiology_score', 0):.3f}", None),
        ])
        smart_dataframe(audited, height=430, key="step99_outbreak_epi_links")
    with recomb_tab:
        screen = outbreak_recombination_screen(distances)
        smart_dataframe(screen, height=400, key="step99_outbreak_recombination")
    with report_tab:
        name = st.session_state.get("step99_outbreak_profile", "Generic exploratory")
        smart_dataframe(outbreak_reporting_checklist(name), height=390, key="step99_outbreak_checklist")


def render_synthetic_biology_excellence(sequence: str, parts: pd.DataFrame, name: str = "BioIntel construct") -> None:
    st.divider()
    section_title("Step 99 · Circuit simulation and manufacturability", "🧩")
    simulation_tab, build_tab, burden_tab, sbol_tab = st.tabs(["Dynamic simulation", "Manufacturability", "Chassis burden", "SBOL-like export"])
    with simulation_tab:
        c1, c2, c3, c4 = st.columns(4)
        production = c1.number_input("Production rate", 0.0, 20.0, 1.5, 0.1, key="step99_syn_prod")
        degradation = c2.number_input("Degradation rate", 0.001, 5.0, 0.2, 0.05, key="step99_syn_deg")
        hill = c3.number_input("Hill coefficient", 0.1, 8.0, 2.0, 0.1, key="step99_syn_hill")
        signal = c4.number_input("Input signal", 0.0, 10.0, 1.0, 0.1, key="step99_syn_signal")
        simulation = simulate_genetic_circuit(production_rate=production, degradation_rate=degradation, hill_coefficient=hill, input_signal=signal)
        st.plotly_chart(px.line(simulation, x="time", y=["expression", "production", "degradation"], title="Deterministic circuit trajectory"), width="stretch")
    with build_tab:
        findings, report = construct_manufacturability(sequence)
        metric_cards([
            ("Length", report["length_bp"], None),
            ("GC", f"{report['gc_percent']:.1f}%", None),
            ("Findings", report["findings"], None),
            ("Manufacturability", f"{report['manufacturability_score']}/100", None),
        ])
        smart_dataframe(findings, height=380, key="step99_synbio_manufacturability")
    with burden_tab:
        chassis = st.selectbox("Chassis", ["E. coli", "Yeast", "Mammalian", "Plant", "Cell-free"], key="step99_syn_chassis")
        copy_number = st.slider("Estimated construct copy number", 1, 500, 20, key="step99_syn_copy")
        burden = chassis_burden_estimate(parts, chassis, copy_number)
        smart_json(burden, key="step99_synbio_burden")
    with sbol_tab:
        chassis = st.session_state.get("step99_syn_chassis", "E. coli")
        payload = sbol_like_document(name, sequence, parts, chassis)
        _download_json("Download SBOL-like design document", payload, "biointel_construct_sbol3_lite.json", "step99_synbio_sbol_download")


def render_rare_disease_excellence(ranked: pd.DataFrame, hpo_terms: Sequence[str], variants: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 99 · Phenotype and clinical-review excellence", "🔎")
    phenotype_tab, acmg_tab, spectrum_tab, reanalysis_tab = st.tabs(["HPO normalization", "ACMG evidence assistance", "Variant spectrum", "Reanalysis plan"])
    with phenotype_tab:
        normalized = normalize_hpo_terms(hpo_terms)
        smart_dataframe(normalized, height=260, key="step99_hpo_normalized")
        if not ranked.empty and "gene" in ranked:
            demo_map = pd.DataFrame([{"gene": gene, "phenotype": term} for gene in ranked["gene"].astype(str).head(20) for term in normalized["canonical_term"].astype(str).head(2)])
            smart_dataframe(phenotype_gene_similarity(hpo_terms, demo_map), height=280, key="step99_hpo_gene_similarity")
    with acmg_tab:
        if ranked.empty:
            st.info("No ranked variants are available.")
        else:
            sample = ranked.head(100).copy()
            assists = pd.DataFrame([formal_acmg_assistance(row) for row in sample.to_dict(orient="records")])
            review = pd.concat([sample.reset_index(drop=True), assists], axis=1)
            smart_dataframe(review, height=430, key="step99_formal_acmg_assist")
            insight_callout("Clinical boundary", "The rules generate review prompts only. A qualified laboratory must confirm variant identity, gene mechanism, segregation, evidence strength and final classification.", tone="warning")
    with spectrum_tab:
        smart_dataframe(variant_spectrum_audit(variants), height=320, key="step99_variant_spectrum")
    with reanalysis_tab:
        case_id = st.text_input("Case identifier", "CASE-001", key="step99_case_id")
        months = st.slider("Reanalysis interval (months)", 3, 36, 12, 3, key="step99_reanalysis_months")
        plan = rare_disease_reanalysis_plan(case_id, {"ClinVar": "record current release", "gnomAD": "record current release", "ClinGen": "record current release"}, months)
        smart_json(plan, key="step99_reanalysis_plan")
        _download_json("Download reanalysis plan", plan, "rare_disease_reanalysis_plan.json", "step99_reanalysis_download")


def render_knowledge_graph_excellence(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 99 · Evidence-grounded graph intelligence", "🕸")
    normalize_tab, evidence_tab, retrieval_tab = st.tabs(["Entity normalization", "Evidence scoring", "Citation-grounded retrieval"])
    with normalize_tab:
        normalized = normalize_biomedical_entities(nodes)
        metric_cards([
            ("Entities", len(normalized), None),
            ("Normalized duplicates", int(normalized.get("duplicate_normalized_key", pd.Series(dtype=bool)).sum()), None),
            ("Entity types", normalized.get("type", pd.Series(dtype=str)).nunique(), None),
        ])
        smart_dataframe(normalized, height=400, key="step99_kg_entities")
    with evidence_tab:
        scored = score_evidence_edges(edges)
        smart_dataframe(scored, height=430, key="step99_kg_scored_edges")
    with retrieval_tab:
        query = st.text_input("Evidence question", "Which evidence connects this gene to disease and treatment?", key="step99_kg_query")
        docs = pd.DataFrame({
            "document_id": [f"EDGE-{i+1}" for i in range(len(edges))],
            "citation": edges.get("citation", pd.Series([""] * len(edges))).astype(str),
            "text": edges.apply(lambda row: f"{row.get('source','')} {row.get('relation','related to')} {row.get('target','')}. Evidence type {row.get('evidence_type','unspecified')}. Direction {row.get('direction','unknown')}.", axis=1),
        })
        retrieval = exact_evidence_retrieval(query, docs, top_k=8) if query.strip() and not docs.empty else pd.DataFrame()
        smart_dataframe(retrieval, height=380, key="step99_kg_retrieval")
        bundle = claim_evidence_bundle(query, retrieval)
        _download_json("Download citation evidence bundle", bundle, "knowledge_graph_evidence_bundle.json", "step99_kg_bundle_download")


def render_biomarker_excellence(
    data: pd.DataFrame,
    outcome_column: str,
    features: Sequence[str],
    predictions: pd.DataFrame | None,
) -> None:
    st.divider()
    section_title("Step 99 · Biomarker robustness and utility", "📈")
    harmonize_tab, stability_tab, decision_tab = st.tabs(["Harmonization & missingness", "Selection stability", "Decision utility"])
    with harmonize_tab:
        harmonized, mapping = harmonize_multiomics_columns(data)
        missing, report = multiomics_missingness(harmonized)
        metric_cards([
            ("Samples", report["samples"], None),
            ("Features", report["features"], None),
            ("Missing cells", f"{report['cells_missing_fraction']:.1%}", None),
            (">40% missing", report["features_over_40pct_missing"], None),
        ])
        c1, c2 = st.columns(2)
        with c1:
            smart_dataframe(mapping, height=330, key="step99_omics_mapping")
        with c2:
            smart_dataframe(missing, height=330, key="step99_omics_missingness")
    with stability_tab:
        iterations = st.slider("Bootstrap iterations", 10, 200, 40, 10, key="step99_biomarker_iterations")
        if st.button("Run selection stability", key="step99_run_biomarker_stability", width="stretch"):
            try:
                stability = biomarker_selection_stability(data, outcome_column, features, iterations=iterations)
                st.session_state["step99_biomarker_stability"] = stability
            except Exception as exc:
                st.error(str(exc))
        stability = st.session_state.get("step99_biomarker_stability")
        if isinstance(stability, pd.DataFrame):
            smart_dataframe(stability, height=420, key="step99_biomarker_stability_table")
    with decision_tab:
        if predictions is None or predictions.empty or not {"observed", "probability"}.issubset(predictions.columns):
            st.info("Run the biomarker model first to generate out-of-fold observed outcomes and probabilities.")
        else:
            curve = decision_curve_analysis(predictions["observed"], predictions["probability"])
            st.plotly_chart(px.line(curve, x="threshold", y=["model_net_benefit", "treat_all_net_benefit", "treat_none_net_benefit"], title="Decision-curve analysis"), width="stretch")
            smart_dataframe(curve, height=300, key="step99_decision_curve")


def render_workflow_excellence(dag: pd.DataFrame) -> None:
    st.divider()
    section_title("Step 99 · Typed workflow and marketplace trust", "🔗")
    schema_tab, critical_tab, trust_tab = st.tabs(["Schema-aware connections", "Critical path", "Marketplace trust"])
    with schema_tab:
        audit, report = workflow_schema_audit(dag)
        metric_cards([
            ("Steps", report["steps"], None),
            ("Compatible", report["compatible"], None),
            ("Mismatches", report["mismatches"], None),
            ("Typed DAG", "Valid" if report["valid"] else "Review", None),
        ])
        smart_dataframe(audit, height=420, key="step99_workflow_schema")
    with critical_tab:
        try:
            table, report = workflow_critical_path(dag, WORKFLOW_BLOCKS)
            metric_cards([
                ("Critical path", f"{report['critical_path_minutes']:.1f} min", None),
                ("Critical steps", report["critical_steps"], None),
                ("Parallel opportunities", report["parallelism_opportunity"], None),
            ])
            smart_dataframe(table, height=380, key="step99_workflow_critical")
        except Exception as exc:
            st.warning(str(exc))
    with trust_tab:
        templates = pd.DataFrame([
            {"template": "Genome QC to assembly", "signed": True, "tests_passed": True, "container_pinned": False, "license_declared": True, "example_data": True, "security_scanned": True},
            {"template": "Multi-omics biomarker", "signed": True, "tests_passed": True, "container_pinned": True, "license_declared": True, "example_data": True, "security_scanned": True},
            {"template": "User-imported workflow", "signed": False, "tests_passed": False, "container_pinned": False, "license_declared": False, "example_data": False, "security_scanned": False},
        ])
        smart_dataframe(marketplace_trust_score(templates), height=300, key="step99_marketplace_trust")


def render_innovation_hub_excellence() -> None:
    st.divider()
    section_title("Step 99 · Live module readiness", "✨")
    tool_names = sorted({tool for requirement in [
        ["odgi", "vg", "minigraph"], ["flye", "hifiasm", "quast", "busco"], ["proteinmpnn", "rfdiffusion", "colabfold_batch"], ["mageck"], ["mash", "iqtree", "amrfinderplus"], ["bcftools", "vep", "snpeff"]
    ] for tool in requirement})
    status = {}
    for tool in tool_names:
        try:
            status[tool] = bool(verified_tool_status(tool).get("available", False))
        except Exception:
            status[tool] = False
    readiness = innovation_readiness(status)
    role_col, gpu_col, offline_col = st.columns(3)
    role = role_col.selectbox("Primary role", ["Bioinformatician", "Drug discovery scientist", "Wet-lab scientist", "Platform engineer"], key="step99_hub_role")
    has_gpu = gpu_col.toggle("CUDA-capable GPU available", value=False, key="step99_hub_gpu")
    offline = offline_col.toggle("Prefer offline workflows", value=True, key="step99_hub_offline")
    ranked = innovation_recommendations(readiness, role, has_gpu, offline)
    metric_cards([
        ("Ready modules", int((readiness["status"] == "Ready").sum()), None),
        ("Partially ready", int((readiness["status"] == "Partially ready").sum()), None),
        ("External tools missing", int((readiness["status"] == "External tools missing").sum()), None),
        ("Best recommendation", ranked.iloc[0]["module"] if not ranked.empty else "—", None),
    ])
    smart_dataframe(ranked, height=500, key="step99_innovation_readiness")
    st.download_button("Export module readiness", ranked.to_csv(index=False).encode(), "innovation_module_readiness.csv", "text/csv", key="step99_hub_download")
