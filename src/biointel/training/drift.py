from __future__ import annotations

import numpy as np


def _nearest_tanimoto(current: np.ndarray, reference: np.ndarray) -> np.ndarray:
    if current.size == 0 or reference.size == 0:
        return np.array([], dtype=float)
    current_b = current.astype(bool)
    ref_b = reference.astype(bool)
    output = []
    for row in current_b:
        intersections = np.logical_and(ref_b, row).sum(axis=1)
        unions = np.logical_or(ref_b, row).sum(axis=1)
        sims = np.divide(
            intersections, unions, out=np.zeros_like(intersections, dtype=float), where=unions > 0
        )
        output.append(float(sims.max()) if len(sims) else 0.0)
    return np.asarray(output)


def compute_feature_drift(matrix: np.ndarray, names: tuple[str, ...], reference: dict[str, object]):
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(names):
        raise ValueError("External feature matrix shape does not match feature names.")
    fp_mask = np.array([name.startswith("morgan_bit_") for name in names], dtype=bool)
    lookup = {name: index for index, name in enumerate(names)}
    ref_names = list(reference.get("feature_names", []))
    minimum = np.asarray(reference.get("minimum", []), dtype=float)
    maximum = np.asarray(reference.get("maximum", []), dtype=float)
    mean = np.asarray(reference.get("mean", []), dtype=float)
    std = np.asarray(reference.get("std", []), dtype=float)
    if not ref_names or len(ref_names) != len(minimum):
        return {
            "status": "Unknown",
            "reason": "Training statistics unavailable.",
            "external_rows": len(values),
        }
    selected = values[:, [lookup[name] for name in ref_names]]
    outside = (selected < minimum) | (selected > maximum)
    safe_std = np.where(std > 1e-12, std, 1.0)
    row_z = np.mean(np.abs((selected - mean) / safe_std), axis=1)
    external_mean = selected.mean(axis=0)
    mean_shift = np.abs((external_mean - mean) / safe_std)
    train_fp = np.asarray(reference.get("training_fingerprints", []), dtype=np.uint8)
    nearest = _nearest_tanimoto(values[:, fp_mask], train_fp)
    outside_mean = float(outside.mean())
    z_mean = float(row_z.mean())
    low_sim_fraction = float(np.mean(nearest < 0.35)) if len(nearest) else None
    if (
        outside_mean > 0.25
        or z_mean > 5.0
        or (low_sim_fraction is not None and low_sim_fraction > 0.5)
    ):
        status = "High drift"
    elif (
        outside_mean > 0.10
        or z_mean > 3.0
        or (low_sim_fraction is not None and low_sim_fraction > 0.2)
    ):
        status = "Moderate drift"
    else:
        status = "Low detected drift"
    top = np.argsort(mean_shift)[::-1][:20]
    return {
        "status": status,
        "external_rows": int(len(values)),
        "mean_outside_training_range_fraction": outside_mean,
        "mean_absolute_standardized_distance": z_mean,
        "mean_nearest_training_drug_similarity": float(nearest.mean()) if len(nearest) else None,
        "median_nearest_training_drug_similarity": (
            float(np.median(nearest)) if len(nearest) else None
        ),
        "low_similarity_fraction_below_0_35": low_sim_fraction,
        "top_shifted_features": [
            {
                "feature": ref_names[i],
                "standardized_mean_shift": float(mean_shift[i]),
                "training_mean": float(mean[i]),
                "external_mean": float(external_mean[i]),
            }
            for i in top
        ],
    }
