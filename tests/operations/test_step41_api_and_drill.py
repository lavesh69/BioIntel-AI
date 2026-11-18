from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.realworld import sha256_text

ROOT = Path(__file__).resolve().parents[2]


def test_realworld_readiness_and_summary_api():
    client = TestClient(app)
    readiness = client.get("/operations/realworld-readiness")
    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["implementation_average"] == 10.0
    assert payload["capability_count"] == 18
    summary = client.get("/operations/realworld-evidence-summary")
    assert summary.status_code == 200
    assert summary.json()["integrity"]["ok"]


def test_api_rejects_template_evidence_from_qualification():
    client = TestClient(app)
    response = client.post(
        "/operations/realworld-evidence",
        json={
            "study": {
                "evidence_id": "API-REHEARSAL",
                "area_key": "production_sla_history",
                "title": "API rehearsal",
                "status": "completed",
                "evidence_class": "rehearsal",
                "issuer_organization": "external-monitor",
                "subject_organization": "platform-operator",
                "environment": "test",
                "country": "IN",
                "started_at": "2025-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:00+00:00",
                "manifest_sha256": sha256_text("api rehearsal manifest"),
                "metadata": {},
            },
            "artifacts": [
                {"artifact_type": "signed_sla_report", "uri": "evidence://a", "sha256": sha256_text("a"), "observed_at": "2026-01-02T00:00:00+00:00", "metadata": {}},
                {"artifact_type": "incident_postmortems", "uri": "evidence://b", "sha256": sha256_text("b"), "observed_at": "2026-01-02T00:00:00+00:00", "metadata": {}},
            ],
            "metrics": [
                {"metric_name": "availability_percent", "metric_value": 99.99, "unit": "%", "passed": True},
                {"metric_name": "error_rate_percent", "metric_value": 0.1, "unit": "%", "passed": True},
                {"metric_name": "p95_latency_ms", "metric_value": 100, "unit": "ms", "passed": True},
            ],
            "attestations": [
                {"signer_organization": "external-monitor", "signer_identity": "reviewer", "signer_role": "reviewer", "independent": True, "decision": "approved", "signature_sha256": sha256_text("sig"), "signed_at": "2026-01-03T00:00:00+00:00", "notes": "rehearsal"}
            ],
            "entities": [],
        },
    )
    assert response.status_code == 200
    record = response.json()["record"]
    assert not record["release_eligible"]
    assert any("rehearsal" in item.lower() for item in record["blockers"])


def test_dr_drill_produces_checksum_verified_rehearsal(tmp_path: Path):
    database = tmp_path / "sample.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO sample(value) VALUES('ok')")
    output = tmp_path / "dr.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_step41_dr_drill.py"), str(database), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["restore_checksum_match"]
    assert payload["sqlite_integrity"] == "ok"
    assert payload["classification"] == "local_rehearsal_not_external_operating_history"
