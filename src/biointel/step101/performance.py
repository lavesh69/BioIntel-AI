from __future__ import annotations

import gc
import json
import os
import sqlite3
from biointel.database.core import managed_connect
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


@dataclass(frozen=True)
class PerformanceEvent:
    component: str
    operation: str
    duration_ms: float
    rows: int = 0
    bytes_processed: int = 0
    cache_hit: bool = False
    status: str = "ok"
    detail: dict[str, Any] | None = None


class PerformanceRegistry:
    """Small persistent profiler used by UI pages and background jobs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with managed_connect(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS performance_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    rows_processed INTEGER NOT NULL DEFAULT 0,
                    bytes_processed INTEGER NOT NULL DEFAULT 0,
                    cache_hit INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ok',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_performance_component_time
                    ON performance_events(component, created_at_utc DESC);
                """
            )

    def record(self, event: PerformanceEvent) -> None:
        with managed_connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO performance_events(
                    component,operation,duration_ms,rows_processed,bytes_processed,
                    cache_hit,status,detail_json
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    event.component,
                    event.operation,
                    max(float(event.duration_ms), 0.0),
                    max(int(event.rows), 0),
                    max(int(event.bytes_processed), 0),
                    int(event.cache_hit),
                    event.status,
                    json.dumps(event.detail or {}, sort_keys=True, default=str),
                ),
            )

    @contextmanager
    def span(self, component: str, operation: str, **detail: Any) -> Iterator[dict[str, Any]]:
        state: dict[str, Any] = {"rows": 0, "bytes_processed": 0, "cache_hit": False}
        started = time.perf_counter()
        status = "ok"
        try:
            yield state
        except Exception:
            status = "error"
            raise
        finally:
            self.record(
                PerformanceEvent(
                    component=component,
                    operation=operation,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    rows=int(state.get("rows", 0)),
                    bytes_processed=int(state.get("bytes_processed", 0)),
                    cache_hit=bool(state.get("cache_hit", False)),
                    status=status,
                    detail=detail,
                )
            )

    def recent(self, limit: int = 500) -> list[dict[str, Any]]:
        with managed_connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM performance_events ORDER BY event_id DESC LIMIT ?",
                (max(1, min(int(limit), 5000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with managed_connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT component, COUNT(*) AS events, AVG(duration_ms) AS avg_ms,
                       MAX(duration_ms) AS max_ms, SUM(cache_hit) AS cache_hits,
                       SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
                FROM performance_events GROUP BY component ORDER BY avg_ms DESC
                """
            ).fetchall()
        return {"components": [dict(row) for row in rows], "event_count": sum(int(r["events"]) for r in rows)}


@lru_cache(maxsize=64)
def cached_directory_inventory(root_string: str, mtime_ns: int) -> tuple[tuple[str, int], ...]:
    del mtime_ns
    root = Path(root_string)
    return tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.stat().st_size)
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    )


def directory_inventory(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    return [
        {"path": path, "size_bytes": size}
        for path, size in cached_directory_inventory(str(base), base.stat().st_mtime_ns)
    ]


def chunked_csv_preview(path: str | Path, *, rows: int = 500, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(path, nrows=max(1, min(int(rows), 100_000)), usecols=columns, low_memory=False)


def bounded_frame(frame: pd.DataFrame, *, max_rows: int = 10_000, max_columns: int = 250) -> pd.DataFrame:
    return frame.iloc[: max(1, int(max_rows)), : max(1, int(max_columns))].copy(deep=False)


def release_memory() -> int:
    return int(gc.collect())


def process_memory_mb() -> float:
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value / (1024.0 if os.name != "darwin" else 1024.0**2)
    except Exception:
        return 0.0


def audit_ui_source(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    pages = sorted((base / "pages").glob("*.py"))
    records = []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        records.append(
            {
                "page": page.name,
                "lines": text.count("\n") + 1,
                "forms": text.count("st.form("),
                "uploaders": text.count("st.file_uploader("),
                "cache_data": text.count("st.cache_data"),
                "cache_resource": text.count("st.cache_resource"),
                "dataframes": text.count("st.dataframe("),
                "json_views": text.count("st.json("),
                "top_level_risk": int("for " in text[:4000] and "st." in text[:4000]),
            }
        )
    return {
        "pages": records,
        "page_count": len(records),
        "forms": sum(row["forms"] for row in records),
        "uploaders": sum(row["uploaders"] for row in records),
        "cached_pages": sum(bool(row["cache_data"] or row["cache_resource"]) for row in records),
    }
