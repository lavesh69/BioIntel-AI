from __future__ import annotations

import sqlite3
from pathlib import Path

from biointel.database.core import aggregate_table_counts, execute_many_chunked
from biointel.database.migrations import optimize_existing_registries, query_plan


def test_chunked_writes_and_aggregate_counts(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, status TEXT)")
        rows = [(i, "ready") for i in range(2505)]
        assert execute_many_chunked(connection, "INSERT INTO items(id, status) VALUES (?, ?)", rows, chunk_size=500) == 2505
    assert aggregate_table_counts(db, ["items"]) == {"items": 2505}


def test_optimizer_deploys_indexes_and_query_plan(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    db = reports / "internet_downloads.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("""CREATE TABLE internet_downloads(
            download_id TEXT PRIMARY KEY, provider TEXT, resource_id TEXT, url TEXT,
            filename TEXT, relative_path TEXT, content_type TEXT, size_bytes INTEGER,
            sha256 TEXT, status TEXT, downloaded_at_utc TEXT, etag TEXT,
            last_modified TEXT, notes TEXT)""")
    result = optimize_existing_registries(tmp_path)
    assert "internet_downloads.sqlite3" in result
    plan = query_plan(db, "SELECT * FROM internet_downloads WHERE provider=? AND resource_id=?", ("pdb", "1abc"))
    assert any("idx_downloads_provider_resource" in row for row in plan)
