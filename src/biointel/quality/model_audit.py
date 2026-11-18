from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROBUST_SPLITS = {
    "cold_drug",
    "cold_target",
    "cold_drug_and_target",
    "scaffold",
    "scaffold_group",
    "temporal",
    "protein_sequence_cluster",
}


@dataclass(frozen=True)
class ModelQualityAudit:
    model_file: str
    task: str
    synthetic_demo: bool
    split_strategy: str
    performance_passed: bool
    uncertainty_passed: bool
    robust_split_passed: bool
    external_validation_present: bool
    release_eligible: bool
    score: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: dict[str, Any]


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def audit_model_metadata(metadata: dict[str, Any], *, model_file: str = "") -> ModelQualityAudit:
    task = str(metadata.get("task_type") or metadata.get("task") or "unknown").lower()
    metrics = dict(metadata.get("metrics") or {})
    split_strategy = str(metadata.get("split_strategy") or "unknown").lower()
    synthetic = bool(metadata.get("synthetic_demo", False))
    blockers: list[str] = []
    warnings: list[str] = []

    if synthetic:
        blockers.append("Training data is marked synthetic/demo.")

    if task == "classification":
        roc_auc = _number(metrics.get("roc_auc"))
        balanced_accuracy = _number(metrics.get("balanced_accuracy"))
        performance_passed = bool(
            roc_auc is not None
            and balanced_accuracy is not None
            and roc_auc >= 0.70
            and balanced_accuracy >= 0.65
        )
        if not performance_passed:
            blockers.append("Classification performance is below the minimum release gate.")
        coverage = _number(metrics.get("conformal_coverage"))
        brier = _number(metrics.get("brier_score"))
        uncertainty_passed = bool(
            coverage is not None and coverage >= 0.80 and (brier is None or brier <= 0.25)
        )
    elif task == "regression":
        r2 = _number(metrics.get("r2"))
        pearson = _number(metrics.get("pearson"))
        rmse = _number(metrics.get("rmse"))
        performance_passed = bool(
            r2 is not None
            and pearson is not None
            and rmse is not None
            and r2 > 0.0
            and pearson >= 0.20
            and rmse <= 1.50
        )
        if not performance_passed:
            blockers.append("Regression performance does not beat the minimum baseline gate.")
        coverage = _number(metrics.get("conformal_coverage"))
        uncertainty_passed = bool(coverage is not None and 0.80 <= coverage <= 1.0)
    else:
        performance_passed = False
        uncertainty_passed = False
        blockers.append("Unknown model task type.")

    if not uncertainty_passed:
        warnings.append("Uncertainty or calibration evidence is incomplete or below target.")

    robust_split_passed = split_strategy in ROBUST_SPLITS
    if not robust_split_passed:
        blockers.append(
            "A leakage-resistant cold, scaffold, sequence-cluster or temporal split is required."
        )

    external = metadata.get("external_validation") or metadata.get("external_validation_report")
    external_validation_present = bool(external)
    if not external_validation_present:
        blockers.append("Independent external validation is missing.")

    dataset_hash = str(metadata.get("dataset_sha256") or "").strip()
    if len(dataset_hash) != 64:
        blockers.append("A valid immutable training-dataset SHA-256 binding is missing.")

    checks = [
        not synthetic,
        performance_passed,
        uncertainty_passed,
        robust_split_passed,
        external_validation_present,
        len(dataset_hash) == 64,
    ]
    score = round(100.0 * sum(checks) / len(checks), 1)
    return ModelQualityAudit(
        model_file=model_file,
        task=task,
        synthetic_demo=synthetic,
        split_strategy=split_strategy,
        performance_passed=performance_passed,
        uncertainty_passed=uncertainty_passed,
        robust_split_passed=robust_split_passed,
        external_validation_present=external_validation_present,
        release_eligible=not blockers,
        score=score,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        metrics=metrics,
    )


def audit_model_directory(models_directory: str | Path) -> dict[str, Any]:
    directory = Path(models_directory).resolve()
    audits: list[ModelQualityAudit] = []
    errors: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name == "catalog.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            audits.append(audit_model_metadata(payload, model_file=path.stem + ".joblib"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors[path.name] = str(exc)

    regression = [item for item in audits if item.task == "regression"]
    classification = [item for item in audits if item.task == "classification"]
    return {
        "models": [asdict(item) for item in audits],
        "model_count": len(audits),
        "classification_models": len(classification),
        "regression_models": len(regression),
        "synthetic_models": sum(item.synthetic_demo for item in audits),
        "release_eligible_models": sum(item.release_eligible for item in audits),
        "negative_r2_models": sum(
            1
            for item in regression
            if _number(item.metrics.get("r2")) is not None
            and float(item.metrics["r2"]) < 0
        ),
        "robust_split_models": sum(item.robust_split_passed for item in audits),
        "externally_validated_models": sum(item.external_validation_present for item in audits),
        "mean_quality_score": round(
            sum(item.score for item in audits) / max(len(audits), 1), 1
        ),
        "errors": errors,
    }
