from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from biointel.training.model_artifact import ModelArtifact, utc_now_iso


class WeightedEnsembleEstimator:
    """Schema-compatible soft-voting estimator for trusted local artifacts."""

    def __init__(self, estimators: list[Any], weights: list[float], task_type: str) -> None:
        if not estimators:
            raise ValueError("At least one estimator is required.")
        if len(estimators) != len(weights):
            raise ValueError("estimators and weights must have equal length.")
        weight_array = np.asarray(weights, dtype=float)
        if not np.isfinite(weight_array).all() or (weight_array <= 0).any():
            raise ValueError("Ensemble weights must be finite positive values.")
        self.estimators = estimators
        self.weights = weight_array / weight_array.sum()
        self.task_type = task_type

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        if self.task_type != "classification":
            raise AttributeError("Regression ensemble does not provide predict_proba.")
        probabilities = np.stack(
            [
                np.asarray(estimator.predict_proba(matrix), dtype=float)
                for estimator in self.estimators
            ]
        )
        return np.tensordot(self.weights, probabilities, axes=(0, 0))

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        if self.task_type == "classification":
            return (self.predict_proba(matrix)[:, 1] >= 0.5).astype(int)
        predictions = np.stack(
            [np.asarray(estimator.predict(matrix), dtype=float) for estimator in self.estimators]
        )
        return np.tensordot(self.weights, predictions, axes=(0, 0))


def build_weighted_ensemble_artifact(
    artifacts: list[ModelArtifact],
    *,
    weights: list[float] | None = None,
    model_version: str = "1.0.0",
) -> ModelArtifact:
    if len(artifacts) < 2:
        raise ValueError("At least two artifacts are required for an ensemble.")
    first = artifacts[0]
    for artifact in artifacts[1:]:
        if artifact.metadata.task_type != first.metadata.task_type:
            raise ValueError("All ensemble artifacts must use the same task type.")
        first.validate_feature_schema(artifact.feature_schema, artifact.feature_names)
    resolved_weights = weights or [1.0] * len(artifacts)
    estimator = WeightedEnsembleEstimator(
        [artifact.estimator for artifact in artifacts],
        resolved_weights,
        first.metadata.task_type,
    )
    member_names = [
        f"{artifact.metadata.model_name}:{artifact.metadata.model_version}"
        for artifact in artifacts
    ]
    metadata = replace(
        first.metadata,
        experiment_id="ensemble-" + first.metadata.experiment_id,
        model_version=model_version,
        model_name="weighted_ensemble",
        trained_at_utc=utc_now_iso(),
        metrics={},
        validation_metrics={},
        confidence_intervals={},
        training_config={
            **first.metadata.training_config,
            "ensemble_members": member_names,
            "ensemble_weights": list(map(float, resolved_weights)),
            "requires_external_revalidation": True,
        },
        synthetic_demo=any(artifact.metadata.synthetic_demo for artifact in artifacts),
    )
    return ModelArtifact(
        estimator=estimator,
        feature_schema=first.feature_schema,
        feature_names=first.feature_names,
        metadata=metadata,
        applicability_statistics=first.applicability_statistics,
    )
