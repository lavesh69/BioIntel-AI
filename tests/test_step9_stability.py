from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.integrations import http_client
from biointel.integrations.cache import ExternalResponseCache
from biointel.integrations.http_client import (
    ExternalServiceError,
    HttpResponse,
)
from biointel.utils.diagnostics import diagnostic_summary
from biointel.utils.workspace_backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)


def test_external_response_cache_round_trip(
    tmp_path: Path,
) -> None:
    cache = ExternalResponseCache(tmp_path / "cache")
    entry = cache.put(
        "https://example.test/data",
        b'{"ok": true}',
        "application/json",
        created_at_epoch=100.0,
    )

    loaded = cache.get("https://example.test/data")
    assert loaded is not None
    assert loaded.key == entry.key
    assert cache.read_bytes(loaded) == b'{"ok": true}'
    assert loaded.is_fresh(60, now=150)
    assert not loaded.is_fresh(60, now=200)


def test_http_client_uses_stale_cache_on_network_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_directory = tmp_path / "cache"
    url = "https://example.test/resource"

    def success_transport(
        requested_url: str,
        timeout: float,
        headers: dict[str, str],
    ) -> HttpResponse:
        assert requested_url == url
        return HttpResponse(
            status=200,
            body=b'{"value": 7}',
            content_type="application/json",
        )

    monkeypatch.setattr(
        http_client,
        "default_transport",
        success_transport,
    )
    first = http_client.get_json(
        url,
        transport=success_transport,
        cache_directory=cache_directory,
        cache_ttl_seconds=0,
    )
    assert first["value"] == 7

    def failing_transport(
        requested_url: str,
        timeout: float,
        headers: dict[str, str],
    ) -> HttpResponse:
        raise ExternalServiceError("offline")

    monkeypatch.setattr(
        http_client,
        "default_transport",
        failing_transport,
    )
    second = http_client.get_json(
        url,
        transport=failing_transport,
        cache_directory=cache_directory,
        cache_ttl_seconds=0,
        allow_stale_on_error=True,
    )
    assert second == {"value": 7}


def test_workspace_backup_and_restore(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "models").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "cache" / "external").mkdir(parents=True)

    (root / "models" / "user.joblib").write_bytes(b"model")
    (root / "models" / "demo_model.joblib").write_bytes(b"demo")
    (root / "reports" / "history.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (root / "cache" / "external" / "entry.bin").write_bytes(b"cached")

    backup = create_workspace_backup(
        root,
        include_demo_models=False,
        include_cache=True,
    )
    summary = inspect_workspace_backup(backup)

    assert "models/user.joblib" in summary.files
    assert "models/demo_model.joblib" not in summary.files
    assert "reports/history.json" in summary.files
    assert "cache/external/entry.bin" in summary.files

    target = tmp_path / "target"
    (target / "models").mkdir(parents=True)
    (target / "reports").mkdir()
    result = restore_workspace_backup(target, backup)

    assert result["restored_count"] == 3
    assert (target / "models" / "user.joblib").read_bytes() == b"model"
    assert (target / "reports" / "history.json").is_file()


def test_workspace_backup_rejects_path_traversal() -> None:
    manifest = {
        "backup_format_version": "1.0",
        "created_at_utc": "2026-07-04T00:00:00+00:00",
        "included_demo_models": False,
        "included_cache": False,
        "file_count": 1,
        "total_bytes": 4,
        "sha256": {
            "../outside.txt": (
                "3a6eb0790f39ac87c94f3856b2dd2c5d" "110e6811602261a9a923d3bb23adc8b7"
            )
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "WORKSPACE_MANIFEST.json",
            json.dumps(manifest),
        )
        archive.writestr("../outside.txt", b"data")

    with pytest.raises(ValueError, match="Unsafe backup path"):
        inspect_workspace_backup(buffer.getvalue())


def test_workspace_backup_detects_checksum_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "models").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "models" / "user.joblib").write_bytes(b"model")
    original = create_workspace_backup(root)

    source = zipfile.ZipFile(io.BytesIO(original), "r")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "models/user.joblib":
                content = b"tampered"
            target.writestr(info, content)
    source.close()

    with pytest.raises(ValueError, match="Checksum mismatch"):
        inspect_workspace_backup(buffer.getvalue())


def test_api_keeps_no_login_but_rejects_untrusted_host() -> None:
    client = TestClient(app)

    local = client.get("/health")
    assert local.status_code == 200
    assert local.json()["authentication_required"] is False
    assert local.headers["x-biointel-access"] == "no-login-local"

    rejected = client.get(
        "/health",
        headers={"host": "public.example.com"},
    )
    assert rejected.status_code == 400


def test_api_request_size_limit() -> None:
    client = TestClient(app)
    response = client.post(
        "/sequence/analyze",
        headers={"content-length": str(100 * 1024 * 1024 + 1)},
        content=b"{}",
    )
    assert response.status_code == 413


def test_api_diagnostics_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/system/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert payload["summary"]["total"] > 0


def test_diagnostic_summary() -> None:
    from biointel.utils.diagnostics import DiagnosticCheck

    summary = diagnostic_summary(
        [
            DiagnosticCheck("a", "PASS", "ok", "x"),
            DiagnosticCheck("b", "WARN", "warning", "x"),
        ]
    )
    assert summary["overall"] == "WARN"
    assert summary["PASS"] == 1
    assert summary["WARN"] == 1


def test_cli_workspace_backup_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "config").mkdir()
    (root / "models" / "user.joblib").write_bytes(b"model")

    monkeypatch.chdir(root)
    backup_path = root / "backup.zip"

    assert (
        cli_main(
            [
                "workspace-backup",
                "--output",
                str(backup_path),
            ]
        )
        == 0
    )
    assert backup_path.is_file()

    (root / "models" / "user.joblib").unlink()
    assert (
        cli_main(
            [
                "workspace-restore",
                "--backup",
                str(backup_path),
            ]
        )
        == 0
    )
    assert (root / "models" / "user.joblib").is_file()

    output = capsys.readouterr().out
    assert "restored_count" in output
