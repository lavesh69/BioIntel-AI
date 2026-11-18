from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QpcrResult:
    sample: str
    target_ct: float
    reference_ct: float
    delta_ct: float
    delta_delta_ct: float
    relative_expression: float


def qpcr_delta_delta_ct(
    frame: pd.DataFrame,
    *,
    sample_column: str = "sample",
    target_ct_column: str = "target_ct",
    reference_ct_column: str = "reference_ct",
    calibrator_sample: str,
    target_efficiency: float = 2.0,
    reference_efficiency: float = 2.0,
    maximum_ct: float = 40.0,
    replicate_sd_limit: float = 0.5,
) -> pd.DataFrame:
    """Calculate efficiency-aware relative expression with technical-replicate QC."""
    required = {sample_column, target_ct_column, reference_ct_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing qPCR columns: " + ", ".join(sorted(missing)))
    if target_efficiency <= 1 or reference_efficiency <= 1:
        raise ValueError("Amplification efficiencies must be greater than 1.0.")
    data = frame.copy()
    data[target_ct_column] = pd.to_numeric(data[target_ct_column], errors="coerce")
    data[reference_ct_column] = pd.to_numeric(data[reference_ct_column], errors="coerce")
    data["undetermined_ct"] = (
        data[target_ct_column].isna()
        | data[reference_ct_column].isna()
        | (data[target_ct_column] > maximum_ct)
        | (data[reference_ct_column] > maximum_ct)
    )
    valid = data[~data["undetermined_ct"]].copy()
    if valid.empty:
        raise ValueError("No valid qPCR measurements remain after undetermined/maximum-Ct filtering.")
    valid["delta_ct"] = valid[target_ct_column] - valid[reference_ct_column]
    replicate_stats = valid.groupby(sample_column).agg(
        target_ct_mean=(target_ct_column, "mean"),
        target_ct_sd=(target_ct_column, "std"),
        reference_ct_mean=(reference_ct_column, "mean"),
        reference_ct_sd=(reference_ct_column, "std"),
        technical_replicates=(target_ct_column, "size"),
    ).reset_index()
    replicate_stats[["target_ct_sd", "reference_ct_sd"]] = replicate_stats[["target_ct_sd", "reference_ct_sd"]].fillna(0.0)
    calibrator = replicate_stats[replicate_stats[sample_column].astype(str) == str(calibrator_sample)]
    if calibrator.empty:
        raise ValueError("Calibrator sample was not found among valid measurements.")
    calibrator_target = float(calibrator.iloc[0]["target_ct_mean"])
    calibrator_reference = float(calibrator.iloc[0]["reference_ct_mean"])
    replicate_stats["delta_ct"] = replicate_stats["target_ct_mean"] - replicate_stats["reference_ct_mean"]
    calibrator_delta = calibrator_target - calibrator_reference
    replicate_stats["delta_delta_ct"] = replicate_stats["delta_ct"] - calibrator_delta
    replicate_stats["relative_expression"] = (
        target_efficiency ** (-(replicate_stats["target_ct_mean"] - calibrator_target))
        / reference_efficiency ** (-(replicate_stats["reference_ct_mean"] - calibrator_reference))
    )
    replicate_stats["delta_ct_sd"] = np.sqrt(
        np.square(replicate_stats["target_ct_sd"]) + np.square(replicate_stats["reference_ct_sd"])
    )
    calibrator_target_sd = float(calibrator.iloc[0]["target_ct_sd"])
    calibrator_reference_sd = float(calibrator.iloc[0]["reference_ct_sd"])
    log_variance = (
        np.log(target_efficiency) ** 2
        * (np.square(replicate_stats["target_ct_sd"]) + calibrator_target_sd**2)
        + np.log(reference_efficiency) ** 2
        * (np.square(replicate_stats["reference_ct_sd"]) + calibrator_reference_sd**2)
    )
    replicate_stats["log_relative_expression_se"] = np.sqrt(log_variance)
    replicate_stats["relative_expression_ci95_lower"] = replicate_stats["relative_expression"] * np.exp(
        -1.96 * replicate_stats["log_relative_expression_se"]
    )
    replicate_stats["relative_expression_ci95_upper"] = replicate_stats["relative_expression"] * np.exp(
        1.96 * replicate_stats["log_relative_expression_se"]
    )
    replicate_stats["target_efficiency"] = float(target_efficiency)
    replicate_stats["reference_efficiency"] = float(reference_efficiency)
    replicate_stats["replicate_qc_status"] = np.where(
        (replicate_stats["target_ct_sd"] <= replicate_sd_limit)
        & (replicate_stats["reference_ct_sd"] <= replicate_sd_limit),
        "Pass",
        "Review",
    )
    invalid_counts = data.groupby(sample_column)["undetermined_ct"].sum().rename("undetermined_measurements")
    replicate_stats = replicate_stats.merge(invalid_counts, on=sample_column, how="left")
    return replicate_stats.sort_values(sample_column).reset_index(drop=True)

def enzyme_kinetics(substrate, velocity) -> dict:
    """Fit Michaelis-Menten kinetics with covariance-based parameter intervals."""
    s = np.asarray(substrate, dtype=float)
    v = np.asarray(velocity, dtype=float)
    if len(s) < 3 or len(s) != len(v) or np.any(s <= 0) or np.any(v < 0):
        raise ValueError(
            "Provide at least three positive substrate values and matching non-negative velocities."
        )

    def model(values, vmax, km):
        return vmax * values / (km + values)

    covariance = None
    try:
        from scipy.optimize import curve_fit

        params, covariance = curve_fit(
            model,
            s,
            v,
            p0=[max(float(v.max()), 1e-9), max(float(np.median(s)), 1e-9)],
            bounds=([0.0, 1e-12], [np.inf, np.inf]),
            maxfev=20_000,
        )
        vmax, km = map(float, params)
        method = "nonlinear least-squares Michaelis-Menten"
    except Exception:
        vmax_grid = np.linspace(max(v) * 1.001, max(v) * 5, 500)
        km_grid = np.logspace(np.log10(max(min(s) / 10, 1e-9)), np.log10(max(s) * 10), 500)
        best = None
        for candidate_vmax in vmax_grid:
            predicted = candidate_vmax * s[:, None] / (km_grid[None, :] + s[:, None])
            errors = ((predicted - v[:, None]) ** 2).mean(axis=0)
            index = int(errors.argmin())
            candidate = (float(errors[index]), float(candidate_vmax), float(km_grid[index]))
            if best is None or candidate[0] < best[0]:
                best = candidate
        _, vmax, km = best
        method = "bounded grid Michaelis-Menten fallback"
    pred = model(s, vmax, km)
    residuals = v - pred
    ss_res = float(np.square(residuals).sum())
    ss_tot = float(np.square(v - v.mean()).sum())
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    result = {
        "vmax": round(vmax, 6),
        "km": round(km, 6),
        "rmse": round(rmse, 6),
        "r_squared": round(1 - ss_res / ss_tot, 6) if ss_tot else None,
        "predicted_velocity": pred.tolist(),
        "residuals": residuals.tolist(),
        "fit_method": method,
    }
    if covariance is not None and np.asarray(covariance).shape == (2, 2):
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
        result.update(
            {
                "vmax_standard_error": float(standard_errors[0]),
                "km_standard_error": float(standard_errors[1]),
                "vmax_ci95_lower": float(max(0.0, vmax - 1.96 * standard_errors[0])),
                "vmax_ci95_upper": float(vmax + 1.96 * standard_errors[0]),
                "km_ci95_lower": float(max(0.0, km - 1.96 * standard_errors[1])),
                "km_ci95_upper": float(km + 1.96 * standard_errors[1]),
            }
        )
    else:
        result.update({key: None for key in ("vmax_standard_error", "km_standard_error", "vmax_ci95_lower", "vmax_ci95_upper", "km_ci95_lower", "km_ci95_upper")})
    return result

def growth_metrics(time, od, *, minimum_window_points: int = 3) -> dict:
    """Estimate maximum growth from a robust sliding log-linear window."""
    t = np.asarray(time, dtype=float)
    y = np.asarray(od, dtype=float)
    if len(t) < minimum_window_points or len(t) != len(y) or np.any(y <= 0):
        raise ValueError("Provide positive OD values at three or more time points.")
    order = np.argsort(t)
    t = t[order]
    y = y[order]
    if np.any(np.diff(t) <= 0):
        raise ValueError("Growth-curve time values must be strictly increasing.")
    log_y = np.log(y)
    best = None
    maximum_window = min(max(minimum_window_points + 3, minimum_window_points), len(t))
    for width in range(int(minimum_window_points), maximum_window + 1):
        for start_index in range(0, len(t) - width + 1):
            stop_index = start_index + width
            x_window = t[start_index:stop_index]
            y_window = log_y[start_index:stop_index]
            slope, intercept = np.polyfit(x_window, y_window, 1)
            predicted = slope * x_window + intercept
            ss_res = float(np.square(y_window - predicted).sum())
            ss_tot = float(np.square(y_window - y_window.mean()).sum())
            r_squared = 1 - ss_res / ss_tot if ss_tot else 0.0
            if slope <= 0 or r_squared < 0.90:
                continue
            score = float(slope) * max(float(r_squared), 0.0)
            candidate = (score, float(slope), float(r_squared), start_index, stop_index)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        rates = np.diff(log_y) / np.diff(t)
        index = int(np.argmax(rates))
        mu = float(rates[index])
        r_squared = None
        start_index, stop_index = index, index + 2
        method = "adjacent-point fallback; review noisy curve"
    else:
        _, mu, r_squared, start_index, stop_index = best
        method = "sliding log-linear regression"
    doubling = np.log(2) / mu if mu > 0 else None
    return {
        "maximum_specific_growth_rate": round(mu, 6),
        "doubling_time": round(float(doubling), 6) if doubling else None,
        "maximum_od": float(y.max()),
        "log_phase_start": float(t[start_index]),
        "log_phase_end": float(t[stop_index - 1]),
        "log_phase_points": int(stop_index - start_index),
        "log_phase_r_squared": round(float(r_squared), 6) if r_squared is not None else None,
        "method": method,
    }

def _single_bioprocess_yield(data: pd.DataFrame) -> dict:
    ordered = data.sort_values("time").copy()
    for column in ("time", "biomass", "substrate", "product"):
        ordered[column] = pd.to_numeric(ordered[column], errors="raise")
    initial = ordered.iloc[0]
    final = ordered.iloc[-1]
    substrate_used = float(initial["substrate"] - final["substrate"])
    biomass_gain = float(final["biomass"] - initial["biomass"])
    product_gain = float(final["product"] - initial["product"])
    duration = float(final["time"] - initial["time"])
    consumed = float(initial["substrate"]) - ordered["substrate"].to_numpy(float)
    biomass_delta = ordered["biomass"].to_numpy(float) - float(initial["biomass"])
    product_delta = ordered["product"].to_numpy(float) - float(initial["product"])
    positive = consumed > 0
    biomass_regression = float(np.dot(consumed[positive], biomass_delta[positive]) / np.dot(consumed[positive], consumed[positive])) if positive.any() and np.dot(consumed[positive], consumed[positive]) > 0 else None
    product_regression = float(np.dot(consumed[positive], product_delta[positive]) / np.dot(consumed[positive], consumed[positive])) if positive.any() and np.dot(consumed[positive], consumed[positive]) > 0 else None
    return {
        "substrate_consumed": substrate_used,
        "biomass_gain": biomass_gain,
        "product_gain": product_gain,
        "biomass_yield_per_substrate": biomass_gain / substrate_used if substrate_used > 0 else None,
        "product_yield_per_substrate": product_gain / substrate_used if substrate_used > 0 else None,
        "biomass_yield_regression": biomass_regression,
        "product_yield_regression": product_regression,
        "volumetric_productivity": product_gain / duration if duration > 0 else None,
        "duration": duration,
    }


def bioprocess_yields(frame: pd.DataFrame) -> dict:
    required = {"time", "biomass", "substrate", "product"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing bioprocess columns: " + ", ".join(sorted(missing)))
    if "replicate" not in frame.columns:
        return _single_bioprocess_yield(frame)
    replicate_rows = []
    for replicate, group in frame.groupby("replicate", dropna=False):
        result = _single_bioprocess_yield(group)
        result["replicate"] = str(replicate)
        replicate_rows.append(result)
    replicate_frame = pd.DataFrame(replicate_rows)
    output: dict[str, object] = {"replicate_yields": replicate_rows, "replicates": len(replicate_rows)}
    for column in [column for column in replicate_frame.columns if column != "replicate"]:
        values = pd.to_numeric(replicate_frame[column], errors="coerce")
        output[column] = float(values.mean()) if values.notna().any() else None
        output[column + "_sd"] = float(values.std(ddof=1)) if values.notna().sum() > 1 else 0.0
    return output

def four_parameter_logistic(x, bottom: float, top: float, ec50: float, hill: float):
    values = np.asarray(x, dtype=float)
    return bottom + (top - bottom) / (1 + (ec50 / np.maximum(values, 1e-15)) ** hill)


def fit_elisa_4pl(concentrations, absorbance) -> dict:
    x = np.asarray(concentrations, dtype=float)
    y = np.asarray(absorbance, dtype=float)
    if len(x) < 4 or len(x) != len(y) or np.any(x <= 0):
        raise ValueError(
            "ELISA 4PL requires four or more positive standards and matching responses."
        )
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    try:
        from scipy.optimize import curve_fit

        initial = [float(y.min()), float(y.max()), float(np.median(x)), 1.0]
        bounds = (
            [-np.inf, -np.inf, float(x.min() / 100), 0.05],
            [np.inf, np.inf, float(x.max() * 100), 10.0],
        )
        params, _ = curve_fit(
            four_parameter_logistic, x, y, p0=initial, bounds=bounds, maxfev=20000
        )
        method = "nonlinear 4PL curve_fit"
    except Exception:
        # Dependency-light grid fallback.
        best = None
        for bottom in np.linspace(float(y.min()) - 0.1, float(y.min()) + 0.1, 20):
            for top in np.linspace(float(y.max()) - 0.1, float(y.max()) + 0.1, 20):
                for ec50 in np.logspace(np.log10(x.min()), np.log10(x.max()), 50):
                    for hill in (0.5, 0.75, 1, 1.5, 2, 3):
                        pred = four_parameter_logistic(x, bottom, top, ec50, hill)
                        err = float(((pred - y) ** 2).mean())
                        candidate = (err, bottom, top, ec50, hill)
                        if best is None or candidate[0] < best[0]:
                            best = candidate
        _, *params = best
        method = "grid 4PL fallback"
    bottom, top, ec50, hill = map(float, params)
    pred = four_parameter_logistic(x, bottom, top, ec50, hill)
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "bottom": bottom,
        "top": top,
        "ec50": ec50,
        "hill_slope": hill,
        "r_squared": 1 - ss_res / ss_tot if ss_tot else None,
        "method": method,
        "predicted": pred.tolist(),
    }


def inverse_4pl(absorbance, fit: dict) -> np.ndarray:
    y = np.asarray(absorbance, dtype=float)
    bottom = float(fit["bottom"])
    top = float(fit["top"])
    ec50 = float(fit["ec50"])
    hill = float(fit["hill_slope"])
    ratio = np.clip((top - bottom) / np.maximum(y - bottom, 1e-15) - 1, 1e-15, None)
    return ec50 / (ratio ** (1 / hill))


def quantify_elisa(
    standard_concentrations,
    standard_absorbance,
    unknown_absorbance,
    *,
    blank_absorbance: float = 0.0,
    blank_standard_deviation: float | None = None,
    dilution_factors=None,
) -> dict:
    standards = np.asarray(standard_absorbance, dtype=float) - float(blank_absorbance)
    unknown_response = np.asarray(unknown_absorbance, dtype=float) - float(blank_absorbance)
    fit = fit_elisa_4pl(standard_concentrations, standards)
    unknown = inverse_4pl(unknown_response, fit)
    dilution = np.ones(len(unknown), dtype=float) if dilution_factors is None else np.asarray(dilution_factors, dtype=float)
    if len(dilution) != len(unknown) or np.any(dilution <= 0):
        raise ValueError("Dilution factors must be positive and match the unknown measurements.")
    corrected = unknown * dilution
    concentration_values = np.asarray(standard_concentrations, dtype=float)
    response_min = float(np.min(standards))
    response_max = float(np.max(standards))
    records = []
    for index, value in enumerate(corrected):
        in_range = response_min <= float(unknown_response[index]) <= response_max
        records.append(
            {
                "unknown_index": index + 1,
                "blank_corrected_absorbance": float(unknown_response[index]),
                "dilution_factor": float(dilution[index]),
                "estimated_concentration": float(value),
                "within_standard_response_range": bool(in_range),
                "range_flag": "In range" if in_range else "Out of range",
            }
        )
    lod = loq = None
    if blank_standard_deviation is not None and blank_standard_deviation >= 0:
        lod_response = 3.0 * float(blank_standard_deviation)
        loq_response = 10.0 * float(blank_standard_deviation)
        lod = float(inverse_4pl([lod_response], fit)[0])
        loq = float(inverse_4pl([loq_response], fit)[0])
    return {
        "fit": fit,
        "blank_absorbance": float(blank_absorbance),
        "standard_concentration_range": [float(concentration_values.min()), float(concentration_values.max())],
        "unknown_concentrations": [float(value) for value in corrected],
        "unknown_results": records,
        "estimated_lod": lod,
        "estimated_loq": loq,
    }

