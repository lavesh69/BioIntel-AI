from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import calibration_curve
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from .assessment import bh_fdr
from .native_workflows import _check, _column, _metric, _numeric, _robust_z

def _flow(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    event_id = _column(frame, "event_id", "event", "id")
    time_col = _column(frame, "time", "acquisition_time")
    channels = _numeric(frame, exclude=[c for c in (event_id, time_col) if c])
    _check(checks, "Numeric channel coverage", "pass" if len(channels) >= 2 else "fail", f"{len(channels)} numeric channels")
    channel_rows: list[dict[str, Any]] = []
    for channel in channels[:64]:
        values = pd.to_numeric(frame[channel], errors="coerce")
        low, high = values.quantile([0.001, 0.999]).tolist() if values.notna().any() else (np.nan, np.nan)
        span = high - low if np.isfinite(high) and np.isfinite(low) else np.nan
        at_low = float((values <= low).mean()) if np.isfinite(low) else np.nan
        at_high = float((values >= high).mean()) if np.isfinite(high) else np.nan
        channel_rows.append(
            {
                "channel": channel,
                "events": int(values.notna().sum()),
                "median": float(values.median()),
                "robust_spread": float((values - values.median()).abs().median()),
                "low_tail_fraction": at_low,
                "high_tail_fraction": at_high,
                "dynamic_range_99_8pct": float(span) if np.isfinite(span) else np.nan,
            }
        )
    channel_qc = pd.DataFrame(channel_rows)
    saturation = int(((channel_qc.get("low_tail_fraction", 0) > 0.02) | (channel_qc.get("high_tail_fraction", 0) > 0.02)).sum()) if not channel_qc.empty else 0
    _check(checks, "Channel saturation/tail audit", "review" if saturation else "pass", f"{saturation} channels need review")
    _metric(metrics, "channels_analyzed", len(channel_qc), "channels")
    _metric(metrics, "events", len(frame), "events")
    drift_rows: list[dict[str, Any]] = []
    if time_col and channels:
        time_values = pd.to_numeric(frame[time_col], errors="coerce")
        for channel in channels[:20]:
            signal = pd.to_numeric(frame[channel], errors="coerce")
            valid = time_values.notna() & signal.notna()
            if valid.sum() >= 20:
                rho, p_value = stats.spearmanr(time_values[valid], signal[valid])
                drift_rows.append({"channel": channel, "spearman_rho": float(rho), "p_value": float(p_value), "drift_flag": bool(abs(rho) >= 0.20 and p_value < 0.01)})
        drift_count = sum(bool(row["drift_flag"]) for row in drift_rows)
        _check(checks, "Acquisition-time drift", "review" if drift_count else "pass", f"{drift_count} channels with |rho|≥0.20 and p<0.01")
    else:
        _check(checks, "Acquisition-time drift", "review", "Time column not detected")
    duplicate_events = int(frame.astype(str).duplicated().sum())
    _check(checks, "Duplicate event audit", "review" if duplicate_events else "pass", f"{duplicate_events} duplicate events")
    transformed = pd.DataFrame()
    compensated = pd.DataFrame()
    control_audit = pd.DataFrame()
    if channels:
        cofactor = float(metadata.get("arcsinh_cofactor", 150.0) or 150.0)
        transformed = pd.DataFrame({f"asinh_{c}": np.arcsinh(pd.to_numeric(frame[c], errors="coerce") / cofactor) for c in channels[:20]})
        transformed.insert(0, "row_index", frame.index[: len(transformed)].astype(str))
        _metric(metrics, "arcsinh_cofactor", cofactor, "instrument units")
        compensation = metadata.get("compensation_matrix")
        if compensation is not None:
            try:
                from biointel.biotech.flow_cytometry import apply_compensation
                matrix = compensation if isinstance(compensation, pd.DataFrame) else pd.DataFrame(compensation)
                compensated, comp_summary = apply_compensation(frame, channels, matrix)
                _check(checks, "Compensation matrix", "pass", f"condition_number={comp_summary.get('condition_number')}")
                _metric(metrics, "compensation_condition_number", comp_summary.get("condition_number"), "condition number")
            except Exception as exc:
                _check(checks, "Compensation matrix", "fail", f"{type(exc).__name__}: {exc}")
        else:
            _check(checks, "Compensation matrix", "review", "No explicit matrix supplied; raw signals were not treated as compensated")
        controls = metadata.get("control_manifest")
        if controls is not None:
            try:
                from biointel.biotech.flow_cytometry import validate_control_manifest
                manifest = controls if isinstance(controls, pd.DataFrame) else pd.DataFrame(controls)
                fluorescence = metadata.get("fluorescence_channels") or [c for c in channels if not str(c).upper().startswith(("FSC", "SSC"))]
                audit = validate_control_manifest(
                    manifest,
                    fluorescence,
                    require_fmo_channels=metadata.get("required_fmo_channels", ()),
                    minimum_events=max(20, int(metadata.get("minimum_control_events", 500))),
                )
                control_audit = audit.checks.copy()
                for row in audit.checks.to_dict(orient="records"):
                    source_status = str(row.get("status", "review")).lower()
                    mapped = "fail" if source_status == "block" else source_status
                    _check(checks, f"Flow control · {row.get('check')}", mapped, str(row.get("detail", "")))
                _metric(metrics, "control_manifest_release_ready", int(bool(audit.release_ready)), "boolean")
            except Exception as exc:
                _check(checks, "Flow control manifest", "fail", f"{type(exc).__name__}: {exc}")
        else:
            _check(checks, "Flow control manifest", "review", "Unstained, single-stain and FMO control manifest not supplied")
    return {
        "channel_qc": channel_qc,
        "time_drift": pd.DataFrame(drift_rows),
        "transformed_preview": transformed.head(5_000),
        "compensated_preview": compensated.head(5_000),
        "control_manifest_audit": control_audit,
    }, [
        "Use matched unstained, single-stain and FMO controls for compensation and threshold decisions.",
        "Confirm representative gates independently and retain instrument/panel QC provenance.",
    ]


def _metabolomics(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    feature = _column(frame, "feature", "feature_id", "metabolite", "compound", "lipid", "glycopeptide", "peptide")
    sample = _column(frame, "sample", "sample_id", "injection", "run")
    intensity = _column(frame, "intensity", "abundance", "area", "peak_area", "signal")
    group = _column(frame, "group", "condition", "class")
    sample_type = _column(frame, "sample_type", "type", "role")
    order = _column(frame, "injection_order", "run_order", "order")
    if not (feature and intensity):
        _check(checks, "Feature/intensity schema", "fail", "Feature and intensity columns are required")
        return {}, ["Provide a long feature table with feature, sample and intensity columns."]
    work = frame.copy()
    work["_intensity"] = pd.to_numeric(work[intensity], errors="coerce")
    _check(checks, "Feature/intensity schema", "pass", f"{feature} / {intensity}")
    grouped = work.groupby(feature, dropna=False)["_intensity"].agg(["count", "mean", "median", "std"])
    grouped["cv"] = grouped["std"] / grouped["mean"].abs().replace(0, np.nan)
    grouped["missing_fraction"] = 1.0 - grouped["count"] / max(work[sample].nunique() if sample else len(work), 1)
    grouped = grouped.reset_index()
    high_cv = int((grouped["cv"] > 0.30).sum())
    _check(checks, "Feature precision", "review" if high_cv else "pass", f"{high_cv} features with CV >30%")
    _metric(metrics, "features", int(work[feature].nunique()), "features")
    _metric(metrics, "features_cv_gt_30pct", high_cv, "features")
    blank_table = pd.DataFrame()
    qc_table = pd.DataFrame()
    if sample_type:
        role = work[sample_type].astype(str).str.lower()
        blanks = work[role.str.contains("blank", na=False)].groupby(feature)["_intensity"].median()
        biological = work[~role.str.contains("blank|qc|pool", regex=True, na=False)].groupby(feature)["_intensity"].median()
        if not blanks.empty:
            blank_table = pd.concat([biological.rename("biological_median"), blanks.rename("blank_median")], axis=1)
            blank_table["blank_ratio"] = blank_table["blank_median"] / blank_table["biological_median"].abs().replace(0, np.nan)
            blank_table = blank_table.reset_index()
            high_blank = int((blank_table["blank_ratio"] > 0.20).sum())
            _check(checks, "Blank contamination", "review" if high_blank else "pass", f"{high_blank} features with blank ratio >20%")
        pooled = work[role.str.contains("qc|pool", regex=True, na=False)]
        if not pooled.empty:
            qc = pooled.groupby(feature)["_intensity"].agg(["mean", "std", "count"])
            qc["qc_cv"] = qc["std"] / qc["mean"].abs().replace(0, np.nan)
            qc_table = qc.reset_index()
            bad_qc = int((qc_table["qc_cv"] > 0.30).sum())
            _check(checks, "Pooled-QC precision", "review" if bad_qc else "pass", f"{bad_qc} pooled-QC features with CV >30%")
        else:
            _check(checks, "Pooled-QC precision", "review", "No pooled-QC rows detected")
    else:
        _check(checks, "Blank and pooled-QC roles", "review", "Sample-type/role column not detected")
    drift_rows: list[dict[str, Any]] = []
    if order:
        order_values = pd.to_numeric(work[order], errors="coerce")
        for feature_value, subset in work.groupby(feature, sort=False):
            if len(drift_rows) >= 2_000:
                break
            signal = subset["_intensity"]
            x = order_values.loc[subset.index]
            valid = x.notna() & signal.notna()
            if valid.sum() >= 6 and x[valid].nunique() >= 2 and signal[valid].nunique() >= 2:
                rho, p_value = stats.spearmanr(x[valid], signal[valid])
                drift_rows.append({"feature": feature_value, "rho": float(rho), "p_value": float(p_value), "drift_flag": bool(np.isfinite(rho) and np.isfinite(p_value) and abs(rho) >= 0.40 and p_value < 0.05)})
        drift_count = sum(bool(row["drift_flag"]) for row in drift_rows)
        _check(checks, "Injection-order drift", "review" if drift_count else "pass", f"{drift_count} features flagged")
    drift_correction = pd.DataFrame()
    drift_corrected = pd.DataFrame()
    if order and sample_type:
        role_for_drift = work[sample_type].astype(str).str.lower()
        qc_mask = role_for_drift.str.contains("qc|pool", regex=True, na=False)
        correction_rows: list[dict[str, Any]] = []
        corrected_parts: list[pd.DataFrame] = []
        for feature_value, subset in work.groupby(feature, sort=False):
            qcs = subset.loc[qc_mask.loc[subset.index]].copy()
            qcs["_order"] = pd.to_numeric(qcs[order], errors="coerce")
            qcs["_log_intensity"] = np.log(qcs["_intensity"].clip(lower=1e-12))
            qcs = qcs.dropna(subset=["_order", "_log_intensity"])
            target = subset.copy()
            target["_order"] = pd.to_numeric(target[order], errors="coerce")
            if len(qcs) >= 4 and qcs["_order"].nunique() >= 3 and qcs["_log_intensity"].nunique() >= 2:
                slope, intercept, r_value, p_value, _ = stats.linregress(qcs["_order"], qcs["_log_intensity"])
                reference_order = float(qcs["_order"].median())
                correction_factor = np.exp(-slope * (target["_order"] - reference_order))
                target["drift_corrected_intensity"] = target["_intensity"] * correction_factor
                before_cv = float(qcs["_intensity"].std(ddof=1) / qcs["_intensity"].mean()) if qcs["_intensity"].mean() else np.nan
                qc_corrected = qcs["_intensity"] * np.exp(-slope * (qcs["_order"] - reference_order))
                after_cv = float(qc_corrected.std(ddof=1) / qc_corrected.mean()) if qc_corrected.mean() else np.nan
                correction_rows.append({"feature": feature_value, "qc_points": len(qcs), "log_slope_per_injection": float(slope), "r_squared": float(r_value**2), "p_value": float(p_value), "qc_cv_before": before_cv, "qc_cv_after": after_cv, "reference_order": reference_order})
            else:
                target["drift_corrected_intensity"] = np.nan
            corrected_parts.append(target[[feature] + ([sample] if sample else []) + ([order] if order else []) + ["_intensity", "drift_corrected_intensity"]])
        drift_correction = pd.DataFrame(correction_rows)
        drift_corrected = pd.concat(corrected_parts, ignore_index=True) if corrected_parts else pd.DataFrame()
        improved = int((drift_correction.get("qc_cv_after", pd.Series(dtype=float)) < drift_correction.get("qc_cv_before", pd.Series(dtype=float))).sum()) if not drift_correction.empty else 0
        _check(checks, "Pooled-QC drift correction", "pass" if improved and improved == len(drift_correction) else ("review" if not drift_correction.empty else "review"), f"{improved}/{len(drift_correction)} modeled features improved QC CV")
        _metric(metrics, "features_with_qc_drift_model", len(drift_correction), "features")
    else:
        _check(checks, "Pooled-QC drift correction", "review", "Injection order and pooled-QC roles are required")
    statistics = pd.DataFrame()
    statistics_work = work
    if sample_type:
        role_for_stats = work[sample_type].astype(str).str.lower()
        statistics_work = work.loc[~role_for_stats.str.contains("blank|qc|pool", regex=True, na=False)].copy()
    if group and statistics_work[group].nunique(dropna=True) == 2:
        groups = list(statistics_work[group].dropna().unique())
        rows: list[dict[str, Any]] = []
        for feature_value, subset in statistics_work.groupby(feature, sort=False):
            a = subset.loc[subset[group] == groups[0], "_intensity"].dropna()
            b = subset.loc[subset[group] == groups[1], "_intensity"].dropna()
            if min(len(a), len(b)) < 2:
                continue
            mean_a = float(a.mean())
            mean_b = float(b.mean())
            var_a = float(a.var(ddof=1)) if len(a) > 1 else 0.0
            var_b = float(b.var(ddof=1)) if len(b) > 1 else 0.0
            if np.isclose(var_a, 0.0) and np.isclose(var_b, 0.0):
                p_value = 1.0 if np.isclose(mean_a, mean_b) else 0.0
            else:
                test = stats.ttest_ind(a, b, equal_var=False, nan_policy="omit")
                p_value = float(test.pvalue) if np.isfinite(test.pvalue) else 1.0
            rows.append({
                "feature": feature_value,
                "group_a": str(groups[0]),
                "group_b": str(groups[1]),
                "mean_a": mean_a,
                "mean_b": mean_b,
                "log2_fold_change": float(np.log2((mean_b + 1e-9) / (mean_a + 1e-9))) if mean_a >= 0 and mean_b >= 0 else np.nan,
                "p_value": p_value,
            })
        statistics = pd.DataFrame(rows)
        if not statistics.empty:
            statistics["fdr"] = bh_fdr(statistics["p_value"]).values
            statistics = statistics.sort_values(["fdr", "p_value"], na_position="last")
            _metric(metrics, "features_fdr_lt_0_05", int((statistics["fdr"] < 0.05).sum()), "features")
    return {
        "feature_qc": grouped.sort_values(["cv", "missing_fraction"], ascending=False).head(10_000),
        "blank_audit": blank_table.head(10_000),
        "pooled_qc": qc_table.head(10_000),
        "drift_audit": pd.DataFrame(drift_rows),
        "drift_correction_models": drift_correction,
        "drift_corrected_intensities": drift_corrected,
        "feature_statistics": statistics.head(10_000),
    }, [
        "Treat feature identities as provisional until MS/MS, retention-time and reference-standard evidence is attached.",
        "Preserve raw intensities and the complete normalization/filter manifest.",
    ]


def _imaging(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    image = _column(frame, "image_id", "image", "field", "slide", "roi")
    obj = _column(frame, "object_id", "object", "cell_id", "nucleus_id")
    condition = _column(frame, "condition", "group", "treatment")
    numeric = _numeric(frame, exclude=[c for c in (image, obj) if c])
    _check(checks, "Image identifier", "pass" if image else "review", image or "Not detected")
    _check(checks, "Object identifier", "pass" if obj else "review", obj or "Not detected")
    if image and obj:
        duplicate = frame.astype({image: str, obj: str}).duplicated([image, obj], keep=False)
        _check(checks, "Image-object uniqueness", "review" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicate keys")
    summaries = pd.DataFrame()
    if image and numeric:
        agg = {column: ["mean", "median", "std", "count"] for column in numeric[:20]}
        summaries = frame.assign(**{c: pd.to_numeric(frame[c], errors="coerce") for c in numeric[:20]}).groupby(image).agg(agg)
        summaries.columns = ["__".join(map(str, item)) for item in summaries.columns]
        summaries = summaries.reset_index()
        _metric(metrics, "images", int(frame[image].nunique()), "images")
        if condition:
            image_conditions = frame[[image, condition]].drop_duplicates()
            counts = image_conditions.groupby(condition)[image].nunique()
            _check(checks, "Image-level replication", "review" if (counts < 2).any() else "pass", "; ".join(f"{k}:{int(v)}" for k, v in counts.items()))
    _metric(metrics, "numeric_object_features", len(numeric), "features")
    ground_truth = pd.DataFrame()
    pred = _column(frame, "predicted_mask", "prediction", "predicted_label")
    truth = _column(frame, "ground_truth", "manual_label", "truth")
    if pred and truth:
        predicted = frame[pred].astype(str)
        actual = frame[truth].astype(str)
        labels = sorted(set(predicted) | set(actual))
        matrix = confusion_matrix(actual, predicted, labels=labels)
        ground_truth = pd.DataFrame(matrix, index=[f"true:{x}" for x in labels], columns=[f"pred:{x}" for x in labels]).rename_axis("label").reset_index()
        accuracy = accuracy_score(actual, predicted)
        _check(checks, "Ground-truth comparison", "pass" if accuracy >= 0.80 else "review", f"accuracy={accuracy:.3f}")
        _metric(metrics, "ground_truth_accuracy", float(accuracy), "fraction")
    else:
        _check(checks, "Ground-truth comparison", "review", "Prediction/manual-label pair not detected")
    return {"image_level_summary": summaries.head(10_000), "ground_truth_matrix": ground_truth}, [
        "Use image/field/subject—not segmented objects—as the independent experimental unit where appropriate.",
        "Validate segmentation/classification on representative manually reviewed images and record model/calibration metadata.",
    ]


def _spatial(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    x = _column(frame, "x", "x_coord", "pxl_col_in_fullres", "centroid_x")
    y = _column(frame, "y", "y_coord", "pxl_row_in_fullres", "centroid_y")
    sample = _column(frame, "sample", "sample_id", "section", "slide")
    region = _column(frame, "region", "roi", "domain", "cell_type")
    signal_candidates = _numeric(frame, exclude=[c for c in (x, y) if c])
    if not (x and y):
        _check(checks, "Coordinate schema", "fail", "x/y coordinates are required")
        return {}, ["Provide numeric x and y coordinates with a sample/section identifier."]
    coordinates = frame[[x, y]].apply(pd.to_numeric, errors="coerce")
    valid = coordinates.notna().all(axis=1)
    duplicate = coordinates.duplicated(keep=False)
    _check(checks, "Coordinate validity", "review" if (~valid).any() else "pass", f"{int((~valid).sum())} invalid rows")
    _check(checks, "Coordinate uniqueness", "review" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicate-coordinate rows")
    if sample:
        sample_count = int(frame[sample].nunique(dropna=True))
        _metric(metrics, "samples_or_sections", sample_count, "samples")
        _check(checks, "Sample/section replication", "review" if sample_count < 2 else "pass", f"{sample_count} samples/sections")
    else:
        _check(checks, "Sample/section identity", "review", "Not detected")
    neighborhood_rows: list[dict[str, Any]] = []
    moran_rows: list[dict[str, Any]] = []
    subset_index = frame.index[valid][:20_000]
    coords = coordinates.loc[subset_index].to_numpy(dtype=float)
    if len(coords) >= 4:
        k = min(8, len(coords) - 1)
        model = NearestNeighbors(n_neighbors=k + 1).fit(coords)
        distances, indices = model.kneighbors(coords)
        mean_distance = distances[:, 1:].mean(axis=1)
        neighborhood_rows = [{"row_index": str(index), "mean_neighbor_distance": float(distance)} for index, distance in zip(subset_index, mean_distance)]
        _metric(metrics, "median_neighbor_distance", float(np.median(mean_distance)), "coordinate units")
        for signal in signal_candidates[:10]:
            values = pd.to_numeric(frame.loc[subset_index, signal], errors="coerce").to_numpy(dtype=float)
            valid_signal = np.isfinite(values)
            if valid_signal.sum() < 10:
                continue
            centered = values - np.nanmean(values)
            denominator = np.nansum(centered**2)
            if denominator <= 0:
                continue
            numerator = 0.0
            weight_sum = 0.0
            for i in range(len(values)):
                if not np.isfinite(values[i]):
                    continue
                for j in indices[i, 1:]:
                    if np.isfinite(values[j]):
                        numerator += centered[i] * centered[j]
                        weight_sum += 1.0
            moran_i = (len(values) / max(weight_sum, 1.0)) * (numerator / denominator)
            moran_rows.append({"signal": signal, "moran_i_knn": float(moran_i), "n": int(valid_signal.sum()), "neighbors": k})
        _check(checks, "Neighborhood calculation", "pass", f"k={k}; {len(coords):,} bounded coordinates")
    else:
        _check(checks, "Neighborhood calculation", "review", "At least four valid coordinates are required")
    if region:
        _metric(metrics, "annotated_regions", int(frame[region].nunique(dropna=True)), "regions")
    return {"neighborhood_qc": pd.DataFrame(neighborhood_rows), "spatial_autocorrelation": pd.DataFrame(moran_rows)}, [
        "Record image-to-coordinate transforms and registration residuals.",
        "Use patient/section replication and independent pathology review for high-stakes interpretation.",
    ]


def _parse_genotype(value: Any) -> float:
    text = str(value).strip().replace("|", "/")
    if text in {"0/0", "0", "AA", "A/A"}:
        return 0.0
    if text in {"0/1", "1/0", "1", "AB", "A/B", "B/A"}:
        return 1.0
    if text in {"1/1", "2", "BB", "B/B"}:
        return 2.0
    try:
        numeric = float(text)
        return numeric if numeric in {0.0, 1.0, 2.0} else np.nan
    except ValueError:
        return np.nan


def _population(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    variant = _column(frame, "variant_id", "variant", "rsid", "locus")
    sample = _column(frame, "sample_id", "sample", "individual_id", "patient")
    genotype = _column(frame, "genotype", "gt", "dosage")
    maf_col = _column(frame, "maf", "minor_allele_frequency", "af")
    call_col = _column(frame, "call_rate", "missingness")
    p_col = _column(frame, "p_value", "pvalue", "p")
    rows: list[dict[str, Any]] = []
    if variant and genotype:
        work = frame[[variant] + ([sample] if sample else []) + [genotype]].copy()
        work["_dosage"] = work[genotype].map(_parse_genotype)
        for variant_value, subset in work.groupby(variant, sort=False):
            dosage = subset["_dosage"]
            called = dosage.dropna()
            n = len(called)
            call_rate = n / max(len(subset), 1)
            af = float(called.sum() / (2 * n)) if n else np.nan
            maf = min(af, 1 - af) if np.isfinite(af) else np.nan
            counts = called.value_counts()
            n0, n1, n2 = int(counts.get(0.0, 0)), int(counts.get(1.0, 0)), int(counts.get(2.0, 0))
            hwe_p = np.nan
            if n >= 10 and np.isfinite(af):
                p_ref = 1 - af
                expected = np.array([n * p_ref * p_ref, 2 * n * p_ref * af, n * af * af])
                observed = np.array([n0, n1, n2], dtype=float)
                if np.all(expected > 0):
                    hwe_p = float(stats.chisquare(observed, expected).pvalue)
            rows.append({"variant": variant_value, "n_called": n, "call_rate": call_rate, "allele_frequency": af, "maf": maf, "hwe_p": hwe_p, "hom_ref": n0, "het": n1, "hom_alt": n2})
            if len(rows) >= 100_000:
                break
        variant_qc = pd.DataFrame(rows)
    else:
        variant_qc = frame[[c for c in (variant, maf_col, call_col, p_col) if c]].copy() if any((variant, maf_col, call_col, p_col)) else pd.DataFrame()
        if maf_col:
            variant_qc["maf"] = pd.to_numeric(frame[maf_col], errors="coerce")
        if call_col:
            values = pd.to_numeric(frame[call_col], errors="coerce")
            variant_qc["call_rate"] = 1 - values if "missing" in call_col.lower() else values
        if p_col:
            variant_qc["p_value"] = pd.to_numeric(frame[p_col], errors="coerce")
            variant_qc["fdr"] = bh_fdr(variant_qc["p_value"]).values
    if variant_qc.empty:
        _check(checks, "Variant schema", "fail", "No variant/genotype or summary-statistic schema detected")
        return {}, ["Provide long genotype calls or a variant-level QC/association table."]
    _check(checks, "Variant schema", "pass", f"{len(variant_qc):,} variant rows")
    if "call_rate" in variant_qc:
        low_call = pd.to_numeric(variant_qc["call_rate"], errors="coerce") < 0.98
        _check(checks, "Call-rate threshold", "review" if low_call.any() else "pass", f"{int(low_call.sum())} variants below 98%")
        _metric(metrics, "variants_below_98pct_call_rate", int(low_call.sum()), "variants")
    if "maf" in variant_qc:
        rare = pd.to_numeric(variant_qc["maf"], errors="coerce") < 0.01
        _metric(metrics, "variants_maf_lt_1pct", int(rare.sum()), "variants")
    if "hwe_p" in variant_qc:
        hwe_fail = pd.to_numeric(variant_qc["hwe_p"], errors="coerce") < 1e-6
        _check(checks, "HWE screen", "review" if hwe_fail.any() else "pass", f"{int(hwe_fail.sum())} variants p<1e-6")
    if sample:
        _metric(metrics, "samples", int(frame[sample].nunique(dropna=True)), "samples")
    _metric(metrics, "variants", len(variant_qc), "variants")
    return {"variant_qc": variant_qc.sort_values("call_rate" if "call_rate" in variant_qc else variant_qc.columns[0]).head(100_000)}, [
        "Use ancestry-aware population structure, relatedness and prespecified covariates for association testing.",
        "Confirm clinically relevant calls with specialist tools, pinned references and independent evidence.",
    ]


def _kaplan_meier(time: np.ndarray, event: np.ndarray, group: str) -> pd.DataFrame:
    order = np.argsort(time)
    times = time[order]
    events = event[order]
    unique_event_times = np.unique(times[events == 1])
    survival = 1.0
    rows: list[dict[str, Any]] = [{"group": group, "time": 0.0, "at_risk": int(len(times)), "events": 0, "survival": 1.0}]
    for t in unique_event_times:
        at_risk = int((times >= t).sum())
        d = int(((times == t) & (events == 1)).sum())
        if at_risk:
            survival *= 1.0 - d / at_risk
        rows.append({"group": group, "time": float(t), "at_risk": at_risk, "events": d, "survival": float(survival)})
    return pd.DataFrame(rows)



def _cox_univariate(time: np.ndarray, event: np.ndarray, values: np.ndarray, label: str) -> dict[str, Any] | None:
    valid = np.isfinite(time) & np.isfinite(event) & np.isfinite(values) & (time >= 0) & np.isin(event, [0, 1])
    t = np.asarray(time[valid], dtype=float)
    e = np.asarray(event[valid], dtype=int)
    x = np.asarray(values[valid], dtype=float)
    if len(t) < 20 or e.sum() < 5 or np.nanstd(x) <= 0:
        return None
    center = float(np.nanmean(x)); scale = float(np.nanstd(x, ddof=1))
    z = (x - center) / scale
    beta = 0.0
    hessian = np.nan
    for _ in range(50):
        gradient = 0.0; hessian = 0.0
        exp_bx = np.exp(np.clip(beta * z, -30, 30))
        for event_time in np.unique(t[e == 1]):
            event_mask = (t == event_time) & (e == 1)
            risk = t >= event_time
            d = int(event_mask.sum())
            if d == 0:
                continue
            s0 = float(exp_bx[risk].sum())
            s1 = float((exp_bx[risk] * z[risk]).sum())
            s2 = float((exp_bx[risk] * z[risk] ** 2).sum())
            if s0 <= 0:
                continue
            gradient += float(z[event_mask].sum()) - d * s1 / s0
            hessian -= d * (s2 / s0 - (s1 / s0) ** 2)
        if not np.isfinite(hessian) or hessian >= -1e-12:
            return None
        step = gradient / hessian
        beta -= step
        if abs(step) < 1e-8:
            break
    se = math.sqrt(-1.0 / hessian) if hessian < 0 else np.nan
    z_stat = beta / se if np.isfinite(se) and se > 0 else np.nan
    p_value = float(2 * stats.norm.sf(abs(z_stat))) if np.isfinite(z_stat) else np.nan
    hr = float(math.exp(beta)); low = float(math.exp(beta - 1.96 * se)); high = float(math.exp(beta + 1.96 * se))
    # Schoenfeld-style residual/time correlation is an exploratory PH diagnostic.
    residuals = []; residual_times = []
    exp_bx = np.exp(np.clip(beta * z, -30, 30))
    for event_time in np.unique(t[e == 1]):
        risk = t >= event_time
        s0 = float(exp_bx[risk].sum())
        if s0 <= 0:
            continue
        expected = float((exp_bx[risk] * z[risk]).sum() / s0)
        for value in z[(t == event_time) & (e == 1)]:
            residuals.append(float(value - expected)); residual_times.append(float(event_time))
    ph_rho = ph_p = np.nan
    if len(residuals) >= 5 and len(set(residual_times)) >= 3:
        ph_rho, ph_p = stats.spearmanr(np.log1p(residual_times), residuals)
    return {
        "covariate": label, "n": len(t), "events": int(e.sum()), "hazard_ratio_per_sd": hr,
        "ci95_low": low, "ci95_high": high, "coefficient": beta, "se": se, "p_value": p_value,
        "ph_schoenfeld_rho": float(ph_rho) if np.isfinite(ph_rho) else np.nan,
        "ph_schoenfeld_p": float(ph_p) if np.isfinite(ph_p) else np.nan, "original_mean": center, "original_sd": scale,
    }

def _survival(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    time_col = _column(frame, "time", "duration", "follow_up", "followup", "os_time", "pfs_time")
    event_col = _column(frame, "event", "status", "death", "outcome_event", "os_event", "pfs_event")
    group_col = _column(frame, "group", "arm", "treatment", "biomarker_group", "stratum")
    if not (time_col and event_col):
        _check(checks, "Survival schema", "fail", "Time and event columns are required")
        return {}, ["Provide non-negative follow-up time and a binary event indicator."]
    work = frame.copy()
    work["_time"] = pd.to_numeric(work[time_col], errors="coerce")
    event_text = work[event_col].astype(str).str.lower()
    mapped = event_text.map({"true": 1, "false": 0, "yes": 1, "no": 0, "dead": 1, "alive": 0, "event": 1, "censored": 0})
    work["_event"] = mapped.fillna(pd.to_numeric(work[event_col], errors="coerce"))
    valid = work["_time"].notna() & work["_event"].isin([0, 1]) & (work["_time"] >= 0)
    work = work.loc[valid].copy()
    _check(checks, "Survival schema", "pass" if len(work) >= 5 else "review", f"{len(work):,} valid records")
    groups = work[group_col].astype(str) if group_col else pd.Series("All", index=work.index)
    km_tables: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for group_value in groups.unique()[:20]:
        subset = work.loc[groups == group_value]
        km_tables.append(_kaplan_meier(subset["_time"].to_numpy(float), subset["_event"].to_numpy(int), str(group_value)))
        summary_rows.append({"group": str(group_value), "n": len(subset), "events": int(subset["_event"].sum()), "event_rate": float(subset["_event"].mean()), "median_follow_up": float(subset["_time"].median())})
    logrank = pd.DataFrame()
    if group_col and groups.nunique() == 2:
        labels = list(groups.unique())
        a = work.loc[groups == labels[0]]
        b = work.loc[groups == labels[1]]
        event_times = np.unique(work.loc[work["_event"] == 1, "_time"])
        observed_a = expected_a = variance = 0.0
        for t in event_times:
            n_a = float((a["_time"] >= t).sum())
            n_b = float((b["_time"] >= t).sum())
            d_a = float(((a["_time"] == t) & (a["_event"] == 1)).sum())
            d_b = float(((b["_time"] == t) & (b["_event"] == 1)).sum())
            n = n_a + n_b
            d = d_a + d_b
            if n <= 1 or d == 0:
                continue
            observed_a += d_a
            expected_a += d * n_a / n
            variance += n_a * n_b * d * (n - d) / (n * n * (n - 1))
        statistic = (observed_a - expected_a) ** 2 / variance if variance > 0 else np.nan
        p_value = float(stats.chi2.sf(statistic, 1)) if np.isfinite(statistic) else np.nan
        logrank = pd.DataFrame([{"group_a": labels[0], "group_b": labels[1], "chi_square": statistic, "p_value": p_value}])
        _check(checks, "Two-group log-rank", "pass" if np.isfinite(p_value) else "review", f"p={p_value:.4g}" if np.isfinite(p_value) else "Not estimable")
        _metric(metrics, "logrank_p_value", p_value, "p-value")
    else:
        _check(checks, "Group comparison", "review", "Exactly two groups not detected")
    cox_rows: list[dict[str, Any]] = []
    if group_col and groups.nunique() == 2:
        labels = list(groups.unique())
        binary = (groups == labels[1]).astype(float).to_numpy()
        fitted = _cox_univariate(work["_time"].to_numpy(float), work["_event"].to_numpy(float), binary, f"{labels[1]} vs {labels[0]}")
        if fitted:
            cox_rows.append(fitted)
    configured_covariates = [str(value) for value in metadata.get("covariates", []) if str(value) in work.columns]
    if not configured_covariates:
        configured_covariates = [c for c in _numeric(work, exclude=[time_col, event_col]) if c not in {"_time", "_event"}][:5]
    for covariate in configured_covariates:
        values = pd.to_numeric(work[covariate], errors="coerce").to_numpy(float)
        fitted = _cox_univariate(work["_time"].to_numpy(float), work["_event"].to_numpy(float), values, covariate)
        if fitted:
            cox_rows.append(fitted)
    cox = pd.DataFrame(cox_rows)
    if not cox.empty:
        ph_flags = int((cox["ph_schoenfeld_p"] < 0.05).fillna(False).sum())
        _check(checks, "Cox proportional-hazards diagnostics", "review" if ph_flags else "pass", f"{len(cox)} univariate fits; {ph_flags} PH flags")
        _metric(metrics, "cox_models", len(cox), "models")
    else:
        _check(checks, "Cox proportional-hazards diagnostics", "review", "No estimable covariate model")
    _metric(metrics, "participants", len(work), "records")
    _metric(metrics, "events", int(work["_event"].sum()), "events")
    return {"kaplan_meier": pd.concat(km_tables, ignore_index=True) if km_tables else pd.DataFrame(), "group_summary": pd.DataFrame(summary_rows), "logrank": logrank, "cox_univariate": cox}, [
        "Prespecify endpoints, censoring rules, covariates and cut-offs before confirmatory analysis.",
        "Validate the locked model/cut-off in an independent cohort and assess proportional-hazards assumptions where relevant.",
    ]


