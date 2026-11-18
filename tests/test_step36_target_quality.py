from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from biointel.dti.validation_suite import REQUIRED_DTI_SPLITS, build_validation_matrix
from biointel.multitenancy.storage import TenantStorageRouter
from biointel.multitenancy.store import TenantStore
from biointel.quality.capability_readiness import build_target_capability_readiness
from biointel.training.release_gate import complete_dti_release_config, evaluate_release_gate
from biointel.validation.rigorous import classification_validation, regression_validation

ROOT = Path(__file__).resolve().parents[1]


def test_rigorous_classification_validation_has_statistics_and_calibration() -> None:
    rng = np.random.default_rng(42)
    truth = rng.integers(0, 2, 400)
    probabilities = np.clip(0.08 + 0.84 * truth + rng.normal(0, 0.08, 400), 0.001, 0.999)
    report = classification_validation(
        truth,
        probabilities,
        groups=np.where(np.arange(400) % 2 == 0, "site-a", "site-b"),
        bootstrap_iterations=200,
        permutation_iterations=200,
    )
    assert report.passed
    assert report.metrics["roc_auc"] > 0.9
    assert report.confidence_intervals["roc_auc"]["lower_95"] > 0.65
    assert report.calibration["expected_calibration_error"] <= 0.10
    assert set(report.subgroup_metrics) == {"site-a", "site-b"}


def test_rigorous_regression_validation_beats_baseline() -> None:
    rng = np.random.default_rng(7)
    truth = rng.normal(7.0, 1.2, 400)
    prediction = truth + rng.normal(0, 0.15, 400)
    report = regression_validation(
        truth,
        prediction,
        bootstrap_iterations=200,
        permutation_iterations=200,
    )
    assert report.passed
    assert report.metrics["r2"] > 0.9
    assert report.confidence_intervals["r2"]["lower_95"] > 0.0
    assert report.permutation_p_value <= 0.05


def _evidence(split: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "split": split,
        "task": "classification",
        "dataset_sha256": "a" * 64,
        "train_rows": 2000,
        "test_rows": 500,
        "drug_overlap": 0,
        "target_overlap": 0,
        "scaffold_overlap": 0,
        "temporal_order_valid": True,
        "metrics": {"roc_auc": 0.81, "balanced_accuracy": 0.74},
        "confidence_intervals": {"roc_auc": {"lower_95": 0.76, "upper_95": 0.85}},
        "calibration": {"expected_calibration_error": 0.06},
        "reviewer": "independent-reviewer",
        "signed_manifest": True,
    }
    return payload


def test_complete_dti_validation_matrix_requires_all_leakage_resistant_splits(tmp_path: Path) -> None:
    model = tmp_path / "model.joblib"
    model.write_bytes(b"immutable-model")
    matrix = build_validation_matrix(model, [_evidence(split) for split in REQUIRED_DTI_SPLITS])
    assert matrix.coverage_fraction == 1.0
    assert matrix.release_eligible
    assert not matrix.blockers


def test_dti_validation_matrix_blocks_missing_prospective_evidence(tmp_path: Path) -> None:
    model = tmp_path / "model.joblib"
    model.write_bytes(b"immutable-model")
    evidence = [_evidence(split) for split in REQUIRED_DTI_SPLITS if split != "prospective"]
    matrix = build_validation_matrix(model, evidence)
    assert not matrix.release_eligible
    assert any("prospective" in item for item in matrix.blockers)


def test_maximum_release_policy_requires_complete_dti_matrix(tmp_path: Path) -> None:
    model = tmp_path / "model.joblib"
    model.write_bytes(b"immutable-model")
    matrix = build_validation_matrix(model, [_evidence(split) for split in REQUIRED_DTI_SPLITS]).to_dict()
    metadata = {
        "task_type": "classification",
        "metrics": {"conformal_coverage": 0.91},
        "split_strategy": "cold_drug_and_target",
        "synthetic_demo": False,
        "dataset_sha256": "a" * 64,
    }
    result = evaluate_release_gate(
        metadata=metadata,
        external_validation={
            "valid_rows": 500, "input_rows": 500,
            "metrics": {"roc_auc": 0.82, "balanced_accuracy": 0.74},
            "drift": {"overall_level": "low"},
        },
        prospective_validation={"passed": True, "validated_rows": 150},
        split_summary={"strategy": "cold_drug_and_target", "drug_overlap": 0, "target_overlap": 0},
        leakage_audit={"passed": True},
        evidence_manifest={
            "license_coverage": 1.0, "review_coverage": 1.0, "mean_quality": 0.9,
            "source_count": 2, "publication_coverage": 0.8, "dataset_sha256": "a" * 64,
        },
        dataset_metadata={
            "synthetic": False, "real_experimental_data": True,
            "authenticity_status": "provider_reference_reviewed", "dataset_sha256": "a" * 64,
        },
        validation_matrix=matrix,
        config=complete_dti_release_config(),
    )
    assert result.passed
    assert any(check["name"] == "Complete DTI validation matrix" and check["passed"] for check in result.checks)


def test_tenant_resources_are_strictly_isolated(tmp_path: Path) -> None:
    store = TenantStore(tmp_path / "tenants.sqlite3")
    store.ensure_tenant("alpha-lab", "Alpha Lab")
    store.ensure_tenant("beta-lab", "Beta Lab")
    store.add_membership("alpha-lab", "alpha-user", "owner")
    store.add_membership("beta-lab", "beta-user", "owner")
    alpha = store.resolve_context(client_id="alpha-user", api_role="admin", requested_tenant="alpha-lab")
    beta = store.resolve_context(client_id="beta-user", api_role="admin", requested_tenant="beta-lab")
    resource = store.put_resource(alpha, resource_type="dataset", name="Private alpha data", payload={"secret": 42})
    assert store.list_resources(alpha)[0]["payload"]["secret"] == 42
    assert store.list_resources(beta) == []
    with pytest.raises(KeyError):
        store.get_resource(beta, resource["resource_id"])
    with pytest.raises(PermissionError):
        store.resolve_context(client_id="beta-user", api_role="admin", requested_tenant="alpha-lab")


def test_tenant_storage_router_prevents_path_and_object_key_escape(tmp_path: Path) -> None:
    store = TenantStore(tmp_path / "tenants.sqlite3")
    store.ensure_tenant("alpha-lab", "Alpha Lab")
    store.add_membership("alpha-lab", "alpha-user", "owner")
    context = store.resolve_context(client_id="alpha-user", api_role="admin", requested_tenant="alpha-lab")
    router = TenantStorageRouter(tmp_path / "objects")
    safe = router.path(context, "datasets", "manifest.json", create_parent=True)
    assert safe.parent.name == "datasets"
    assert "alpha-lab" in safe.parts
    assert router.object_key(context, "models", "candidate.joblib") == "tenants/alpha-lab/models/candidate.joblib"
    with pytest.raises(ValueError):
        router.path(context, "..", "beta-lab", "secret.txt")
    with pytest.raises(ValueError):
        router.object_key(context, "../beta-lab/secret.txt")


def test_kubernetes_chart_has_production_resilience_and_security_controls() -> None:
    chart = ROOT / "deploy" / "helm" / "biointel"
    required = {
        "templates/deployments.yaml": ["startupProbe", "readinessProbe", "livenessProbe", "containerSecurityContext"],
        "values.yaml": ["readOnlyRootFilesystem", "runAsNonRoot", "seccompProfile"],
        "templates/hpa.yaml": ["HorizontalPodAutoscaler", "autoscaling/v2"],
        "templates/pdb.yaml": ["PodDisruptionBudget"],
        "templates/networkpolicy.yaml": ["NetworkPolicy", "Ingress", "Egress"],
        "templates/migration-job.yaml": ["pre-install,pre-upgrade"],
        "values.schema.json": ["$schema"],
    }
    for relative, needles in required.items():
        text = (chart / relative).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text


def test_requested_capability_implementation_matrix_is_complete() -> None:
    report = build_target_capability_readiness(ROOT)
    assert report["all_implementation_targets_complete"] is True
    assert report["implementation_average"] == 10.0
    assert all(item["implementation_score"] == 10.0 for item in report["capabilities"])
    ml = next(item for item in report["capabilities"] if item["key"] == "ml_validation_framework")
    assert ml["evidence_score"] < ml["implementation_score"]
