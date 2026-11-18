from __future__ import annotations

import sqlite3
from pathlib import Path

from biointel import __version__
from biointel.data.dataset_registry import list_datasets
from biointel.data.scientific_registry import scientific_registry_summary
from biointel.dti.feature_cache import FeatureCache
from biointel.genomics.annotations import annotation_summary, parse_gff
from biointel.genomics.fastq import fastq_qc, parse_fastq
from biointel.genomics.variants import parse_vcf, variant_summary

ROOT = Path(__file__).resolve().parents[1]


def test_step30_scaled_reference_files() -> None:
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    demo = ROOT / "data" / "bioinformatics_demo"
    assert fastq_qc(parse_fastq((demo / "demo_reads.fastq").read_text())).reads == 20_000
    assert variant_summary(parse_vcf((demo / "demo_variants.vcf").read_text())).variants == 5_000
    assert annotation_summary(parse_gff((demo / "demo_annotations.gff3").read_text())).genes == 2_000
    assert sum(1 for _ in (demo / "demo_expression_counts.csv").open()) - 1 == 5_000
    assert len(list((demo / "structures").glob("*.pdb"))) == 12


def test_step30_dataset_registry_depth_and_boundary() -> None:
    records = list_datasets(ROOT / "reports" / "datasets.sqlite3", 5000)
    step30 = [record for record in records if record.metadata.get("step") == 30]
    assert len(records) >= 51
    assert len(step30) >= 19
    assert all(record.metadata["synthetic"] is True for record in step30)
    assert all(record.metadata["scientific_release_eligible"] is False for record in step30)
    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM dataset_files").fetchone()[0] >= 19
        assert connection.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0] >= 130
        assert connection.execute("SELECT COUNT(*) FROM dataset_columns").fetchone()[0] >= 2500


def test_step30_experiment_evidence_and_sources() -> None:
    with sqlite3.connect(ROOT / "reports" / "experiments.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_folds").fetchone()[0] == 115
        assert connection.execute("SELECT COUNT(*) FROM hyperparameter_trials").fetchone()[0] == 230
        assert connection.execute("SELECT COUNT(*) FROM experiments WHERE synthetic_demo=0").fetchone()[0] == 0
    with sqlite3.connect(ROOT / "reports" / "evidence.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence_assay_context").fetchone()[0] == 660
        assert connection.execute("SELECT COUNT(*) FROM evidence_replicates").fetchone()[0] == 1980
    with sqlite3.connect(ROOT / "reports" / "internet_downloads.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM scientific_source_catalog").fetchone()[0] == 16


def test_step30_feature_cache_and_summary() -> None:
    stats = FeatureCache(ROOT / "reports" / "feature_cache.sqlite3").stats()
    assert stats.entries >= 1200
    summary = scientific_registry_summary(ROOT)
    assert summary["databases"]["datasets.sqlite3"]["counts"]["dataset_columns"] >= 2500


def test_step30_scientific_summary_api() -> None:
    from fastapi.testclient import TestClient

    from biointel.api.main import app

    response = TestClient(app).get("/scientific-data/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["databases"]["datasets.sqlite3"]["counts"]["datasets"] >= 51
    assert payload["databases"]["evidence.sqlite3"]["counts"]["evidence_replicates"] == 1980
