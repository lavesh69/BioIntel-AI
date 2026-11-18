from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.readiness import platform_readiness_summary, provider_readiness_rows
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG


def scalar(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def portable(value):
    if isinstance(value, dict):
        return {key: portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item) for item in value]
    if isinstance(value, str):
        root_text = str(ROOT.resolve())
        return value.replace(root_text + "/", "").replace(root_text, ".")
    return value


def main() -> None:
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    assert len({page.key for page in PAGE_CATALOG}) >= 71
    assert len({page.path for page in PAGE_CATALOG}) >= 71
    assert any(page.key == "scientific_data_readiness" for page in PAGE_CATALOG)

    summary = platform_readiness_summary(ROOT)
    datasets = summary["datasets"]
    assert datasets["datasets"] == 52
    assert datasets["with_files"] == 52
    assert datasets["with_columns"] == 52
    assert datasets["with_qc"] == 52
    assert datasets["with_provenance"] == 52
    assert datasets["release_eligible"] == 0
    assert summary["open_dataset_issues"] == 52
    assert summary["dataset_aliases"] >= 10

    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_files") >= 102
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_columns") >= 3_000
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_samples") >= 400
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_qc_metrics") >= 280
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_provenance") == 52
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_aliases") >= 10
        assert (
            scalar(connection, "SELECT COUNT(*) FROM dataset_readiness WHERE readiness_score=100")
            == 52
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM dataset_readiness WHERE scientific_status='release_eligible'",
            )
            == 0
        )

    with sqlite3.connect(ROOT / "reports" / "experiments.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM experiments") == 23
        assert scalar(connection, "SELECT COUNT(*) FROM experiments WHERE synthetic_demo=1") == 23
        assert scalar(connection, "SELECT COUNT(*) FROM experiment_dataset_bindings") == 46
        assert (
            scalar(connection, "SELECT COUNT(*) FROM experiment_dataset_bindings WHERE verified=1")
            == 46
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM experiment_dataset_bindings WHERE resolution_type='historical_alias'",
            )
            == 23
        )
        assert (
            scalar(connection, "SELECT COUNT(*) FROM experiment_artifacts WHERE status='available'")
            == 69
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM experiment_validation_requirements WHERE requirement_key='registered_dataset' AND status='passed'",
            )
            == 23
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM experiment_validation_requirements WHERE requirement_key='real_experimental_training' AND status='blocked'",
            )
            == 23
        )

    providers = provider_readiness_rows(ROOT)
    assert len(providers) == 16
    assert sum(int(row.get("records_available") or 0) for row in providers) == 569
    with sqlite3.connect(ROOT / "reports" / "evidence.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM evidence_source_releases") == 15
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM evidence_source_releases WHERE local_record_count>0",
            )
            == 0
        )
    with sqlite3.connect(ROOT / "reports" / "internet_downloads.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM source_sync_events") == 16

    with sqlite3.connect(ROOT / "reports" / "projects.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM projects") == 30
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM projects WHERE dataset_sha256 IS NOT NULL AND dataset_sha256!=''",
            )
            == 30
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM projects WHERE model_filename IS NOT NULL AND model_filename!=''",
            )
            == 30
        )
        assert scalar(connection, "SELECT COUNT(*) FROM project_resources") >= 120

    with sqlite3.connect(ROOT / "reports" / "feature_cache.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM feature_cache") >= 1_291
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM feature_cache WHERE schema_version IS NULL OR schema_version=''",
            )
            == 0
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM feature_cache WHERE library_version IS NULL OR library_version=''",
            )
            == 0
        )
        assert scalar(connection, "SELECT COUNT(*) FROM feature_cache_profiles") >= 2

    with sqlite3.connect(ROOT / "reports" / "document_history.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM document_registry_versions") == scalar(
            connection, "SELECT COUNT(*) FROM document_extraction_runs"
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM document_registry_versions WHERE registry_version='3.1.0'",
            )
            == 68
        )

    with sqlite3.connect(ROOT / "reports" / "assets.sqlite3") as connection:
        assert (
            scalar(connection, "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'")
            == 12
        )
        assert (
            scalar(connection, "SELECT COUNT(*) FROM research_assets WHERE asset_type='module'")
            >= 71
        )

    models = sorted((ROOT / "models").glob("*.joblib"))
    assert len(models) == 23
    for model_path in models:
        load_model_artifact(model_path, trusted_root=ROOT / "models")

    health = all_database_health(ROOT)
    assert health["database_count"] >= 13
    assert health["healthy_count"] == health["database_count"]

    payload = portable(
        {
            "version": __version__,
            "milestone": "Step 31 Scientific Data & UI Overhaul",
            "screens": len(PAGE_CATALOG),
            "models_loaded": len(models),
            "database_health": health,
            "readiness": summary,
            "providers": {
                "profiles": len(providers),
                "local_records": sum(int(row.get("records_available") or 0) for row in providers),
            },
            "scientific_boundary": (
                "Registry completeness is verified, but all bundled model/data evidence remains "
                "reference or synthetic and is not scientific-release eligible."
            ),
        }
    )
    output = ROOT / "reports" / "generated" / "step31_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
