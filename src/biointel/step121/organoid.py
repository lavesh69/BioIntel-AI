from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.optimize import curve_fit, linear_sum_assignment
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class OrganoidAnalysisResult:
    objects: pd.DataFrame
    tracks: pd.DataFrame
    plate_qc: pd.DataFrame
    normalized_measurements: pd.DataFrame
    dose_response: pd.DataFrame
    morphology_embedding: pd.DataFrame
    validation: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def segment_volume(
    volume: np.ndarray,
    *,
    threshold: float | None = None,
    min_voxels: int = 20,
) -> tuple[np.ndarray, float]:
    array = np.asarray(volume, dtype=float)
    if array.ndim != 3:
        raise ValueError("Organoid volume must be a 3D array.")
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ValueError("Organoid volume contains no finite values.")
    if threshold is None:
        threshold = float(np.median(finite) + 1.5 * np.std(finite))
    mask = np.isfinite(array) & (array >= float(threshold))
    labels, _ = ndimage.label(mask)
    if min_voxels > 1:
        counts = np.bincount(labels.ravel())
        keep = counts >= int(min_voxels)
        keep[0] = False
        labels = labels * keep[labels]
        labels, _ = ndimage.label(labels > 0)
    return labels.astype(np.int32), float(threshold)


def measure_volume_objects(
    labels: np.ndarray,
    *,
    voxel_size_um: tuple[float, float, float] = (1.0, 1.0, 1.0),
    frame_id: str = "frame_0",
    well: str = "A01",
) -> pd.DataFrame:
    label_array = np.asarray(labels)
    if label_array.ndim != 3:
        raise ValueError("Label mask must be a 3D array.")
    voxel_volume = float(np.prod(voxel_size_um))
    rows: list[dict[str, Any]] = []
    for label_id in sorted(int(value) for value in np.unique(label_array) if int(value) > 0):
        mask = label_array == label_id
        voxel_count = int(mask.sum())
        coords = np.argwhere(mask)
        if not voxel_count:
            continue
        centroid_voxel = coords.mean(axis=0)
        minima = coords.min(axis=0)
        maxima = coords.max(axis=0)
        eroded = ndimage.binary_erosion(mask)
        boundary_voxels = int((mask & ~eroded).sum())
        volume_um3 = voxel_count * voxel_volume
        equivalent_diameter_um = float((6.0 * volume_um3 / np.pi) ** (1.0 / 3.0))
        bbox_um = (maxima - minima + 1) * np.asarray(voxel_size_um)
        rows.append(
            {
                "frame_id": frame_id,
                "well": well,
                "object_id": f"{frame_id}_obj_{label_id}",
                "label_id": label_id,
                "voxel_count": voxel_count,
                "volume_um3": volume_um3,
                "equivalent_diameter_um": equivalent_diameter_um,
                "boundary_voxels": boundary_voxels,
                "centroid_z_um": float(centroid_voxel[0] * voxel_size_um[0]),
                "centroid_y_um": float(centroid_voxel[1] * voxel_size_um[1]),
                "centroid_x_um": float(centroid_voxel[2] * voxel_size_um[2]),
                "bbox_z_um": float(bbox_um[0]),
                "bbox_y_um": float(bbox_um[1]),
                "bbox_x_um": float(bbox_um[2]),
                "sphericity_proxy": float(
                    min(1.0, (np.pi ** (1 / 3) * (6 * volume_um3) ** (2 / 3)) / max(boundary_voxels * voxel_size_um[1] * voxel_size_um[2], 1e-9))
                ),
            }
        )
    return pd.DataFrame(rows)


def track_organoids(
    objects: pd.DataFrame,
    *,
    max_distance_um: float = 100.0,
) -> pd.DataFrame:
    required = {"frame_id", "object_id", "centroid_z_um", "centroid_y_um", "centroid_x_um", "volume_um3"}
    if not required.issubset(objects.columns):
        return pd.DataFrame()
    frame_order = list(dict.fromkeys(objects["frame_id"].astype(str)))
    if len(frame_order) < 2:
        return pd.DataFrame()
    tracks: list[dict[str, Any]] = []
    next_track = 1
    active: dict[str, str] = {}
    first = objects[objects["frame_id"].astype(str) == frame_order[0]]
    for row in first.itertuples(index=False):
        active[str(row.object_id)] = f"TRACK-{next_track:05d}"
        next_track += 1
    for previous_frame, current_frame in zip(frame_order[:-1], frame_order[1:]):
        previous = objects[objects["frame_id"].astype(str) == previous_frame].reset_index(drop=True)
        current = objects[objects["frame_id"].astype(str) == current_frame].reset_index(drop=True)
        if previous.empty or current.empty:
            continue
        previous_coords = previous[["centroid_z_um", "centroid_y_um", "centroid_x_um"]].to_numpy(float)
        current_coords = current[["centroid_z_um", "centroid_y_um", "centroid_x_um"]].to_numpy(float)
        distance = np.linalg.norm(previous_coords[:, None, :] - current_coords[None, :, :], axis=2)
        row_idx, col_idx = linear_sum_assignment(distance)
        assigned_current: set[int] = set()
        for prev_index, curr_index in zip(row_idx, col_idx):
            if float(distance[prev_index, curr_index]) > max_distance_um:
                continue
            previous_id = str(previous.iloc[prev_index]["object_id"])
            current_id = str(current.iloc[curr_index]["object_id"])
            track_id = active.get(previous_id, f"TRACK-{next_track:05d}")
            if previous_id not in active:
                next_track += 1
            active[current_id] = track_id
            assigned_current.add(int(curr_index))
            previous_volume = float(previous.iloc[prev_index]["volume_um3"])
            current_volume = float(current.iloc[curr_index]["volume_um3"])
            tracks.append(
                {
                    "track_id": track_id,
                    "from_frame": previous_frame,
                    "to_frame": current_frame,
                    "from_object": previous_id,
                    "to_object": current_id,
                    "distance_um": float(distance[prev_index, curr_index]),
                    "volume_fold_change": current_volume / previous_volume if previous_volume > 0 else np.nan,
                    "event": "continuation",
                }
            )
        for curr_index, row in current.iterrows():
            if curr_index in assigned_current:
                continue
            track_id = f"TRACK-{next_track:05d}"
            next_track += 1
            active[str(row["object_id"])] = track_id
            tracks.append(
                {
                    "track_id": track_id,
                    "from_frame": previous_frame,
                    "to_frame": current_frame,
                    "from_object": "",
                    "to_object": str(row["object_id"]),
                    "distance_um": np.nan,
                    "volume_fold_change": np.nan,
                    "event": "appearance_or_unmatched",
                }
            )
    return pd.DataFrame(tracks)


def median_polish_plate(
    measurements: pd.DataFrame,
    *,
    value_column: str,
    row_column: str = "plate_row",
    column_column: str = "plate_column",
    iterations: int = 10,
) -> pd.DataFrame:
    required = {value_column, row_column, column_column}
    if not required.issubset(measurements.columns):
        raise ValueError("Plate normalization requires value, plate_row and plate_column columns.")
    working = measurements.copy()
    pivot = working.pivot_table(index=row_column, columns=column_column, values=value_column, aggfunc="median")
    matrix = pivot.to_numpy(float)
    overall = float(np.nanmedian(matrix))
    residual = matrix - overall
    row_effects = np.zeros(residual.shape[0], dtype=float)
    col_effects = np.zeros(residual.shape[1], dtype=float)
    for _ in range(max(1, iterations)):
        row_median = np.nanmedian(residual, axis=1)
        row_median = np.nan_to_num(row_median)
        residual -= row_median[:, None]
        row_effects += row_median
        col_median = np.nanmedian(residual, axis=0)
        col_median = np.nan_to_num(col_median)
        residual -= col_median[None, :]
        col_effects += col_median
    row_map = dict(zip(pivot.index, row_effects))
    col_map = dict(zip(pivot.columns, col_effects))
    working["plate_row_effect"] = working[row_column].map(row_map).fillna(0.0)
    working["plate_column_effect"] = working[column_column].map(col_map).fillna(0.0)
    working["plate_normalized_value"] = (
        pd.to_numeric(working[value_column], errors="coerce")
        - working["plate_row_effect"]
        - working["plate_column_effect"]
    )
    center = float(working["plate_normalized_value"].median())
    mad = float((working["plate_normalized_value"] - center).abs().median())
    scale = 1.4826 * mad if mad > 1e-12 else float(working["plate_normalized_value"].std(ddof=1) or 1.0)
    working["robust_z"] = (working["plate_normalized_value"] - center) / max(scale, 1e-12)
    working.attrs["overall_median"] = overall
    return working


def z_prime(
    measurements: pd.DataFrame,
    *,
    value_column: str,
    control_column: str = "control_type",
) -> float:
    if control_column not in measurements.columns:
        return np.nan
    positive = pd.to_numeric(measurements.loc[measurements[control_column].astype(str).str.lower().isin({"positive", "pos"}), value_column], errors="coerce").dropna()
    negative = pd.to_numeric(measurements.loc[measurements[control_column].astype(str).str.lower().isin({"negative", "neg"}), value_column], errors="coerce").dropna()
    if len(positive) < 2 or len(negative) < 2:
        return np.nan
    denominator = abs(float(positive.mean()) - float(negative.mean()))
    if denominator <= 1e-12:
        return np.nan
    return float(1.0 - 3.0 * (positive.std(ddof=1) + negative.std(ddof=1)) / denominator)


def _four_parameter_logistic(x: np.ndarray, bottom: float, top: float, log_ic50: float, hill: float) -> np.ndarray:
    concentration = np.maximum(np.asarray(x, dtype=float), 1e-12)
    return bottom + (top - bottom) / (1.0 + 10.0 ** ((np.log10(concentration) - log_ic50) * hill))


def fit_dose_response(
    measurements: pd.DataFrame,
    *,
    concentration_column: str = "concentration",
    response_column: str = "plate_normalized_value",
    group_column: str = "compound",
) -> pd.DataFrame:
    if not {concentration_column, response_column}.issubset(measurements.columns):
        return pd.DataFrame()
    group_values = measurements[group_column] if group_column in measurements.columns else pd.Series("all", index=measurements.index)
    rows: list[dict[str, Any]] = []
    for group, indices in group_values.groupby(group_values).groups.items():
        subset = measurements.loc[indices].copy()
        x = pd.to_numeric(subset[concentration_column], errors="coerce").to_numpy(float)
        y = pd.to_numeric(subset[response_column], errors="coerce").to_numpy(float)
        usable = np.isfinite(x) & np.isfinite(y) & (x > 0)
        x, y = x[usable], y[usable]
        if len(np.unique(x)) < 4 or len(y) < 6:
            rows.append({"group": group, "status": "insufficient_dose_levels"})
            continue
        initial = [float(np.min(y)), float(np.max(y)), float(np.median(np.log10(x))), 1.0]
        try:
            params, covariance = curve_fit(_four_parameter_logistic, x, y, p0=initial, maxfev=20_000)
            predicted = _four_parameter_logistic(x, *params)
            residual = y - predicted
            r2 = 1.0 - float(np.sum(residual**2) / max(np.sum((y - np.mean(y)) ** 2), 1e-12))
            rows.append(
                {
                    "group": group,
                    "bottom": float(params[0]),
                    "top": float(params[1]),
                    "ic50": float(10 ** params[2]),
                    "hill_slope": float(params[3]),
                    "r2": r2,
                    "parameter_se_mean": float(np.mean(np.sqrt(np.clip(np.diag(covariance), 0, None)))),
                    "status": "fit_completed",
                }
            )
        except Exception as exc:
            rows.append({"group": group, "status": f"fit_failed:{type(exc).__name__}"})
    return pd.DataFrame(rows)


def morphology_embedding(
    measurements: pd.DataFrame,
    *,
    id_columns: tuple[str, ...] = ("object_id", "well", "frame_id"),
    max_components: int = 3,
) -> pd.DataFrame:
    numeric = measurements.select_dtypes(include=[np.number]).copy()
    numeric = numeric.drop(columns=[column for column in numeric.columns if column.lower().endswith("id")], errors="ignore")
    if numeric.shape[1] < 2 or len(numeric) < 3:
        return pd.DataFrame()
    numeric = numeric.fillna(numeric.median())
    scaled = StandardScaler().fit_transform(numeric)
    component_count = min(max_components, numeric.shape[1], len(numeric) - 1)
    if component_count < 1:
        return pd.DataFrame()
    pca = PCA(n_components=component_count, random_state=42)
    embedding = pca.fit_transform(scaled)
    result = measurements[[column for column in id_columns if column in measurements.columns]].reset_index(drop=True).copy()
    for index in range(component_count):
        result[f"morphology_pc{index + 1}"] = embedding[:, index]
        result[f"pc{index + 1}_variance_percent"] = float(pca.explained_variance_ratio_[index] * 100.0)
    return result


def segmentation_validation(predicted: np.ndarray | None, truth: np.ndarray | None) -> pd.DataFrame:
    if predicted is None or truth is None:
        return pd.DataFrame()
    pred = np.asarray(predicted) > 0
    ref = np.asarray(truth) > 0
    if pred.shape != ref.shape:
        raise ValueError("Predicted and ground-truth masks must have the same shape.")
    intersection = int(np.logical_and(pred, ref).sum())
    union = int(np.logical_or(pred, ref).sum())
    dice = 2.0 * intersection / max(int(pred.sum()) + int(ref.sum()), 1)
    iou = intersection / max(union, 1)
    return pd.DataFrame(
        [
            {
                "dice": float(dice),
                "iou": float(iou),
                "predicted_voxels": int(pred.sum()),
                "truth_voxels": int(ref.sum()),
                "status": "pass" if dice >= 0.80 and iou >= 0.67 else "review_required",
            }
        ]
    )


def analyse_organoid_experiment(
    measurements: pd.DataFrame,
    *,
    value_column: str = "volume_um3",
    truth_metrics: pd.DataFrame | None = None,
) -> OrganoidAnalysisResult:
    required = {"object_id", "well", value_column}
    if not required.issubset(measurements.columns):
        raise ValueError("Organoid measurements require object_id, well and the selected value column.")
    working = measurements.copy()
    if "plate_row" not in working.columns:
        working["plate_row"] = working["well"].astype(str).str.extract(r"([A-Za-z]+)", expand=False).fillna("A")
    if "plate_column" not in working.columns:
        working["plate_column"] = pd.to_numeric(working["well"].astype(str).str.extract(r"(\d+)", expand=False), errors="coerce").fillna(1).astype(int)
    normalized = median_polish_plate(working, value_column=value_column)
    plate_rows = [
        {"metric": "objects", "value": len(working)},
        {"metric": "wells", "value": int(working["well"].nunique())},
        {"metric": "median_value", "value": float(pd.to_numeric(working[value_column], errors="coerce").median())},
        {"metric": "z_prime", "value": z_prime(normalized, value_column="plate_normalized_value")},
        {"metric": "extreme_robust_z_fraction", "value": float((normalized["robust_z"].abs() > 3.5).mean())},
    ]
    plate_qc = pd.DataFrame(plate_rows)
    dose = fit_dose_response(normalized)
    embedding = morphology_embedding(normalized)
    tracks = track_organoids(normalized) if {"frame_id", "centroid_z_um", "centroid_y_um", "centroid_x_um", "volume_um3"}.issubset(normalized.columns) else pd.DataFrame()
    validation = truth_metrics.copy() if truth_metrics is not None else pd.DataFrame()
    blockers: list[str] = []
    z_value = plate_qc.loc[plate_qc["metric"] == "z_prime", "value"].iloc[0]
    if pd.notna(z_value) and float(z_value) < 0.5:
        blockers.append(f"Plate Z-prime is {float(z_value):.3f} (<0.5)")
    if validation.empty:
        blockers.append("Representative manual/ground-truth segmentation validation is not attached")
    if "replicate" not in normalized.columns and "image_id" not in normalized.columns:
        blockers.append("Biological/image replicate identifiers are not available")
    blockers.extend(
        [
            "Automated 3D phenotypes require manual mask review and biological replication",
            "Dose-response fits are exploratory until replicate and assay-quality criteria pass",
        ]
    )
    digest = pd.util.hash_pandas_object(normalized.astype("string").fillna(""), index=True).values.tobytes()
    manifest = {
        "schema": "biointel.step121.organoid_3d.v1",
        "objects": len(normalized),
        "wells": int(normalized["well"].nunique()),
        "value_column": value_column,
        "input_sha256": sha256(digest).hexdigest(),
        "ground_truth_attached": not validation.empty,
        "scientific_release_ready": False,
    }
    return OrganoidAnalysisResult(
        objects=working,
        tracks=tracks,
        plate_qc=plate_qc,
        normalized_measurements=normalized,
        dose_response=dose,
        morphology_embedding=embedding,
        validation=validation,
        release_gate={
            "analysis_ready": True,
            "scientific_release_ready": False,
            "blockers": blockers,
            "boundary": "Automated organoid segmentation, tracking and dose-response results require representative manual QC and biological replication.",
        },
        manifest=manifest,
    )
