from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.innovation.professional_engines import (
    acmg_points_assistance,
    assembly_contamination_screen,
    assembly_iteration_compare,
    assembly_storage_guard,
    batch_center_correct,
    circuit_parameter_sensitivity,
    crispr_library_plan,
    dna_assembly_plan,
    evidence_claim_highlight,
    expand_scatter_plan,
    graph_components,
    graph_gene_presence,
    graph_path_genotypes,
    graph_release_diff,
    guide_sequence_qc,
    inheritance_model_screen,
    knowledge_contradiction_audit,
    knowledge_paths,
    knowledge_rdf_export,
    logrank_screen,
    module_dependency_matrix,
    multi_view_latent_factors,
    outbreak_case_audit,
    outbreak_geospatial_summary,
    outbreak_temporal_signal,
    paired_guide_library,
    perturbseq_pseudobulk,
    phenotype_semantic_screen,
    protein_active_learning_queue,
    protein_mutation_library,
    protein_structure_quality,
    similarity_network_fusion_screen,
    simulate_circuit_gillespie,
    simulate_circuit_ode,
    variant_normalisation_audit,
    workflow_cache_key,
    workflow_container_audit,
    workflow_resource_schedule,
    workflow_test_matrix,
)


def test_graph_professional_capabilities():
    nodes = pd.DataFrame({"node": ["1", "2", "3", "4"]})
    edges = pd.DataFrame({"source": ["1", "2", "1"], "target": ["2", "4", "3"]})
    paths = pd.DataFrame({"path": ["p1", "p2"], "nodes": ["1,2,4", "1,3,4"]})
    bubbles = pd.DataFrame({"start": ["1"], "end": ["4"], "branch_roots": ["2,3"]})
    components, report = graph_components(nodes, edges)
    assert report["components"] == 1
    assert len(components) == 4
    genotypes = graph_path_genotypes(paths, bubbles)
    assert set(genotypes["screening_genotype"]) == {"1/1"}
    annotations = pd.DataFrame({"node": ["2", "3", "4"], "gene": ["A", "B", "C"]})
    presence = graph_gene_presence(paths, annotations)
    assert set(["A", "B", "C"]).issubset(presence.columns)
    diff = graph_release_diff(nodes, edges, pd.DataFrame({"node": ["1", "2", "3", "4", "5"]}), edges)
    assert diff["nodes_added"] == ["5"]


def test_long_read_professional_capabilities():
    contigs = pd.DataFrame({"contig": ["a", "b", "c", "d"], "length": [1_000_000, 900_000, 850_000, 2_000], "gc": [50, 49, 51, 80]})
    screened, report = assembly_contamination_screen(contigs)
    assert report["contigs"] == 4
    assert "composition_outlier" in screened
    iterations = pd.DataFrame({"iteration": [1, 2, 3], "n50": [100, 120, 121], "busco_complete": [90, 95, 95.1], "qv": [30, 35, 35.1], "errors": [100, 40, 39]})
    compared = assembly_iteration_compare(iterations)
    assert "marginal_gain_score" in compared
    guard = assembly_storage_guard(3000, 30, "PacBio HiFi", 1000)
    assert guard["recommended_workspace_gb"] > guard["estimated_raw_reads_gb"]


def test_protein_professional_capabilities():
    sequence = "A" * 10 + "L" * 20
    candidates = pd.DataFrame({"mutation": ["A5V", "L20I", "A8G"], "design_score": [0.9, 0.8, 0.7], "confidence": [0.7, 0.6, 0.4]})
    library = protein_mutation_library(sequence, candidates, top_n=3, max_pairs=10)
    assert (library["mutation_count"] == 2).any()
    report = protein_structure_quality([95, 85, 45, 80], clashes=0)
    assert report["residues"] == 4
    queue = protein_active_learning_queue(candidates)
    assert queue.iloc[0]["acquisition_score"] >= queue.iloc[-1]["acquisition_score"]


def test_crispr_professional_capabilities():
    guides = pd.DataFrame({"guide": ["g1", "g2"], "gene": ["A", "B"], "sequence": ["ACGTACGTACGTACGTACGT", "TTTTACGTACGTACGTACGT"]})
    qc = guide_sequence_qc(guides)
    assert qc.loc[1, "poly_t_termination_risk"]
    plan = crispr_library_plan(100, 4, 50, 500, 500)
    assert plan["total_guides"] == 450
    expression = pd.DataFrame({"gene1": [1, 2, 3, 4], "gene2": [5, 6, 7, 8]})
    pseudobulk = perturbseq_pseudobulk(expression, ["A", "A", "B", "B"])
    assert pseudobulk["cell_count"].sum() == 4
    pairs = paired_guide_library(guides)
    assert len(pairs) == 1


def test_outbreak_professional_capabilities():
    samples = pd.DataFrame({
        "sample_id": ["A", "B", "C", "D"],
        "collection_date": ["2026-01-01", "2026-01-05", "2026-02-01", "2026-03-01"],
        "location": ["W1", "W1", "W2", "W3"],
        "latitude": [28.6, 28.61, 28.7, 28.8],
        "longitude": [77.2, 77.21, 77.3, 77.4],
    })
    distances = pd.DataFrame(
        [[0, 1, 10, 20], [1, 0, 9, 19], [10, 9, 0, 8], [20, 19, 8, 0]],
        index=["A", "B", "C", "D"], columns=["A", "B", "C", "D"],
    )
    report = outbreak_temporal_signal(samples, distances)
    assert report["pairs"] == 6
    mapped, geo = outbreak_geospatial_summary(samples)
    assert geo["mapped_samples"] == 4
    audit = outbreak_case_audit(samples, "SARS-CoV-2")
    assert "organism_profile" in set(audit["field"])


def test_synthetic_biology_professional_capabilities():
    ode = simulate_circuit_ode(duration=12)
    assert ode["reporter"].iloc[-1] > 0
    stochastic = simulate_circuit_gillespie(duration=2, seed=1)
    assert len(stochastic) > 1
    params = {"inducer": 1.0, "production_rate": 5.0, "degradation_rate": 0.35, "hill_k": 0.5, "hill_n": 2.0, "burden": 0.15}
    sensitivity = circuit_parameter_sensitivity(params)
    assert set(sensitivity["direction"]) == {"up", "down"}
    plan = dna_assembly_plan("ATGC" * 1000, "Gibson", 1000, 30)
    assert len(plan) == 4


def test_rare_disease_professional_capabilities():
    gene_hpo = pd.DataFrame({"gene": ["SCN1A", "GENE2"], "hpo_terms": ["HP:0001250;HP:0001263", "HP:0000252"]})
    phenotype = phenotype_semantic_screen(["seizure", "developmental delay"], gene_hpo)
    assert phenotype.iloc[0]["gene"] == "SCN1A"
    variants = pd.DataFrame({"gene": ["A", "A", "B"], "zygosity": ["het", "het", "hom"], "chrom": ["1", "1", "X"]})
    inheritance = inheritance_model_screen(variants, "Male")
    assert "Compound-heterozygous" in inheritance.loc[inheritance["gene"] == "A", "candidate_models"].iloc[0]
    acmg = acmg_points_assistance(["PVS1", "PM2", "PP3"])
    assert acmg["point_score"] == 11
    audit = variant_normalisation_audit(pd.DataFrame({"chrom": ["1"], "pos": [100], "ref": ["A"], "alt": ["T"], "build": ["GRCh38"]}))
    assert audit.iloc[0]["normalisation_status"] == "Screening format valid"


def test_knowledge_graph_professional_capabilities():
    nodes = pd.DataFrame({"node": ["A", "B", "C"], "type": ["gene", "disease", "drug"]})
    edges = pd.DataFrame({
        "source": ["A", "A", "B"], "target": ["B", "B", "C"],
        "relation": ["associated_with", "associated_with", "treated_by"],
        "direction": ["supports", "contradicts", "supports"],
    })
    conflicts = knowledge_contradiction_audit(edges)
    assert "Conflicting" in set(conflicts["conflict_status"])
    paths = knowledge_paths(edges, "A", "C", 3)
    assert paths.iloc[0]["hop_count"] == 2
    rdf = knowledge_rdf_export(nodes, edges)
    assert "@prefix" in rdf
    evidence = pd.DataFrame({"text": ["A is associated with B in a curated study."]})
    highlighted = evidence_claim_highlight("A associated B", evidence)
    assert not highlighted.empty


def test_multiomics_professional_capabilities():
    frame = pd.DataFrame({"x": [1, 2, 10, 11], "y": [2, 3, 12, 13]})
    corrected = batch_center_correct(frame, ["A", "A", "B", "B"])
    assert corrected.shape == frame.shape
    views = {"rna": frame, "protein": frame * 2}
    factors, loadings = multi_view_latent_factors(views, components=2)
    assert factors.shape[0] == 4
    assert not loadings.empty
    fused = similarity_network_fusion_screen(views, neighbours=2, iterations=2)
    assert fused.shape == (4, 4)
    survival = logrank_screen([1, 2, 3, 4, 5, 6, 7, 8], [1, 1, 0, 1, 1, 0, 1, 0], [0, 0, 0, 0, 1, 1, 1, 1])
    assert survival["n"] == 8


def test_workflow_and_hub_professional_capabilities():
    dag = pd.DataFrame([
        {"id": "a", "depends_on": "", "duration_minutes": 2, "cpu": 1, "ram_gb": 1, "container": "tool@sha256:" + "a" * 64, "scatter_values": "S1,S2"},
        {"id": "b", "depends_on": "a", "duration_minutes": 4, "cpu": 2, "ram_gb": 2, "container": "tool:latest", "scatter_values": ""},
    ])
    audit = workflow_container_audit(dag)
    assert audit.iloc[0]["digest_pinned"]
    schedule, report = workflow_resource_schedule(dag, 4, 8, 0)
    assert report["valid_dag"]
    assert schedule["finish_minute"].max() == 6
    expanded = expand_scatter_plan(dag)
    assert len(expanded) == 3
    tests = workflow_test_matrix(dag)
    assert len(tests) == 8
    assert len(workflow_cache_key(dag.iloc[0].to_dict(), ["x"])) == 64
    matrix = module_dependency_matrix()
    assert len(matrix) == 11
