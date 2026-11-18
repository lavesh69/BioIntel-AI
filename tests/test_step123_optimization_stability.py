from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from biointel.database.core import (
    connect,
    database_file_signature,
    database_health,
    managed_connect,
)
from biointel.ui.performance import read_sql_cached
from biointel.utils.runtime_cache import clear_runtime_caches, read_csv_cached


def test_managed_connection_closes_after_context(tmp_path: Path) -> None:
    path = tmp_path / "managed.sqlite3"
    connection = managed_connect(path)
    with connection as active:
        active.execute("CREATE TABLE sample(value INTEGER)")
        active.execute("INSERT INTO sample VALUES (1)")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    with managed_connect(path) as verification:
        assert verification.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1


def test_managed_connection_rolls_back_and_closes(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite3"
    with managed_connect(path) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
    connection = managed_connect(path)
    with pytest.raises(RuntimeError):
        with connection as active:
            active.execute("INSERT INTO sample VALUES (9)")
            raise RuntimeError("stop")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with managed_connect(path) as verification:
        assert verification.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0


def test_wal_signature_ignores_read_noise_but_changes_on_write(tmp_path: Path) -> None:
    path = tmp_path / "signature.sqlite3"
    with connect(path) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (1)")
    first = database_file_signature(path)
    with connect(path, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1
    assert database_file_signature(path) == first

    with connect(path) as connection:
        connection.execute("INSERT INTO sample VALUES (2)")
    assert database_file_signature(path) != first


def test_database_health_cache_invalidates_after_write(tmp_path: Path) -> None:
    path = tmp_path / "health.sqlite3"
    with connect(path) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (1)")
    assert database_health(path, full_check=False).row_count == 1
    assert database_health(path, full_check=False).row_count == 1
    with connect(path) as connection:
        connection.execute("INSERT INTO sample VALUES (2)")
    assert database_health(path, full_check=False).row_count == 2


def test_streamlit_sql_cache_is_wal_aware(tmp_path: Path) -> None:
    path = tmp_path / "ui.sqlite3"
    with connect(path) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (1)")
    assert int(read_sql_cached(path, "SELECT COUNT(*) AS n FROM sample").iloc[0]["n"]) == 1
    with connect(path) as connection:
        connection.execute("INSERT INTO sample VALUES (2)")
    assert int(read_sql_cached(path, "SELECT COUNT(*) AS n FROM sample").iloc[0]["n"]) == 2


def test_runtime_csv_cache_returns_mutation_isolated_frames(tmp_path: Path) -> None:
    clear_runtime_caches()
    path = tmp_path / "sample.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(path, index=False)
    first = read_csv_cached(path)
    first.loc[0, "value"] = 999
    second = read_csv_cached(path)
    assert second["value"].tolist() == [1, 2]


def test_standard_windows_launcher_uses_optimized_runtime_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "run_biointel_step97.py").read_text(encoding="utf-8")
    assert "PYTHONPYCACHEPREFIX" in source
    assert "JOBLIB_TEMP_FOLDER" in source
    assert "OMP_NUM_THREADS" in source
    assert "_rotate_logs" in source
    assert "_atomic_write_json" in source
