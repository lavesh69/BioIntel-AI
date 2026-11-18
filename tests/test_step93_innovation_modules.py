from __future__ import annotations

from pathlib import Path

from biointel.innovation.engines import (
    WORKFLOW_TEMPLATES,
    biomarker_model,
    crispr_screen_analysis,
    demo_crispr_counts,
    demo_multiomics,
    demo_outbreak_data,
    demo_pangenome_graph,
    demo_variants,
    outbreak_clusters,
    pangenome_metrics,
    prioritize_variants,
    protein_design_candidates,
    validate_workflow,
)
from biointel.ui.navigation import PAGE_BY_KEY


def test_step93_navigation_pages_exist():
    root = Path(__file__).resolve().parents[1]
    keys = {
        "innovation_modules_hub", "pangenome_graph", "long_read_assembly", "protein_design_lab",
        "crispr_perturbseq", "pathogen_outbreak", "synthetic_biology_designer", "rare_disease_board",
        "knowledge_graph_copilot", "multiomics_biomarker", "visual_workflow_builder",
    }
    assert keys.issubset(PAGE_BY_KEY)
    for key in keys:
        assert (root / PAGE_BY_KEY[key].path).is_file()


def test_pangenome_and_outbreak_engines():
    nodes, edges, paths = demo_pangenome_graph()
    metrics = pangenome_metrics(nodes, edges, paths)
    assert metrics["nodes"] >= 10
    samples, distances = demo_outbreak_data()
    clustered, links = outbreak_clusters(samples, distances, 12)
    assert clustered["outbreak_cluster"].nunique() >= 2
    assert not links.empty


def test_crispr_protein_and_rare_disease_engines():
    _, genes, metrics = crispr_screen_analysis(demo_crispr_counts())
    assert metrics["genes"] >= 20
    assert {"Negative-selection hit", "Positive-selection hit"}.issubset(set(genes["hit_class"]))
    candidates = protein_design_candidates("MKKIGYSAPRQTQKDLKELGVEVVEFDVVEGEGDTL", top_n=20)
    assert len(candidates) == 20
    ranked = prioritize_variants(demo_variants(), ["HP:0001250"], "De novo dominant")
    assert ranked.iloc[0]["priority_score"] >= ranked.iloc[-1]["priority_score"]


def test_biomarker_and_workflow_engines():
    result = biomarker_model(demo_multiomics(120), "outcome", "batch", 4)
    assert 0 <= result["metrics"]["roc_auc"] <= 1
    frame, summary = validate_workflow(WORKFLOW_TEMPLATES["Long-read genome assembly"])
    assert len(frame) >= 5
    assert summary["final_output"] == "report"
