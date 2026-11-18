from __future__ import annotations

import json
from pathlib import Path

from biointel.assurance import build_final_assurance
from biointel.database.core import verify_database_backup_manifest
from biointel.engineering.repository_audit import check_version_consistency, scan_repository_secrets
from biointel.intelligence.data_intelligence import backup_all_databases, database_paths

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_secret_audit() -> None:
    assert check_version_consistency(ROOT)["passed"]
    assert scan_repository_secrets(ROOT)["passed"]


def test_secret_audit_distinguishes_probe_header_from_private_key(tmp_path: Path) -> None:
    probe = tmp_path / "probe.txt"
    probe.write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    assert scan_repository_secrets(tmp_path)["passed"]
    probe.write_text(
        "-----BEGIN PRIVATE KEY-----\n" + "A" * 64 + "\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    report = scan_repository_secrets(tmp_path)
    assert report["passed"] is False
    assert report["findings"][0]["key"] == "private_key"


def test_dynamic_database_discovery_and_health() -> None:
    paths = database_paths(ROOT)
    assert len(paths) >= 18
    assert len(set(path.resolve() for path in paths.values())) == len(paths)
    report = build_final_assurance(ROOT)
    assert report["database_health"]["healthy_count"] == report["database_health"]["database_count"]
    assert report["implementation_score"] >= 9.0


def test_verified_database_backup(tmp_path: Path) -> None:
    outputs = backup_all_databases(ROOT, tmp_path)
    assert len(outputs) == len([path for path in database_paths(ROOT).values() if path.is_file()])
    manifest = tmp_path / "database_backup_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["schema"] == "biointel.database-backup.v2"
    verification = verify_database_backup_manifest(manifest)
    assert verification["valid"]


def test_final_assurance_has_three_score_boundary() -> None:
    report = build_final_assurance(ROOT)
    assert report["schema"] == "biointel.final-assurance.v1"
    assert report["implementation_score"] >= report["authentic_external_evidence_score"]
    assert "third-party" in report["boundary"].lower() or "external" in report["boundary"].lower()


def test_final_assurance_api() -> None:
    from fastapi.testclient import TestClient

    from biointel.api.main import app

    response = TestClient(app).get("/assurance/final")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "biointel.final-assurance.v1"
    assert payload["implementation_score"] >= 9.0


def test_reproducible_release_verifies_every_member(tmp_path: Path) -> None:
    from biointel.engineering.release import build_reproducible_release, verify_release_bundle

    source = tmp_path / "sample-project"
    source.mkdir()
    (source / "README.md").write_text("qualified\n", encoding="utf-8")
    script = source / "run.sh"
    script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    script.chmod(0o755)
    first = build_reproducible_release(source, tmp_path / "first.zip")
    second = build_reproducible_release(source, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    verification = verify_release_bundle(first)
    assert verification["valid"]
    assert verification["verified_file_count"] == 2


def test_security_store_logs_unregistered_local_identity_without_fk_failure(tmp_path):
    from biointel.api.security_store import ApiSecurityStore

    store = ApiSecurityStore(tmp_path / "security.sqlite3")
    store.log_request({
        "request_id": "req-local-operator",
        "client_id": "local-operator",
        "role": "local_operator",
        "method": "GET",
        "path": "/live",
        "status_code": 200,
        "duration_ms": 1.0,
    })
    with store._connect() as connection:
        row = connection.execute(
            "SELECT client_id, role, status_code FROM api_request_log WHERE request_id=?",
            ("req-local-operator",),
        ).fetchone()
    assert row is not None
    assert row["client_id"] is None
    assert row["role"] == "local_operator"
    assert row["status_code"] == 200
