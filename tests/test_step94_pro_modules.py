from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from biointel.innovation.engines import (
    PART_LIBRARY, WORKFLOW_TEMPLATES, build_construct, demo_crispr_counts,
    demo_multiomics, demo_outbreak_data, demo_pangenome_graph, demo_protein_sequence,
)
from biointel.innovation.advanced_engines import (
    advanced_protein_design, biomarker_model_advanced, codon_optimize,
    construct_quality, contig_qc_advanced, crispr_replicate_analysis,
    execute_internal_workflow, gibson_primer_plan, graph_conflicts,
    graph_research_gaps, knowledge_graph_paths, long_read_qc_metrics,
    normalize_graph, outbreak_advanced, pangenome_quality_report,
    parse_fastq_advanced, parse_gfa_extended, parse_pdb_residues,
    parse_vcf_extended, perturbseq_advanced, prioritize_variants_advanced,
    validate_workflow_dag, workflow_dag_from_blocks,
)


def test_pangenome_extended_parser_and_audit():
    gfa = "\n".join([
        "H\tVN:Z:1.1",
        "S\t1\tACGTACGT",
        "S\t2\tAAAA",
        "S\t3\tCCCC",
        "S\t4\tGGGG",
        "L\t1\t+\t2\t+\t0M",
        "L\t1\t+\t3\t+\t0M",
        "L\t2\t+\t4\t+\t0M",
        "L\t3\t+\t4\t+\t0M",
        "P\tref\t1+,2+,4+\t*",
        "P\talt\t1+,3+,4+\t*",
    ])
    nodes, edges, paths, issues = parse_gfa_extended(gfa)
    report = pangenome_quality_report(nodes, edges, paths, issues)
    assert report["nodes"] == 4
    assert report["bubble_candidates"] >= 1
    assert report["quality_score"] >= 70


def test_fastq_and_contig_advanced_metrics():
    fastq = "@r1\nACGTACGT\n+\nIIIIIIII\n@r2\nGGGGCCCCAAAA\n+\n555555555555\n"
    reads = parse_fastq_advanced(fastq)
    metrics = long_read_qc_metrics(reads, 0.00002)
    assert metrics["reads"] == 2
    assert metrics["n50"] >= 8
    contigs, summary = contig_qc_advanced(">c1\n" + "ACGT" * 50 + "\n>c2\n" + "GGCC" * 20)
    assert summary["contigs"] == 2
    assert summary["auN"] > 0


def test_protein_design_is_ranked_and_bounded():
    frame = advanced_protein_design(demo_protein_sequence(), "Balanced developability", [1, 2], [10, 11], 40)
    assert not frame.empty
    assert {"blosum62", "pareto_optimal", "uncertainty"}.issubset(frame.columns)
    assert frame["confidence"].between(0, 1).all()


def test_crispr_replicate_fdr():
    base = demo_crispr_counts().head(60)
    data = base[["guide", "gene"]].copy()
    for i in range(1, 3):
        data[f"control_{i}"] = base["control"] + i
        data[f"treated_{i}"] = base["treated"] + i
    guide, gene, metrics = crispr_replicate_analysis(data)
    assert len(guide) == len(data)
    assert gene["fdr"].between(0, 1).all()
    assert metrics["control_replicates"] == 2


def test_perturbseq_advanced():
    rng = np.random.default_rng(94)
    matrix = pd.DataFrame(rng.normal(size=(40, 8)), columns=[f"g{i}" for i in range(8)])
    labels = ["NTC"] * 20 + ["KO"] * 20
    matrix.loc[20:, "g0"] += 2
    result = perturbseq_advanced(matrix, labels, "NTC")
    assert len(result["embedding"]) == 40
    assert not result["differential"].empty


def test_outbreak_advanced_outputs_mst():
    samples, distances = demo_outbreak_data()
    result = outbreak_advanced(samples, distances, 12, 30, 100)
    assert len(result["samples"]) == len(samples)
    assert "outbreak_cluster" in result["samples"]
    assert not result["cluster_summary"].empty


def test_synbio_quality_and_exports():
    seq, architecture, _ = build_construct(["pLac promoter", "Strong RBS", "GFP CDS", "Double terminator"])
    quality = construct_quality(seq)
    primers = gibson_primer_plan(["pLac promoter", "Strong RBS", "GFP CDS"], 20, 18)
    optimized = codon_optimize(PART_LIBRARY["GFP CDS"], "E. coli")
    assert quality["length"] == len(seq)
    assert len(primers) == 3
    assert len(optimized["optimized"]) == len(optimized["original"])


def test_vcf_extended_and_prioritization():
    vcf = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tPROBAND
1\t100\t.\tA\tT\t99\tPASS\tGENE=SCN1A;CSQ=stop_gained;AF=0.00001;CLNSIG=Pathogenic;CADD=30;REVEL=0.9\tGT\t0/1
"""
    frame = parse_vcf_extended(vcf)
    ranked = prioritize_variants_advanced(frame, ["HP:0001250"], "Autosomal dominant")
    assert ranked.iloc[0]["gene"] == "SCN1A"
    assert ranked.iloc[0]["evidence_tier"] == "High"


def test_graph_import_paths_conflicts_and_gaps():
    nodes = pd.DataFrame([("A", "Gene"), ("B", "Disease"), ("C", "Drug")], columns=["node", "type"])
    edges = pd.DataFrame([
        ("A", "B", "associated", 0.9, "curated", "PMID:1", "supporting"),
        ("B", "C", "treated_by", 0.8, "trial", "NCT1", "supporting"),
        ("A", "B", "not_associated", 0.4, "study", "PMID:2", "refuting"),
    ], columns=["source", "target", "relation", "evidence_score", "evidence_type", "citation", "direction"])
    n, e, issues = normalize_graph(nodes, edges)
    paths = knowledge_graph_paths(e, "A", "C", 3)
    conflicts = graph_conflicts(e)
    gaps = graph_research_gaps(n, e)
    assert issues.empty
    assert not paths.empty
    assert not conflicts.empty
    assert len(gaps) == 3


def test_biomarker_nested_cv_and_permutation():
    data = demo_multiomics(100, 94)
    result = biomarker_model_advanced(data, "outcome", "batch", "Logistic L1", 2, 2, 5, 94)
    assert result["metrics"]["samples"] == 100
    assert 0 <= result["metrics"]["roc_auc"] <= 1
    assert len(result["predictions"]) == 100
    assert not result["importance"].empty


def test_workflow_dag_and_resume(tmp_path: Path):
    blocks = next(iter(WORKFLOW_TEMPLATES.values()))
    dag = workflow_dag_from_blocks(blocks)
    validated, summary = validate_workflow_dag(dag)
    assert summary["valid"]
    first = execute_internal_workflow(dag, tmp_path, "test_workflow", True)
    second = execute_internal_workflow(dag, tmp_path, "test_workflow", True)
    assert first.status == "completed"
    assert second.run_id == first.run_id
    assert Path(first.output_directory, "run_summary.json").is_file()
