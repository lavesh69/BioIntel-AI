from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.assets.research_assets import (
    add_asset_note,
    asset_health,
    asset_summary,
    get_asset,
    list_collections,
    search_assets,
    toggle_favourite,
)
from biointel.cli import main as cli_main
from biointel.database.core import (
    database_health,
    export_database_json,
)
from biointel.database.migrations import (
    optimize_existing_registries,
    query_plan,
)
from biointel.intelligence.data_intelligence import (
    all_database_health,
    universal_search,
)
from biointel.intelligence.knowledge_warehouse import (
    knowledge_health,
    knowledge_relations,
    knowledge_summary,
    list_protocols,
    list_saved_queries,
    search_knowledge,
)
from biointel.observability.analytics_store import (
    alert_overview,
    analytics_health,
    analytics_summary,
    daily_metric_series,
    module_performance,
    quality_overview,
    recent_events,
    system_overview,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG
from biointel.ui.theme import (
    command_bar,
    database_cards,
    density_bar,
    insight_callout,
)

ROOT = Path(__file__).resolve().parents[1]


def test_step21_database_files_and_health() -> None:
    health = all_database_health(ROOT)
    assert health["database_count"] >= 18
    assert health["healthy_count"] == health["database_count"]
    assert health["health_percent"] == 100.0
    assert health["total_rows"] >= 45000
    assert health["total_indices"] >= 60

    for name in (
        "knowledge.sqlite3",
        "analytics.sqlite3",
        "assets.sqlite3",
        "datasets.sqlite3",
        "experiments.sqlite3",
        "projects.sqlite3",
        "internet_downloads.sqlite3",
        "evidence.sqlite3",
        "document_history.sqlite3",
    ):
        path = ROOT / "reports" / name
        result = database_health(path)
        assert result.exists is True
        assert result.integrity == "ok"
        assert result.journal_mode == "wal"
        assert result.index_count > 0


def test_knowledge_warehouse_quantities_and_search() -> None:
    database = ROOT / "reports" / "knowledge.sqlite3"
    summary = knowledge_summary(database)
    assert summary.entities >= 9500
    assert summary.relations >= 7500
    assert summary.protocols == 36
    assert summary.saved_queries >= 6
    assert summary.entity_types["compound"] == 1000
    assert summary.entity_types["interaction_candidate"] == 2500
    assert knowledge_health(database)["healthy"] is True

    results = search_knowledge(
        database,
        "extra trees",
        limit=50,
    )
    assert results
    assert any(
        "extra" in str(item["name"]).lower() or "extra" in str(item["summary"]).lower()
        for item in results
    )

    model_results = search_knowledge(
        database,
        "",
        entity_type="model",
        limit=100,
    )
    assert len(model_results) >= 23
    relations = knowledge_relations(
        database,
        model_results[0]["entity_id"],
    )
    assert isinstance(relations, list)
    assert len(list_protocols(database)) == 36
    assert len(list_saved_queries(database)) >= 6


def test_analytics_warehouse_quantities_and_queries() -> None:
    database = ROOT / "reports" / "analytics.sqlite3"
    summary = analytics_summary(database)
    assert summary.run_events >= 14900
    assert summary.daily_metrics == 1800
    assert summary.quality_snapshots == 90
    assert summary.system_samples == 720
    assert summary.alerts == 80
    assert summary.success_rate >= 90.0
    assert analytics_health(database)["healthy"] is True

    modules = module_performance(
        database,
        days=180,
        limit=200,
    )
    assert len(modules) >= 39
    assert sum(item["runs"] for item in modules) == summary.run_events

    assert (
        len(
            daily_metric_series(
                database,
                "success_rate",
                days=180,
            )
        )
        >= 179
    )
    assert quality_overview(database)
    assert system_overview(database, limit=50)
    assert alert_overview(database)
    assert recent_events(database, limit=25)


def test_asset_database_quantities_search_and_notes(
    tmp_path: Path,
) -> None:
    source = ROOT / "reports" / "assets.sqlite3"
    database = tmp_path / "assets.sqlite3"
    shutil.copy2(source, database)

    summary = asset_summary(database)
    assert summary.assets >= 700
    assert summary.collections == 12
    assert summary.tags >= 2700
    assert summary.notes >= 500
    assert summary.favourites >= 39
    assert asset_health(database)["healthy"] is True

    results = search_assets(
        database,
        "model",
        limit=100,
    )
    assert results
    assert list_collections(database)

    asset_id = results[0]["asset_id"]
    detail = get_asset(database, asset_id)
    assert detail["asset_id"] == asset_id
    previous = bool(detail["is_favourite"])
    current = toggle_favourite(database, asset_id)
    assert current is not previous
    note = add_asset_note(
        database,
        asset_id,
        "Step 21 temporary test note.",
        author_label="Test runner",
    )
    assert note["note_id"] > 0


def test_step21_universal_search_and_export() -> None:
    results = universal_search(
        ROOT,
        "extra trees",
        limit_per_source=20,
    )
    assert results["counts"]["knowledge"] > 0
    assert results["counts"]["assets"] > 0
    assert isinstance(results["analytics"], list)

    payload = export_database_json(ROOT / "reports" / "datasets.sqlite3")
    assert payload["database"] == "datasets.sqlite3"
    assert "datasets" in payload["tables"]


def test_existing_registry_indices_and_query_plans() -> None:
    results = optimize_existing_registries(ROOT)
    assert {"datasets.sqlite3", "experiments.sqlite3", "projects.sqlite3"}.issubset(results)
    assert {
        "knowledge.sqlite3",
        "analytics.sqlite3",
        "assets.sqlite3",
        "evidence.sqlite3",
        "document_history.sqlite3",
        "internet_downloads.sqlite3",
    }.issubset(results)
    assert results["datasets.sqlite3"]["index_count"] >= 6
    assert results["experiments.sqlite3"]["index_count"] >= 6
    assert results["projects.sqlite3"]["index_count"] >= 17

    plan = query_plan(
        ROOT / "reports" / "datasets.sqlite3",
        "SELECT * FROM datasets WHERE task_type = ?",
        ("classification",),
    )
    assert any("idx_datasets_task" in item for item in plan)


def test_step21_navigation_and_professional_ui() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["data_intelligence"].path.endswith("38_Data_Intelligence_Hub.py")
    assert PAGE_BY_KEY["knowledge_warehouse"].path.endswith("39_Knowledge_Warehouse.py")
    assert PAGE_BY_KEY["analytics_observability"].path.endswith("40_Analytics_Observability.py")
    assert PAGE_BY_KEY["research_assets"].path.endswith("41_Research_Assets.py")

    for function in (
        command_bar,
        database_cards,
        density_bar,
        insight_callout,
    ):
        assert callable(function)

    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    for marker in (
        ".bio-db-grid",
        ".bio-db-card",
        ".bio-command-bar",
        ".bio-insight",
        ".bio-density",
    ):
        assert marker in theme


def test_step21_api_endpoints() -> None:
    client = TestClient(app)

    status = client.get("/databases/status")
    assert status.status_code == 200
    assert status.json()["database_count"] >= 18

    search = client.get(
        "/intelligence/search",
        params={"q": "extra trees", "limit": 10},
    )
    assert search.status_code == 200
    assert search.json()["counts"]["knowledge"] > 0

    knowledge = client.get(
        "/knowledge/search",
        params={"q": "dataset", "limit": 20},
    )
    assert knowledge.status_code == 200
    assert knowledge.json()["results"]

    analytics = client.get(
        "/analytics/overview",
        params={"days": 30},
    )
    assert analytics.status_code == 200
    assert analytics.json()["summary"]["run_events"] > 0

    assets = client.get(
        "/assets/search",
        params={"q": "model", "limit": 20},
    )
    assert assets.status_code == 200
    assert assets.json()["results"]

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["database_systems"] >= 18
    assert health.json()["professional_warehouses"] == 3


def test_step21_cli_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_main(["database-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["database_count"] >= 18

    assert (
        cli_main(
            [
                "intelligence-search",
                "extra trees",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    search = json.loads(capsys.readouterr().out)
    assert search["counts"]["knowledge"] > 0

    assert (
        cli_main(
            [
                "knowledge-search",
                "dataset",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    knowledge = json.loads(capsys.readouterr().out)
    assert knowledge["results"]

    assert (
        cli_main(
            [
                "analytics-overview",
                "--days",
                "30",
            ]
        )
        == 0
    )
    analytics = json.loads(capsys.readouterr().out)
    assert analytics["run_events"] > 0

    assert (
        cli_main(
            [
                "asset-search",
                "model",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    assets = json.loads(capsys.readouterr().out)
    assert assets["results"]


def test_step21_windows_seed_and_generated_summary() -> None:
    assert (ROOT / "SEED_PROFESSIONAL_DATABASES_WINDOWS.bat").is_file()
    script = ROOT / "scripts" / "seed_professional_databases.py"
    assert script.is_file()
    summary = ROOT / "reports" / "generated" / "step22_connected_databases_summary.json"
    assert summary.is_file()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["health"]["database_count"] == 18
