from __future__ import annotations

import sqlite3
from pathlib import Path

from biointel import __version__
from biointel.data.readiness import platform_readiness_summary, provider_readiness_rows
from biointel.ui.navigation import PAGE_CATALOG, search_pages

ROOT = Path(__file__).resolve().parents[1]


def count(database: str, sql: str) -> int:
    with sqlite3.connect(ROOT / "reports" / database) as connection:
        return int(connection.execute(sql).fetchone()[0])


def test_step31_registry_completeness_without_false_release_claims() -> None:
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    summary = platform_readiness_summary(ROOT)
    total = summary["datasets"]["datasets"]
    assert total >= 52
    assert summary["datasets"]["readiness_scored"] == total
    assert summary["datasets"]["with_files"] == total
    assert summary["datasets"]["with_columns"] == total
    assert summary["datasets"]["with_qc"] == total
    assert summary["datasets"]["with_provenance"] == total
    assert summary["datasets"]["release_eligible"] == 0
    assert summary["dataset_aliases"] >= 10
    assert summary["open_dataset_issues"] >= 0


def test_step31_historical_experiment_lineage_is_resolved_not_rewritten() -> None:
    with sqlite3.connect(ROOT / "reports" / "experiments.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiment_dataset_bindings").fetchone()[0] == 46
        assert connection.execute("SELECT COUNT(*) FROM experiment_dataset_bindings WHERE verified=1").fetchone()[0] == 46
        assert connection.execute("SELECT COUNT(*) FROM experiment_dataset_bindings WHERE resolution_type='historical_alias'").fetchone()[0] == 23
        assert connection.execute("SELECT COUNT(*) FROM experiment_validation_requirements WHERE requirement_key='real_experimental_training' AND status='blocked'").fetchone()[0] == 23
    assert count("datasets.sqlite3", "SELECT COUNT(*) FROM dataset_aliases") >= 10


def test_step31_sources_are_synchronized_but_not_falsely_imported() -> None:
    providers = provider_readiness_rows(ROOT)
    assert len(providers) == 16
    assert sum(int(row.get("records_available") or 0) for row in providers) == 569
    assert count("evidence.sqlite3", "SELECT COUNT(*) FROM evidence_source_releases") == 15
    assert count("evidence.sqlite3", "SELECT COUNT(*) FROM evidence_source_releases WHERE local_record_count>0") == 0
    assert count("internet_downloads.sqlite3", "SELECT COUNT(*) FROM source_sync_events") == 16


def test_step31_projects_cache_documents_and_assets_are_linked() -> None:
    assert count("projects.sqlite3", "SELECT COUNT(*) FROM projects WHERE dataset_sha256 IS NOT NULL AND dataset_sha256!=''") == 30
    assert count("projects.sqlite3", "SELECT COUNT(*) FROM projects WHERE model_filename IS NOT NULL AND model_filename!=''") == 30
    assert count("projects.sqlite3", "SELECT COUNT(*) FROM project_resources") >= 120
    assert count("feature_cache.sqlite3", "SELECT COUNT(*) FROM feature_cache WHERE schema_version IS NULL OR schema_version=''") == 0
    assert count("document_history.sqlite3", "SELECT COUNT(*) FROM document_registry_versions") == 68
    assert count("assets.sqlite3", "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'") >= 18


def test_step31_navigation_and_global_search() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert len({page.key for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    assert len({page.path for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    results = search_pages("readiness", "All", set())
    assert results
    assert results[0].key == "scientific_data_readiness"
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "showSidebarNavigation = false" in config
    assert "Find a workspace" in theme
    assert "bio-page-context" in theme


def test_step31_readiness_api() -> None:
    from fastapi.testclient import TestClient

    from biointel.api.main import app

    client = TestClient(app)
    summary = client.get("/readiness/summary")
    datasets = client.get("/readiness/datasets")
    providers = client.get("/readiness/providers")
    assert summary.status_code == 200
    assert datasets.status_code == 200
    assert providers.status_code == 200
    total = summary.json()["datasets"]["datasets"]
    assert total >= 52
    assert datasets.json()["count"] == total
    assert len(datasets.json()["rows"]) == total
    assert providers.json()["count"] == 16
    assert len(providers.json()["rows"]) == 16
