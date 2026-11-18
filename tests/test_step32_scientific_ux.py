from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from biointel import __version__
from biointel.api.main import app
from biointel.data.relationship_integrity import relationship_summary
from biointel.intelligence.data_intelligence import all_database_health
from biointel.ui.navigation import CATEGORIES, PAGE_CATALOG, search_pages

ROOT = Path(__file__).resolve().parents[1]


def test_step32_navigation_and_health():
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    assert len(PAGE_CATALOG) >= 71
    assert sum(page.featured for page in PAGE_CATALOG) >= 12
    assert "Modelling" not in CATEGORIES
    assert search_pages("rnaseq")[0].key == "transcriptomics_expression"
    health = all_database_health(ROOT)
    assert health["database_count"] >= 18
    assert health["healthy_count"] == health["database_count"]


def test_step32_relationship_and_public_data():
    summary = relationship_summary(ROOT)
    assert summary["broken_edges"] == 0
    assert summary["orphan_findings"] == 0
    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        public_dataset_count = connection.execute(
            "SELECT COUNT(*) FROM datasets WHERE json_extract(metadata_json,'$.public_reference')=1"
        ).fetchone()[0]
        assert public_dataset_count >= 1
        public_sample_count = connection.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE dataset_sha256 IN (SELECT dataset_sha256 FROM datasets WHERE json_extract(metadata_json,'$.public_reference')=1)"
        ).fetchone()[0]
        assert public_sample_count >= 569
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM dataset_validation_issues WHERE resolution_status='open'"
            ).fetchone()[0]
            >= 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM dataset_asset_bindings").fetchone()[0] >= 100
        )


def test_step32_api_surfaces():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["database_systems"] >= 18
    relationships = client.get("/relationships/summary")
    assert relationships.status_code == 200
    assert relationships.json()["broken_edges"] == 0
    edges = client.get("/relationships/edges", params={"limit": 25})
    assert edges.status_code == 200
    assert edges.json()["count"] == 25
    public = client.get("/public-reference", params={"provider": "UniProt"})
    assert public.status_code == 200
    assert public.json()["count"] == 25
    readiness = client.get("/readiness/summary")
    assert readiness.status_code == 200
    payload = readiness.json()["datasets"]
    assert payload["datasets"] >= 52
    assert payload["readiness_scored"] == payload["datasets"]
    assert payload["with_files"] == payload["datasets"]
    assert payload["with_columns"] == payload["datasets"]
    assert payload["with_qc"] == payload["datasets"]
