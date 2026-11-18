from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from biointel.database.core import connect, database_health
from biointel.engineering.runtime_optimizer import discover_databases


def _retryable(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def execute_with_retry(
    path: str | Path,
    sql: str,
    parameters: Sequence[object] = (),
    *,
    attempts: int = 5,
    base_delay_seconds: float = 0.05,
    fetch: str = "none",
) -> Any:
    """Execute one short transaction and retry only SQLite lock/busy failures."""
    if attempts < 1 or attempts > 10:
        raise ValueError("attempts must be between 1 and 10")
    if fetch not in {"none", "one", "all"}:
        raise ValueError("fetch must be none, one or all")
    last: sqlite3.OperationalError | None = None
    for index in range(attempts):
        try:
            with connect(path) as connection:
                cursor = connection.execute(sql, tuple(parameters))
                if fetch == "one":
                    result = cursor.fetchone()
                elif fetch == "all":
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount
                connection.commit()
                return result
        except sqlite3.OperationalError as exc:
            if not _retryable(exc) or index + 1 >= attempts:
                raise
            last = exc
            time.sleep(base_delay_seconds * (2**index))
    if last is not None:
        raise last
    raise RuntimeError("database operation did not execute")


def maintain_database_file(path: str | Path) -> dict[str, Any]:
    database = Path(path).resolve()
    with connect(database) as connection:
        before_wal = Path(f"{database}-wal").stat().st_size if Path(f"{database}-wal").exists() else 0
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check").fetchmany(101))
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone() or ())
        connection.execute("PRAGMA optimize=0x10002")
        connection.commit()
    health = database_health(database, full_check=False, use_cache=False)
    after_wal = Path(f"{database}-wal").stat().st_size if Path(f"{database}-wal").exists() else 0
    return {
        "path": str(database), "quick_check": quick, "foreign_key_violations": len(foreign_keys),
        "foreign_key_check_truncated": len(foreign_keys) > 100, "checkpoint": list(checkpoint),
        "wal_bytes_before": before_wal, "wal_bytes_after": after_wal,
        "tables": health.table_count, "rows": health.row_count,
        "passed": quick == "ok" and not foreign_keys,
    }


def maintain_database_fleet(root: str | Path, *, paths: Iterable[str | Path] | None = None) -> dict[str, Any]:
    project_root = Path(root).resolve()
    selected = [Path(item).resolve() for item in paths] if paths is not None else discover_databases(project_root)
    results: list[dict[str, Any]] = []
    for path in selected:
        try:
            row = maintain_database_file(path)
            try:
                row["path"] = path.relative_to(project_root).as_posix()
            except ValueError:
                pass
        except (OSError, sqlite3.Error) as exc:
            row = {"path": str(path), "passed": False, "error": f"{type(exc).__name__}: {exc}"}
        results.append(row)
    return {
        "database_count": len(results), "passed_count": sum(bool(row.get("passed")) for row in results),
        "failed_count": sum(not bool(row.get("passed")) for row in results), "results": results,
        "passed": bool(results) and all(bool(row.get("passed")) for row in results),
    }
