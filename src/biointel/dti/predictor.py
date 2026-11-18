from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import pandas as pd

from biointel.dti.feature_combiner import combine_dti_features
from biointel.dti.inference_matrix import build_inference_matrix
from biointel.training.model_artifact import ModelArtifact
from biointel.training.uncertainty import (
    classification_prediction_set,
    regression_prediction_interval,
)

_ESTIMATOR_PREDICTION_LOCK = RLock()


def _predict_estimator(estimator: Any, method: str, values: np.ndarray) -> Any:
    """Run inference with a single estimator worker on restricted Windows hosts."""

    with _ESTIMATOR_PREDICTION_LOCK:
        original_n_jobs = getattr(estimator, "n_jobs", None)
        changed_n_jobs = False
        if original_n_jobs not in (None, 1):
            try:
                estimator.n_jobs = 1
                changed_n_jobs = True
            except (AttributeError, TypeError):
                pass
        try:
            return getattr(estimator, method)(values)
        finally:
            if changed_n_jobs:
                estimator.n_jobs = original_n_jobs


@dataclass(frozen=True)
class DtiPrediction:
    task_type: str
    predicted_class: int | None
    positive_probability: float | None
    predicted_p_activity: float | None
    decision_threshold: float | None
    confidence: str
    applicability_status: str
    applicability_details: str
    nearest_training_drug_similarity: float | None
    canonical_smiles: str
    protein_length: int
    model_name: str
    model_version: str
    prediction_timestamp_utc: str
    synthetic_demo_model: bool
    conformal_alpha: float | None
    prediction_set: tuple[int, ...] | None
    prediction_interval_lower: float | None
    prediction_interval_upper: float | None


def _confidence_label(probability: float, threshold: float) -> str:
    distance = abs(probability - threshold)
    if distance < 0.10:
        return "Uncertain — probability is close to the " "decision threshold"

    strength = "High" if distance >= 0.30 else "Moderate"
    class_name = "positive" if probability >= threshold else "negative"
    return f"{strength} model confidence in {class_name} class"


def _tanimoto_to_training(
    current: np.ndarray,
    training: np.ndarray,
) -> float | None:
    if training.size == 0 or current.size == 0:
        return None
    if training.ndim != 2 or current.ndim != 1 or training.shape[1] != current.shape[0]:
        return None

    current_bool = current.astype(bool)
    training_bool = training.astype(bool)
    intersections = np.logical_and(training_bool, current_bool).sum(axis=1)
    unions = np.logical_or(training_bool, current_bool).sum(axis=1)
    similarities = np.divide(
        intersections,
        unions,
        out=np.zeros_like(intersections, dtype=float),
        where=unions > 0,
    )
    return float(similarities.max()) if len(similarities) else None




def _validated_threshold(value: float | None) -> float:
    threshold = 0.5 if value is None else float(value)
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("Model decision threshold must be finite and between 0 and 1.")
    return threshold


def _validated_probability_output(raw: object) -> float:
    values = np.asarray(raw, dtype=float)
    if values.ndim != 2 or values.shape[0] != 1 or values.shape[1] < 2:
        raise ValueError("Classifier predict_proba output must contain two class probabilities.")
    probability = float(values[0, 1])
    if not np.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("Classifier returned an invalid positive-class probability.")
    return probability


def _validated_regression_output(raw: object) -> float:
    values = np.asarray(raw, dtype=float).reshape(-1)
    if values.size != 1 or not np.isfinite(values[0]):
        raise ValueError("Regressor returned a non-finite or malformed prediction.")
    return float(values[0])


def _validated_interval(lower: float | None, upper: float | None) -> tuple[float | None, float | None]:
    if lower is None or upper is None:
        return None, None
    low, high = float(lower), float(upper)
    if not np.isfinite(low) or not np.isfinite(high) or low > high:
        raise ValueError("Prediction interval is non-finite or reversed.")
    return low, high

def _applicability_check(
    values: np.ndarray,
    names: tuple[str, ...],
    statistics: dict[str, object],
) -> tuple[str, str, float | None]:
    selected_lookup = {
        name: float(value)
        for name, value in zip(names, values, strict=True)
        if not name.startswith("morgan_bit_")
    }
    reference_names = list(statistics.get("feature_names", []))
    minimum = np.asarray(statistics.get("minimum", []), dtype=float)
    maximum = np.asarray(statistics.get("maximum", []), dtype=float)
    mean = np.asarray(statistics.get("mean", []), dtype=float)
    std = np.asarray(statistics.get("std", []), dtype=float)

    fingerprint_mask = np.array(
        [name.startswith("morgan_bit_") for name in names],
        dtype=bool,
    )
    training_fingerprints = np.asarray(
        statistics.get("training_fingerprints", []),
        dtype=np.uint8,
    )
    similarity = _tanimoto_to_training(
        values[fingerprint_mask],
        training_fingerprints,
    )

    lengths = {len(reference_names), len(minimum), len(maximum), len(mean), len(std)}
    missing_names = [name for name in reference_names if name not in selected_lookup]
    if (
        not reference_names
        or len(lengths) != 1
        or missing_names
        or not all(np.all(np.isfinite(array)) for array in (minimum, maximum, mean, std))
    ):
        detail = "Training-distribution statistics are unavailable or incompatible."
        if missing_names:
            detail += " Missing monitored features: " + ", ".join(missing_names[:6]) + "."
        return "Unknown", detail, similarity

    current = np.array([selected_lookup[name] for name in reference_names], dtype=float)
    if not np.all(np.isfinite(current)):
        return "Unknown", "Input features contain non-finite monitored values.", similarity
    outside = (current < minimum) | (current > maximum)
    outside_fraction = float(outside.mean())
    safe_std = np.where(std > 1e-12, std, 1.0)
    mean_abs_z = float(np.mean(np.abs((current - mean) / safe_std)))

    if (
        outside_fraction > 0.25
        or mean_abs_z > 5.0
        or (similarity is not None and similarity < 0.20)
    ):
        status = "Outside training distribution"
    elif (
        outside_fraction > 0.10
        or mean_abs_z > 3.0
        or (similarity is not None and similarity < 0.35)
    ):
        status = "Caution"
    else:
        status = "Within basic training range"

    details = (
        f"{outside_fraction:.1%} of monitored non-fingerprint "
        "features are outside training ranges; "
        f"mean absolute standardized distance is {mean_abs_z:.2f}."
    )
    if similarity is not None:
        details += " Nearest sampled training-drug Tanimoto " f"similarity: {similarity:.2f}."

    return status, details, similarity


def predict_dti_pair(
    artifact: ModelArtifact,
    smiles: str,
    protein_sequence: str,
) -> DtiPrediction:
    """Generate a schema-checked, model-backed DTI prediction."""

    schema = artifact.feature_schema
    combined = combine_dti_features(
        smiles=smiles,
        protein_sequence=protein_sequence,
        radius=schema.fingerprint_radius,
        n_bits=schema.fingerprint_bits,
        use_chirality=schema.use_chirality,
        include_dipeptides=schema.include_dipeptides,
    )
    artifact.validate_feature_schema(combined.schema, combined.names)

    (
        applicability_status,
        applicability_details,
        similarity,
    ) = _applicability_check(
        combined.values,
        combined.names,
        artifact.applicability_statistics,
    )

    vector = combined.values.reshape(1, -1)
    metadata = artifact.metadata

    if metadata.task_type == "classification":
        probability = _validated_probability_output(
            _predict_estimator(artifact.estimator, "predict_proba", vector)
        )
        threshold = _validated_threshold(metadata.decision_threshold)
        predicted_class = int(probability >= threshold)
        predicted_p_activity = None
        confidence = _confidence_label(probability, threshold)
        calibration = metadata.uncertainty_calibration
        prediction_set = (
            tuple(classification_prediction_set(probability, calibration))
            if "score_quantile" in calibration
            else None
        )
        conformal_alpha = (
            float(calibration.get("alpha", 0.1)) if prediction_set is not None else None
        )
        interval_lower = interval_upper = None
    else:
        predicted_p_activity = _validated_regression_output(
            _predict_estimator(artifact.estimator, "predict", vector)
        )
        probability = None
        threshold = None
        predicted_class = None
        confidence = (
            "Regression estimate — interpret with held-out "
            "error metrics and the applicability warning"
        )
        calibration = metadata.uncertainty_calibration
        if "absolute_residual_quantile" in calibration:
            interval_lower, interval_upper = _validated_interval(
                *regression_prediction_interval(predicted_p_activity, calibration)
            )
            conformal_alpha = float(calibration.get("alpha", 0.1))
        else:
            interval_lower = interval_upper = conformal_alpha = None
        prediction_set = None

    return DtiPrediction(
        task_type=metadata.task_type,
        predicted_class=predicted_class,
        positive_probability=probability,
        predicted_p_activity=predicted_p_activity,
        decision_threshold=threshold,
        confidence=confidence,
        applicability_status=applicability_status,
        applicability_details=applicability_details,
        nearest_training_drug_similarity=similarity,
        canonical_smiles=combined.drug.canonical_smiles,
        protein_length=combined.protein.sequence_length,
        model_name=metadata.model_name,
        model_version=metadata.model_version,
        prediction_timestamp_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        synthetic_demo_model=metadata.synthetic_demo,
        conformal_alpha=conformal_alpha,
        prediction_set=prediction_set,
        prediction_interval_lower=interval_lower,
        prediction_interval_upper=interval_upper,
    )


def _empty_batch_row(
    sample_id: object,
    canonical_smiles: object,
    error: str,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "canonical_smiles": canonical_smiles,
        "prediction": None,
        "positive_probability": None,
        "decision_threshold": None,
        "confidence": "",
        "applicability_status": "",
        "nearest_training_drug_similarity": None,
        "conformal_alpha": None,
        "prediction_set": "",
        "prediction_interval_lower": None,
        "prediction_interval_upper": None,
        "error": error,
    }


def batch_predict_dti(
    artifact: ModelArtifact,
    dataframe: pd.DataFrame,
    max_rows: int = 1000,
    *,
    n_jobs: int | None = 0,
    feature_cache_path: str | Path | None = None,
) -> pd.DataFrame:
    """Run vectorized inference while isolating invalid rows.

    Unique molecular and protein entities are extracted only once. Feature
    extraction can use multiple local threads and an optional persistent
    SQLite cache. The estimator receives one matrix call per batch rather
    than one call per row.
    """

    required = {"canonical_smiles", "protein_sequence"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    if len(dataframe) > max_rows:
        raise ValueError(f"Batch contains {len(dataframe)} rows; maximum is {max_rows}.")
    if dataframe.empty:
        return pd.DataFrame(columns=list(_empty_batch_row("", "", "").keys()))

    source = dataframe.copy().reset_index(drop=True)
    if "sample_id" not in source.columns:
        source["sample_id"] = np.arange(1, len(source) + 1)

    schema = artifact.feature_schema
    prepared = build_inference_matrix(
        source,
        radius=schema.fingerprint_radius,
        n_bits=schema.fingerprint_bits,
        use_chirality=schema.use_chirality,
        include_dipeptides=schema.include_dipeptides,
        n_jobs=n_jobs,
        cache_path=feature_cache_path,
    )

    output_by_position: dict[int, dict[str, object]] = {}
    for _, row in prepared.errors.iterrows():
        position = int(row["_source_position"])
        output_by_position[position] = _empty_batch_row(
            row.get("sample_id", source.iloc[position]["sample_id"]),
            row.get("canonical_smiles", source.iloc[position]["canonical_smiles"]),
            str(row.get("error", "Feature extraction failed.")),
        )

    if len(prepared.valid_rows):
        artifact.validate_feature_schema(prepared.schema, prepared.feature_names)
        matrix = prepared.matrix
        metadata = artifact.metadata
        if metadata.task_type == "classification":
            raw_probabilities = np.asarray(
                _predict_estimator(artifact.estimator, "predict_proba", matrix),
                dtype=float,
            )
            if raw_probabilities.ndim != 2 or raw_probabilities.shape != (len(matrix), 2):
                raise ValueError("Classifier predict_proba output shape does not match the batch.")
            probabilities = raw_probabilities[:, 1]
            if not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0) | (probabilities > 1)):
                raise ValueError("Classifier returned invalid batch probabilities.")
            predictions = np.zeros(len(matrix), dtype=float)
            threshold = _validated_threshold(metadata.decision_threshold)
            predictions[:] = probabilities >= threshold
        else:
            predictions = np.asarray(
                _predict_estimator(artifact.estimator, "predict", matrix),
                dtype=float,
            ).reshape(-1)
            if predictions.shape != (len(matrix),) or not np.all(np.isfinite(predictions)):
                raise ValueError("Regressor returned invalid batch predictions.")
            probabilities = np.full(len(matrix), np.nan, dtype=float)
            threshold = None

        for valid_index, (_, row) in enumerate(prepared.valid_rows.iterrows()):
            position = int(row["_source_position"])
            try:
                applicability_status, _, similarity = _applicability_check(
                    matrix[valid_index],
                    prepared.feature_names,
                    artifact.applicability_statistics,
                )
                if metadata.task_type == "classification":
                    probability = float(probabilities[valid_index])
                    confidence = _confidence_label(probability, float(threshold))
                    calibration = metadata.uncertainty_calibration
                    prediction_set = (
                        tuple(classification_prediction_set(probability, calibration))
                        if "score_quantile" in calibration
                        else None
                    )
                    conformal_alpha = (
                        float(calibration.get("alpha", 0.1)) if prediction_set is not None else None
                    )
                    interval_lower = interval_upper = None
                    prediction_value: int | float = int(predictions[valid_index])
                else:
                    prediction_value = float(predictions[valid_index])
                    confidence = (
                        "Regression estimate — interpret with held-out error metrics "
                        "and the applicability warning"
                    )
                    calibration = metadata.uncertainty_calibration
                    if "absolute_residual_quantile" in calibration:
                        interval_lower, interval_upper = _validated_interval(
                            *regression_prediction_interval(prediction_value, calibration)
                        )
                        conformal_alpha = float(calibration.get("alpha", 0.1))
                    else:
                        interval_lower = interval_upper = conformal_alpha = None
                    prediction_set = None
                    probability = None

                output_by_position[position] = {
                    "sample_id": row.get("sample_id", position + 1),
                    "canonical_smiles": prepared.canonical_smiles[valid_index],
                    "prediction": prediction_value,
                    "positive_probability": probability,
                    "decision_threshold": threshold,
                    "confidence": confidence,
                    "applicability_status": applicability_status,
                    "nearest_training_drug_similarity": similarity,
                    "conformal_alpha": conformal_alpha,
                    "prediction_set": (
                        ",".join(map(str, prediction_set)) if prediction_set is not None else ""
                    ),
                    "prediction_interval_lower": interval_lower,
                    "prediction_interval_upper": interval_upper,
                    "error": "",
                }
            except Exception as exc:
                output_by_position[position] = _empty_batch_row(
                    row.get("sample_id", position + 1),
                    row.get("canonical_smiles", ""),
                    str(exc),
                )

    outputs = [
        output_by_position.get(
            position,
            _empty_batch_row(
                source.iloc[position]["sample_id"],
                source.iloc[position]["canonical_smiles"],
                "Prediction result was not produced.",
            ),
        )
        for position in range(len(source))
    ]
    return pd.DataFrame(outputs)
