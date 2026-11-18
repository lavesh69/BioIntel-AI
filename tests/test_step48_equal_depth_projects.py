from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from biointel.projects.cancer_genomics import (
    clonality_screen,
    demo_cancer_variants,
    gene_cooccurrence_matrix,
    oncoprint_matrix,
    run_cancer_genomics_pipeline,
    snv_spectrum,
    threshold_sensitivity,
    variant_qc_report,
)
from biointel.projects.comparative_genomics import (
    best_hit_summary,
    compare_genomes,
    demo_marker_panel,
    demo_query_panel,
    demo_reference_panel,
    distance_matrix,
    genome_qc,
    pairwise_variant_table,
    screen_markers_with_tolerance,
    upgma_newick,
)
from biointel.projects.metagenomics_pipeline import (
    aitchison_distance,
    alpha_group_summary,
    core_microbiome,
    demo_metagenomics_data,
    permanova_screen,
    rarefaction_curve,
    run_metagenomics_pipeline,
    sample_quality_flags,
    taxon_prevalence,
)
from biointel.projects.ppi import (
    calibration_table,
    candidate_network_tables,
    demo_ppi_pairs,
    pair_dataset_qc,
    precision_recall_points,
    split_leakage_audit,
    threshold_analysis,
    train_and_score_ppi_classifier,
)
from biointel.projects.reporting import build_project_bundle
from biointel.projects.single_cell import (
    annotate_clusters_by_markers,
    cluster_stability,
    default_cell_type_markers,
    demo_single_cell_counts,
    differential_expression_between_clusters,
    estimate_doublet_scores,
    run_single_cell_pipeline,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step48_ppi_has_evaluation_calibration_network_and_leakage_controls() -> None:
    pairs = demo_ppi_pairs(80)
    qc, summary = pair_dataset_qc(pairs)
    result, candidates = train_and_score_ppi_classifier(
        pairs,
        pairs.drop(columns=["label"]).head(12),
        algorithm="Logistic regression",
    )
    assert summary["pairs"] == 80
    assert set(qc["status"]).issubset({"Pass", "Review", "Fail"})
    assert len(precision_recall_points(result.predictions)) > 5
    assert len(threshold_analysis(result.predictions)) == 41
    assert not calibration_table(result.predictions).empty
    assert len(split_leakage_audit(pairs, result.predictions)) == 4
    edges, nodes = candidate_network_tables(candidates, threshold=0.5)
    assert set(edges.columns) >= {"protein_a", "protein_b", "interaction_probability"}
    assert set(nodes.columns) >= {"protein", "degree"}


def test_step48_comparative_genomics_has_qc_tree_variants_and_tolerant_markers() -> None:
    queries = demo_query_panel()
    references = demo_reference_panel()
    ranking = compare_genomes(queries, references, k=9)
    best = best_hit_summary(ranking)
    matrix = distance_matrix([*queries, *references], k=9)
    variants = pairwise_variant_table(queries[0], references[0])
    markers = screen_markers_with_tolerance(queries, demo_marker_panel(), maximum_mismatches=1)
    assert (genome_qc(queries, k=9)["qc_status"] == "Pass").all()
    assert len(best) == len(queries)
    assert upgma_newick(matrix).endswith(";")
    assert not variants.empty
    assert {"position_1_based", "variant_type"}.issubset(variants.columns)
    assert {"mismatches", "position_1_based", "strand"}.issubset(markers.columns)


def test_step48_single_cell_has_doublet_stability_annotation_and_cluster_comparison() -> None:
    counts = demo_single_cell_counts(genes=320, cells=96, clusters=4)
    result = run_single_cell_pipeline(
        counts,
        min_counts=100,
        min_genes=30,
        top_variable_genes=140,
        n_clusters=4,
    )
    doublets = estimate_doublet_scores(result.qc)
    stability = cluster_stability(
        result.normalized,
        result.variable_genes,
        n_clusters=4,
        random_seeds=[11, 23, 37],
    )
    scores, annotations = annotate_clusters_by_markers(
        result.normalized,
        result.embedding,
        default_cell_type_markers(),
    )
    comparison = differential_expression_between_clusters(
        result.normalized,
        result.embedding,
        cluster_a="Cluster 1",
        cluster_b="Cluster 2",
    )
    assert len(doublets) == result.summary["input_cells"]
    assert stability["adjusted_rand_index"].between(-1, 1).all()
    assert annotations["cluster"].nunique() == 4
    assert not scores.empty
    assert len(comparison) == 100


def test_step48_cancer_genomics_has_cohort_spectrum_oncoprint_and_sensitivity() -> None:
    variants = demo_cancer_variants(samples=4, variants_per_sample=30)
    result = run_cancer_genomics_pipeline(variants)
    assert len(variant_qc_report(variants)) >= 6
    assert not snv_spectrum(result.variants).empty
    oncoprint = oncoprint_matrix(result.variants, top_genes=12)
    cooccurrence = gene_cooccurrence_matrix(result.variants, top_genes=10)
    assert not oncoprint.empty
    assert np.allclose(cooccurrence.to_numpy(), cooccurrence.to_numpy().T)
    assert len(clonality_screen(result.variants)) == 4
    assert len(threshold_sensitivity(variants)) == 16


def test_step48_metagenomics_has_compositional_geometry_inference_and_rarefaction() -> None:
    abundance, metadata = demo_metagenomics_data(taxa=50, samples_per_group=5)
    result = run_metagenomics_pipeline(abundance, metadata, group_a="Control", group_b="Case")
    prevalence = taxon_prevalence(result.filtered_counts)
    core = core_microbiome(result.relative_abundance)
    aitchison = aitchison_distance(result.relative_abundance)
    permanova = permanova_screen(result.distance_matrix, metadata, permutations=49)
    rarefaction = rarefaction_curve(result.filtered_counts, steps=6, replicates=3)
    alpha_summary = alpha_group_summary(result.alpha_diversity, metadata)
    flags = sample_quality_flags(result.qc)
    assert not prevalence.empty and not core.empty
    assert np.allclose(aitchison.to_numpy(), aitchison.to_numpy().T)
    assert 0 <= permanova["permutation_p_value"] <= 1
    assert rarefaction["sampling_depth"].nunique() == 6
    assert set(alpha_summary["group"]) == {"Control", "Case"}
    assert set(flags["qc_status"]).issubset({"Pass", "Review"})


def test_step48_project_bundle_contains_manifest_inputs_and_outputs() -> None:
    bundle = build_project_bundle(
        project_code="TEST-PROJECT",
        project_name="Test Project",
        parameters={"threshold": 0.5},
        inputs={"input_table": pd.DataFrame({"value": [1, 2]})},
        outputs={"result_table": pd.DataFrame({"score": [0.8, 0.2]})},
        scientific_boundary="Research use only.",
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "README.txt", "inputs/input_table.csv", "outputs/result_table.csv"}.issubset(names)
        manifest = json.loads(archive.read("manifest.json"))
    assert len(manifest["run_fingerprint"]) == 64
    assert manifest["inputs"]["input_table"]["rows"] == 2


def test_step48_equal_depth_pages_render_and_expose_complete_run_actions() -> None:
    expected_actions = {
        "pages/78_Protein_Interaction_ML.py": "Run complete PPI workbench",
        "pages/79_Comparative_Pathogen_Genomics.py": "Run complete comparative-genomics workbench",
        "pages/80_Single_Cell_Heterogeneity.py": "Run complete single-cell workbench",
        "pages/81_Cancer_Genomics.py": "Run complete cancer-genomics workbench",
        "pages/82_Metagenomics_Pipeline.py": "Run complete metagenomics workbench",
    }
    for source, action in expected_actions.items():
        app = AppTest.from_file(str(ROOT / source), default_timeout=120).run()
        assert not app.exception, source
        assert action in [button.label for button in app.button], source
        assert len(app.tabs) >= 3, source
