from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from biointel.dti.dataset_validation import validate_dti_dataset
from biointel.provenance import stable_dataframe_sha256
from biointel.training.drift import compute_feature_drift
from biointel.training.evaluation import classification_metrics, regression_metrics
from biointel.training.feature_matrix import build_feature_matrix
from biointel.training.model_artifact import ModelArtifact
from biointel.training.uncertainty import (
    classification_conformal_diagnostics,
    regression_conformal_diagnostics,
)


@dataclass(frozen=True)
class ExternalValidationResult:
    task_type: str
    dataset_sha256: str
    input_rows: int
    valid_rows: int
    invalid_rows: int
    metrics: dict[str, float | None]
    conformal_diagnostics: dict[str, float]
    drift: dict[str, object]
    predictions: pd.DataFrame
    errors: pd.DataFrame
    data_quality_summary: dict[str, object]


def evaluate_external_dataset(
    artifact: ModelArtifact, dataframe: pd.DataFrame
) -> ExternalValidationResult:
    task = artifact.metadata.task_type
    report = validate_dti_dataset(dataframe, task)
    if report.valid_rows < 2:
        raise ValueError("External validation requires at least two valid unique rows.")
    target_column = "label" if task == "classification" else "p_activity"
    schema = artifact.feature_schema
    features = build_feature_matrix(
        report.cleaned,
        target_column=target_column,
        radius=schema.fingerprint_radius,
        n_bits=schema.fingerprint_bits,
        use_chirality=schema.use_chirality,
        include_dipeptides=schema.include_dipeptides,
    )
    artifact.validate_feature_schema(features.example_features.schema, features.feature_names)
    target = features.target.astype(int if task == "classification" else float)
    if task == "classification":
        probabilities = artifact.estimator.predict_proba(features.matrix)[:, 1]
        threshold = float(artifact.metadata.decision_threshold or 0.5)
        predicted = (probabilities >= threshold).astype(int)
        metrics = classification_metrics(target, predicted, probabilities)
        conformal = (
            classification_conformal_diagnostics(
                target, probabilities, artifact.metadata.uncertainty_calibration
            )
            if artifact.metadata.uncertainty_calibration.get("score_quantile") is not None
            else {}
        )
        predictions = pd.DataFrame(
            {"actual": target, "predicted": predicted, "positive_probability": probabilities}
        )
    else:
        predicted = artifact.estimator.predict(features.matrix)
        metrics = regression_metrics(target, predicted)
        conformal = (
            regression_conformal_diagnostics(
                target, predicted, artifact.metadata.uncertainty_calibration
            )
            if artifact.metadata.uncertainty_calibration.get("absolute_residual_quantile")
            is not None
            else {}
        )
        predictions = pd.DataFrame(
            {"actual": target, "predicted": predicted, "residual": target - predicted}
        )
    drift = compute_feature_drift(
        features.matrix, features.feature_names, artifact.applicability_statistics
    )
    errors = pd.concat([report.errors, features.errors], ignore_index=True).drop_duplicates()
    quality = dict(report.summary)
    quality["feature_extraction_errors"] = int(len(features.errors))
    return ExternalValidationResult(
        task_type=task,
        dataset_sha256=stable_dataframe_sha256(report.cleaned),
        input_rows=len(dataframe),
        valid_rows=len(features.valid_rows),
        invalid_rows=len(errors),
        metrics=metrics,
        conformal_diagnostics=conformal,
        drift=drift,
        predictions=predictions,
        errors=errors,
        data_quality_summary=quality,
    )
