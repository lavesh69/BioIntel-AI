from __future__ import annotations

# ruff: noqa: E402
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.api.main import app
from biointel.api.middleware import OptionalApiKeyMiddleware
from biointel.production.config import validate_runtime_configuration
from biointel.quality.model_audit import audit_model_directory
from biointel.quality.scorecard import build_quality_scorecard
from biointel.training.model_catalog import update_model_catalog
from biointel.training.release_gate import (
    evaluate_release_gate,
    strict_scientific_release_config,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG


def test_step35_version_navigation_and_home_order() -> None:
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    assert len(PAGE_CATALOG) >= 89
    assert PAGE_BY_KEY["platform_quality"].path == "pages/71_Platform_Quality_Center.py"
    featured = {page.key for page in PAGE_CATALOG if page.featured}
    assert 14 <= len(featured) <= 25
    assert {"privacy_security", "store_readiness"} <= featured
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app_text.index("def safe_page_link") < app_text.index("start_actions = [")
    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    assert '[data-testid="stSidebarNav"]' in theme
    assert "display: none !important" in theme


def test_quality_scorecard_and_model_audit_are_truthful() -> None:
    report = build_quality_scorecard(ROOT)
    assert report["overall_score"] >= report["target_score"]
    assert report["group_scores"]["User experience"] >= 7.0
    assert report["blockers"]
    audit = audit_model_directory(ROOT / "models")
    assert audit["model_count"] == 23
    assert audit["synthetic_models"] == 23
    assert audit["release_eligible_models"] == 0
    assert audit["negative_r2_models"] >= 1


def test_strict_release_policy_requires_real_prospective_evidence() -> None:
    metadata = SimpleNamespace(
        synthetic_demo=False,
        task_type="classification",
        dataset_sha256="a" * 64,
        split_strategy="cold_drug_and_target",
        metrics={"conformal_coverage": 0.9},
        uncertainty_calibration={"coverage": 0.9},
    )
    external = {
        "valid_rows": 200,
        "input_rows": 200,
        "metrics": {"roc_auc": 0.82, "balanced_accuracy": 0.74},
        "drift": {"status": "low"},
    }
    manifest = {
        "dataset_sha256": "a" * 64,
        "license_coverage": 1.0,
        "review_coverage": 1.0,
        "mean_quality": 0.8,
        "source_count": 2,
        "publication_coverage": 0.8,
    }
    blocked = evaluate_release_gate(
        metadata=metadata,
        external_validation=external,
        split_summary={"strategy": "cold_drug_and_target", "group_overlap": False},
        evidence_manifest=manifest,
        dataset_metadata={
            "synthetic": False,
            "real_experimental_data": True,
            "dataset_sha256": "a" * 64,
            "authenticity_status": "provider_reference_reviewed",
        },
        config=strict_scientific_release_config(),
    )
    assert blocked.passed is False
    assert any("Prospective validation" in value for value in blocked.blockers)

    passed = evaluate_release_gate(
        metadata=metadata,
        external_validation=external,
        prospective_validation={"passed": True, "validated_rows": 30},
        split_summary={"strategy": "cold_drug_and_target", "group_overlap": False},
        evidence_manifest=manifest,
        dataset_metadata={
            "synthetic": False,
            "real_experimental_data": True,
            "dataset_sha256": "a" * 64,
            "authenticity_status": "provider_reference_reviewed",
        },
        config=strict_scientific_release_config(),
    )
    assert passed.passed is True


def test_reviewer_permissions_are_non_destructive() -> None:
    assert OptionalApiKeyMiddleware._allowed(
        "reviewer", "POST", "/documents/history/run-123/ocr-corrections"
    )
    assert not OptionalApiKeyMiddleware._allowed("reviewer", "DELETE", "/documents/history/run-123")
    assert not OptionalApiKeyMiddleware._allowed(
        "reviewer", "DELETE", "/documents/history/run-123/purge"
    )
    assert not OptionalApiKeyMiddleware._allowed(
        "reviewer", "POST", "/documents/history/run-123/restore"
    )


def test_production_configuration_requires_auth_and_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BIOINTEL_ENV", "production")
    for key in (
        "BIOINTEL_API_CLIENTS_JSON",
        "BIOINTEL_API_KEY",
        "BIOINTEL_DATABASE_URL",
        "BIOINTEL_REDIS_URL",
        "BIOINTEL_OBJECT_STORAGE_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    report = validate_runtime_configuration()
    assert report["valid"] is False
    assert report["critical_count"] >= 4


def test_synthetic_model_cannot_be_promoted_with_quality_enforcement(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    model = models / "demo.joblib"
    model.write_bytes(b"placeholder")
    metadata = {
        "task_type": "regression",
        "synthetic_demo": True,
        "split_strategy": "random_pair",
        "dataset_sha256": "a" * 64,
        "metrics": {"r2": -0.2, "pearson": 0.0, "rmse": 1.0},
    }
    model.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be activated"):
        update_model_catalog(
            models,
            model.name,
            state="active",
            is_default=True,
            enforce_quality=True,
        )


def test_quality_and_metrics_api_surfaces() -> None:
    client = TestClient(app)
    scorecard = client.get("/quality/scorecard")
    assert scorecard.status_code == 200
    assert scorecard.json()["model_audit"]["synthetic_models"] == 23
    models = client.get("/quality/models")
    assert models.status_code == 200
    assert models.json()["release_eligible_models"] == 0
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "biointel_http_requests_total" in metrics.text
    ready = client.get("/ready")
    assert ready.status_code == 200
