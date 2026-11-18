from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from biointel.training.model_artifact import ModelArtifact


def _importance_vector(estimator: Any) -> np.ndarray | None:
    if hasattr(estimator, "feature_importances_"):
        return np.asarray(estimator.feature_importances_, dtype=float)
    if hasattr(estimator, "coef_"):
        coefficients = np.asarray(estimator.coef_, dtype=float)
        if coefficients.ndim == 1:
            return np.abs(coefficients)
        return np.mean(np.abs(coefficients), axis=0)
    if hasattr(estimator, "named_steps"):
        final_estimator = list(estimator.named_steps.values())[-1]
        return _importance_vector(final_estimator)
    return None


def extract_global_feature_importance(
    artifact: ModelArtifact,
    top_n: int = 30,
) -> pd.DataFrame:
    """Extract model-native global importance without claiming causality."""

    estimator = artifact.estimator
    vectors: list[np.ndarray] = []

    direct = _importance_vector(estimator)
    if direct is not None:
        vectors.append(direct)

    calibrated = getattr(estimator, "calibrated_classifiers_", None)
    if calibrated:
        for calibrated_classifier in calibrated:
            vector = _importance_vector(calibrated_classifier.estimator)
            if vector is not None:
                vectors.append(vector)

    if not vectors:
        return pd.DataFrame(columns=["feature", "importance", "rank"])

    valid = [vector for vector in vectors if len(vector) == len(artifact.feature_names)]
    if not valid:
        return pd.DataFrame(columns=["feature", "importance", "rank"])

    importance = np.mean(np.vstack(valid), axis=0)
    order = np.argsort(importance)[::-1][: max(1, min(top_n, len(importance)))]
    rows = [
        {
            "feature": artifact.feature_names[index],
            "importance": float(importance[index]),
            "rank": rank,
        }
        for rank, index in enumerate(order, start=1)
    ]
    return pd.DataFrame(rows)


def explain_prediction_features(
    artifact: ModelArtifact,
    feature_vector: np.ndarray,
    *,
    top_n: int = 20,
) -> pd.DataFrame:
    """Return model-native local contribution approximations.

    Linear models use signed coefficient × feature contributions. Tree models
    use signed deviation from the training mean weighted by global feature
    importance. These are diagnostic approximations, not causal explanations.
    """

    values = np.asarray(feature_vector, dtype=float).reshape(-1)
    if len(values) != len(artifact.feature_names):
        raise ValueError("Feature vector length does not match the model schema.")

    estimator = artifact.estimator
    final_estimator = (
        list(estimator.named_steps.values())[-1] if hasattr(estimator, "named_steps") else estimator
    )
    coefficients = getattr(final_estimator, "coef_", None)
    if coefficients is not None:
        coefficient_vector = np.asarray(coefficients, dtype=float)
        if coefficient_vector.ndim > 1:
            coefficient_vector = coefficient_vector[0]
        contributions = coefficient_vector * values
        method = "signed_linear_contribution"
    else:
        importance = _importance_vector(estimator)
        if importance is None or len(importance) != len(values):
            return pd.DataFrame(columns=["feature", "value", "contribution", "magnitude", "method"])
        statistics = artifact.applicability_statistics
        mean_lookup = dict(
            zip(
                statistics.get("feature_names", []),
                statistics.get("mean", []),
                strict=False,
            )
        )
        baseline = np.array(
            [float(mean_lookup.get(name, 0.0)) for name in artifact.feature_names],
            dtype=float,
        )
        contributions = importance * (values - baseline)
        method = "importance_weighted_deviation"

    order = np.argsort(np.abs(contributions))[::-1][: max(1, min(top_n, len(values)))]
    return pd.DataFrame(
        [
            {
                "feature": artifact.feature_names[index],
                "value": float(values[index]),
                "contribution": float(contributions[index]),
                "magnitude": float(abs(contributions[index])),
                "method": method,
            }
            for index in order
        ]
    )
