from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.innovation.excellence_engines import (
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
    pangenome_bubble_support,
    pangenome_core_accessory,
    pangenome_graph_integrity,
    pangenome_path_presence,
    pangenome_resource_estimate,
    perturbseq_cell_qc,
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


def test_pangenome_excellence_core_accessory_integrity_and_resources():
    nodes = pd.DataFrame({"node": ["1", "2", "3", "4"], "length": [100, 120, 80, 60], "gc": [50, 48, 52, 45]})
    edges = pd.DataFrame({"source": ["1", "2", "1", "3"], "target": ["2", "4", "3", "4"]})
    paths = pd.DataFrame({"path": ["p1", "p2"], "nodes": ["1,2,4", "1,3,4"]})
    bubbles = pd.DataFrame({"start": ["1"], "end": ["4"], "branch_roots": ["2,3"]})
    presence = pangenome_path_presence(paths)
    prevalence = pangenome_core_accessory(paths, nodes)
    integrity = pangenome_graph_integrity(nodes, edges, paths)
    support = pangenome_bubble_support(bubbles, paths)
    estimate = pangenome_resource_estimate(4, 4, 2, 360, 100)
    assert presence.shape == (2, 5)
    assert set(prevalence["class"]) == {"Core", "Accessory"}
    assert (integrity["severity"] != "error").all()
    assert support.iloc[0]["paths_supporting_any_branch"] == 2
    assert estimate["recommended_ram_gb"] >= 4


def test_long_read_platform_resource_and_t2t_audits():
    reads = pd.DataFrame({"length": [12000, 20000, 8000], "mean_q": [25, 24, 26]})
    metrics = {"mean_q": 25, "n50": 12000, "q20_base_fraction": 0.9, "estimated_coverage": 30}
    checks, report = long_read_platform_qc(reads, metrics, "PacBio HiFi")
    assert report["checks_passed"] == 4
    assert len(long_read_resource_plan(5, 30, "PacBio HiFi", "Bacterial/microbial")) == 4
    assert len(polishing_workflow("Oxford Nanopore", True)) == 3
    contigs = pd.DataFrame({"contig": ["c1", "c2"], "length": [1000000, 5000], "n_per_100kb": [0, 20], "left_telomere_hits": [3, 0], "right_telomere_hits": [4, 0]})
    audited, t2t = t2t_completeness_audit(contigs, {"n50": 1000000, "largest": 1000000})
    assert audited["chromosome_candidate"].sum() == 1
    assert t2t["t2t_readiness_score"] > 50


def test_protein_design_excellence_outputs_consensus_pairs_and_risk():
    candidates = pd.DataFrame({
        "mutation": ["A5V", "L20I", "G6A"],
        "design_score": [0.9, 0.8, 0.7],
        "stability_score": [0.8, 0.7, 0.6],
        "solubility_score": [0.7, 0.9, 0.5],
        "confidence": [0.9, 0.8, 0.7],
        "pareto_optimal": [True, True, False],
        "risk_flag": ["conservative", "conservative", "review"],
    })
    consensus = protein_design_consensus(candidates)
    pairs = protein_pair_designs("A" * 30, consensus)
    liabilities = protein_sequence_developability("AVILMFWY" * 5)
    plan = protein_design_validation_plan("Stability first", len(candidates))
    assert consensus.iloc[0]["review_priority"] == "Top consensus"
    assert not pairs.empty
    assert liabilities["developability_risk"].max() > 0
    assert len(plan) == 4


def test_crispr_excellence_qc_adjustment_cell_qc_and_design():
    counts = pd.DataFrame({
        "guide": ["g1", "g2", "g3"], "gene": ["A", "A", "B"],
        "control_1": [100, 10, 0], "control_2": [110, 8, 0],
        "treated_1": [20, 5, 0], "treated_2": [22, 4, 0],
    })
    qc, metrics = crispr_library_qc(counts, ["control_1", "control_2"], ["treated_1", "treated_2"])
    assert metrics["guides"] == 3
    gene = pd.DataFrame({"gene": ["A", "B"], "median_log2_fc": [-2.0, -1.0]})
    adjusted = crispr_copy_number_adjustment(gene, pd.DataFrame({"gene": ["A", "B"], "copy_number": [8, 2]}))
    assert adjusted.loc[0, "cn_bias_flag"]
    expression = pd.DataFrame({"x": [1, 2, 100], "y": [1, 2, 100]})
    cells, cell_metrics = perturbseq_cell_qc(expression, ["NTC", "A", "B"])
    assert len(cells) == 3
    design = crispr_design_matrix(pd.DataFrame({"condition": ["c", "t"], "batch": ["a", "b"]}), "condition", ["batch"])
    assert "intercept" in design


def test_outbreak_excellence_profiles_links_and_recombination():
    samples = pd.DataFrame({
        "sample_id": ["A", "B", "C"],
        "collection_date": ["2026-01-01", "2026-01-05", "2026-03-01"],
        "location": ["Ward1", "Ward1", "Ward2"],
    })
    links = pd.DataFrame({"source": ["A", "A"], "target": ["B", "C"], "snp_distance": [1, 20], "days_apart": [4, 59], "distance_km": [1, 100]})
    audited, metrics = outbreak_epidemiology_audit(samples, links)
    assert audited.iloc[0]["review_priority"] == "High"
    assert metrics["links"] == 2
    distances = pd.DataFrame([[0, 1, 40], [1, 0, 42], [40, 42, 0]], index=["A", "B", "C"], columns=["A", "B", "C"])
    screen = outbreak_recombination_screen(distances)
    assert len(screen) == 3
    assert outbreak_profile("SARS-CoV-2")["snp"] == 3


def test_synthetic_biology_simulation_manufacturability_burden_and_export():
    sim = simulate_genetic_circuit()
    assert len(sim) == 241
    findings, report = construct_manufacturability("ATG" + "A" * 10 + "GGTCTC" + "CGT" * 20)
    assert report["findings"] >= 2
    parts = pd.DataFrame({"part": ["promoter", "CDS"], "length": [100, 900], "strength": [1.0, 1.5]})
    burden = chassis_burden_estimate(parts, "E. coli", 100)
    assert burden["burden_score"] > 0
    sbol = sbol_like_document("Test", "ATGC", parts, "E. coli")
    assert sbol["schema"].startswith("biointel.sbol")


def test_rare_disease_hpo_acmg_spectrum_and_reanalysis():
    normalized = normalize_hpo_terms(["HP:0001250", "hypotonia"])
    assert normalized["normalized"].all()
    assist = formal_acmg_assistance({"gnomad_af": 0.0, "consequence": "stop_gained", "clinvar": "pathogenic", "is_de_novo": True})
    assert "PVS1_candidate" in assist["criteria"]
    spectrum = variant_spectrum_audit(pd.DataFrame({"variant_type": ["SNV", "CNV"], "consequence": ["missense", "deletion"]}))
    assert spectrum["count"].sum() == 2
    plan = rare_disease_reanalysis_plan("CASE", {"ClinVar": "2026-01"}, 12)
    assert len(plan["snapshot_sha256"]) == 64


def test_knowledge_graph_normalization_scoring_and_retrieval():
    nodes = pd.DataFrame({"node": ["BRCA1", "brca1", "Breast cancer"], "type": ["gene", "gene", "disease"]})
    normalized = normalize_biomedical_entities(nodes)
    assert normalized["duplicate_normalized_key"].sum() == 2
    edges = pd.DataFrame({"source": ["BRCA1"], "target": ["Breast cancer"], "relation": ["associated_with"], "evidence_score": [0.8], "evidence_type": ["curated database"], "citation": ["PMID:123"], "direction": ["supports"]})
    scored = score_evidence_edges(edges)
    assert scored.iloc[0]["evidence_quality_score"] > 0.7
    docs = pd.DataFrame({"document_id": ["d1", "d2"], "text": ["BRCA1 is associated with hereditary breast cancer.", "TP53 controls DNA damage response."], "citation": ["PMID:1", "PMID:2"]})
    retrieval = exact_evidence_retrieval("BRCA1 breast cancer", docs)
    assert retrieval.iloc[0]["document_id"] == "d1"
    bundle = claim_evidence_bundle("query", retrieval)
    assert len(bundle["bundle_sha256"]) == 64


def test_multiomics_harmonization_missingness_stability_and_decision_curve():
    frame = pd.DataFrame({
        "Sample ID": [f"S{i}" for i in range(40)],
        "Outcome": [0, 1] * 20,
        "rna GeneA": np.r_[np.random.default_rng(1).normal(0, 1, 20), np.random.default_rng(2).normal(2, 1, 20)],
        "protein GeneA": np.random.default_rng(3).normal(size=40),
    })
    harmonized, mapping = harmonize_multiomics_columns(frame)
    assert "sample_id" in harmonized
    missing, report = multiomics_missingness(harmonized)
    assert report["samples"] == 40
    stability = biomarker_selection_stability(harmonized, "outcome", ["rna_genea", "protein_genea"], iterations=10)
    assert len(stability) == 2
    curve = decision_curve_analysis([0, 1, 0, 1], [0.1, 0.8, 0.2, 0.9])
    assert len(curve) == 18


def test_workflow_schema_critical_path_and_marketplace_trust():
    dag = pd.DataFrame([
        {"id": "a", "block": "FASTQ QC", "depends_on": "", "condition": "always", "enabled": True},
        {"id": "b", "block": "Genome assembly", "depends_on": "a", "condition": "always", "enabled": True},
        {"id": "c", "block": "Assembly review", "depends_on": "b", "condition": "always", "enabled": True},
    ])
    audit, report = workflow_schema_audit(dag)
    assert report["valid"]
    table, critical = workflow_critical_path(dag, {"FASTQ QC": {"minutes": 1}, "Genome assembly": {"minutes": 10}, "Assembly review": {"minutes": 2}})
    assert critical["critical_path_minutes"] == 13
    trust = marketplace_trust_score(pd.DataFrame([{"template": "x", "signed": True, "tests_passed": True, "container_pinned": True, "license_declared": True, "example_data": True, "security_scanned": True}]))
    assert trust.iloc[0]["trust_score"] == 100


def test_innovation_hub_readiness_and_recommendations():
    readiness = innovation_readiness({"odgi": True, "vg": True, "minigraph": True})
    assert len(readiness) == 11
    ranked = innovation_recommendations(readiness, "Bioinformatician", has_gpu=False, prefers_offline=True)
    assert ranked.iloc[0]["recommendation_score"] >= ranked.iloc[-1]["recommendation_score"]
