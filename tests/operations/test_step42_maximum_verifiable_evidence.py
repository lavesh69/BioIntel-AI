from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.api.middleware import OptionalApiKeyMiddleware
from biointel.realworld import (
    INTERNAL_SCORE_CAPS,
    build_step42_maximum_evidence,
    verify_step42_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]


def _json(name: str) -> dict[str, object]:
    return json.loads((ROOT / "reports" / "step42" / name).read_text(encoding="utf-8"))


def test_step42_three_layer_score_is_complete_and_honest() -> None:
    report = build_step42_maximum_evidence(ROOT)
    assert report["capability_count"] == 18
    assert report["implementation_average"] == 10.0
    assert report["verifiable_average"] >= 6.0
    assert report["authentic_external_average"] == 0.0
    assert report["artifact_integrity"]["ok"]
    assert report["strong_verifiable_areas"] >= 8


def test_step42_internal_scores_never_exceed_published_caps() -> None:
    report = build_step42_maximum_evidence(ROOT)
    for capability in report["capabilities"]:
        assert capability["verifiable_score"] <= INTERNAL_SCORE_CAPS[capability["key"]]
        assert capability["authentic_external_score"] in {0.0, 10.0}
        if capability["authentic_external_score"] == 0.0:
            assert capability["missing_external_proof"]


def test_step42_database_restore_drill_is_measured() -> None:
    drill = _json("database_drill.json")
    assert drill["passed"]
    assert drill["database_count"] == 18
    assert drill["rpo_minutes"] == 0.0
    assert all(item["checksum_match"] for item in drill["records"])
    assert all(item["integrity"] == "ok" for item in drill["records"])
    assert all(item["foreign_key_issues"] == 0 for item in drill["records"])


def test_step42_tenant_isolation_and_load_are_measured() -> None:
    isolation = _json("multitenant_isolation.json")
    load = _json("api_load.json")
    assert isolation["passed"]
    assert isolation["isolation_tests"] >= 1000
    assert isolation["confirmed_isolation_breaches"] == 0
    assert isolation["expected_cross_tenant_denials"] == isolation["isolation_tests"]
    assert load["passed"]
    assert load["availability_percent"] == 100.0
    assert load["error_rate_percent"] == 0.0
    assert load["p95_latency_ms"] <= 2000


def test_step42_failover_and_deployment_controls_pass() -> None:
    ha = _json("ha_rehearsal.json")
    kubernetes = _json("kubernetes_static.json")
    cloud = _json("cloud_iac.json")
    assert ha["passed"] and ha["successful_failovers"] == 1
    assert ha["failed_requests"] == 0
    assert kubernetes["passed"] and kubernetes["controls_passed"] == kubernetes["controls_total"]
    assert cloud["passed"] and cloud["controls_passed"] == cloud["controls_total"]


def test_step42_artifact_manifest_is_cryptographically_verified() -> None:
    integrity = verify_step42_artifacts(ROOT)
    assert integrity["ok"]
    assert integrity["artifact_count"] >= 16
    assert integrity["artifact_count"] == integrity["verified_count"]


def test_step42_policy_preserves_external_evidence_boundary() -> None:
    policy = yaml.safe_load((ROOT / "config" / "step42_maximum_verifiable_evidence.yaml").read_text(encoding="utf-8"))
    assert policy["anti_fabrication"]["preserve_external_score_separation"] is True
    assert policy["anti_fabrication"]["require_sha256"] is True
    assert policy["area_caps_without_external_evidence"]["disaster_recovery_drill"] == 9.0
    assert policy["area_caps_without_external_evidence"]["regulatory_approval"] == 3.0


def test_local_api_identity_uses_configurable_quota() -> None:
    app = FastAPI()

    @app.get("/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    app.add_middleware(
        OptionalApiKeyMiddleware,
        api_key=None,
        require_auth=False,
        default_quota_per_minute=999,
    )
    with TestClient(app) as client:
        response = client.get("/live")
    assert response.status_code == 200
    assert response.headers["X-BioIntel-Client"] == "local-operator"
