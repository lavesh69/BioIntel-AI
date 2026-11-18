from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.projects.cancer_genomics import (
    demo_cancer_variants,
    gene_association_screen,
    recurrent_hotspot_screen,
    run_cancer_genomics_pipeline,
    sample_mutation_similarity,
    sample_quality_tiers,
    six_class_signature_exposure,
    vaf_confidence_intervals,
)
from biointel.projects.comparative_genomics import (
    assignment_bootstrap_stability,
    demo_query_panel,
    demo_reference_panel,
    gc_skew_profile,
    pangenome_kmer_presence,
    predict_orfs,
    window_reference_assignment,
)
from biointel.projects.metagenomics_pipeline import (
    beta_dispersion,
    demo_metagenomics_data,
    differential_abundance_permutation,
    indicator_taxa,
    leave_one_out_pcoa_stability,
    prevalence_sensitivity,
    run_metagenomics_pipeline,
)
from biointel.projects.ppi import (
    bootstrap_classification_metrics,
    candidate_ood_report,
    cold_start_validation,
    decision_curve_analysis,
    demo_ppi_pairs,
    train_and_score_ppi_classifier,
)
from biointel.projects.professional import QualityGate, model_card_payload, quality_gate_table
from biointel.projects.reporting import build_project_bundle, build_run_manifest
from biointel.projects.run_registry import compare_runs, list_runs, register_run
from biointel.projects.single_cell import (
    batch_effect_audit,
    cluster_quality_metrics,
    demo_single_cell_counts,
    dropout_profile,
    marker_specificity,
    pseudobulk_expression,
    run_single_cell_pipeline,
    trajectory_screen,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step49_ppi_deep_validation_uncertainty_and_ood() -> None:
    training = demo_ppi_pairs(100)
    candidates = training.drop(columns=["label"]).head(10)
    result, _ = train_and_score_ppi_classifier(training, candidates)
    cold_metrics, cold_predictions = cold_start_validation(training)
    intervals = bootstrap_classification_metrics(result.predictions, samples=120)
    ood = candidate_ood_report(training, candidates)
    decision = decision_curve_analysis(result.predictions)
    assert cold_metrics.loc[0, "held_out_proteins"] > 0
    assert set(cold_predictions["cold_start_type"]).issubset({"cold_one", "cold_both"})
    assert set(intervals["metric"]) == {"roc_auc", "balanced_accuracy", "f1", "precision", "recall"}
    assert len(ood) == len(candidates)
    assert set(ood["ood_status"]).issubset({"in_domain", "review", "high"})
    assert {"model_net_benefit", "treat_all_net_benefit"}.issubset(decision.columns)


def test_step49_comparative_genomics_bootstrap_windows_orfs_and_pangenome() -> None:
    queries = demo_query_panel()
    references = demo_reference_panel()
    stability = assignment_bootstrap_stability(queries, references, k=9, repeats=20)
    windows = window_reference_assignment(queries[0], references, k=9, window=200, step=100)
    skew = gc_skew_profile(queries[0], window=100, step=50)
    orfs = predict_orfs(queries[0], minimum_amino_acids=10)
    matrix, summary = pangenome_kmer_presence([*queries, *references], k=7, maximum_kmers=100)
    assert len(stability) == len(queries)
    assert stability["bootstrap_support_percent"].between(0, 100).all()
    assert not windows.empty and not skew.empty
    assert set(orfs.columns) >= {"strand", "frame", "length_aa"}
    assert len(matrix) <= 100
    assert set(summary["category"]) == {"core", "shell", "unique", "total"}


def test_step49_single_cell_batch_cluster_pseudobulk_and_trajectory() -> None:
    counts = demo_single_cell_counts(genes=220, cells=72, clusters=3)
    result = run_single_cell_pipeline(
        counts,
        min_counts=10,
        min_genes=5,
        max_mito_percent=50,
        top_variable_genes=90,
        n_clusters=3,
    )
    cells = [column for column in counts.columns if column != "gene"]
    metadata = pd.DataFrame(
        {
            "cell": cells,
            "sample": ["S1" if index < len(cells) // 2 else "S2" for index in range(len(cells))],
            "batch": ["B1" if index % 2 == 0 else "B2" for index in range(len(cells))],
            "condition": ["Control" if index < len(cells) // 2 else "Case" for index in range(len(cells))],
        }
    )
    embedding = result.embedding.merge(metadata, on="cell", how="left")
    assert not batch_effect_audit(embedding, metadata).empty
    assert not cluster_quality_metrics(result.embedding).empty
    assert not pseudobulk_expression(result.normalized, result.embedding, metadata).empty
    assert not marker_specificity(result.markers).empty
    cells_table, edges = trajectory_screen(result.embedding)
    assert "screening_pseudotime" in cells_table.columns
    assert len(edges) == result.embedding["cluster"].nunique() - 1
    assert not dropout_profile(result.filtered_counts).empty


def test_step49_cancer_uncertainty_recurrence_similarity_and_association() -> None:
    variants = demo_cancer_variants(samples=6, variants_per_sample=30)
    result = run_cancer_genomics_pipeline(variants)
    passing = result.variants[result.variants["passes_qc"]]
    intervals = vaf_confidence_intervals(result.variants)
    hotspots = recurrent_hotspot_screen(passing)
    similarity = sample_mutation_similarity(passing)
    associations = gene_association_screen(passing, top_genes=12)
    tiers = sample_quality_tiers(result.variants)
    exposure = six_class_signature_exposure(passing)
    assert intervals["vaf_ci95_lower"].between(0, 1).all()
    assert intervals["vaf_ci95_upper"].between(0, 1).all()
    assert not hotspots.empty and not similarity.empty and not tiers.empty
    assert set(associations.get("association_type", [])) <= {"co_occurrence", "mutual_exclusion", "neutral"}
    assert abs(float(exposure["exposure_fraction"].sum()) - 1.0) < 1e-9


def test_step49_metagenomics_permutation_dispersion_indicators_and_stability() -> None:
    abundance, metadata = demo_metagenomics_data(taxa=40, samples_per_group=4)
    result = run_metagenomics_pipeline(abundance, metadata, group_a="Control", group_b="Case")
    permutation = differential_abundance_permutation(result.relative_abundance, metadata, permutations=99)
    dispersion = beta_dispersion(result.distance_matrix, metadata)
    indicators = indicator_taxa(result.relative_abundance, metadata)
    sensitivity = prevalence_sensitivity(abundance)
    stability = leave_one_out_pcoa_stability(result.distance_matrix)
    assert permutation["fdr_q_value"].between(0, 1).all()
    assert len(dispersion) == len(metadata)
    assert not indicators.empty
    assert sensitivity["minimum_prevalence"].is_monotonic_increasing
    assert stability["pairwise_geometry_correlation"].between(-1, 1).all()


def test_step49_research_bundle_contains_report_method_card_and_schema_v2() -> None:
    inputs = {"input": pd.DataFrame({"value": [1, 2, 3]})}
    outputs = {"result": pd.DataFrame({"score": [0.1, 0.5, 0.9]})}
    gates = quality_gate_table([QualityGate("T-1", "Test gate", "pass", 100.0, "evidence", "none")])
    manifest = build_run_manifest(
        project_code="TEST-49",
        project_name="Test Step 49",
        parameters={"seed": 42},
        inputs=inputs,
        outputs=outputs,
        scientific_boundary="Research only.",
    )
    card = model_card_payload(
        project_code="TEST-49",
        title="Test Step 49",
        intended_use="Testing",
        out_of_scope=["Clinical use"],
        methodology=["Deterministic test"],
        metrics={"score": 0.9},
        validation=["Unit test"],
        limitations=["Test only"],
        quality_gates=gates,
        run_fingerprint=manifest["run_fingerprint"],
    )
    bundle = build_project_bundle(
        project_code="TEST-49",
        project_name="Test Step 49",
        parameters={"seed": 42},
        inputs=inputs,
        outputs=outputs,
        scientific_boundary="Research only.",
        quality_gates=gates,
        methods=["Deterministic test"],
        model_card=card,
    )
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"manifest.json", "report.html", "quality_gates.csv", "methods.json", "model_card.json"}.issubset(names)
        payload = json.loads(archive.read("manifest.json"))
        report = archive.read("report.html").decode("utf-8")
    assert payload["schema_version"] == "2.0"
    assert "input_profiles" in payload and "output_profiles" in payload
    assert "Scientific boundary" in report


def test_step49_run_registry_records_and_compares_runs(tmp_path: Path) -> None:
    registry = tmp_path / "runs.sqlite3"
    for index in range(2):
        register_run(
            registry,
            run_fingerprint=f"run-{index}",
            project_code="BIO-PPI-ML",
            project_name="PPI",
            status="qualified",
            quality_score=80 + index,
            input_rows=100,
            output_rows=200,
            parameters={"seed": index},
            metrics={"roc_auc": 0.8 + index * 0.05},
        )
    runs = list_runs(registry, project_code="BIO-PPI-ML")
    comparison = compare_runs(registry, project_code="BIO-PPI-ML")
    assert len(runs) == 2
    assert "metric_roc_auc" in comparison.columns


def test_step49_api_exposes_project_catalogue_and_run_history() -> None:
    client = TestClient(app)
    catalogue = client.get("/v1/biotechnology/projects")
    history = client.get("/v1/biotechnology/runs", params={"limit": 5})
    assert catalogue.status_code == 200
    assert catalogue.json()["count"] == 5
    assert {item["maturity"] for item in catalogue.json()["projects"]} == {"step49_deep_professional_workbench"}
    assert history.status_code == 200
    assert history.json()["count"] <= 5


def test_step49_pages_expose_deep_assurance_contracts() -> None:
    expected = {
        "pages/78_Protein_Interaction_ML.py": "Deep validation & assurance",
        "pages/79_Comparative_Pathogen_Genomics.py": "Deep genome assurance",
        "pages/80_Single_Cell_Heterogeneity.py": "Deep single-cell assurance",
        "pages/81_Cancer_Genomics.py": "Deep cohort assurance",
        "pages/82_Metagenomics_Pipeline.py": "Deep microbiome assurance",
    }
    for relative, phrase in expected.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert phrase in source
        assert "quality_gates" in source
        assert "model_card" in source
        assert "register_run" in source
