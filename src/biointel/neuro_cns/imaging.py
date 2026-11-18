from __future__ import annotations

import io
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from biointel.neuro_cns.schemas import table_quality_report


def optional_adapter_status() -> dict[str, bool]:
    status: dict[str, bool] = {}
    for module_name, label in (("nibabel", "nifti"), ("pydicom", "dicom"), ("SimpleITK", "simpleitk")):
        try:
            __import__(module_name)
            status[label] = True
        except Exception:
            status[label] = False
    return status


def load_image_payload(data: bytes, filename: str) -> dict[str, Any]:
    name = str(filename or "").lower()
    metadata: dict[str, Any] = {"filename": filename, "format": None, "voxel_spacing_mm": None, "affine": None}
    if name.endswith(".npy"):
        array = np.load(io.BytesIO(data), allow_pickle=False)
        metadata["format"] = "NPY"
    elif name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")):
        with Image.open(io.BytesIO(data)) as image:
            array = np.asarray(image.convert("F"), dtype=float)
            metadata.update({"format": image.format or "2D image", "pixel_size": list(image.size)})
    elif name.endswith(".csv"):
        array = pd.read_csv(io.BytesIO(data)).select_dtypes(include=[np.number]).to_numpy(float)
        metadata["format"] = "numeric CSV"
    elif name.endswith((".nii", ".nii.gz")):
        try:
            import nibabel as nib
        except Exception as exc:
            raise ValueError("NIfTI upload requires the optional nibabel adapter to be installed and qualified.") from exc
        suffix = ".nii.gz" if name.endswith(".nii.gz") else ".nii"
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(data)
            handle.flush()
            image = nib.load(handle.name)
            array = np.asarray(image.get_fdata(dtype=np.float32), dtype=float)
            metadata.update({"format": "NIfTI", "voxel_spacing_mm": [float(value) for value in image.header.get_zooms()[: array.ndim]], "affine": np.asarray(image.affine).round(6).tolist(), "orientation_codes": list(nib.aff2axcodes(image.affine)), "qform_code": int(image.header.get("qform_code", 0)), "sform_code": int(image.header.get("sform_code", 0))})
    elif name.endswith((".dcm", ".dicom")):
        try:
            import pydicom
        except Exception as exc:
            raise ValueError("DICOM upload requires the optional pydicom adapter to be installed and qualified.") from exc
        dataset = pydicom.dcmread(io.BytesIO(data))
        array = np.asarray(dataset.pixel_array, dtype=float)
        spacing = getattr(dataset, "PixelSpacing", None)
        thickness = getattr(dataset, "SliceThickness", None)
        metadata.update({"format": "DICOM", "voxel_spacing_mm": [float(value) for value in spacing] + ([float(thickness)] if thickness else []) if spacing else None, "modality": str(getattr(dataset, "Modality", "")), "series_instance_uid": str(getattr(dataset, "SeriesInstanceUID", "")), "instance_number": int(getattr(dataset, "InstanceNumber", 0) or 0), "image_orientation_patient": [float(value) for value in getattr(dataset, "ImageOrientationPatient", [])], "image_position_patient": [float(value) for value in getattr(dataset, "ImagePositionPatient", [])]})
    else:
        raise ValueError("Supported core formats are NPY, numeric CSV and common 2D images. NIfTI/DICOM need their optional qualified adapters.")
    if not isinstance(array, np.ndarray) or array.size == 0:
        raise ValueError("The uploaded array is empty.")
    if array.ndim not in {2, 3, 4}:
        raise ValueError("Expected a 2D image, 3D volume or 4D image/time array.")
    return {"array": np.asarray(array, dtype=float), "metadata": metadata}


def load_array_from_bytes(data: bytes, filename: str) -> np.ndarray:
    return load_image_payload(data, filename)["array"]


def _otsu_threshold(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < 2 or float(np.nanmin(finite)) == float(np.nanmax(finite)):
        return float(np.nanmean(finite))
    hist, edges = np.histogram(finite, bins=256)
    probabilities = hist.astype(float) / max(hist.sum(), 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    omega = np.cumsum(probabilities)
    mu = np.cumsum(probabilities * centers)
    mu_total = mu[-1]
    between = (mu_total * omega - mu) ** 2 / np.maximum(omega * (1.0 - omega), 1e-12)
    return float(centers[int(np.nanargmax(between))])


def profile_image_array(
    array: np.ndarray,
    threshold: float | None = None,
    voxel_volume_mm3: float = 1.0,
    *,
    threshold_method: str = "mean_plus_1.5sd",
    minimum_component_voxels: int = 1,
) -> dict[str, Any]:
    values = np.asarray(array, dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("Array contains no finite values.")
    if voxel_volume_mm3 <= 0 or not math.isfinite(float(voxel_volume_mm3)):
        raise ValueError("Voxel volume must be a finite positive value.")
    clean = np.where(finite, values, np.nan)
    observed = clean[finite]
    if threshold is None:
        method = str(threshold_method).lower()
        if method == "otsu":
            threshold = _otsu_threshold(observed)
        elif method == "percentile_95":
            threshold = float(np.nanpercentile(observed, 95))
        else:
            threshold = float(np.nanmean(observed) + 1.5 * np.nanstd(observed))
    mask = finite & (values >= float(threshold))
    labels, component_count = ndimage.label(mask)
    component_sizes = np.bincount(labels.ravel())[1:] if component_count else np.asarray([], dtype=int)
    if minimum_component_voxels > 1 and component_count:
        keep = np.where(component_sizes >= int(minimum_component_voxels))[0] + 1
        mask = np.isin(labels, keep)
        labels, component_count = ndimage.label(mask)
        component_sizes = np.bincount(labels.ravel())[1:] if component_count else np.asarray([], dtype=int)
    indices = np.argwhere(mask)
    center = indices.mean(axis=0).tolist() if len(indices) else []
    bounding_box = []
    if len(indices):
        bounding_box = [{"axis": axis, "start": int(indices[:, axis].min()), "end": int(indices[:, axis].max())} for axis in range(indices.shape[1])]
    segmented_voxels = int(mask.sum())
    p01, median, p99 = np.nanpercentile(observed, [1, 50, 99])
    return {
        "shape": list(values.shape),
        "dimensions": values.ndim,
        "finite_fraction": round(float(finite.mean()), 6),
        "minimum": round(float(np.nanmin(clean)), 6),
        "maximum": round(float(np.nanmax(clean)), 6),
        "mean": round(float(np.nanmean(clean)), 6),
        "median": round(float(median), 6),
        "percentile_01": round(float(p01), 6),
        "percentile_99": round(float(p99), 6),
        "standard_deviation": round(float(np.nanstd(clean)), 6),
        "threshold": round(float(threshold), 6),
        "threshold_method": threshold_method if threshold is not None else "manual",
        "segmented_voxels": segmented_voxels,
        "segmented_volume_mm3": round(segmented_voxels * float(voxel_volume_mm3), 6),
        "center_of_mass_index": [round(float(value), 4) for value in center],
        "bounding_box_index": bounding_box,
        "segmentation_fraction": round(segmented_voxels / values.size, 6),
        "connected_components": int(component_count),
        "largest_component_voxels": int(component_sizes.max()) if component_sizes.size else 0,
        "component_size_distribution": component_sizes.astype(int).tolist(),
        "optional_adapters": optional_adapter_status(),
        "scientific_boundary": "Generic array QC and threshold segmentation; not anatomical, radiological or clinical segmentation.",
    }


def connectivity_from_timeseries(
    frame: pd.DataFrame,
    time_column: str | None = None,
    *,
    confound_columns: tuple[str, ...] = (),
    threshold_absolute: float = 0.30,
) -> dict[str, Any]:
    data = frame.copy()
    if time_column and time_column in data.columns:
        data = data.drop(columns=[time_column])
    confounds = data[list(confound_columns)].apply(pd.to_numeric, errors="coerce") if confound_columns and all(column in data.columns for column in confound_columns) else pd.DataFrame(index=data.index)
    data = data.drop(columns=list(confound_columns), errors="ignore")
    numeric = data.select_dtypes(include=[np.number]).copy()
    if numeric.empty:
        numeric = data.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    if numeric.shape[1] < 2:
        raise ValueError("At least two numeric ROI time-series columns are required.")
    numeric = numeric.interpolate(limit_direction="both")
    if not confounds.empty:
        design = np.column_stack([np.ones(len(confounds)), confounds.interpolate(limit_direction="both").fillna(0.0).to_numpy(float)])
        residuals = {}
        for column in numeric:
            values = numeric[column].to_numpy(float)
            beta, *_ = np.linalg.lstsq(design, values, rcond=None)
            residuals[column] = values - design @ beta
        numeric = pd.DataFrame(residuals)
    corr = numeric.corr(method="pearson")
    covariance = np.cov(numeric.to_numpy(float), rowvar=False)
    regularized = covariance + np.eye(covariance.shape[0]) * max(float(np.trace(covariance)) / max(covariance.shape[0], 1) * 1e-6, 1e-9)
    precision = np.linalg.pinv(regularized)
    denominator = np.sqrt(np.outer(np.diag(precision), np.diag(precision)))
    partial = -precision / np.maximum(denominator, 1e-12)
    np.fill_diagonal(partial, 1.0)
    partial_corr = pd.DataFrame(partial, index=numeric.columns, columns=numeric.columns)
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool)).stack().reset_index()
    upper.columns = ["roi_a", "roi_b", "correlation"]
    upper["absolute_correlation"] = upper["correlation"].abs()
    upper["fisher_z"] = np.arctanh(upper["correlation"].clip(-0.999999, 0.999999))
    upper["passes_threshold"] = upper["absolute_correlation"] >= float(threshold_absolute)
    strongest = upper.sort_values("absolute_correlation", ascending=False, ignore_index=True).head(50)
    mean_abs = float(upper["absolute_correlation"].mean()) if not upper.empty else 0.0
    degree = (corr.abs() >= float(threshold_absolute)).sum(axis=1) - 1
    node_metrics = pd.DataFrame({"roi": corr.columns, "threshold_degree": degree.to_numpy(int), "mean_absolute_connectivity": (corr.abs().sum(axis=1) - 1) / max(len(corr) - 1, 1)})
    quality = table_quality_report(frame)
    network_summary = connectivity_network_summary(corr, threshold_absolute=threshold_absolute)
    return {
        "connectivity_matrix": corr,
        "partial_connectivity_matrix": partial_corr,
        "strongest_connections": strongest,
        "node_metrics": node_metrics.sort_values("threshold_degree", ascending=False, ignore_index=True),
        "network_summary": network_summary,
        "roi_count": numeric.shape[1],
        "timepoints": numeric.shape[0],
        "mean_absolute_connectivity": round(mean_abs, 6),
        "confounds_regressed": list(confound_columns) if not confounds.empty else [],
        "edge_threshold_absolute": threshold_absolute,
        "input_fingerprint_sha256": quality.fingerprint_sha256,
        "scientific_boundary": "Exploratory correlation/partial-correlation connectivity; imaging use still requires motion, acquisition and atlas qualification.",
    }


def load_dicom_series(payloads: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Load a single DICOM series with ordering and mixed-series protection."""
    if not payloads:
        raise ValueError("No DICOM files were supplied.")
    try:
        import pydicom
    except Exception as exc:
        raise ValueError("DICOM series upload requires the optional pydicom adapter to be installed and qualified.") from exc
    records: list[tuple[float, int, np.ndarray, Any, str]] = []
    series_uids: set[str] = set()
    for filename, data in payloads:
        dataset = pydicom.dcmread(io.BytesIO(data))
        uid = str(getattr(dataset, "SeriesInstanceUID", "unspecified"))
        series_uids.add(uid)
        position = getattr(dataset, "ImagePositionPatient", None)
        z_position = float(position[2]) if position is not None and len(position) >= 3 else float(getattr(dataset, "SliceLocation", 0.0) or 0.0)
        instance = int(getattr(dataset, "InstanceNumber", 0) or 0)
        records.append((z_position, instance, np.asarray(dataset.pixel_array, dtype=float), dataset, filename))
    if len(series_uids) > 1:
        raise ValueError(f"Multiple DICOM SeriesInstanceUID values were supplied ({len(series_uids)}). Select one series per run.")
    shapes = {record[2].shape for record in records}
    if len(shapes) != 1:
        raise ValueError("DICOM slices have inconsistent pixel dimensions.")
    records.sort(key=lambda item: (item[0], item[1], item[4]))
    volume = np.stack([record[2] for record in records], axis=-1)
    first = records[0][3]
    spacing = getattr(first, "PixelSpacing", None)
    z_positions = [record[0] for record in records]
    inferred_thickness = float(np.median(np.diff(sorted(set(z_positions))))) if len(set(z_positions)) >= 2 else float(getattr(first, "SliceThickness", 1.0) or 1.0)
    voxel_spacing = [float(value) for value in spacing] + [abs(inferred_thickness)] if spacing else [1.0, 1.0, abs(inferred_thickness)]
    return {
        "array": volume,
        "metadata": {
            "format": "DICOM series",
            "series_instance_uid": next(iter(series_uids)),
            "slice_count": len(records),
            "voxel_spacing_mm": voxel_spacing,
            "modality": str(getattr(first, "Modality", "")),
            "ordering": "ImagePositionPatient/InstanceNumber",
            "filenames": [record[4] for record in records],
        },
    }


def volume_qc_workflow(
    array: np.ndarray,
    *,
    metadata: dict[str, Any] | None = None,
    threshold: float | None = None,
    threshold_method: str = "otsu",
    minimum_component_voxels: int = 1,
    atlas_labels: np.ndarray | None = None,
    atlas_lookup: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Run orientation/spacing QC, generic segmentation and optional atlas summaries."""
    values = np.asarray(array, dtype=float)
    if values.ndim not in {2, 3, 4}:
        raise ValueError("Expected a 2D, 3D or 4D imaging array.")
    meta = dict(metadata or {})
    spatial = values[..., 0] if values.ndim == 4 else values
    spacing = meta.get("voxel_spacing_mm")
    spatial_spacing = [float(value) for value in spacing[: spatial.ndim]] if isinstance(spacing, (list, tuple)) and spacing else [1.0] * spatial.ndim
    voxel_volume = float(np.prod(spatial_spacing))
    profile = profile_image_array(
        spatial,
        threshold=threshold,
        voxel_volume_mm3=voxel_volume,
        threshold_method=threshold_method,
        minimum_component_voxels=minimum_component_voxels,
    )
    finite_spacing = [value for value in spatial_spacing if math.isfinite(value) and value > 0]
    anisotropy = max(finite_spacing) / min(finite_spacing) if finite_spacing else None
    affine = np.asarray(meta.get("affine"), dtype=float) if meta.get("affine") is not None else None
    affine_determinant = float(np.linalg.det(affine[:3, :3])) if affine is not None and affine.shape == (4, 4) else None
    orientation_codes = meta.get("orientation_codes") or []
    orientation_warnings: list[str] = []
    if not orientation_codes and str(meta.get("format", "")).lower() == "nifti":
        orientation_warnings.append("NIfTI orientation codes were unavailable.")
    if anisotropy is not None and anisotropy > 3.0:
        orientation_warnings.append("Voxel spacing is strongly anisotropic; resampling may be needed before spatial analysis.")
    if affine_determinant is not None and abs(affine_determinant) < 1e-9:
        orientation_warnings.append("Affine transform is singular or near-singular.")

    center_indices = [int(size // 2) for size in spatial.shape]
    slices: dict[str, list[list[float]]] = {}
    if spatial.ndim == 2:
        slices["plane"] = np.nan_to_num(spatial).tolist()
    elif spatial.ndim >= 3:
        slices = {
            "axis_0": np.nan_to_num(np.take(spatial, center_indices[0], axis=0)).tolist(),
            "axis_1": np.nan_to_num(np.take(spatial, center_indices[1], axis=1)).tolist(),
            "axis_2": np.nan_to_num(np.take(spatial, center_indices[2], axis=2)).tolist(),
        }

    atlas_summary = pd.DataFrame()
    if atlas_labels is not None:
        labels = np.asarray(atlas_labels)
        if labels.shape != spatial.shape:
            raise ValueError("Atlas label array must have the same spatial shape as the image array.")
        rows: list[dict[str, Any]] = []
        for raw_label in np.unique(labels):
            try:
                label = int(raw_label)
            except (TypeError, ValueError):
                continue
            if label == 0:
                continue
            mask = labels == raw_label
            observed = spatial[mask]
            finite = observed[np.isfinite(observed)]
            rows.append({
                "label": label,
                "region": (atlas_lookup or {}).get(label, f"label_{label}"),
                "voxel_count": int(mask.sum()),
                "volume_mm3": round(float(mask.sum() * voxel_volume), 6),
                "mean_intensity": round(float(finite.mean()), 6) if finite.size else None,
                "median_intensity": round(float(np.median(finite)), 6) if finite.size else None,
            })
        atlas_summary = pd.DataFrame(rows).sort_values("voxel_count", ascending=False, ignore_index=True) if rows else pd.DataFrame()

    motion_summary = pd.DataFrame()
    if values.ndim == 4:
        volume_means = np.nanmean(values, axis=tuple(range(values.ndim - 1)))
        framewise_difference = np.zeros(len(volume_means), dtype=float)
        if values.shape[-1] >= 2:
            diffs = np.nanmean(np.abs(np.diff(values, axis=-1)), axis=tuple(range(values.ndim - 1)))
            framewise_difference[1:] = diffs
        motion_summary = pd.DataFrame({
            "frame": np.arange(values.shape[-1]),
            "global_mean_signal": volume_means,
            "mean_absolute_frame_difference": framewise_difference,
        })

    return {
        "profile": profile,
        "source_metadata": meta,
        "orientation_qc": {
            "orientation_codes": list(orientation_codes),
            "voxel_spacing_mm": spatial_spacing,
            "anisotropy_ratio": round(float(anisotropy), 6) if anisotropy is not None else None,
            "affine_determinant": round(float(affine_determinant), 6) if affine_determinant is not None else None,
            "warnings": orientation_warnings,
        },
        "orthogonal_slices": slices,
        "slice_indices": center_indices,
        "atlas_summary": atlas_summary,
        "motion_qc": motion_summary,
        "scientific_boundary": "Generic imaging QC, threshold segmentation and optional label summaries; no anatomical registration, radiological diagnosis or clinical segmentation is claimed.",
    }


def connectivity_network_summary(connectivity: pd.DataFrame, *, threshold_absolute: float = 0.30) -> dict[str, Any]:
    if connectivity.empty or connectivity.shape[0] != connectivity.shape[1]:
        raise ValueError("A square connectivity matrix is required.")
    matrix = connectivity.to_numpy(float)
    np.fill_diagonal(matrix, 0.0)
    adjacency = np.abs(matrix) >= float(threshold_absolute)
    np.fill_diagonal(adjacency, False)
    node_count = len(matrix)
    edge_count = int(np.triu(adjacency, k=1).sum())
    possible_edges = max(1, node_count * (node_count - 1) // 2)
    degree = adjacency.sum(axis=1)
    clustering_values: list[float] = []
    for index in range(node_count):
        neighbours = np.flatnonzero(adjacency[index])
        if len(neighbours) < 2:
            clustering_values.append(0.0)
            continue
        local_edges = int(np.triu(adjacency[np.ix_(neighbours, neighbours)], k=1).sum())
        clustering_values.append(2.0 * local_edges / (len(neighbours) * (len(neighbours) - 1)))
    # Connected components over graph nodes.
    visited: set[int] = set()
    component_sizes: list[int] = []
    for start in range(node_count):
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            for neighbour in np.flatnonzero(adjacency[current]):
                neighbour = int(neighbour)
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)
        component_sizes.append(size)
    nodes = pd.DataFrame({
        "roi": connectivity.index.astype(str),
        "degree": degree.astype(int),
        "strength": np.abs(matrix).sum(axis=1),
        "clustering_coefficient": clustering_values,
    }).sort_values(["degree", "strength"], ascending=[False, False], ignore_index=True)
    return {
        "nodes": nodes,
        "node_count": node_count,
        "edge_count": edge_count,
        "network_density": round(edge_count / possible_edges, 6),
        "connected_components": len(component_sizes),
        "largest_component_nodes": max(component_sizes) if component_sizes else 0,
        "mean_clustering_coefficient": round(float(np.mean(clustering_values)), 6) if clustering_values else 0.0,
        "threshold_absolute": float(threshold_absolute),
    }


def validate_bids_dataset(root_path: str | Path) -> dict[str, Any]:
    """Validate Brain Imaging Data Structure (BIDS) folder layout."""
    root = Path(root_path)
    if not root.is_dir():
        return {"valid": False, "error": f"Path '{root}' is not a directory."}
    dataset_description = root / "dataset_description.json"
    subjects = [d.name for d in root.glob("sub-*") if d.is_dir()]
    return {
        "valid": dataset_description.is_file(),
        "has_description": dataset_description.is_file(),
        "subject_count": len(subjects),
        "subjects": subjects[:20],
        "root_path": str(root),
    }


def skull_stripping_adapter(volume: np.ndarray) -> dict[str, Any]:
    """Perform threshold-based brain extraction/skull stripping fallback."""
    if volume.ndim < 2:
        return {"masked_volume": volume, "brain_volume_voxels": 0}
    threshold = np.mean(volume) + 0.5 * np.std(volume)
    mask = volume > threshold
    masked = np.where(mask, volume, 0.0)
    return {
        "masked_volume": masked,
        "brain_volume_voxels": int(mask.sum()),
        "threshold": float(threshold),
    }

