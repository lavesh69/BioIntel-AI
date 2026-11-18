from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .schema import MIGRATION_ID, SCHEMA


class ResearchPlatformError(Exception):
    pass


class PermissionDenied(ResearchPlatformError):
    pass


class Conflict(ResearchPlatformError):
    pass


class Missing(ResearchPlatformError):
    pass


class IntegrityFailure(ResearchPlatformError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class PlatformStore:
    def __init__(self, database: str | Path):
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        if read_only:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                uri=True,
                timeout=30,
            )
        else:
            connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        if not read_only:
            connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            if not read_only:
                connection.commit()
        except Exception:
            if not read_only:
                connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> str:
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO education_p35_migrations VALUES(?,?)",
                (MIGRATION_ID, now_utc()),
            )
        return MIGRATION_ID

    def one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection(read_only=True) as connection:
            return row_dict(connection.execute(sql, parameters).fetchone())

    def all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection(read_only=True) as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def quick_check(self) -> bool:
        with self.connection(read_only=True) as connection:
            return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
