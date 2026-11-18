"""
BioIntel AI — SQLite Database Performance & High-Concurrency Optimizer
Configures Write-Ahead Logging (WAL), memory-mapped I/O, and memory caching.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def optimize_sqlite_db(db_path: Path) -> dict[str, str]:
    """Applies high-performance PRAGMA optimizations to an SQLite database file."""
    if not db_path.is_file():
        return {"status": "skipped", "reason": "file_not_found"}

    results = {}
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-64000;")     # 64MB Cache
            conn.execute("PRAGMA mmap_size=268435456;")    # 256MB MMAP I/O
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA busy_timeout=15000;")
            conn.commit()

            wal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            cache = conn.execute("PRAGMA cache_size;").fetchone()[0]
            results = {
                "status": "optimized",
                "journal_mode": str(wal),
                "cache_size": str(cache),
                "db": db_path.name,
            }
    except Exception as exc:
        results = {"status": "error", "error": str(exc), "db": db_path.name}

    return results


def optimize_all_app_databases(root: Path) -> list[dict[str, str]]:
    """Scans and optimizes all SQLite databases across BioIntel user data and release paths."""
    optimized = []
    for db_path in root.rglob("*.sqlite3"):
        res = optimize_sqlite_db(db_path)
        if res.get("status") == "optimized":
            optimized.append(res)
    return optimized
