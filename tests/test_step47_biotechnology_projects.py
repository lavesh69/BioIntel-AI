from __future__ import annotations

from pathlib import Path

import numpy as np
from streamlit.testing.v1 import AppTest

from biointel.portfolio.project_registry import list_projects
from biointel.projects.cancer_genomics import demo_cancer_variants, run_cancer_genomics_pipeline
from biointel.projects.catalog import PROJECT_CATALOG
from biointel.projects.comparative_genomics import (
    compare_genomes,
    demo_query_panel,
    demo_reference_panel,
)
from biointel.projects.metagenomics_pipeline import (
    demo_metagenomics_data,
    run_metagenomics_pipeline,
)
from biointel.projects.ppi import compare_algorithms, demo_ppi_pairs, train_ppi_classifier
from biointel.projects.single_cell import demo_single_cell_counts, run_single_cell_pipeline
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step47_catalog_and_navigation_are_complete() -> None:
    assert len(PROJECT_CATALOG) == 5
    assert len(PAGE_CATALOG) >= 89
    expected = {
        "biotechnology_projects",
        "ppi_interaction_ml",
        "comparative_pathogen_genomics",
        "single_cell_heterogeneity",
        "cancer_genomics",
        "metagenomics_pipeline",
    }
    assert expected.issubset(PAGE_BY_KEY)
    assert all((ROOT / PAGE_BY_KEY[key].path).is_file() for key in expected)


def test_step47_projects_are_registered_in_portfolio() -> None:
    projects = {record.project_code: record for record in list_projects(ROOT / "reports" / "projects.sqlite3")}
    assert {project.code for project in PROJECT_CATALOG}.issubset(projects)
    for definition in PROJECT_CATALOG:
        record = projects[definition.code]
        assert record.status == "Active"
        assert record.priority == "High"
        assert "deterministic demo/reference" in record.notes


def test_step47_ppi_ml_workflow_has_useful_deterministic_signal() -> None:
    pairs = demo_ppi_pairs(120)
    comparison = compare_algorithms(pairs)
    result = train_ppi_classifier(pairs, algorithm="Random forest", test_size=0.25)
    assert set(pairs["label"]) == {0, 1}
    assert float(comparison.iloc[0]["roc_auc"]) > 0.85
    assert result.metrics["roc_auc"] > 0.80
    assert len(result.feature_importance) == 10


def test_step47_comparative_genomics_recovers_nearest_demo_references() -> None:
    ranking = compare_genomes(demo_query_panel(), demo_reference_panel(), k=9)
    best = ranking.groupby("query_genome", as_index=False).first().set_index("query_genome")
    assert best.loc["Query_Isolate_01", "reference_genome"] == "Demo_Enterobacterales_A"
    assert best.loc["Query_Isolate_02", "reference_genome"] == "Demo_GramPositive_A"
    assert (best["screening_score"] > 0.7).all()


def test_step47_single_cell_pipeline_resolves_clusters_and_markers() -> None:
    counts = demo_single_cell_counts(genes=320, cells=96, clusters=4)
    result = run_single_cell_pipeline(
        counts,
        min_counts=100,
        min_genes=30,
        top_variable_genes=140,
        n_clusters=4,
    )
    assert result.summary["retained_cells"] >= 80
    assert result.embedding["cluster"].nunique() == 4
    assert len(result.markers) == 48
    assert result.markers["marker_score"].max() > 0


def test_step47_cancer_genomics_prioritizes_research_variants() -> None:
    result = run_cancer_genomics_pipeline(demo_cancer_variants(samples=4, variants_per_sample=30))
    assert result.metrics["samples"] == 4
    assert result.metrics["qc_passing_variants"] > 0
    assert result.metrics["known_cancer_gene_variants"] > 0
    assert result.variants["research_tier"].str.startswith("Tier 1").any()
    assert not result.pathway_summary.empty


def test_step47_metagenomics_pipeline_returns_valid_diversity_geometry() -> None:
    abundance, metadata = demo_metagenomics_data(taxa=50, samples_per_group=5)
    result = run_metagenomics_pipeline(abundance, metadata, group_a="Control", group_b="Case")
    distance = result.distance_matrix.to_numpy(dtype=float)
    assert np.allclose(distance, distance.T)
    assert np.allclose(np.diag(distance), 0)
    assert result.summary["retained_taxa"] > 20
    assert result.summary["screening_taxa"] > 0
    assert set(result.ordination["group"]) == {"Control", "Case"}


def test_step47_project_pages_render_without_streamlit_exceptions() -> None:
    for source in (
        "pages/77_Biotechnology_Project_Center.py",
        "pages/78_Protein_Interaction_ML.py",
        "pages/79_Comparative_Pathogen_Genomics.py",
        "pages/80_Single_Cell_Heterogeneity.py",
        "pages/81_Cancer_Genomics.py",
        "pages/82_Metagenomics_Pipeline.py",
    ):
        app = AppTest.from_file(str(ROOT / source), default_timeout=120).run()
        assert not app.exception, source
        assert len(app.markdown) > 0, source
