from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from biointel.database.core import connect

_DATABASE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}


def discover_databases(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    return sorted(
        {
            path.resolve()
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix.lower() in _DATABASE_SUFFIXES
            and not any(part.startswith(".") for part in path.relative_to(base).parts)
        }
    )


def optimize_database_file(path: str | Path) -> dict[str, object]:
    database = Path(path).resolve()
    before_size = database.stat().st_size
    with connect(database) as connection:
        integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        before_pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
        before_free = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        connection.execute("PRAGMA optimize=0x10002")
        connection.commit()
        after_pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
        after_free = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    return {
        "path": str(database),
        "integrity": integrity,
        "journal_mode": journal_mode,
        "size_bytes_before": before_size,
        "size_bytes_after": database.stat().st_size,
        "page_count_before": before_pages,
        "page_count_after": after_pages,
        "freelist_before": before_free,
        "freelist_after": after_free,
        "checkpoint": list(checkpoint) if checkpoint is not None else [],
        "passed": integrity == "ok",
    }


def optimize_database_fleet(
    root: str | Path,
    *,
    paths: Iterable[str | Path] | None = None,
) -> dict[str, object]:
    base = Path(root).resolve()
    selected = [Path(item).resolve() for item in paths] if paths is not None else discover_databases(base)
    results: list[dict[str, object]] = []
    for path in selected:
        try:
            item = optimize_database_file(path)
            item["path"] = path.relative_to(base).as_posix() if path.is_relative_to(base) else str(path)
        except (OSError, sqlite3.Error) as exc:
            item = {"path": str(path), "passed": False, "error": str(exc)}
        results.append(item)
    return {
        "database_count": len(results),
        "optimized_databases": sum(bool(item.get("passed")) for item in results),
        "failed_databases": sum(not bool(item.get("passed")) for item in results),
        "results": results,
    }
