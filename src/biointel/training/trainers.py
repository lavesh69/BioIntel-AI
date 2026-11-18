from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

import Bio
import joblib
import numpy as np
import pandas as pd
import rdkit
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    ElasticNet,
    LogisticRegression,
    Ridge,
    SGDClassifier,
    SGDRegressor,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from biointel.dti.dataset_validation import validate_dti_dataset
from biointel.provenance import stable_dataframe_sha256
from biointel.training.evaluation import (
    bootstrap_classification_intervals,
    bootstrap_regression_intervals,
    classification_metrics,
    optimize_binary_threshold,
    regression_metrics,
)
from biointel.training.feature_matrix import (
    FeatureMatrixResult,
    build_feature_matrix,
)
from biointel.training.model_artifact import (
    ARTIFACT_VERSION,
    ModelArtifact,
    ModelMetadata,
    utc_now_iso,
)
from biointel.training.scaffold import murcko_scaffold_smiles
from biointel.training.scientific_splits import (
    cold_drug_target_split_indices,
    sequence_cluster_split_indices,
    temporal_split_indices,
)
from biointel.training.uncertainty import (
    classification_conformal_diagnostics,
    fit_classification_conformal,
    fit_regression_conformal,
    regression_conformal_diagnostics,
)
from biointel.utils.exceptions import TrainingError


@dataclass(frozen=True)
class TrainingConfig:
    task_type: str = "classification"
    model_name: str = "random_forest"
    split_strategy: str = "random_pair"
    test_fraction: float = 0.20
    validation_fraction: float = 0.15
    random_seed: int = 42
    decision_threshold: float = 0.5
    threshold_strategy: str = "fixed"
    calibration_method: str = "none"
    fingerprint_radius: int = 2
    fingerprint_bits: int = 256
    use_chirality: bool = True
    include_dipeptides: bool = False
    dataset_name: str = "user_dataset"
    dataset_version: str = "1.0"
    model_version: str = "1.0.0"
    activity_type: str | None = None
    synthetic_demo: bool = False
    n_estimators: int = 160
    tree_max_depth: int | None = None
    tree_min_samples_leaf: int = 2
    tree_max_features: str | float | None = None
    tree_max_samples: float | None = None
    bootstrap_iterations: int = 200
    parallel_jobs: int = 1
    source_description: str = "User-provided or local dataset"
    conformal_alpha: float = 0.10
    temporal_column: str = "publication_date"
    sequence_identity_threshold: float = 0.70


@dataclass(frozen=True)
class TrainingResult:
    artifact: ModelArtifact
    metrics: dict[str, float | None]
    validation_metrics: dict[str, float | None]
    predictions: pd.DataFrame
    validation_predictions: pd.DataFrame
    feature_errors: pd.DataFrame
    data_quality_summary: dict[str, object]
    train_rows: int
    validation_rows: int
    test_rows: int


def _make_estimator(config: TrainingConfig) -> Any:
    if config.task_type == "classification":
        if config.model_name == "logistic_regression":
            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=3000,
                            class_weight="balanced",
                            random_state=config.random_seed,
                        ),
                    ),
                ]
            )
        if config.model_name == "random_forest":
            return RandomForestClassifier(
                n_estimators=config.n_estimators,
                class_weight="balanced",
                random_state=config.random_seed,
                n_jobs=config.parallel_jobs,
                min_samples_leaf=config.tree_min_samples_leaf,
                max_depth=config.tree_max_depth,
                max_features=(
                    config.tree_max_features if config.tree_max_features is not None else "sqrt"
                ),
                max_samples=config.tree_max_samples,
            )
        if config.model_name == "extra_trees":
            return ExtraTreesClassifier(
                n_estimators=config.n_estimators,
                class_weight="balanced",
                random_state=config.random_seed,
                n_jobs=config.parallel_jobs,
                min_samples_leaf=config.tree_min_samples_leaf,
                max_depth=config.tree_max_depth,
                max_features=(
                    config.tree_max_features if config.tree_max_features is not None else "sqrt"
                ),
            )
        if config.model_name == "sgd_logistic":
            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        SGDClassifier(
                            loss="log_loss",
                            class_weight="balanced",
                            max_iter=2500,
                            tol=1e-4,
                            random_state=config.random_seed,
                            early_stopping=True,
                            validation_fraction=0.1,
                        ),
                    ),
                ]
            )
        if config.model_name == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(
                random_state=config.random_seed,
                max_iter=180,
                learning_rate=0.08,
            )

    if config.task_type == "regression":
        if config.model_name == "ridge":
            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("model", Ridge(alpha=1.0, solver="lsqr")),
                ]
            )
        if config.model_name == "random_forest":
            return RandomForestRegressor(
                n_estimators=config.n_estimators,
                random_state=config.random_seed,
                n_jobs=config.parallel_jobs,
                min_samples_leaf=config.tree_min_samples_leaf,
                max_depth=config.tree_max_depth,
                max_features=(
                    config.tree_max_features if config.tree_max_features is not None else 1.0
                ),
                max_samples=config.tree_max_samples,
            )
        if config.model_name == "extra_trees":
            return ExtraTreesRegressor(
                n_estimators=config.n_estimators,
                random_state=config.random_seed,
                n_jobs=config.parallel_jobs,
                min_samples_leaf=config.tree_min_samples_leaf,
                max_depth=config.tree_max_depth,
                max_features=(
                    config.tree_max_features if config.tree_max_features is not None else "sqrt"
                ),
            )
        if config.model_name == "elastic_net":
            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        ElasticNet(
                            alpha=0.001,
                            l1_ratio=0.15,
                            max_iter=5000,
                            random_state=config.random_seed,
                        ),
                    ),
                ]
            )
        if config.model_name == "sgd_regression":
            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        SGDRegressor(
                            loss="huber",
                            penalty="elasticnet",
                            alpha=0.0005,
                            l1_ratio=0.10,
                            max_iter=3000,
                            tol=1e-4,
                            random_state=config.random_seed,
                            early_stopping=True,
                            validation_fraction=0.1,
                        ),
                    ),
                ]
            )
        if config.model_name == "hist_gradient_boosting":
            return HistGradientBoostingRegressor(
                random_state=config.random_seed,
                max_iter=180,
                learning_rate=0.08,
            )

    raise TrainingError(f"Unsupported {config.task_type} model: {config.model_name}")


def _split_once(
    indices: np.ndarray,
    target: np.ndarray,
    fraction: float,
    seed: int,
    task_type: str,
    groups: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if groups is None:
        stratify = target if task_type == "classification" else None
        if stratify is not None:
            _, counts = np.unique(stratify, return_counts=True)
            if len(counts) < 2 or counts.min() < 2:
                raise TrainingError(
                    "Both classes need at least two rows for " "stratified splitting."
                )

        left, right = train_test_split(
            indices,
            test_size=fraction,
            random_state=seed,
            stratify=stratify,
        )
        return np.asarray(left), np.asarray(right)

    if len(np.unique(groups)) < 3:
        raise TrainingError("Group/scaffold splitting requires at least three unique groups.")

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=fraction,
        random_state=seed,
    )
    left_positions, right_positions = next(splitter.split(indices, target, groups))
    return indices[left_positions], indices[right_positions]


def _split_indices(
    data: pd.DataFrame,
    target: np.ndarray,
    config: TrainingConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object]]:
    indices = np.arange(len(data))
    if len(indices) < 12:
        raise TrainingError(
            "At least 12 valid unique rows are required for " "train/validation/test."
        )

    if config.split_strategy == "temporal":
        result = temporal_split_indices(
            data,
            config.temporal_column,
            test_fraction=config.test_fraction,
            validation_fraction=config.validation_fraction,
        )
        return (
            result.train_indices,
            result.validation_indices,
            result.test_indices,
            result.summary,
        )
    if config.split_strategy == "cold_drug_target":
        result = cold_drug_target_split_indices(
            data,
            drug_column="drug_id",
            target_column="target_id",
            test_fraction=config.test_fraction,
            validation_fraction=config.validation_fraction,
            random_seed=config.random_seed,
        )
        return (
            result.train_indices,
            result.validation_indices,
            result.test_indices,
            result.summary,
        )
    if config.split_strategy == "protein_cluster":
        result = sequence_cluster_split_indices(
            data,
            sequence_column="protein_sequence",
            identity_threshold=config.sequence_identity_threshold,
            test_fraction=config.test_fraction,
            validation_fraction=config.validation_fraction,
            random_seed=config.random_seed,
        )
        return (
            result.train_indices,
            result.validation_indices,
            result.test_indices,
            result.summary,
        )

    groups: np.ndarray | None = None
    if config.split_strategy == "drug_group":
        if "drug_id" not in data.columns:
            raise TrainingError("drug_group split requires a drug_id column.")
        groups = data["drug_id"].astype(str).to_numpy()
    elif config.split_strategy == "target_group":
        if "target_id" not in data.columns:
            raise TrainingError("target_group split requires a target_id column.")
        groups = data["target_id"].astype(str).to_numpy()
    elif config.split_strategy == "scaffold":
        groups = data["canonical_smiles"].map(murcko_scaffold_smiles).to_numpy()
    elif config.split_strategy != "random_pair":
        raise TrainingError(f"Unsupported split strategy: {config.split_strategy}")

    remaining, test_indices = _split_once(
        indices,
        target,
        config.test_fraction,
        config.random_seed,
        config.task_type,
        groups,
    )

    relative_validation = config.validation_fraction / (1.0 - config.test_fraction)
    remaining_groups = groups[remaining] if groups is not None else None
    train_indices, validation_indices = _split_once(
        remaining,
        target[remaining],
        relative_validation,
        config.random_seed + 1,
        config.task_type,
        remaining_groups,
    )

    summary: dict[str, object] = {
        "strategy": config.split_strategy,
        "train_rows": len(train_indices),
        "validation_rows": len(validation_indices),
        "test_rows": len(test_indices),
    }

    if groups is not None:
        summary.update(
            {
                "train_groups": len(np.unique(groups[train_indices])),
                "validation_groups": len(np.unique(groups[validation_indices])),
                "test_groups": len(np.unique(groups[test_indices])),
                "group_overlap": bool(
                    set(groups[train_indices]) & set(groups[validation_indices])
                    or set(groups[train_indices]) & set(groups[test_indices])
                    or set(groups[validation_indices]) & set(groups[test_indices])
                ),
            }
        )

    return (
        train_indices,
        validation_indices,
        test_indices,
        summary,
    )


def _applicability_statistics(
    matrix: np.ndarray,
    names: tuple[str, ...],
    max_fingerprints: int = 256,
) -> dict[str, Any]:
    fingerprint_mask = np.array(
        [name.startswith("morgan_bit_") for name in names],
        dtype=bool,
    )
    numeric_mask = ~fingerprint_mask
    selected = matrix[:, numeric_mask]

    return {
        "feature_names": [name for name, keep in zip(names, numeric_mask, strict=True) if keep],
        "minimum": selected.min(axis=0).tolist(),
        "maximum": selected.max(axis=0).tolist(),
        "mean": selected.mean(axis=0).tolist(),
        "std": selected.std(axis=0).tolist(),
        "fingerprint_names": [
            name for name, keep in zip(names, fingerprint_mask, strict=True) if keep
        ],
        "training_fingerprints": matrix[:max_fingerprints, fingerprint_mask]
        .astype(np.uint8)
        .tolist(),
    }


def _check_split_classes(
    target: np.ndarray,
    indices: np.ndarray,
    name: str,
) -> None:
    if len(np.unique(target[indices])) < 2:
        raise TrainingError(
            f"{name} split contains only one class; " "choose another split or seed."
        )


def train_dti_model(
    dataframe: pd.DataFrame,
    config: TrainingConfig,
) -> TrainingResult:
    """Clean, split, train, tune and evaluate a DTI model."""

    if config.task_type not in {"classification", "regression"}:
        raise TrainingError("task_type must be classification or regression")
    if not 0.1 <= config.test_fraction <= 0.4:
        raise TrainingError("test_fraction must be between 0.10 and 0.40")
    if not 0.1 <= config.validation_fraction <= 0.3:
        raise TrainingError("validation_fraction must be between 0.10 and 0.30")
    if config.test_fraction + config.validation_fraction >= 0.6:
        raise TrainingError("test_fraction + validation_fraction must be below 0.60")
    if not 0.0 < config.decision_threshold < 1.0:
        raise TrainingError("decision_threshold must be between 0 and 1")
    if config.threshold_strategy not in {
        "fixed",
        "optimize_f1",
        "optimize_balanced",
    }:
        raise TrainingError("Unsupported threshold strategy")
    if not 0.01 <= config.conformal_alpha <= 0.50:
        raise TrainingError("conformal_alpha must be between 0.01 and 0.50")
    if not isinstance(config.parallel_jobs, int) or config.parallel_jobs == 0:
        raise TrainingError("parallel_jobs must be a non-zero integer")
    if config.calibration_method not in {
        "none",
        "sigmoid",
        "isotonic",
    }:
        raise TrainingError("Unsupported calibration method")

    validation_report = validate_dti_dataset(dataframe, config.task_type)
    if validation_report.valid_rows < 12:
        raise TrainingError("At least 12 valid unique rows are required after cleaning.")

    target_column = "label" if config.task_type == "classification" else "p_activity"
    features: FeatureMatrixResult = build_feature_matrix(
        validation_report.cleaned,
        target_column=target_column,
        radius=config.fingerprint_radius,
        n_bits=config.fingerprint_bits,
        use_chirality=config.use_chirality,
        include_dipeptides=config.include_dipeptides,
    )

    target = features.target.astype(int if config.task_type == "classification" else float)
    if config.task_type == "classification" and set(np.unique(target)) != {0, 1}:
        raise TrainingError("Classification requires both label classes: 0 and 1.")

    (
        train_indices,
        validation_indices,
        test_indices,
        split_summary,
    ) = _split_indices(features.valid_rows, target, config)

    if config.task_type == "classification":
        for split_name, split_indices in (
            ("Training", train_indices),
            ("Validation", validation_indices),
            ("Test", test_indices),
        ):
            _check_split_classes(target, split_indices, split_name)

    estimator = _make_estimator(config)
    if config.task_type == "classification" and config.calibration_method != "none":
        estimator = CalibratedClassifierCV(
            estimator=estimator,
            method=config.calibration_method,
            cv=3,
            n_jobs=config.parallel_jobs,
        )

    try:
        estimator.fit(
            features.matrix[train_indices],
            target[train_indices],
        )
    except Exception as exc:
        raise TrainingError(f"Estimator training failed: {exc}") from exc

    threshold = config.decision_threshold

    if config.task_type == "classification":
        validation_probabilities = estimator.predict_proba(features.matrix[validation_indices])[
            :, 1
        ]

        if config.threshold_strategy != "fixed":
            objective = "f1" if config.threshold_strategy == "optimize_f1" else "balanced"
            threshold, _ = optimize_binary_threshold(
                target[validation_indices],
                validation_probabilities,
                objective=objective,
            )

        validation_predicted = (validation_probabilities >= threshold).astype(int)
        validation_metrics = classification_metrics(
            target[validation_indices],
            validation_predicted,
            validation_probabilities,
        )
        validation_predictions = pd.DataFrame(
            {
                "actual": target[validation_indices],
                "predicted": validation_predicted,
                "positive_probability": validation_probabilities,
            }
        )
        if len(validation_indices) >= 3:
            uncertainty_calibration = fit_classification_conformal(
                target[validation_indices], validation_probabilities, alpha=config.conformal_alpha
            )
        else:
            uncertainty_calibration = {
                "method": "split_conformal_classification",
                "alpha": config.conformal_alpha,
                "warning": "Too few validation rows for conformal calibration.",
                "calibration_rows": int(len(validation_indices)),
            }

        test_probabilities = estimator.predict_proba(features.matrix[test_indices])[:, 1]
        test_predicted = (test_probabilities >= threshold).astype(int)
        metrics = classification_metrics(
            target[test_indices],
            test_predicted,
            test_probabilities,
        )
        predictions = pd.DataFrame(
            {
                "actual": target[test_indices],
                "predicted": test_predicted,
                "positive_probability": test_probabilities,
            }
        )
        confidence_intervals = bootstrap_classification_intervals(
            target[test_indices],
            test_probabilities,
            threshold=threshold,
            iterations=config.bootstrap_iterations,
            random_seed=config.random_seed,
        )
        if "score_quantile" in uncertainty_calibration:
            metrics.update(
                classification_conformal_diagnostics(
                    target[test_indices], test_probabilities, uncertainty_calibration
                )
            )
    else:
        validation_values = estimator.predict(features.matrix[validation_indices])
        validation_metrics = regression_metrics(target[validation_indices], validation_values)
        validation_predictions = pd.DataFrame(
            {
                "actual": target[validation_indices],
                "predicted": validation_values,
            }
        )
        if len(validation_indices) >= 3:
            uncertainty_calibration = fit_regression_conformal(
                target[validation_indices], validation_values, alpha=config.conformal_alpha
            )
        else:
            uncertainty_calibration = {
                "method": "split_conformal_regression",
                "alpha": config.conformal_alpha,
                "warning": "Too few validation rows for conformal calibration.",
                "calibration_rows": int(len(validation_indices)),
            }

        test_values = estimator.predict(features.matrix[test_indices])
        metrics = regression_metrics(target[test_indices], test_values)
        predictions = pd.DataFrame(
            {
                "actual": target[test_indices],
                "predicted": test_values,
            }
        )
        confidence_intervals = bootstrap_regression_intervals(
            target[test_indices],
            test_values,
            iterations=config.bootstrap_iterations,
            random_seed=config.random_seed,
        )
        if "absolute_residual_quantile" in uncertainty_calibration:
            metrics.update(
                regression_conformal_diagnostics(
                    target[test_indices], test_values, uncertainty_calibration
                )
            )

    software_versions = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "rdkit": rdkit.__version__,
        "biopython": Bio.__version__,
        "joblib": joblib.__version__,
    }
    quality_summary = dict(validation_report.summary)
    quality_summary["split_summary"] = split_summary
    quality_summary["feature_cache"] = features.cache_summary

    trained_at = utc_now_iso()
    experiment_id = (
        "exp-"
        + trained_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
        + "-"
        + uuid4().hex[:8]
    )
    dataset_sha256 = stable_dataframe_sha256(features.valid_rows)

    metadata = ModelMetadata(
        artifact_version=ARTIFACT_VERSION,
        experiment_id=experiment_id,
        model_version=config.model_version,
        model_name=config.model_name,
        task_type=config.task_type,
        trained_at_utc=trained_at,
        dataset_name=config.dataset_name,
        dataset_version=config.dataset_version,
        dataset_sha256=dataset_sha256,
        split_strategy=config.split_strategy,
        threshold_strategy=config.threshold_strategy,
        calibration_method=config.calibration_method,
        decision_threshold=(threshold if config.task_type == "classification" else None),
        positive_class_name=(
            "interaction_positive" if config.task_type == "classification" else None
        ),
        activity_type=config.activity_type,
        synthetic_demo=config.synthetic_demo,
        train_rows=len(train_indices),
        validation_rows=len(validation_indices),
        test_rows=len(test_indices),
        metrics=metrics,
        validation_metrics=validation_metrics,
        confidence_intervals=confidence_intervals,
        data_quality_summary=quality_summary,
        training_config=asdict(config),
        software_versions=software_versions,
        uncertainty_calibration=uncertainty_calibration,
    )

    artifact = ModelArtifact(
        estimator=estimator,
        feature_schema=features.example_features.schema,
        feature_names=features.feature_names,
        metadata=metadata,
        applicability_statistics=_applicability_statistics(
            features.matrix[train_indices],
            features.feature_names,
        ),
    )

    return TrainingResult(
        artifact=artifact,
        metrics=metrics,
        validation_metrics=validation_metrics,
        predictions=predictions,
        validation_predictions=validation_predictions,
        feature_errors=features.errors,
        data_quality_summary=quality_summary,
        train_rows=len(train_indices),
        validation_rows=len(validation_indices),
        test_rows=len(test_indices),
    )
