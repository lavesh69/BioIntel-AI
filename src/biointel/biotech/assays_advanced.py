from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from biointel.biotech.assays import four_parameter_logistic
from biointel.biotech.assays_quality import (
    bioprocess_advanced_metrics,
    bioprocess_batch_comparison,
    bioprocess_pat_monitor,
    bioprocess_sensor_metrics,
    convert_absorbance_slope_to_rate,
    elisa_assay_qc,
    elisa_hook_effect_screen,
    elisa_parallelism_recovery_qc,
    elisa_validation_summary,
    extract_initial_rates,
    qpcr_amplification_curve_qc,
    qpcr_control_qc,
    qpcr_reference_gene_stability,
)

__all__ = [
    "bioprocess_advanced_metrics",
    "bioprocess_batch_comparison",
    "bioprocess_pat_monitor",
    "bioprocess_sensor_metrics",
    "convert_absorbance_slope_to_rate",
    "elisa_assay_qc",
    "elisa_hook_effect_screen",
    "elisa_parallelism_recovery_qc",
    "elisa_validation_summary",
    "extract_initial_rates",
    "qpcr_amplification_curve_qc",
    "qpcr_control_qc",
    "qpcr_reference_gene_stability",
]


@dataclass(frozen=True)
class CalibrationFit:
    model: str
    parameters: dict[str, float]
    predicted: list[float]
    residuals: list[float]
    r_squared: float | None
    rmse: float
    aic: float
    aicc: float
    parameter_count: int
    covariance_ok: bool
    monotonic: bool
    warnings: tuple[str, ...] = ()


def qpcr_standard_curve(concentration, ct) -> dict[str, float | list[float]]:
    x = np.asarray(concentration, dtype=float)
    y = np.asarray(ct, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y) & (x > 0)
    x, y = x[valid], y[valid]
    if len(x) < 3 or len(np.unique(x)) < 3:
        raise ValueError("qPCR efficiency requires at least three distinct positive standard concentrations.")
    log_x = np.log10(x)
    slope, intercept = np.polyfit(log_x, y, 1)
    predicted = slope * log_x + intercept
    residuals = y - predicted
    ss_res = float(np.square(residuals).sum())
    ss_tot = float(np.square(y - y.mean()).sum())
    efficiency_fraction = 10 ** (-1 / slope) - 1 if slope < 0 else np.nan
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(1 - ss_res / ss_tot) if ss_tot else 1.0,
        "efficiency_fraction": float(efficiency_fraction),
        "efficiency_percent": float(100 * efficiency_fraction),
        "amplification_factor": float(1 + efficiency_fraction),
        "predicted_ct": predicted.tolist(),
        "residuals": residuals.tolist(),
    }


def qpcr_multi_reference(
    frame: pd.DataFrame,
    *,
    sample_column: str = "sample",
    target_column: str = "target",
    gene_column: str = "gene",
    ct_column: str = "ct",
    reference_genes: list[str],
    calibrator_sample: str,
    efficiency_by_gene: dict[str, float] | None = None,
    maximum_ct: float = 40.0,
    strict_roles: bool = True,
) -> pd.DataFrame:
    required = {sample_column, target_column, gene_column, ct_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing qPCR long-format columns: " + ", ".join(sorted(missing)))
    if len(reference_genes) < 1:
        raise ValueError("At least one reference gene is required.")
    data = frame.copy()
    data[ct_column] = pd.to_numeric(data[ct_column], errors="coerce")
    data = data[data[ct_column].notna() & (data[ct_column] <= maximum_ct)].copy()
    if data.empty:
        raise ValueError("No valid qPCR measurements remain.")

    role_aliases = {
        "target": "target",
        "assay": "target",
        "reference": "reference",
        "ref": "reference",
        "housekeeping": "reference",
        "endogenous_control": "reference",
        "ntc": "control",
        "negative": "control",
        "negative_control": "control",
        "no_rt": "control",
        "no-rt": "control",
        "positive": "control",
        "positive_control": "control",
        "extraction_control": "control",
        "ipc": "control",
        "ignore": "ignore",
        "excluded": "ignore",
    }
    role_values = data[target_column].astype(str).str.strip().str.lower().str.replace(" ", "_", regex=False)
    canonical_roles = role_values.map(role_aliases)
    unknown_roles = sorted(set(role_values[canonical_roles.isna()]))
    if unknown_roles and strict_roles:
        raise ValueError(
            "Unknown qPCR role values: " + ", ".join(unknown_roles[:20])
            + ". Use target, reference, control roles or ignore."
        )
    data["_canonical_role"] = canonical_roles.fillna("target")
    data = data[~data["_canonical_role"].isin(["control", "ignore"])].copy()
    if data.empty:
        raise ValueError("No target/reference measurements remain after role filtering.")

    selected_references = [str(gene) for gene in reference_genes]
    role_references = set(data.loc[data["_canonical_role"] == "reference", gene_column].astype(str))
    if role_references and not set(selected_references).issubset(role_references):
        missing_reference_roles = sorted(set(selected_references) - role_references)
        raise ValueError(
            "Selected reference genes are not labelled as reference: "
            + ", ".join(missing_reference_roles)
        )
    refs = data[data[gene_column].astype(str).isin(selected_references)]
    if refs.empty:
        raise ValueError("None of the selected reference genes were found.")
    reference_summary = refs.groupby([sample_column, gene_column])[ct_column].mean().unstack()
    missing_reference = reference_summary.isna().any(axis=1)
    reference_summary = reference_summary[~missing_reference]
    if reference_summary.empty:
        raise ValueError("No sample contains all selected reference genes.")
    reference_geometric_signal = np.exp(np.log(np.power(2.0, -reference_summary)).mean(axis=1))
    equivalent_reference_ct = -np.log2(reference_geometric_signal)
    targets = data[
        (data["_canonical_role"] == "target")
        & ~data[gene_column].astype(str).isin(selected_references)
    ]
    if targets.empty:
        raise ValueError("No target-gene measurements remain after role filtering.")
    targets = targets.groupby([sample_column, gene_column])[ct_column].agg(["mean", "std", "size"]).reset_index()
    targets = targets.merge(equivalent_reference_ct.rename("reference_ct"), left_on=sample_column, right_index=True, how="inner")
    targets["delta_ct"] = targets["mean"] - targets["reference_ct"]
    calibrator = targets[targets[sample_column].astype(str) == str(calibrator_sample)]
    if calibrator.empty:
        raise ValueError("Calibrator sample is not available after reference-gene QC.")
    calibration = calibrator.set_index(gene_column)["delta_ct"]
    targets["calibrator_delta_ct"] = targets[gene_column].map(calibration)
    targets = targets[targets["calibrator_delta_ct"].notna()].copy()
    targets["delta_delta_ct"] = targets["delta_ct"] - targets["calibrator_delta_ct"]
    efficiencies = efficiency_by_gene or {}
    targets["amplification_factor"] = targets[gene_column].map(lambda value: float(efficiencies.get(str(value), 2.0)))
    targets["relative_expression"] = targets["amplification_factor"] ** (-targets["delta_delta_ct"])
    targets["log2_relative_expression"] = np.log2(targets["relative_expression"].where(targets["relative_expression"] > 0))
    targets["reference_genes"] = ", ".join(reference_genes)
    targets["reference_completeness"] = "Pass"
    targets["excluded_control_or_ignore_rows"] = int((frame.shape[0] - data.shape[0]))
    return targets.rename(columns={"mean": "target_ct_mean", "std": "target_ct_sd", "size": "technical_replicates"})


def qpcr_group_statistics(
    frame: pd.DataFrame,
    *,
    group_column: str,
    value_column: str = "relative_expression",
    reference_group: str | None = None,
    bootstrap_iterations: int = 1000,
    random_state: int = 42,
    inference_scale: str = "auto",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from scipy.stats import ttest_ind

    if group_column not in frame.columns or value_column not in frame.columns:
        raise ValueError("Group and value columns are required for qPCR group statistics.")
    if inference_scale not in {"auto", "raw", "log2"}:
        raise ValueError("inference_scale must be auto, raw or log2.")
    values_all = pd.to_numeric(frame[value_column], errors="coerce")
    use_log2 = inference_scale == "log2" or (inference_scale == "auto" and value_column == "relative_expression")
    if use_log2 and (values_all.dropna() <= 0).any():
        raise ValueError("Log2 qPCR inference requires strictly positive expression values.")
    analysis = frame.copy()
    analysis["_inference_value"] = np.log2(values_all) if use_log2 else values_all
    rng = np.random.default_rng(random_state)
    summary_rows = []
    for group, part in analysis.groupby(group_column, dropna=False):
        raw_values = pd.to_numeric(part[value_column], errors="coerce").dropna().to_numpy(float)
        infer_values = pd.to_numeric(part["_inference_value"], errors="coerce").dropna().to_numpy(float)
        if not len(raw_values):
            continue
        boot = np.array([rng.choice(raw_values, len(raw_values), replace=True).mean() for _ in range(max(100, bootstrap_iterations))])
        summary_rows.append({
            "group": str(group),
            "n": int(len(raw_values)),
            "mean": float(raw_values.mean()),
            "median": float(np.median(raw_values)),
            "standard_deviation": float(raw_values.std(ddof=1)) if len(raw_values) > 1 else 0.0,
            "ci95_lower": float(np.quantile(boot, 0.025)),
            "ci95_upper": float(np.quantile(boot, 0.975)),
            "inference_scale": "log2" if use_log2 else "raw",
            "inference_mean": float(infer_values.mean()),
        })
    summary = pd.DataFrame(summary_rows)
    if summary.empty:
        return summary, pd.DataFrame()
    reference = str(reference_group or summary.iloc[0]["group"])
    ref_part = analysis[analysis[group_column].astype(str) == reference]
    ref_raw = pd.to_numeric(ref_part[value_column], errors="coerce").dropna().to_numpy(float)
    ref_infer = pd.to_numeric(ref_part["_inference_value"], errors="coerce").dropna().to_numpy(float)
    tests = []
    for group in summary["group"]:
        if group == reference:
            continue
        part = analysis[analysis[group_column].astype(str) == str(group)]
        raw_values = pd.to_numeric(part[value_column], errors="coerce").dropna().to_numpy(float)
        infer_values = pd.to_numeric(part["_inference_value"], errors="coerce").dropna().to_numpy(float)
        statistic, p_value = ttest_ind(infer_values, ref_infer, equal_var=False) if len(infer_values) > 1 and len(ref_infer) > 1 else (np.nan, np.nan)
        tests.append({
            "comparison": f"{group} vs {reference}",
            "welch_t": float(statistic),
            "p_value": float(p_value),
            "inference_scale": "log2" if use_log2 else "raw",
            "fold_change_of_means": float(raw_values.mean() / ref_raw.mean()) if len(raw_values) and len(ref_raw) and ref_raw.mean() else np.nan,
            "small_sample_warning": bool(len(infer_values) < 3 or len(ref_infer) < 3),
        })
    tests_frame = pd.DataFrame(tests)
    if not tests_frame.empty:
        order = tests_frame["p_value"].fillna(1.0).sort_values().index
        ranked = tests_frame.loc[order, "p_value"].fillna(1.0).to_numpy(float)
        adjusted = np.minimum.accumulate((ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1])[::-1]
        tests_frame.loc[order, "fdr_q_value"] = np.clip(adjusted, 0, 1)
    return summary, tests_frame


def melt_curve_qc(temperature, fluorescence, *, prominence_fraction: float = 0.08) -> dict[str, object]:
    from scipy.signal import find_peaks

    t = np.asarray(temperature, dtype=float)
    f = np.asarray(fluorescence, dtype=float)
    valid = np.isfinite(t) & np.isfinite(f)
    t, f = t[valid], f[valid]
    if len(t) < 8:
        raise ValueError("Melt-curve QC requires at least eight temperature points.")
    order = np.argsort(t)
    t, f = t[order], f[order]
    derivative = -np.gradient(f, t)
    prominence = max(float(np.ptp(derivative)) * prominence_fraction, 1e-12)
    peaks, properties = find_peaks(derivative, prominence=prominence)
    peak_rows = [{"temperature": float(t[index]), "peak_height": float(derivative[index]), "prominence": float(properties["prominences"][position])} for position, index in enumerate(peaks)]
    primary = max(peak_rows, key=lambda row: row["peak_height"]) if peak_rows else None
    return {
        "peak_count": len(peak_rows),
        "primary_tm": primary["temperature"] if primary else None,
        "qc_status": "Pass" if len(peak_rows) == 1 else "Review",
        "warning": None if len(peak_rows) == 1 else "Multiple or absent melt peaks can indicate non-specific products or primer dimers.",
        "peaks": peak_rows,
        "temperature": t.tolist(),
        "negative_derivative": derivative.tolist(),
    }


def five_parameter_logistic(x, bottom: float, top: float, ec50: float, hill: float, asymmetry: float):
    values = np.asarray(x, dtype=float)
    return bottom + (top - bottom) / np.power(1 + np.power(ec50 / np.maximum(values, 1e-15), hill), asymmetry)


def _fit_curve_model(x: np.ndarray, y: np.ndarray, model_name: str, weights: np.ndarray | None = None) -> CalibrationFit:
    from scipy.optimize import curve_fit

    sigma = None
    if weights is not None:
        sigma = 1 / np.sqrt(np.maximum(weights, 1e-12))
    covariance_ok = True
    if model_name == "4PL":
        func: Callable = four_parameter_logistic
        p0 = [float(y.min()), float(y.max()), float(np.median(x)), 1.0]
        bounds = ([-np.inf, -np.inf, x.min() / 100, 0.05], [np.inf, np.inf, x.max() * 100, 10.0])
        names = ["bottom", "top", "ec50", "hill_slope"]
    elif model_name == "5PL":
        func = five_parameter_logistic
        p0 = [float(y.min()), float(y.max()), float(np.median(x)), 1.0, 1.0]
        bounds = ([-np.inf, -np.inf, x.min() / 100, 0.05, 0.1], [np.inf, np.inf, x.max() * 100, 10.0, 10.0])
        names = ["bottom", "top", "ec50", "hill_slope", "asymmetry"]
    elif model_name == "linear":
        coefficients = np.polyfit(x, y, 1, w=np.sqrt(weights) if weights is not None else None)
        predicted = np.polyval(coefficients, x)
        return _fit_payload(
            model_name,
            {"slope": float(coefficients[0]), "intercept": float(coefficients[1])},
            y,
            predicted,
            2,
            covariance_ok=True,
        )
    elif model_name == "log-linear":
        coefficients = np.polyfit(np.log10(x), y, 1, w=np.sqrt(weights) if weights is not None else None)
        predicted = np.polyval(coefficients, np.log10(x))
        return _fit_payload(
            model_name,
            {"slope": float(coefficients[0]), "intercept": float(coefficients[1])},
            y,
            predicted,
            2,
            covariance_ok=True,
        )
    else:
        raise ValueError(f"Unknown calibration model: {model_name}")
    params, covariance = curve_fit(
        func,
        x,
        y,
        p0=p0,
        bounds=bounds,
        sigma=sigma,
        absolute_sigma=False,
        maxfev=50_000,
    )
    covariance_ok = bool(
        covariance.shape == (len(params), len(params))
        and np.all(np.isfinite(covariance))
        and np.all(np.diag(covariance) >= 0)
    )
    predicted = func(x, *params)
    return _fit_payload(
        model_name,
        dict(zip(names, map(float, params))),
        y,
        predicted,
        len(params),
        covariance_ok=covariance_ok,
    )


def _fit_payload(
    model: str,
    parameters: dict[str, float],
    observed: np.ndarray,
    predicted: np.ndarray,
    parameter_count: int,
    *,
    covariance_ok: bool,
) -> CalibrationFit:
    residuals = observed - predicted
    rss = float(np.square(residuals).sum())
    n = len(observed)
    rmse = float(np.sqrt(rss / max(n, 1)))
    ss_tot = float(np.square(observed - observed.mean()).sum())
    r_squared = float(1 - rss / ss_tot) if ss_tot else None
    aic = float(n * np.log(max(rss / max(n, 1), 1e-15)) + 2 * parameter_count)
    denominator = n - parameter_count - 1
    aicc = float(aic + (2 * parameter_count * (parameter_count + 1) / denominator)) if denominator > 0 else float("inf")
    differences = np.diff(np.asarray(predicted, dtype=float))
    monotonic = bool(np.all(differences >= -1e-10) or np.all(differences <= 1e-10))
    warnings: list[str] = []
    if not covariance_ok:
        warnings.append("parameter_covariance_unstable")
    if not monotonic:
        warnings.append("non_monotonic_calibration")
    if model in {"4PL", "5PL"} and parameters.get("top", 0) <= parameters.get("bottom", 0):
        warnings.append("inverted_response_direction")
    return CalibrationFit(
        model,
        parameters,
        predicted.tolist(),
        residuals.tolist(),
        r_squared,
        rmse,
        aic,
        aicc,
        parameter_count,
        covariance_ok,
        monotonic,
        tuple(warnings),
    )


def fit_elisa_calibration(
    standards: pd.DataFrame,
    *,
    concentration_column: str = "concentration",
    response_column: str = "absorbance",
    candidate_models: tuple[str, ...] = ("4PL", "5PL", "log-linear"),
    maximum_replicate_cv_percent: float = 20.0,
    minimum_levels_by_model: dict[str, int] | None = None,
) -> dict[str, object]:
    """Fit ELISA calibrations with model-complexity and extrapolation safeguards."""

    data = standards.copy()
    data[concentration_column] = pd.to_numeric(data[concentration_column], errors="coerce")
    data[response_column] = pd.to_numeric(data[response_column], errors="coerce")
    data = data.dropna(subset=[concentration_column, response_column])
    data = data[data[concentration_column] > 0]
    distinct_levels = int(data[concentration_column].nunique())
    if distinct_levels < 4:
        raise ValueError("ELISA calibration requires at least four distinct positive standards.")
    minimums = {"linear": 4, "log-linear": 4, "4PL": 6, "5PL": 8}
    minimums.update(minimum_levels_by_model or {})
    replicate = data.groupby(concentration_column)[response_column].agg(["mean", "std", "count"]).reset_index()
    replicate["std"] = replicate["std"].fillna(0.0)
    replicate["cv_percent"] = np.where(
        replicate["mean"].abs() > 1e-15,
        100 * replicate["std"].abs() / replicate["mean"].abs(),
        0.0,
    )
    replicate["replicate_qc"] = np.where(
        (replicate["count"] >= 2) & (replicate["cv_percent"] <= maximum_replicate_cv_percent),
        "Pass",
        "Review",
    )
    x = replicate[concentration_column].to_numpy(float)
    y = replicate["mean"].to_numpy(float)
    standard_deviation = replicate["std"].to_numpy(float)
    weights = np.ones_like(standard_deviation, dtype=float)
    positive_standard_deviation = standard_deviation > 0
    weights[positive_standard_deviation] = 1 / np.square(standard_deviation[positive_standard_deviation])
    fits: list[CalibrationFit] = []
    failures: list[dict[str, object]] = []
    for model in candidate_models:
        required_levels = int(minimums.get(model, 4))
        if distinct_levels < required_levels:
            failures.append({
                "model": model,
                "error": f"{model} requires at least {required_levels} distinct concentration levels; {distinct_levels} supplied.",
                "blocked_for_complexity": True,
            })
            continue
        try:
            fit = _fit_curve_model(x, y, model, weights)
            if not fit.monotonic:
                failures.append({"model": model, "error": "Calibration is not monotonic.", "blocked_for_shape": True})
                continue
            if not fit.covariance_ok and model in {"4PL", "5PL"}:
                failures.append({"model": model, "error": "Parameter covariance is unstable.", "blocked_for_covariance": True})
                continue
            fits.append(fit)
        except Exception as exc:
            failures.append({"model": model, "error": str(exc)})
    if not fits:
        details = "; ".join(f"{item['model']}: {item['error']}" for item in failures)
        raise ValueError("No ELISA calibration model could be fitted safely. " + details)
    best = min(fits, key=lambda item: item.aicc)
    fit_table = pd.DataFrame([
        {
            **{"model": item.model},
            **item.parameters,
            "r_squared": item.r_squared,
            "rmse": item.rmse,
            "aic": item.aic,
            "aicc": item.aicc,
            "parameter_count": item.parameter_count,
            "covariance_ok": item.covariance_ok,
            "monotonic": item.monotonic,
            "warnings": ", ".join(item.warnings),
        }
        for item in fits
    ])
    residual_table = replicate[[concentration_column, "mean", "std", "count", "cv_percent", "replicate_qc"]].copy()
    residual_table["predicted"] = best.predicted
    residual_table["residual"] = best.residuals
    return {
        "selected_model": best.model,
        "parameters": best.parameters,
        "fit_table": fit_table,
        "standard_qc": replicate,
        "residuals": residual_table,
        "failures": failures,
        "concentration_range": (float(x.min()), float(x.max())),
        "response_range": (float(y.min()), float(y.max())),
        "distinct_standard_levels": distinct_levels,
        "selection_metric": "AICc",
        "model_warnings": list(best.warnings),
    }


def _calibration_forward(concentration, *, model: str, parameters: dict[str, float]) -> np.ndarray:
    x = np.asarray(concentration, dtype=float)
    if model == "4PL":
        return four_parameter_logistic(x, parameters["bottom"], parameters["top"], parameters["ec50"], parameters["hill_slope"])
    if model == "5PL":
        return five_parameter_logistic(x, parameters["bottom"], parameters["top"], parameters["ec50"], parameters["hill_slope"], parameters["asymmetry"])
    if model == "linear":
        return parameters["intercept"] + parameters["slope"] * x
    if model == "log-linear":
        return parameters["intercept"] + parameters["slope"] * np.log10(x)
    raise ValueError(f"Unsupported calibration model: {model}")


def _inverse_calibration_raw(response, *, model: str, parameters: dict[str, float]) -> np.ndarray:
    y = np.asarray(response, dtype=float)
    if model in {"4PL", "5PL"}:
        bottom, top = parameters["bottom"], parameters["top"]
        hill, ec50 = parameters["hill_slope"], parameters["ec50"]
        asymmetry = parameters.get("asymmetry", 1.0)
        denominator = y - bottom
        ratio = np.power((top - bottom) / denominator, 1 / asymmetry) - 1
        return ec50 / np.power(ratio, 1 / hill)
    if model == "linear":
        return (y - parameters["intercept"]) / parameters["slope"]
    if model == "log-linear":
        return np.power(10.0, (y - parameters["intercept"]) / parameters["slope"])
    raise ValueError(f"Unsupported calibration model: {model}")


def inverse_calibration(
    response,
    *,
    model: str,
    parameters: dict[str, float],
    concentration_range: tuple[float, float] | None = None,
    response_range: tuple[float, float] | None = None,
    extrapolation: str = "nan",
) -> np.ndarray:
    """Invert a calibration without silently emitting extreme extrapolations.

    ``extrapolation='nan'`` is the safe default. Use ``'allow'`` only for an
    explicitly reviewed research workflow.
    """

    y = np.asarray(response, dtype=float)
    with np.errstate(all="ignore"):
        estimates = _inverse_calibration_raw(y, model=model, parameters=parameters)
    invalid = ~np.isfinite(estimates) | (estimates <= 0)
    if response_range is not None:
        low_response, high_response = sorted(map(float, response_range))
        invalid |= (y < low_response) | (y > high_response)
    if concentration_range is not None:
        low_concentration, high_concentration = sorted(map(float, concentration_range))
        invalid |= (estimates < low_concentration) | (estimates > high_concentration)
    if extrapolation not in {"nan", "allow", "clip"}:
        raise ValueError("extrapolation must be nan, allow or clip.")
    if extrapolation == "nan":
        estimates = np.where(invalid, np.nan, estimates)
    elif extrapolation == "clip" and concentration_range is not None:
        low_concentration, high_concentration = sorted(map(float, concentration_range))
        estimates = np.clip(estimates, low_concentration, high_concentration)
        if response_range is not None:
            low_response, high_response = sorted(map(float, response_range))
            boundary_response = _calibration_forward(
                [low_concentration, high_concentration], model=model, parameters=parameters
            )
            increasing = bool(boundary_response[1] >= boundary_response[0])
            low_bound = low_concentration if increasing else high_concentration
            high_bound = high_concentration if increasing else low_concentration
            estimates = np.where((y < low_response) & ~np.isfinite(estimates), low_bound, estimates)
            estimates = np.where((y > high_response) & ~np.isfinite(estimates), high_bound, estimates)
    return np.asarray(estimates, dtype=float)


def inverse_calibration_with_flags(
    response,
    *,
    model: str,
    parameters: dict[str, float],
    concentration_range: tuple[float, float],
    response_range: tuple[float, float],
) -> pd.DataFrame:
    """Return safe estimates and explicit LLOQ/ULOQ-style range labels."""

    y = np.asarray(response, dtype=float)
    low_response, high_response = sorted(map(float, response_range))
    low_concentration, high_concentration = sorted(map(float, concentration_range))
    with np.errstate(all="ignore"):
        raw = _inverse_calibration_raw(y, model=model, parameters=parameters)
    status = np.full(len(y), "In range", dtype=object)
    status[y < low_response] = "<LLOQ / below calibration response"
    status[y > high_response] = ">ULOQ / above calibration response"
    status[(status == "In range") & (raw < low_concentration)] = "<LLOQ / below calibrated concentration"
    status[(status == "In range") & (raw > high_concentration)] = ">ULOQ / above calibrated concentration"
    invalid = ~np.isfinite(raw) | (raw <= 0)
    status[(status == "In range") & invalid] = "Not quantifiable"
    estimate = np.where(status == "In range", raw, np.nan)
    recommendation = np.where(
        np.char.startswith(status.astype(str), ">ULOQ"),
        "Dilute and repeat",
        np.where(np.char.startswith(status.astype(str), "<LLOQ"), "Report below quantification limit", np.where(status == "In range", "Accept after QC review", "Repeat assay")),
    )
    return pd.DataFrame({
        "response": y,
        "raw_extrapolated_concentration": raw,
        "estimated_concentration": estimate,
        "quantification_status": status,
        "recommendation": recommendation,
    })


def bootstrap_elisa_unknown_intervals(
    standards: pd.DataFrame,
    responses,
    *,
    concentration_column: str = "concentration",
    response_column: str = "absorbance",
    model: str = "4PL",
    iterations: int = 300,
    random_state: int = 42,
) -> pd.DataFrame:
    """Bootstrap calibration uncertainty for unknown responses."""

    data = standards[[concentration_column, response_column]].copy()
    data[concentration_column] = pd.to_numeric(data[concentration_column], errors="coerce")
    data[response_column] = pd.to_numeric(data[response_column], errors="coerce")
    data = data.dropna()
    grouped = {level: part for level, part in data.groupby(concentration_column)}
    rng = np.random.default_rng(random_state)
    estimates: list[np.ndarray] = []
    for _ in range(max(50, int(iterations))):
        sampled_parts = []
        for _, part in grouped.items():
            indices = rng.integers(0, len(part), len(part))
            sampled_parts.append(part.iloc[indices])
        sampled = pd.concat(sampled_parts, ignore_index=True)
        try:
            fit = fit_elisa_calibration(sampled, candidate_models=(model,))
            inverse = inverse_calibration(
                responses,
                model=model,
                parameters=fit["parameters"],
                concentration_range=fit["concentration_range"],
                response_range=fit["response_range"],
            )
            estimates.append(inverse)
        except Exception:
            continue
    response_values = np.asarray(responses, dtype=float)
    if not estimates:
        return pd.DataFrame({"response": response_values, "ci95_lower": np.nan, "ci95_upper": np.nan, "bootstrap_successes": 0})
    matrix = np.vstack(estimates)
    return pd.DataFrame({
        "response": response_values,
        "ci95_lower": np.nanquantile(matrix, 0.025, axis=0),
        "ci95_upper": np.nanquantile(matrix, 0.975, axis=0),
        "bootstrap_successes": int(matrix.shape[0]),
    })


def fit_enzyme_model(substrate, velocity, *, model: str = "michaelis_menten", weights=None) -> dict[str, object]:
    from scipy.optimize import curve_fit

    s = np.asarray(substrate, dtype=float)
    v = np.asarray(velocity, dtype=float)
    valid = np.isfinite(s) & np.isfinite(v) & (s > 0) & (v >= 0)
    s, v = s[valid], v[valid]
    if len(s) < 4:
        raise ValueError("At least four valid kinetic observations are required.")
    sigma = None
    if weights is not None:
        weight_values = np.asarray(weights, dtype=float)[valid]
        sigma = 1 / np.sqrt(np.maximum(weight_values, 1e-12))
    if model == "michaelis_menten":
        def func(x, vmax, km):
            return vmax * x / (km + x)

        p0, bounds, names = [v.max(), np.median(s)], ([0, 1e-12], [np.inf, np.inf]), ["vmax", "km"]
    elif model == "hill":
        def func(x, vmax, k_half, hill):
            return vmax * np.power(x, hill) / (np.power(k_half, hill) + np.power(x, hill))

        p0, bounds, names = [v.max(), np.median(s), 1.0], ([0, 1e-12, 0.1], [np.inf, np.inf, 8.0]), ["vmax", "k_half", "hill_coefficient"]
    elif model == "substrate_inhibition":
        def func(x, vmax, km, ki):
            return vmax * x / (km + x + np.square(x) / ki)

        p0, bounds, names = [v.max(), np.median(s), max(s) * 2], ([0, 1e-12, 1e-12], [np.inf, np.inf, np.inf]), ["vmax", "km", "ki"]
    else:
        raise ValueError("Model must be michaelis_menten, hill or substrate_inhibition.")
    params, covariance = curve_fit(func, s, v, p0=p0, bounds=bounds, sigma=sigma, maxfev=50_000)
    predicted = func(s, *params)
    payload = _fit_payload(model, dict(zip(names, map(float, params))), v, predicted, len(params), covariance_ok=bool(np.all(np.isfinite(covariance))))
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0)) if covariance.shape[0] == len(params) else np.repeat(np.nan, len(params))
    return {
        "model": model,
        "parameters": payload.parameters,
        "standard_errors": dict(zip(names, map(float, standard_errors))),
        "r_squared": payload.r_squared,
        "rmse": payload.rmse,
        "aic": payload.aic,
        "aicc": payload.aicc,
        "parameter_count": payload.parameter_count,
        "covariance_ok": payload.covariance_ok,
        "predicted_velocity": payload.predicted,
        "residuals": payload.residuals,
    }



def compare_enzyme_models(substrate, velocity, *, weights=None) -> pd.DataFrame:
    """Fit supported kinetic models and rank them by small-sample corrected AIC."""

    rows = []
    for model in ("michaelis_menten", "hill", "substrate_inhibition"):
        try:
            result = fit_enzyme_model(substrate, velocity, model=model, weights=weights)
            rows.append({
                "model": model,
                "aicc": result["aicc"],
                "aic": result["aic"],
                "r_squared": result["r_squared"],
                "rmse": result["rmse"],
                "covariance_ok": result["covariance_ok"],
                "parameters": result["parameters"],
                "status": "Fitted",
                "error": "",
            })
        except Exception as exc:
            rows.append({"model": model, "aicc": np.inf, "aic": np.inf, "r_squared": np.nan, "rmse": np.nan, "covariance_ok": False, "parameters": {}, "status": "Blocked", "error": str(exc)})
    table = pd.DataFrame(rows).sort_values(["aicc", "rmse"], na_position="last").reset_index(drop=True)
    if np.isfinite(table["aicc"]).any():
        minimum = table.loc[np.isfinite(table["aicc"]), "aicc"].min()
        table["delta_aicc"] = table["aicc"] - minimum
        weights_raw = np.exp(-0.5 * table["delta_aicc"].where(np.isfinite(table["delta_aicc"]), np.inf))
        table["akaike_weight"] = weights_raw / weights_raw.sum() if weights_raw.sum() else 0.0
    else:
        table["delta_aicc"] = np.nan
        table["akaike_weight"] = 0.0
    return table


def compare_inhibition_models(substrate, inhibitor, velocity) -> pd.DataFrame:
    """Compare competitive, noncompetitive, uncompetitive and mixed fits."""

    rows = []
    for model in ("competitive", "noncompetitive", "uncompetitive", "mixed"):
        try:
            result = global_inhibition_fit(substrate, inhibitor, velocity, model=model)
            rows.append({
                "model": model,
                "aicc": result["aicc"],
                "aic": result["aic"],
                "r_squared": result["r_squared"],
                "rmse": result["rmse"],
                "covariance_ok": result["covariance_ok"],
                "parameters": result["parameters"],
                "status": "Fitted",
                "error": "",
            })
        except Exception as exc:
            rows.append({"model": model, "aicc": np.inf, "aic": np.inf, "r_squared": np.nan, "rmse": np.nan, "covariance_ok": False, "parameters": {}, "status": "Blocked", "error": str(exc)})
    table = pd.DataFrame(rows).sort_values(["aicc", "rmse"], na_position="last").reset_index(drop=True)
    if np.isfinite(table["aicc"]).any():
        minimum = table.loc[np.isfinite(table["aicc"]), "aicc"].min()
        table["delta_aicc"] = table["aicc"] - minimum
    else:
        table["delta_aicc"] = np.nan
    return table










def global_inhibition_fit(
    substrate,
    inhibitor,
    velocity,
    *,
    model: str = "competitive",
) -> dict[str, object]:
    from scipy.optimize import curve_fit

    """Fit shared Vmax/Km/Ki inhibition models across inhibitor concentrations."""
    s = np.asarray(substrate, dtype=float)
    i = np.asarray(inhibitor, dtype=float)
    v = np.asarray(velocity, dtype=float)
    valid = np.isfinite(s) & np.isfinite(i) & np.isfinite(v) & (s > 0) & (i >= 0) & (v >= 0)
    s, i, v = s[valid], i[valid], v[valid]
    if len(s) < 8 or len(np.unique(i)) < 2:
        raise ValueError("Global inhibition fitting requires at least eight observations and two inhibitor levels.")

    if model == "competitive":
        def func(x, vmax, km, ki):
            substrate_values, inhibitor_values = x
            return vmax * substrate_values / (km * (1 + inhibitor_values / ki) + substrate_values)

        names = ["vmax", "km", "ki"]
        p0 = [v.max(), np.median(s), max(np.median(i[i > 0]) if np.any(i > 0) else 1.0, 1e-6)]
        bounds = ([0, 1e-12, 1e-12], [np.inf, np.inf, np.inf])
    elif model == "noncompetitive":
        def func(x, vmax, km, ki):
            substrate_values, inhibitor_values = x
            return vmax * substrate_values / ((km + substrate_values) * (1 + inhibitor_values / ki))

        names = ["vmax", "km", "ki"]
        p0 = [v.max(), np.median(s), max(np.median(i[i > 0]) if np.any(i > 0) else 1.0, 1e-6)]
        bounds = ([0, 1e-12, 1e-12], [np.inf, np.inf, np.inf])
    elif model == "uncompetitive":
        def func(x, vmax, km, ki):
            substrate_values, inhibitor_values = x
            alpha_prime = 1 + inhibitor_values / ki
            return vmax * substrate_values / (km + alpha_prime * substrate_values)

        names = ["vmax", "km", "ki"]
        p0 = [v.max(), np.median(s), max(np.median(i[i > 0]) if np.any(i > 0) else 1.0, 1e-6)]
        bounds = ([0, 1e-12, 1e-12], [np.inf, np.inf, np.inf])
    elif model == "mixed":
        def func(x, vmax, km, ki_competitive, ki_uncompetitive):
            substrate_values, inhibitor_values = x
            alpha = 1 + inhibitor_values / ki_competitive
            alpha_prime = 1 + inhibitor_values / ki_uncompetitive
            return vmax * substrate_values / (alpha * km + alpha_prime * substrate_values)

        names = ["vmax", "km", "ki_competitive", "ki_uncompetitive"]
        initial_ki = max(np.median(i[i > 0]) if np.any(i > 0) else 1.0, 1e-6)
        p0 = [v.max(), np.median(s), initial_ki, initial_ki]
        bounds = ([0, 1e-12, 1e-12, 1e-12], [np.inf, np.inf, np.inf, np.inf])
    else:
        raise ValueError("Inhibition model must be competitive, noncompetitive, uncompetitive or mixed.")
    params, covariance = curve_fit(func, (s, i), v, p0=p0, bounds=bounds, maxfev=100_000)
    predicted = func((s, i), *params)
    payload = _fit_payload(model, dict(zip(names, map(float, params))), v, predicted, len(params), covariance_ok=bool(np.all(np.isfinite(covariance))))
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
    return {
        "model": model,
        "parameters": payload.parameters,
        "standard_errors": dict(zip(names, map(float, standard_errors))),
        "r_squared": payload.r_squared,
        "rmse": payload.rmse,
        "aic": payload.aic,
        "aicc": payload.aicc,
        "parameter_count": payload.parameter_count,
        "covariance_ok": payload.covariance_ok,
        "predicted_velocity": payload.predicted,
        "residuals": payload.residuals,
    }


















