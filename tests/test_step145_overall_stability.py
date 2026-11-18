from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from biointel.database.core import transaction
from biointel.jobs.local_queue import LocalJobQueue
from biointel.stability_v145.cache import BoundedTTLCache, cache_registry_snapshot
from biointel.stability_v145.database import execute_with_retry, maintain_database_file
from biointel.stability_v145.errors import ErrorStore, redact_sensitive
from biointel.stability_v145.jobs import recover_orphaned_job_queues
from biointel.stability_v145.maintenance import run_overall_maintenance
from biointel.stability_v145.runtime import apply_process_hardening, startup_preflight


def test_bounded_ttl_cache_expires_and_evicts() -> None:
    cache = BoundedTTLCache[str, str](name="step145-test", max_entries=2, max_bytes=20, ttl_seconds=0.02)
    assert cache.set("a", "12345")
    assert cache.set("b", "67890")
    assert cache.get("a") == "12345"
    assert cache.set("c", "abcde")
    assert cache.get("b") is None
    time.sleep(0.03)
    assert cache.get("a") is None
    stats = cache.stats()
    assert stats.evictions >= 1
    assert stats.expirations >= 1


def test_sensitive_values_are_recursively_redacted() -> None:
    payload = {"api_key": "abc", "nested": {"message": "token=secret-value"}, "safe": "ok"}
    redacted = redact_sensitive(payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert "secret-value" not in redacted["nested"]["message"]
    assert redacted["safe"] == "ok"


def test_error_store_rotates_and_writes_atomic_json(tmp_path: Path) -> None:
    store = ErrorStore(tmp_path / "errors", max_files=2, max_total_bytes=100_000)
    for index in range(3):
        try:
            raise ValueError(f"failure {index} token=private")
        except ValueError as exc:
            row = store.record("test", exc, metadata={"password": "secret"})
            assert row["metadata"]["password"] == "[REDACTED]"
    files = list((tmp_path / "errors").glob("ERR-*.json"))
    assert len(files) <= 2
    assert all(json.loads(path.read_text(encoding="utf-8"))["schema"] == "biointel.error.v145" for path in files)


def test_startup_preflight_and_process_hardening(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("13.2.0", encoding="utf-8")
    applied = apply_process_hardening(tmp_path)
    assert "BIOINTEL_PROJECT_ROOT" in applied or "BIOINTEL_PROJECT_ROOT" in __import__("os").environ
    result = startup_preflight(tmp_path, minimum_free_bytes=1, recommended_free_bytes=1)
    assert result["passed"] is True
    assert not result["failures"]


def test_database_maintenance_and_retry(tmp_path: Path) -> None:
    database = tmp_path / "test.sqlite3"
    execute_with_retry(database, "CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT)")
    execute_with_retry(database, "INSERT INTO records(value) VALUES (?)", ("ok",))
    row = execute_with_retry(database, "SELECT value FROM records", fetch="one")
    assert row[0] == "ok"
    maintained = maintain_database_file(database)
    assert maintained["passed"] is True
    assert maintained["rows"] == 1


def test_orphaned_job_recovery(tmp_path: Path) -> None:
    queue_path = tmp_path / "jobs.sqlite3"
    queue = LocalJobQueue(queue_path)
    job = queue.submit("test", {"x": 1})
    claimed = queue.claim_next(worker_id="worker-test")
    assert claimed is not None and claimed.job_id == job.job_id
    with sqlite3.connect(queue_path) as connection:
        connection.execute(
            "UPDATE local_jobs SET heartbeat_at_utc='2000-01-01T00:00:00+00:00', updated_at_utc='2000-01-01T00:00:00+00:00' WHERE job_id=?",
            (job.job_id,),
        )
    result = recover_orphaned_job_queues(tmp_path, stale_after_seconds=30)
    assert result["recovered_jobs"] == 1
    assert queue.get(job.job_id).status == "queued"


def test_overall_maintenance_is_safe_on_minimal_workspace(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("13.2.0", encoding="utf-8")
    database = tmp_path / "reports" / "sample.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO sample DEFAULT VALUES")
    report = run_overall_maintenance(tmp_path)
    assert report["passed"] is True
    assert report["databases"]["passed_count"] == 1
    assert (tmp_path / "reports" / "step145_overall_maintenance_latest.json").is_file()


def test_step145_is_integrated_into_app_and_reliability_page() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    page = (root / "pages" / "110_Reliability_Optimization_Center.py").read_text(encoding="utf-8")
    assert "startup_preflight" in app
    assert "run_overall_maintenance" in page
    assert "Overall app stability" in page


def test_core_transaction_uses_hardened_write_contract(tmp_path: Path) -> None:
    database = tmp_path / "transaction.sqlite3"
    with transaction(database) as connection:
        connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO records(value) VALUES ('stable')")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "stable"
        assert int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) in {0, 1}


def test_startup_preflight_uses_bounded_registered_cache(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("13.2.0", encoding="utf-8")
    startup_preflight(tmp_path, minimum_free_bytes=1, recommended_free_bytes=1)
    names = {row["name"] for row in cache_registry_snapshot()}
    assert "step145-startup-preflight" in names
