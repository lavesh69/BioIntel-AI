from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.api.middleware import (
    OptionalApiKeyMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)
from biointel.runtime_paths import (
    runtime_data_directory,
    runtime_database_directory,
    runtime_report_path,
)
from biointel.ui.preferences import SAFE_PREFERENCE_THEME
from biointel.utils.audit_log import append_audit_event, read_audit_events, verify_audit_chain


def test_windows_style_runtime_paths_are_isolated(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "LocalData" / "BioIntelAI" / "UserData"
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(target))
    project = tmp_path / "managed-source"
    assert runtime_database_directory(project) == target / "databases"
    assert runtime_data_directory(project) == target / "data"
    assert runtime_report_path(project, "audit.jsonl") == target / "reports" / "audit.jsonl"


def test_professional_theme_is_default() -> None:
    assert SAFE_PREFERENCE_THEME == "Executive"


def test_health_exclusion_is_not_prefix_bypass() -> None:
    inner = FastAPI()

    @inner.get("/{path:path}")
    def any_path(path: str):
        return {"path": path}

    app = OptionalApiKeyMiddleware(inner, api_key=None, require_auth=True)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/healthanything").status_code == 401


def test_remote_client_requires_auth_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BIOINTEL_ALLOW_UNAUTHENTICATED_LAN", raising=False)
    inner = FastAPI()

    @inner.get("/private")
    def private():
        return {"ok": True}

    app = OptionalApiKeyMiddleware(inner, api_key=None)
    client = TestClient(app, client=("192.0.2.50", 50000))
    assert client.get("/private").status_code == 401


def test_ingest_path_receives_upload_limit() -> None:
    middleware = RequestSizeLimitMiddleware(lambda *_: None)
    assert middleware._limit_for_path("/api/shiro/ingest") == 100 * 1024 * 1024
    assert middleware._limit_for_path("/health") == 16 * 1024 * 1024


def test_request_id_is_log_safe() -> None:
    inner = FastAPI()

    @inner.get("/ok")
    def ok():
        return {"ok": True}

    app = RequestContextMiddleware(inner)
    response = TestClient(app).get("/ok", headers={"X-Request-ID": "hello\nforged value"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "hello_forged_value"


def test_nested_audit_secrets_are_hashed(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit_event(
        path,
        "test",
        "ok",
        {"nested": {"access_token": "top-secret", "safe": "visible"}},
    )
    events = read_audit_events(path)
    rendered = json.dumps(events)
    assert "top-secret" not in rendered
    assert "sha256_prefix" in rendered
    assert verify_audit_chain(path)["valid"] is True


def test_isolated_runtime_files_use_portable_virtual_paths(tmp_path: Path, monkeypatch) -> None:
    from biointel.utils.local_data import delete_managed_files, list_managed_files

    project = tmp_path / "managed-source"
    project.mkdir()
    user_data = tmp_path / "LocalData" / "BioIntelAI" / "UserData"
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(user_data))
    database = user_data / "databases" / "projects.sqlite3"
    report = user_data / "reports" / "audit.jsonl"
    data = user_data / "data" / "exports" / "result.csv"
    for path, content in ((database, b"db"), (report, b"{}\n"), (data, b"x\n1\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    managed = {item.relative_path for item in list_managed_files(project)}
    assert managed == {
        "databases/projects.sqlite3",
        "reports/audit.jsonl",
        "data/exports/result.csv",
    }
    deleted = delete_managed_files(project, ["reports/audit.jsonl"])
    assert deleted == ["reports/audit.jsonl"]
    assert not report.exists()


def test_workspace_backup_restores_to_isolated_runtime(tmp_path: Path, monkeypatch) -> None:
    from biointel.utils.workspace_backup import (
        create_workspace_backup,
        inspect_workspace_backup,
        restore_workspace_backup,
    )

    source = tmp_path / "source"
    source.mkdir()
    source_data = tmp_path / "source-user-data"
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(source_data))
    database = source_data / "databases" / "projects.sqlite3"
    report = source_data / "reports" / "audit.jsonl"
    generated = source_data / "data" / "exports" / "result.csv"
    for path, content in ((database, b"db"), (report, b"{}\n"), (generated, b"x\n1\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    backup = create_workspace_backup(source)
    summary = inspect_workspace_backup(backup)
    assert "databases/projects.sqlite3" in summary.files
    assert "reports/audit.jsonl" in summary.files
    assert "data/exports/result.csv" in summary.files

    target = tmp_path / "target"
    target.mkdir()
    target_data = tmp_path / "target-user-data"
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(target_data))
    result = restore_workspace_backup(target, backup)
    assert result["restored_count"] == 3
    assert (target_data / "databases" / "projects.sqlite3").read_bytes() == b"db"
    assert (target_data / "reports" / "audit.jsonl").read_bytes() == b"{}\n"
    assert (target_data / "data" / "exports" / "result.csv").read_bytes() == b"x\n1\n"


def test_integrity_cache_path_is_virtual_and_cache_name_is_safe(
    tmp_path: Path, monkeypatch
) -> None:
    import hashlib
    import pytest

    from biointel.utils.integrity_cache import verify_manifest_files

    project = tmp_path / "managed-source"
    project.mkdir()
    file_path = project / "payload.txt"
    file_path.write_text("biointel", encoding="utf-8")
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "UserData"))
    result = verify_manifest_files(
        project,
        [{"filename": "payload.txt", "sha256": hashlib.sha256(b"biointel").hexdigest()}],
        cache_name="integrity.json",
    )
    assert result["valid"] is True
    assert result["cache_path"] == "reports/integrity.json"
    with pytest.raises(ValueError, match="plain filename"):
        verify_manifest_files(project, [], cache_name="../escape.json")


def test_bundled_experiment_seed_is_demo_only_and_relationships_are_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    import shutil
    import sqlite3

    from biointel.data.relationship_integrity import rebuild_relationship_registry
    from biointel.training.demo_experiments import seed_bundled_demo_experiments

    project = tmp_path / "project"
    models = project / "models"
    models.mkdir(parents=True)
    source_root = Path(__file__).resolve().parents[1]
    for name in ("demo_classification_model.json", "demo_classification_model.joblib"):
        shutil.copy2(source_root / "models" / name, models / name)
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "UserData"))

    counts = seed_bundled_demo_experiments(project)
    assert counts["experiments"] == 1
    database = tmp_path / "UserData" / "databases" / "experiments.sqlite3"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT synthetic_demo,metadata_json FROM experiments"
        ).fetchone()
        assert row[0] == 1
        metadata = json.loads(row[1])
        assert metadata["scientific_release_eligible"] is False
        assert metadata["external_validation_claimed"] is False
        requirement_statuses = {
            item[0]
            for item in connection.execute(
                "SELECT status FROM experiment_validation_requirements"
            )
        }
        assert requirement_statuses == {"blocked", "missing", "review_required"}

    summary = rebuild_relationship_registry(project)
    assert summary.node_count >= 3
    assert summary.warning_edges == 1
    assert summary.orphan_findings == 1
    assert summary.broken_edges == 0
