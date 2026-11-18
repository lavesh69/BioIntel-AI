from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from dataclasses import asdict
from pathlib import Path

from biointel.assets.research_assets import (
    asset_health,
    search_assets,
)
from biointel.database.core import (
    backup_database,
    database_file_signature,
    database_health,
    export_database_json,
    file_sha256,
    optimize_database,
    utc_now,
    verify_database_backup_manifest,
)
from biointel.documents.history import search_content as search_document_content
from biointel.intelligence.knowledge_warehouse import (
    knowledge_health,
    search_knowledge,
)
from biointel.runtime_paths import runtime_database_directory
from biointel.observability.analytics_store import (
    analytics_health,
    module_performance,
    recent_events,
)

NEW_DATABASES = {
    "knowledge": "knowledge.sqlite3",
    "analytics": "analytics.sqlite3",
    "assets": "assets.sqlite3",
    "downloads": "internet_downloads.sqlite3",
    "evidence": "evidence.sqlite3",
    "documents": "document_history.sqlite3",
    "scientific_evidence": "scientific_evidence.sqlite3",
    "prospective_validation": "prospective_validation.sqlite3",
    "tenants": "tenants.sqlite3",
    "validation_evidence": "validation_evidence.sqlite3",
    "realworld_evidence": "realworld_evidence.sqlite3",
    "connected_sources": "connected_sources.sqlite3",
}
DATA_DATABASES = {
    "discovery_projects": "discovery_projects.sqlite3",
    "lab_analytics": "lab_analytics.sqlite3",
}
EXISTING_DATABASES = {
    "datasets": "datasets.sqlite3",
    "experiments": "experiments.sqlite3",
    "projects": "projects.sqlite3",
    "jobs": "jobs.sqlite3",
    "feature_cache": "feature_cache.sqlite3",
    "relationships": "relationships.sqlite3",
    "api_security": "api_security.sqlite3",
}


def database_paths(
    root: str | Path,
) -> dict[str, Path]:
    """Return every active SQLite database, including future registries.

    Known databases keep stable human-facing keys. Any additional ``*.sqlite3``,
    ``*.sqlite`` or ``*.db`` file in ``reports/`` is discovered automatically so
    health, backup, export and worker diagnostics cannot silently omit a newly
    introduced registry.
    """
    project_root = Path(root).resolve()
    database_dir = runtime_database_directory(project_root)
    paths = {
        key: database_dir / filename
        for key, filename in {**EXISTING_DATABASES, **NEW_DATABASES, **DATA_DATABASES}.items()
    }
    known_paths = {path.resolve() for path in paths.values()}
    for base in (database_dir,):
        for pattern in ("*.sqlite3", "*.sqlite", "*.db"):
            for path in sorted(base.glob(pattern)):
                resolved = path.resolve()
                if resolved in known_paths:
                    continue
                key = path.stem.lower().replace("-", "_").replace(" ", "_")
                candidate = key
                suffix = 2
                while candidate in paths:
                    candidate = f"{key}_{suffix}"
                    suffix += 1
                paths[candidate] = path
                known_paths.add(resolved)
    return dict(sorted(paths.items()))


def _all_database_health_uncached(
    root: str | Path,
) -> dict[str, object]:
    """Return interactive health for every database without serially blocking the UI.

    Each health record is WAL-signature cached by :func:`database_health`. A
    bounded thread pool makes the cold scan responsive while preserving stable
    output ordering. Full integrity checks remain available in release and
    backup verification paths.
    """

    paths = database_paths(root)
    ordered_items = list(paths.items())

    def inspect(item: tuple[str, Path]) -> tuple[str, dict[str, object]]:
        key, path = item
        return (
            key,
            asdict(
                database_health(
                    path,
                    name=key.replace("_", " ").title(),
                    full_check=False,
                )
            ),
        )

    workers = max(1, min(8, len(ordered_items)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="biointel-db-health") as executor:
        scanned = dict(executor.map(inspect, ordered_items))
    databases = {key: scanned[key] for key, _ in ordered_items}
    new_health = {
        "knowledge": knowledge_health(paths["knowledge"]),
        "analytics": analytics_health(paths["analytics"]),
        "assets": asset_health(paths["assets"]),
    }
    healthy_count = sum(item["exists"] and item["integrity"] == "ok" for item in databases.values())
    total_rows = sum(int(item["row_count"]) for item in databases.values())
    total_bytes = sum(int(item["size_bytes"]) for item in databases.values())
    total_indices = sum(int(item["index_count"]) for item in databases.values())
    return {
        "generated_at_utc": utc_now(),
        "database_count": len(databases),
        "healthy_count": healthy_count,
        "health_percent": round(
            healthy_count / max(len(databases), 1) * 100.0,
            2,
        ),
        "total_rows": total_rows,
        "total_bytes": total_bytes,
        "total_indices": total_indices,
        "databases": databases,
        "professional_warehouses": new_health,
    }


@lru_cache(maxsize=8)
def _all_database_health_cached(
    root_text: str,
    fleet_signature: tuple[tuple[str, str, tuple[int, int, int, int, int, int]], ...],
) -> dict[str, object]:
    del fleet_signature
    return _all_database_health_uncached(root_text)


def all_database_health(root: str | Path) -> dict[str, object]:
    project_root = Path(root).resolve()
    paths = database_paths(project_root)
    signature = tuple(
        (key, str(path.resolve()), database_file_signature(path))
        for key, path in paths.items()
    )
    return copy.deepcopy(_all_database_health_cached(str(project_root), signature))


def clear_database_fleet_cache() -> None:
    _all_database_health_cached.cache_clear()


def universal_search(
    root: str | Path,
    query: str,
    *,
    limit_per_source: int = 30,
) -> dict[str, object]:
    paths = database_paths(root)
    knowledge = search_knowledge(
        paths["knowledge"],
        query,
        limit=limit_per_source,
    )
    assets = search_assets(
        paths["assets"],
        query,
        limit=limit_per_source,
    )

    lowered = query.strip().lower()
    analytics = [
        row
        for row in module_performance(
            paths["analytics"],
            days=180,
            limit=200,
        )
        if lowered in str(row.get("module_title", "")).lower()
        or lowered in str(row.get("category", "")).lower()
        or lowered in str(row.get("module_key", "")).lower()
    ][:limit_per_source]

    if not analytics and query.strip():
        analytics = [
            row
            for row in recent_events(
                paths["analytics"],
                limit=500,
            )
            if lowered in str(row.get("module_title", "")).lower()
            or lowered in str(row.get("action", "")).lower()
            or lowered in str(row.get("dataset_name", "")).lower()
            or lowered in str(row.get("model_name", "")).lower()
        ][:limit_per_source]

    documents = (
        search_document_content(
            paths["documents"],
            query,
            limit=limit_per_source,
        )
        if query.strip()
        else []
    )

    return {
        "query": query,
        "generated_at_utc": utc_now(),
        "counts": {
            "knowledge": len(knowledge),
            "assets": len(assets),
            "analytics": len(analytics),
            "documents": len(documents),
        },
        "knowledge": knowledge,
        "assets": assets,
        "analytics": analytics,
        "documents": documents,
    }


def optimize_all_databases(
    root: str | Path,
    *,
    vacuum: bool = False,
) -> dict[str, object]:
    results = {}
    for key, path in database_paths(root).items():
        if path.is_file():
            results[key] = asdict(
                optimize_database(
                    path,
                    vacuum=vacuum,
                )
            )
    return {
        "optimized_at_utc": utc_now(),
        "vacuum": vacuum,
        "results": results,
    }


def backup_all_databases(
    root: str | Path,
    destination: str | Path,
) -> list[str]:
    target = Path(destination).resolve()
    target.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    database_entries: list[dict[str, object]] = []
    for key, path in database_paths(root).items():
        if not path.is_file():
            continue
        output = backup_database(path, target / path.name)
        health = database_health(output, name=key)
        outputs.append(str(output))
        database_entries.append({
            "key": key,
            "filename": output.name,
            "sha256": file_sha256(output),
            "size_bytes": output.stat().st_size,
            "integrity": health.integrity,
            "table_count": health.table_count,
            "row_count": health.row_count,
        })
    manifest_path = target / "database_backup_manifest.json"
    manifest = {
        "schema": "biointel.database-backup.v2",
        "created_at_utc": utc_now(),
        "source_root": str(Path(root).resolve()),
        "database_count": len(database_entries),
        "databases": database_entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    verification = verify_database_backup_manifest(manifest_path)
    if not verification["valid"]:
        raise RuntimeError("Database backup verification failed")
    return outputs


def export_all_databases_json(
    root: str | Path,
    destination: str | Path,
) -> list[str]:
    target = Path(destination).resolve()
    target.mkdir(parents=True, exist_ok=True)
    outputs = []
    for key, path in database_paths(root).items():
        if not path.is_file():
            continue
        output = target / f"{key}_database_export.json"
        output.write_text(
            json.dumps(
                export_database_json(path),
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        outputs.append(str(output))
    return outputs
