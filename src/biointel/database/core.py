from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Sequence


class ManagedConnection(sqlite3.Connection):
    """SQLite connection that preserves transaction semantics and closes on context exit.

    Python's native ``sqlite3.Connection`` context manager commits or rolls back,
    but it does not close the handle. Streamlit reruns can therefore accumulate
    file handles and eventually hit locked-database or resource-exhaustion errors.
    This subclass keeps the native transaction behaviour and always closes.
    """

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


def managed_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
    """Create a SQLite connection that is safe to use in ``with`` blocks with 30s busy timeout."""
    kwargs.setdefault("factory", ManagedConnection)
    kwargs.setdefault("timeout", 30.0)
    conn = sqlite3.connect(*args, **kwargs)
    try:
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    return conn



def database_file_signature(path: str | Path) -> tuple[int, int, int, int, int, int]:
    """Return a WAL-aware signature used to invalidate cached database metadata."""

    database = Path(path).resolve()
    values: list[int] = []
    try:
        stat = database.stat()
        values.extend((int(stat.st_mtime_ns), int(stat.st_size)))
    except OSError:
        values.extend((0, 0))

    wal = Path(f"{database}-wal")
    try:
        wal_stat = wal.stat()
        wal_size = int(wal_stat.st_size)
        # SQLite may touch an empty WAL while opening a read-only dashboard.
        # Ignore that mtime noise but retain non-empty WAL changes from writes.
        values.extend((int(wal_stat.st_mtime_ns) if wal_size else 0, wal_size))
    except OSError:
        values.extend((0, 0))

    # The shared-memory file changes during ordinary reads and is not data.
    values.extend((0, 0))
    return tuple(values)  # type: ignore[return-value]


@dataclass(frozen=True)
class DatabaseHealth:
    name: str
    path: str
    exists: bool
    size_bytes: int
    integrity: str
    journal_mode: str
    table_count: int
    index_count: int
    row_count: int
    last_modified_utc: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(
    path: str | Path,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    database = Path(path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        connection = managed_connect(
            f"file:{database.as_posix()}?mode=ro",
            uri=True,
            timeout=30.0,
        )
    else:
        connection = managed_connect(
            database,
            timeout=30.0,
        )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -32000")
    connection.execute("PRAGMA mmap_size = 268435456")
    if read_only:
        try:
            connection.execute("PRAGMA query_only = ON")
        except sqlite3.OperationalError:
            pass
    else:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA wal_autocheckpoint = 1000")
            connection.execute("PRAGMA journal_size_limit = 67108864")
            connection.execute("PRAGMA recursive_triggers = ON")
        except sqlite3.OperationalError:
            pass
    return connection


@contextmanager
def transaction(
    path: str | Path,
    *,
    lock_attempts: int = 5,
    base_delay_seconds: float = 0.05,
) -> Iterator[sqlite3.Connection]:
    """Open a short write transaction with bounded lock/busy recovery."""
    if lock_attempts < 1 or lock_attempts > 10:
        raise ValueError("lock_attempts must be between 1 and 10")
    connection: sqlite3.Connection | None = None
    for attempt in range(lock_attempts):
        candidate = connect(path)
        try:
            candidate.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            candidate.close()
            message = str(exc).lower()
            if ("locked" not in message and "busy" not in message) or attempt + 1 >= lock_attempts:
                raise
            time.sleep(base_delay_seconds * (2**attempt))
            continue
        connection = candidate
        break
    if connection is None:
        raise RuntimeError("Unable to acquire database write transaction")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def execute_script(
    path: str | Path,
    script: str,
) -> None:
    with transaction(path) as connection:
        connection.executescript(script)


def rows_as_dicts(
    rows: Sequence[sqlite3.Row],
) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def json_text(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def table_names(
    path: str | Path,
) -> list[str]:
    with connect(path, read_only=True) as connection:
        return [
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]


def _database_health_uncached(
    database: Path,
    *,
    name: str,
    full_check: bool,
    include_row_count: bool,
) -> DatabaseHealth:
    if not database.is_file():
        return DatabaseHealth(
            name=name,
            path=str(database),
            exists=False,
            size_bytes=0,
            integrity="missing",
            journal_mode="unknown",
            table_count=0,
            index_count=0,
            row_count=0,
            last_modified_utc=None,
        )

    with connect(database, read_only=True) as connection:
        pragma = "integrity_check" if full_check else "quick_check"
        integrity = str(connection.execute(f"PRAGMA {pragma}").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        tables = [
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]
        index_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'index'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchone()[0]
        )
        row_count = 0
        if include_row_count:
            for table in tables:
                quoted = table.replace('"', '""')
                row_count += int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])

    stat = database.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return DatabaseHealth(
        name=name,
        path=str(database),
        exists=True,
        size_bytes=stat.st_size,
        integrity=integrity,
        journal_mode=journal_mode,
        table_count=len(tables),
        index_count=index_count,
        row_count=row_count,
        last_modified_utc=modified,
    )


@lru_cache(maxsize=256)
def _database_health_cached(
    database_text: str,
    signature: tuple[int, int, int, int, int, int],
    name: str,
    full_check: bool,
    include_row_count: bool,
) -> DatabaseHealth:
    del signature
    return _database_health_uncached(
        Path(database_text),
        name=name,
        full_check=full_check,
        include_row_count=include_row_count,
    )


def database_health(
    path: str | Path,
    *,
    name: str | None = None,
    full_check: bool = True,
    include_row_count: bool = True,
    use_cache: bool = True,
) -> DatabaseHealth:
    """Inspect a database with WAL-aware automatic cache invalidation.

    ``full_check=False`` uses SQLite's fast ``quick_check`` and is suitable for
    interactive dashboards. Release verification and backups retain the full
    integrity check.
    """

    database = Path(path).resolve()
    resolved_name = name or database.stem
    if not use_cache:
        return _database_health_uncached(
            database,
            name=resolved_name,
            full_check=full_check,
            include_row_count=include_row_count,
        )
    return _database_health_cached(
        str(database),
        database_file_signature(database),
        resolved_name,
        bool(full_check),
        bool(include_row_count),
    )


def clear_database_health_cache() -> None:
    _database_health_cached.cache_clear()


def optimize_database(
    path: str | Path,
    *,
    vacuum: bool = False,
) -> DatabaseHealth:
    with connect(path) as connection:
        connection.execute("PRAGMA optimize")
        if vacuum:
            connection.execute("VACUUM")
    return database_health(path)


def backup_database(
    path: str | Path,
    destination: str | Path,
) -> Path:
    source = Path(path).resolve()
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(source, read_only=True) as source_connection:
        with connect(target) as target_connection:
            source_connection.backup(target_connection)
    return target



def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_database_backup_manifest(manifest_path: str | Path) -> dict[str, object]:
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.is_file():
        return {"valid": False, "reason": "manifest_missing", "databases": []}
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    for item in payload.get("databases", []):
        path = manifest_file.parent / str(item.get("filename", ""))
        exists = path.is_file()
        digest_ok = exists and file_sha256(path) == str(item.get("sha256", ""))
        health = database_health(path) if exists else None
        integrity_ok = bool(health and health.integrity == "ok")
        results.append({
            "filename": path.name,
            "exists": exists,
            "digest_ok": digest_ok,
            "integrity_ok": integrity_ok,
            "row_count": health.row_count if health else 0,
        })
    return {
        "valid": bool(results) and all(item["exists"] and item["digest_ok"] and item["integrity_ok"] for item in results),
        "database_count": len(results),
        "databases": results,
    }

def export_database_json(
    path: str | Path,
) -> dict[str, object]:
    database = Path(path).resolve()
    payload: dict[str, object] = {
        "database": database.name,
        "exported_at_utc": utc_now(),
        "tables": {},
    }
    with connect(database, read_only=True) as connection:
        for table in table_names(database):
            quoted = table.replace('"', '""')
            rows = rows_as_dicts(connection.execute(f'SELECT * FROM "{quoted}"').fetchall())
            payload["tables"][table] = rows
    return payload


def copy_database_files(
    source_directory: str | Path,
    destination_directory: str | Path,
) -> list[Path]:
    source = Path(source_directory).resolve()
    destination = Path(destination_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for path in sorted(source.glob("*.sqlite3")):
        target = destination / path.name
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def execute_many_chunked(
    connection: sqlite3.Connection,
    sql: str,
    rows: Sequence[Sequence[object]],
    *,
    chunk_size: int = 1000,
) -> int:
    """Execute large write batches with bounded memory and predictable lock time."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    total = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        connection.executemany(sql, chunk)
        total += len(chunk)
    return total


def aggregate_table_counts(
    path: str | Path,
    tables: Sequence[str] | None = None,
) -> dict[str, int]:
    """Return table counts in one connection, avoiding repeated connect overhead."""
    selected = list(tables) if tables is not None else table_names(path)
    counts: dict[str, int] = {}
    with connect(path, read_only=True) as connection:
        for table in selected:
            if not table or "\x00" in table:
                raise ValueError("invalid table name")
            quoted = table.replace('"', '""')
            counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
    return counts
