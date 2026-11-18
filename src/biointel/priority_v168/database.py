from __future__ import annotations

from pathlib import Path
import sqlite3

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS modules (
    module_key TEXT PRIMARY KEY,
    module_title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS production_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    provider TEXT NOT NULL DEFAULT '',
    release_id TEXT NOT NULL DEFAULT '',
    licence_identifier TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    qualified INTEGER NOT NULL DEFAULT 0 CHECK(qualified IN (0,1))
);
CREATE TABLE IF NOT EXISTS validation_studies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    study_id TEXT NOT NULL DEFAULT '',
    independent_site INTEGER NOT NULL DEFAULT 0 CHECK(independent_site IN (0,1)),
    prospective_or_orthogonal INTEGER NOT NULL DEFAULT 0 CHECK(prospective_or_orthogonal IN (0,1)),
    acceptance_thresholds_locked INTEGER NOT NULL DEFAULT 0 CHECK(acceptance_thresholds_locked IN (0,1)),
    complete INTEGER NOT NULL DEFAULT 0 CHECK(complete IN (0,1))
);
CREATE TABLE IF NOT EXISTS expert_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    reviewer TEXT NOT NULL DEFAULT '',
    signed_artifact TEXT NOT NULL DEFAULT '',
    complete INTEGER NOT NULL DEFAULT 0 CHECK(complete IN (0,1))
);
CREATE TABLE IF NOT EXISTS release_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    decision TEXT NOT NULL DEFAULT 'pending',
    intended_use TEXT NOT NULL DEFAULT 'research',
    complete INTEGER NOT NULL DEFAULT 0 CHECK(complete IN (0,1))
);
CREATE TABLE IF NOT EXISTS operating_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    environment TEXT NOT NULL DEFAULT '',
    runs INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    downtime_minutes REAL NOT NULL DEFAULT 0,
    complete INTEGER NOT NULL DEFAULT 0 CHECK(complete IN (0,1))
);
CREATE TABLE IF NOT EXISTS physical_qualification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key),
    windows_tested INTEGER NOT NULL DEFAULT 0 CHECK(windows_tested IN (0,1)),
    gpu_tested INTEGER NOT NULL DEFAULT 0 CHECK(gpu_tested IN (0,1)),
    instrument_tested INTEGER NOT NULL DEFAULT 0 CHECK(instrument_tested IN (0,1)),
    recovery_tested INTEGER NOT NULL DEFAULT 0 CHECK(recovery_tested IN (0,1)),
    complete INTEGER NOT NULL DEFAULT 0 CHECK(complete IN (0,1))
);
"""


def ensure_step168_database(root: str | Path, module_rows: list[tuple[str, str]]) -> Path:
    path = Path(root) / "data" / "databases" / "step168_external_evidence.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO modules(module_key,module_title) VALUES(?,?) ON CONFLICT(module_key) DO UPDATE SET module_title=excluded.module_title",
            module_rows,
        )
        conn.commit()
    return path


__all__ = ["ensure_step168_database"]
