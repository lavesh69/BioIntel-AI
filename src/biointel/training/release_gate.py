from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

ROBUST_SPLIT_STRATEGIES = (
    "cold_drug",
    "cold_target",
    "cold_drug_and_target",
    "scaffold",
    "scaffold_group",
    "temporal",
    "protein_sequence_cluster",
)


@dataclass(frozen=True)
class ReleaseGateConfig:
    require_non_synthetic: bool = True
    require_verified_authenticity: bool = False
    require_external_validation: bool = True
    minimum_external_rows: int = 100
    minimum_roc_auc: float = 0.70
    minimum_balanced_accuracy: float = 0.65
    maximum_rmse: float = 1.50
    require_positive_regression_r2: bool = False
    minimum_regression_pearson: float = 0.20
    maximum_drift_level: str = "moderate"
    maximum_invalid_fraction: float = 0.10
    require_no_split_overlap: bool = True
    require_robust_split_strategy: bool = False
    accepted_split_strategies: tuple[str, ...] = ROBUST_SPLIT_STRATEGIES
    require_uncertainty_calibration: bool = False
    minimum_conformal_coverage: float = 0.80
    require_prospective_validation: bool = False
    minimum_prospective_rows: int = 20
    require_evidence_manifest: bool = True
    minimum_license_coverage: float = 1.0
    minimum_review_coverage: float = 1.0
    minimum_mean_quality: float = 0.55
    minimum_source_count: int = 1
    minimum_publication_coverage: float = 0.0
    require_dataset_hash_match: bool = True
    require_complete_dti_validation_matrix: bool = False


@dataclass(frozen=True)
class ReleaseGateResult:
    passed: bool
    score: float
    checks: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]


_DRIFT_RANK = {
    "low": 0,
    "none": 0,
    "moderate": 1,
    "high": 2,
    "severe": 3,
    "critical": 3,
    "unknown": 4,
}


def strict_scientific_release_config() -> ReleaseGateConfig:
    """Publication-grade policy used by the production API and quality center."""

    return replace(
        ReleaseGateConfig(),
        require_verified_authenticity=True,
        require_robust_split_strategy=True,
        require_uncertainty_calibration=True,
        require_prospective_validation=True,
        require_positive_regression_r2=True,
        minimum_mean_quality=0.65,
        minimum_source_count=2,
        minimum_publication_coverage=0.50,
    )


def complete_dti_release_config() -> ReleaseGateConfig:
    """Maximum DTI policy requiring every leakage-resistant and prospective split."""

    return replace(
        strict_scientific_release_config(),
        require_complete_dti_validation_matrix=True,
        minimum_external_rows=100,
        minimum_prospective_rows=100,
        minimum_regression_pearson=0.30,
        minimum_conformal_coverage=0.85,
    )


def _metadata_value(metadata: Any, name: str, default: Any = None) -> Any:
    if isinstance(metadata, dict):
        return metadata.get(name, default)
    return getattr(metadata, name, default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_release_gate(
    *,
    metadata: Any | None = None,
    external_validation: dict[str, Any] | None = None,
    split_summary: dict[str, Any] | None = None,
    evidence_manifest: dict[str, Any] | None = None,
    model_report: dict[str, Any] | None = None,
    dataset_metadata: dict[str, Any] | None = None,
    leakage_audit: dict[str, Any] | None = None,
    drift_report: dict[str, Any] | None = None,
    prospective_validation: dict[str, Any] | None = None,
    validation_matrix: dict[str, Any] | None = None,
    config: ReleaseGateConfig | None = None,
) -> ReleaseGateResult:
    cfg = config or ReleaseGateConfig()
    model_report = dict(model_report or {})
    dataset_metadata = dict(dataset_metadata or {})
    if metadata is not None:
        model_report.setdefault("task", _metadata_value(metadata, "task_type", "classification"))
        model_report.setdefault("metrics", _metadata_value(metadata, "metrics", {}) or {})
        model_report.setdefault(
            "uncertainty_calibration",
            _metadata_value(metadata, "uncertainty_calibration", {}) or {},
        )
        model_report.setdefault(
            "split_strategy", _metadata_value(metadata, "split_strategy", "unknown")
        )
        dataset_metadata.setdefault(
            "synthetic", bool(_metadata_value(metadata, "synthetic_demo", False))
        )
        dataset_metadata.setdefault(
            "real_experimental_data",
            not bool(_metadata_value(metadata, "synthetic_demo", False)),
        )
        artifact_hash = _metadata_value(metadata, "dataset_sha256", None)
        if artifact_hash:
            dataset_metadata.setdefault("dataset_sha256", artifact_hash)

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    def add(
        name: str,
        passed: bool,
        value: Any,
        requirement: str,
        blocking: bool = True,
    ) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "value": value,
                "requirement": requirement,
                "blocking": blocking,
            }
        )
        if not passed:
            (blockers if blocking else warnings).append(f"{name}: {requirement}")

    synthetic = bool(
        dataset_metadata.get("synthetic", dataset_metadata.get("synthetic_only", False))
    )
    real_flag = bool(dataset_metadata.get("real_experimental_data", False))
    add(
        "Real experimental training data",
        (not synthetic and real_flag) or not cfg.require_non_synthetic,
        {"synthetic": synthetic, "real_experimental_data": real_flag},
        "Training data must be verified real experimental evidence.",
    )

    if cfg.require_verified_authenticity:
        authenticity = str(dataset_metadata.get("authenticity_status") or "unknown")
        accepted = authenticity in {
            "provider_reference_reviewed",
            "provider_reference_pending_review",
            "user_attested_reviewed",
        }
        add(
            "Dataset authenticity",
            accepted,
            authenticity,
            "Dataset authenticity must be provider-verified or explicitly attested and reviewed.",
        )

    manifest = evidence_manifest or {}
    if cfg.require_evidence_manifest:
        add("Evidence manifest", bool(manifest), bool(manifest), "An evidence manifest is required.")
        add(
            "Licence coverage",
            _safe_float(manifest.get("license_coverage")) >= cfg.minimum_license_coverage,
            manifest.get("license_coverage", 0.0),
            f"Licence coverage must be >= {cfg.minimum_license_coverage:.0%}.",
        )
        add(
            "Scientific review coverage",
            _safe_float(manifest.get("review_coverage")) >= cfg.minimum_review_coverage,
            manifest.get("review_coverage", 0.0),
            f"Accepted review coverage must be >= {cfg.minimum_review_coverage:.0%}.",
        )
        add(
            "Evidence quality",
            _safe_float(manifest.get("mean_quality")) >= cfg.minimum_mean_quality,
            manifest.get("mean_quality", 0.0),
            f"Mean evidence quality must be >= {cfg.minimum_mean_quality:.2f}.",
        )
        add(
            "Independent evidence sources",
            int(manifest.get("source_count", 0)) >= cfg.minimum_source_count,
            manifest.get("source_count", 0),
            f"At least {cfg.minimum_source_count} independent source(s) are required.",
        )
        add(
            "Publication coverage",
            _safe_float(manifest.get("publication_coverage"))
            >= cfg.minimum_publication_coverage,
            manifest.get("publication_coverage", 0.0),
            f"Publication coverage must be >= {cfg.minimum_publication_coverage:.0%}.",
            blocking=cfg.minimum_publication_coverage > 0,
        )
        if cfg.require_dataset_hash_match:
            expected = str(dataset_metadata.get("dataset_sha256") or "")
            observed = str(manifest.get("dataset_sha256") or "")
            add(
                "Dataset hash binding",
                bool(expected and observed and expected == observed),
                {"expected": expected, "observed": observed},
                "Model dataset hash and evidence-manifest hash must match.",
            )

    external = external_validation or {}
    if not external:
        add(
            "Independent external validation",
            not cfg.require_external_validation,
            None,
            "External validation report is required.",
        )
    else:
        valid_rows = int(external.get("valid_rows", external.get("rows", 0)))
        input_rows = max(int(external.get("input_rows", valid_rows)), 1)
        invalid_fraction = 1.0 - valid_rows / input_rows
        add(
            "External validation size",
            valid_rows >= cfg.minimum_external_rows,
            valid_rows,
            f"At least {cfg.minimum_external_rows} valid rows are required.",
        )
        add(
            "External invalid-row fraction",
            invalid_fraction <= cfg.maximum_invalid_fraction,
            invalid_fraction,
            f"Invalid fraction must be <= {cfg.maximum_invalid_fraction:.0%}.",
        )
        metrics = external.get("metrics", {}) or {}
        task = str(model_report.get("task", "classification")).lower()
        if task == "classification":
            add(
                "External ROC-AUC",
                metrics.get("roc_auc") is not None
                and _safe_float(metrics["roc_auc"]) >= cfg.minimum_roc_auc,
                metrics.get("roc_auc"),
                f"ROC-AUC must be >= {cfg.minimum_roc_auc:.2f}.",
            )
            add(
                "External balanced accuracy",
                metrics.get("balanced_accuracy") is not None
                and _safe_float(metrics["balanced_accuracy"])
                >= cfg.minimum_balanced_accuracy,
                metrics.get("balanced_accuracy"),
                f"Balanced accuracy must be >= {cfg.minimum_balanced_accuracy:.2f}.",
            )
        else:
            add(
                "External RMSE",
                metrics.get("rmse") is not None
                and _safe_float(metrics["rmse"], float("inf")) <= cfg.maximum_rmse,
                metrics.get("rmse"),
                f"RMSE must be <= {cfg.maximum_rmse:.2f}.",
            )
            if cfg.require_positive_regression_r2:
                add(
                    "External regression baseline",
                    metrics.get("r2") is not None and _safe_float(metrics["r2"]) > 0.0,
                    metrics.get("r2"),
                    "External R² must be positive and beat the mean baseline.",
                )
                add(
                    "External regression correlation",
                    metrics.get("pearson") is not None
                    and _safe_float(metrics["pearson"])
                    >= cfg.minimum_regression_pearson,
                    metrics.get("pearson"),
                    f"External Pearson correlation must be >= {cfg.minimum_regression_pearson:.2f}.",
                )
        drift = drift_report or external.get("drift", {}) or {}
        status = str(drift.get("overall_level", drift.get("status", "unknown"))).lower().strip()
        status = next(
            (label for label in _DRIFT_RANK if status.startswith(label)), "unknown"
        )
        add(
            "Dataset drift",
            _DRIFT_RANK.get(status, 4)
            <= _DRIFT_RANK.get(cfg.maximum_drift_level, 1),
            status,
            f"Drift must be no worse than {cfg.maximum_drift_level}.",
            blocking=False,
        )

    leakage = leakage_audit or split_summary
    if cfg.require_no_split_overlap:
        if leakage is None:
            add(
                "Leakage-safe split",
                False,
                None,
                "Leakage audit or split summary is required.",
            )
        else:
            if "passed" in leakage:
                clean = bool(leakage["passed"])
            else:
                clean = not any(
                    bool(leakage.get(key, False))
                    for key in (
                        "group_overlap",
                        "cluster_overlap",
                        "drug_overlap",
                        "target_overlap",
                        "exact_compound_overlap",
                        "scaffold_overlap",
                        "exact_target_overlap",
                        "target_cluster_overlap",
                        "pair_overlap",
                    )
                )
            add(
                "Leakage-safe split",
                clean,
                leakage,
                "Train, validation and test entities, scaffolds and clusters must not overlap.",
            )

    if cfg.require_robust_split_strategy:
        strategy = str(
            (split_summary or {}).get("strategy")
            or model_report.get("split_strategy")
            or "unknown"
        ).lower()
        add(
            "Robust split strategy",
            strategy in cfg.accepted_split_strategies,
            strategy,
            "Use a cold-drug, cold-target, combined cold, scaffold, temporal or sequence-cluster split.",
        )

    if cfg.require_uncertainty_calibration:
        metrics = model_report.get("metrics", {}) or {}
        calibration = model_report.get("uncertainty_calibration", {}) or {}
        coverage = metrics.get("conformal_coverage", calibration.get("coverage"))
        add(
            "Uncertainty calibration",
            coverage is not None
            and cfg.minimum_conformal_coverage <= _safe_float(coverage) <= 1.0,
            coverage,
            f"Conformal coverage must be >= {cfg.minimum_conformal_coverage:.0%} on held-out data.",
        )

    matrix = validation_matrix or {}
    if cfg.require_complete_dti_validation_matrix:
        required_splits = {
            "cold_drug", "cold_target", "cold_drug_and_target", "scaffold",
            "protein_sequence_cluster", "temporal", "independent_external", "prospective"
        }
        supplied_splits = {
            str(item.get("split", "")).lower()
            for item in matrix.get("evidence", [])
            if isinstance(item, dict)
        }
        matrix_passed = (
            bool(matrix.get("release_eligible", False))
            and _safe_float(matrix.get("coverage_fraction")) >= 1.0
            and required_splits.issubset(supplied_splits)
        )
        add(
            "Complete DTI validation matrix",
            matrix_passed,
            {
                "coverage_fraction": matrix.get("coverage_fraction", 0.0),
                "supplied_splits": sorted(supplied_splits),
                "release_eligible": matrix.get("release_eligible", False),
            },
            "Cold-drug, cold-target, cold-both, scaffold, sequence-cluster, temporal, independent external and prospective validation must all pass.",
        )

    prospective = prospective_validation or {}
    if cfg.require_prospective_validation:
        rows = int(prospective.get("validated_rows", prospective.get("rows", 0)) or 0)
        passed = bool(prospective.get("passed", False)) and rows >= cfg.minimum_prospective_rows
        add(
            "Prospective validation",
            passed,
            {"passed": prospective.get("passed", False), "rows": rows},
            f"A blinded prospective validation with at least {cfg.minimum_prospective_rows} rows is required.",
        )

    score = round(
        100.0 * sum(bool(check["passed"]) for check in checks) / max(len(checks), 1),
        1,
    )
    return ReleaseGateResult(
        passed=not blockers,
        score=score,
        checks=tuple(checks),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        evidence={
            "model_report": model_report,
            "dataset_metadata": dataset_metadata,
            "external_validation": external_validation or {},
            "prospective_validation": prospective_validation or {},
            "split_summary": split_summary or {},
            "leakage_audit": leakage_audit or {},
            "evidence_manifest": manifest,
            "validation_matrix": matrix,
            "config": asdict(cfg),
        },
    )


def release_gate_dict(result: ReleaseGateResult) -> dict[str, Any]:
    return asdict(result)
