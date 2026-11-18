from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

BOUNDARY = (
    "Research software output only. These calculations do not diagnose disease, "
    "select treatment, replace neurological examination, or establish clinical validity."
)


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output.columns = [
        str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for column in output.columns
    ]
    return output


def _require(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))


def _as_bool(series: pd.Series) -> pd.Series:
    truthy = {"1", "true", "yes", "y", "present", "positive", "current"}
    return series.fillna(False).map(
        lambda value: bool(value)
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in truthy
    )


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _cohens_d(left: pd.Series, right: pd.Series) -> float:
    a = _numeric(left).dropna().to_numpy(float)
    b = _numeric(right).dropna().to_numpy(float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = ((len(a) - 1) * np.var(a, ddof=1) + (len(b) - 1) * np.var(b, ddof=1)) / max(len(a) + len(b) - 2, 1)
    if pooled <= 0 or not math.isfinite(pooled):
        return 0.0
    return float((np.mean(b) - np.mean(a)) / math.sqrt(pooled))


def _rank_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    mask = np.isfinite(scores)
    labels = labels[mask]
    scores = scores[mask]
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(scores).rank(method="average").to_numpy(float)
    rank_sum = float(ranks[labels == 1].sum())
    return float((rank_sum - positives * (positives + 1) / 2) / (positives * negatives))


def _bh_fdr(pvalues: pd.Series) -> pd.Series:
    values = pd.to_numeric(pvalues, errors="coerce").to_numpy(float)
    valid = np.isfinite(values)
    result = np.full(len(values), np.nan)
    if not valid.any():
        return pd.Series(result, index=pvalues.index)
    valid_values = values[valid]
    order = np.argsort(valid_values)
    ranked = valid_values[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    restored = np.empty_like(adjusted)
    restored[order] = adjusted
    result[np.where(valid)[0]] = restored
    return pd.Series(result, index=pvalues.index)


def _normal_approx_pvalue(effect: float, n_left: int, n_right: int) -> float:
    if not math.isfinite(effect) or n_left < 2 or n_right < 2:
        return float("nan")
    standard_error = math.sqrt(1 / n_left + 1 / n_right + effect * effect / (2 * max(n_left + n_right - 2, 1)))
    if standard_error <= 0:
        return 1.0
    z = abs(effect) / standard_error
    return float(math.erfc(z / math.sqrt(2.0)))


def neurovascular_research_profile(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("age", "systolic_bp", "diastolic_bp"))
    if frame.empty:
        raise ValueError("Neurovascular dataset is empty.")
    frame = frame.copy()
    frame["subject_id"] = frame.get("subject_id", pd.Series([f"subject_{i+1}" for i in range(len(frame))]))
    for column in ("age", "systolic_bp", "diastolic_bp", "ldl", "hba1c"):
        if column in frame:
            frame[column] = _numeric(frame[column])
    for column in ("smoking", "atrial_fibrillation", "afib"):
        if column in frame:
            frame[column] = _as_bool(frame[column])
    afib = frame["atrial_fibrillation"] if "atrial_fibrillation" in frame else frame.get("afib", False)
    if isinstance(afib, bool):
        afib = pd.Series([afib] * len(frame), index=frame.index)
    smoking = frame.get("smoking", pd.Series([False] * len(frame), index=frame.index))
    pulse_pressure = frame["systolic_bp"] - frame["diastolic_bp"]
    age_points = np.select([frame["age"] >= 75, frame["age"] >= 65, frame["age"] >= 55], [3, 2, 1], default=0)
    sbp_points = np.select([frame["systolic_bp"] >= 160, frame["systolic_bp"] >= 140, frame["systolic_bp"] >= 130], [3, 2, 1], default=0)
    dbp_points = (frame["diastolic_bp"] >= 90).astype(int)
    ldl_points = (frame.get("ldl", pd.Series(np.nan, index=frame.index)) >= 160).fillna(False).astype(int)
    hba1c_points = (frame.get("hba1c", pd.Series(np.nan, index=frame.index)) >= 6.5).fillna(False).astype(int)
    smoking_points = smoking.astype(int)
    afib_points = afib.astype(int) * 2
    pulse_points = (pulse_pressure >= 60).fillna(False).astype(int)
    score = age_points + sbp_points + dbp_points + ldl_points + hba1c_points + smoking_points + afib_points + pulse_points
    completeness_columns = [column for column in ("age", "systolic_bp", "diastolic_bp", "ldl", "hba1c", "smoking", "atrial_fibrillation", "afib") if column in frame]
    completeness = 1.0 - frame[completeness_columns].isna().mean(axis=1) if completeness_columns else pd.Series(0.0, index=frame.index)
    output = pd.DataFrame(
        {
            "subject_id": frame["subject_id"].astype(str),
            "research_score": score.astype(int),
            "research_band": pd.cut(score, [-1, 2, 5, np.inf], labels=["lower", "moderate", "higher"]).astype(str),
            "pulse_pressure": pulse_pressure,
            "data_completeness": completeness,
            "age_points": age_points,
            "blood_pressure_points": sbp_points + dbp_points + pulse_points,
            "metabolic_points": ldl_points + hba1c_points,
            "smoking_points": smoking_points,
            "atrial_fibrillation_points": afib_points,
        }
    )
    factor_summary = pd.DataFrame(
        [
            {"factor": "Age", "flagged_subjects": int((age_points > 0).sum()), "mean_points": float(np.mean(age_points))},
            {"factor": "Blood pressure / pulse pressure", "flagged_subjects": int(((sbp_points + dbp_points + pulse_points) > 0).sum()), "mean_points": float(np.mean(sbp_points + dbp_points + pulse_points))},
            {"factor": "Metabolic", "flagged_subjects": int(((ldl_points + hba1c_points) > 0).sum()), "mean_points": float(np.mean(ldl_points + hba1c_points))},
            {"factor": "Smoking", "flagged_subjects": int((smoking_points > 0).sum()), "mean_points": float(np.mean(smoking_points))},
            {"factor": "Atrial fibrillation", "flagged_subjects": int((afib_points > 0).sum()), "mean_points": float(np.mean(afib_points))},
        ]
    )
    return {
        "subject_scores": output.sort_values(["research_score", "subject_id"], ascending=[False, True]).reset_index(drop=True),
        "factor_summary": factor_summary,
        "cohort_summary": {
            "subjects": int(len(output)),
            "higher_band": int((output["research_band"] == "higher").sum()),
            "median_score": float(output["research_score"].median()),
            "median_completeness": float(output["data_completeness"].median()),
        },
        "methodology": "Transparent point-based research triage from uploaded vascular factors; not a validated stroke score.",
        "scientific_boundary": BOUNDARY,
    }


def sleep_circadian_profile(
    data: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
    activity_col: str = "activity",
    heart_rate_col: str | None = "heart_rate",
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    timestamp_col = timestamp_col.lower().replace(" ", "_")
    activity_col = activity_col.lower().replace(" ", "_")
    heart_rate_col = heart_rate_col.lower().replace(" ", "_") if heart_rate_col else None
    _require(frame, (timestamp_col, activity_col))
    frame = frame.copy()
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], errors="coerce")
    frame[activity_col] = _numeric(frame[activity_col])
    frame = frame.dropna(subset=[timestamp_col, activity_col]).sort_values(timestamp_col)
    if len(frame) < 48:
        raise ValueError("At least 48 valid time points are required for circadian analysis.")
    if heart_rate_col and heart_rate_col in frame:
        frame[heart_rate_col] = _numeric(frame[heart_rate_col])
    deltas = frame[timestamp_col].diff().dt.total_seconds().dropna()
    interval_seconds = float(deltas.median()) if not deltas.empty else float("nan")
    frame["date"] = frame[timestamp_col].dt.date.astype(str)
    frame["hour"] = frame[timestamp_col].dt.hour
    activity = frame[activity_col].to_numpy(float)
    variance = float(np.nanvar(activity))
    hourly = frame.groupby("hour", as_index=False).agg(
        mean_activity=(activity_col, "mean"),
        median_activity=(activity_col, "median"),
        observations=(activity_col, "size"),
    )
    if heart_rate_col and heart_rate_col in frame:
        hr = frame.groupby("hour", as_index=False)[heart_rate_col].mean().rename(columns={heart_rate_col: "mean_heart_rate"})
        hourly = hourly.merge(hr, on="hour", how="left")
    daily = frame.groupby("date", as_index=False).agg(
        mean_activity=(activity_col, "mean"),
        activity_sd=(activity_col, "std"),
        observations=(activity_col, "size"),
    )
    low_threshold = float(np.nanquantile(activity, 0.20))
    frame["low_activity"] = frame[activity_col] <= low_threshold
    daily_low = frame.groupby("date", as_index=False)["low_activity"].mean().rename(columns={"low_activity": "low_activity_fraction"})
    daily = daily.merge(daily_low, on="date", how="left")
    hourly_variance = float(np.nanvar(hourly["mean_activity"].to_numpy(float)))
    interdaily_stability = float(np.clip(hourly_variance / variance, 0.0, 1.0)) if variance > 0 else 0.0
    squared_diff = np.diff(activity) ** 2
    intradaily_variability = float(np.nanmean(squared_diff) / variance) if variance > 0 and len(squared_diff) else 0.0
    acrophase_hour = int(hourly.loc[hourly["mean_activity"].idxmax(), "hour"])
    bathyphase_hour = int(hourly.loc[hourly["mean_activity"].idxmin(), "hour"])
    amplitude = float(hourly["mean_activity"].max() - hourly["mean_activity"].min())
    night = frame[frame["hour"].isin([22, 23, 0, 1, 2, 3, 4, 5])]
    night_rest_fraction = float(night["low_activity"].mean()) if not night.empty else float("nan")
    flags: list[str] = []
    if intradaily_variability > 2.0:
        flags.append("High rhythm fragmentation proxy")
    if interdaily_stability < 0.20:
        flags.append("Low day-to-day rhythm stability")
    if math.isfinite(night_rest_fraction) and night_rest_fraction < 0.50:
        flags.append("Low night-time rest consistency")
    return {
        "hourly_profile": hourly,
        "daily_summary": daily,
        "metrics": {
            "observations": int(len(frame)),
            "days": int(frame["date"].nunique()),
            "median_interval_seconds": interval_seconds,
            "interdaily_stability": interdaily_stability,
            "intradaily_variability": intradaily_variability,
            "acrophase_hour": acrophase_hour,
            "bathyphase_hour": bathyphase_hour,
            "activity_amplitude": amplitude,
            "night_rest_fraction": night_rest_fraction,
        },
        "flags": flags,
        "scientific_boundary": BOUNDARY + " Sleep windows are actigraphy-like heuristics, not polysomnography staging.",
    }


def fluid_biomarker_panel(
    data: pd.DataFrame,
    *,
    group_col: str = "group",
    positive_group: str | None = None,
    bootstrap_iterations: int = 200,
    seed: int = 207,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    group_col = group_col.lower().replace(" ", "_")
    _require(frame, (group_col,))
    groups = [str(value) for value in frame[group_col].dropna().astype(str).unique()]
    if len(groups) != 2:
        raise ValueError("Biomarker panel analysis requires exactly two non-empty groups.")
    positive_group = str(positive_group) if positive_group is not None else groups[-1]
    negative_group = next(group for group in groups if group != positive_group)
    labels = (frame[group_col].astype(str) == positive_group).astype(int).to_numpy()
    numeric_columns = [
        column
        for column in frame.select_dtypes(include=[np.number]).columns
        if column not in {group_col}
        and not column.endswith("_id")
    ]
    if not numeric_columns:
        raise ValueError("No numeric biomarker columns were found.")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    oriented_scores: dict[str, pd.Series] = {}
    for column in numeric_columns:
        values = _numeric(frame[column])
        left = values[frame[group_col].astype(str) == negative_group]
        right = values[frame[group_col].astype(str) == positive_group]
        effect = _cohens_d(left, right)
        auc = _rank_auc(labels, values.to_numpy(float))
        direction = 1.0
        adjusted_auc = auc
        if math.isfinite(auc) and auc < 0.5:
            adjusted_auc = 1.0 - auc
            direction = -1.0
        boot: list[float] = []
        valid_index = np.where(values.notna().to_numpy())[0]
        if len(valid_index) >= 8:
            for _ in range(max(20, min(int(bootstrap_iterations), 2000))):
                sampled = rng.choice(valid_index, size=len(valid_index), replace=True)
                auc_value = _rank_auc(labels[sampled], values.to_numpy(float)[sampled])
                if math.isfinite(auc_value):
                    boot.append(max(auc_value, 1.0 - auc_value))
        ci_low, ci_high = (float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))) if boot else (float("nan"), float("nan"))
        pvalue = _normal_approx_pvalue(effect, int(left.notna().sum()), int(right.notna().sum()))
        rows.append(
            {
                "biomarker": column,
                "negative_group_mean": float(left.mean()) if left.notna().any() else np.nan,
                "positive_group_mean": float(right.mean()) if right.notna().any() else np.nan,
                "cohens_d": effect,
                "direction_adjusted_auc": adjusted_auc,
                "bootstrap_auc_ci_low": ci_low,
                "bootstrap_auc_ci_high": ci_high,
                "missing_fraction": float(values.isna().mean()),
                "pvalue_normal_approx": pvalue,
            }
        )
        standardized = (values - values.mean()) / (values.std(ddof=1) or 1.0)
        oriented_scores[column] = standardized * direction
    ranking = pd.DataFrame(rows)
    ranking["fdr_bh"] = _bh_fdr(ranking["pvalue_normal_approx"])
    ranking["panel_priority"] = (
        ranking["direction_adjusted_auc"].fillna(0.5)
        * (1.0 - ranking["missing_fraction"].clip(0, 1))
        * np.minimum(3.0, ranking["cohens_d"].abs().fillna(0.0))
    )
    ranking = ranking.sort_values(["panel_priority", "biomarker"], ascending=[False, True]).reset_index(drop=True)
    selected = ranking.loc[(ranking["direction_adjusted_auc"] >= 0.65) & (ranking["missing_fraction"] <= 0.30), "biomarker"].head(10).tolist()
    if not selected:
        selected = ranking["biomarker"].head(min(3, len(ranking))).tolist()
    score_frame = pd.DataFrame({column: oriented_scores[column] for column in selected})
    panel_score = score_frame.mean(axis=1, skipna=True)
    sample_scores = pd.DataFrame(
        {
            "sample_id": frame.get("sample_id", pd.Series([f"sample_{i+1}" for i in range(len(frame))])).astype(str),
            "group": frame[group_col].astype(str),
            "panel_score": panel_score,
            "available_selected_biomarkers": score_frame.notna().sum(axis=1),
        }
    )
    return {
        "biomarker_ranking": ranking,
        "sample_scores": sample_scores,
        "selected_biomarkers": selected,
        "panel_auc_internal": _rank_auc(labels, panel_score.to_numpy(float)),
        "group_mapping": {"negative": negative_group, "positive": positive_group},
        "scientific_boundary": BOUNDARY + " Biomarker performance is internal and requires an independent cohort.",
    }


def digital_neurology_sensor_analysis(
    data: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
    window_seconds: float = 10.0,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    timestamp_col = timestamp_col.lower().replace(" ", "_")
    _require(frame, (timestamp_col,))
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], errors="coerce")
    frame = frame.dropna(subset=[timestamp_col]).sort_values(timestamp_col).reset_index(drop=True)
    if len(frame) < 32:
        raise ValueError("At least 32 timestamped observations are required.")
    accel_columns = [column for column in ("accel_x", "accel_y", "accel_z") if column in frame]
    if len(accel_columns) == 3:
        accel = frame[accel_columns].apply(pd.to_numeric, errors="coerce").interpolate(limit_direction="both")
        magnitude = np.sqrt((accel**2).sum(axis=1))
    elif "acceleration" in frame:
        magnitude = _numeric(frame["acceleration"]).interpolate(limit_direction="both")
    elif "gait_speed" in frame:
        magnitude = _numeric(frame["gait_speed"]).interpolate(limit_direction="both")
    else:
        raise ValueError("Provide accel_x/accel_y/accel_z, acceleration, or gait_speed.")
    seconds = (frame[timestamp_col] - frame[timestamp_col].iloc[0]).dt.total_seconds()
    deltas = seconds.diff().dropna()
    median_dt = float(deltas.median()) if not deltas.empty else 1.0
    sampling_rate = 1.0 / median_dt if median_dt > 0 else float("nan")
    magnitude = pd.Series(magnitude, index=frame.index, dtype=float)
    jerk = magnitude.diff() / max(median_dt, 1e-9)
    frame["signal_magnitude"] = magnitude
    frame["jerk"] = jerk
    frame["window_id"] = np.floor(seconds / max(float(window_seconds), median_dt)).astype(int)
    windows = frame.groupby("window_id", as_index=False).agg(
        start_time=(timestamp_col, "min"),
        end_time=(timestamp_col, "max"),
        mean_magnitude=("signal_magnitude", "mean"),
        magnitude_sd=("signal_magnitude", "std"),
        mean_abs_jerk=("jerk", lambda x: float(np.nanmean(np.abs(x)))),
        observations=("signal_magnitude", "size"),
    )
    if "gait_speed" in frame:
        frame["gait_speed"] = _numeric(frame["gait_speed"])
        speed = frame.groupby("window_id")["gait_speed"].mean()
        windows = windows.merge(speed.rename("mean_gait_speed"), on="window_id", how="left")
    low_motion = float(windows["mean_magnitude"].quantile(0.15))
    high_jerk = float(windows["mean_abs_jerk"].quantile(0.85))
    candidate = windows.loc[(windows["mean_magnitude"] <= low_motion) & (windows["mean_abs_jerk"] >= high_jerk)].copy()
    candidate["event_type"] = "low-motion/high-jerk candidate"
    candidate["review_required"] = True
    dominant_frequency = float("nan")
    tremor_ratio = float("nan")
    if math.isfinite(sampling_rate) and sampling_rate > 1 and len(magnitude) >= 64:
        centered = magnitude.to_numpy(float) - float(magnitude.mean())
        frequencies = np.fft.rfftfreq(len(centered), d=1.0 / sampling_rate)
        power = np.abs(np.fft.rfft(centered)) ** 2
        valid = frequencies > 0
        if valid.any():
            dominant_frequency = float(frequencies[valid][np.argmax(power[valid])])
            total_power = float(power[valid].sum())
            band = (frequencies >= 3.0) & (frequencies <= 8.0)
            tremor_ratio = float(power[band].sum() / total_power) if total_power > 0 else 0.0
    gait_cv = float("nan")
    if "gait_speed" in frame and frame["gait_speed"].notna().sum() > 2:
        mean_speed = float(frame["gait_speed"].mean())
        gait_cv = float(frame["gait_speed"].std(ddof=1) / abs(mean_speed)) if abs(mean_speed) > 1e-12 else float("nan")
    return {
        "window_metrics": windows,
        "candidate_events": candidate.reset_index(drop=True),
        "summary": {
            "observations": int(len(frame)),
            "duration_seconds": float(seconds.iloc[-1]),
            "sampling_rate_hz": sampling_rate,
            "dominant_frequency_hz": dominant_frequency,
            "tremor_band_power_ratio_3_8hz": tremor_ratio,
            "gait_speed_cv": gait_cv,
            "candidate_events": int(len(candidate)),
        },
        "scientific_boundary": BOUNDARY + " Candidate events are signal heuristics, not validated freezing, tremor, fall or gait diagnoses.",
    }


def neuroimmune_interaction_analysis(
    data: pd.DataFrame,
    *,
    condition_col: str = "condition",
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    condition_col = condition_col.lower().replace(" ", "_")
    _require(frame, ("cell_type", "pathway", "score", condition_col))
    frame["score"] = _numeric(frame["score"])
    frame = frame.dropna(subset=["cell_type", "pathway", "score", condition_col])
    groups = [str(value) for value in frame[condition_col].astype(str).unique()]
    if len(groups) != 2:
        raise ValueError("Neuroimmune comparison requires exactly two conditions.")
    control, case = groups[0], groups[1]
    rows: list[dict[str, Any]] = []
    for (cell_type, pathway), subset in frame.groupby(["cell_type", "pathway"]):
        left = subset.loc[subset[condition_col].astype(str) == control, "score"]
        right = subset.loc[subset[condition_col].astype(str) == case, "score"]
        if left.notna().sum() < 2 or right.notna().sum() < 2:
            continue
        effect = _cohens_d(left, right)
        rows.append(
            {
                "cell_type": str(cell_type),
                "pathway": str(pathway),
                "control_mean": float(left.mean()),
                "case_mean": float(right.mean()),
                "mean_difference": float(right.mean() - left.mean()),
                "cohens_d": effect,
                "pvalue_normal_approx": _normal_approx_pvalue(effect, int(left.notna().sum()), int(right.notna().sum())),
                "control_n": int(left.notna().sum()),
                "case_n": int(right.notna().sum()),
            }
        )
    differential = pd.DataFrame(rows)
    if differential.empty:
        raise ValueError("No cell-type/pathway combinations had enough observations in both conditions.")
    differential["fdr_bh"] = _bh_fdr(differential["pvalue_normal_approx"])
    differential["priority"] = differential["cohens_d"].abs() * -np.log10(differential["fdr_bh"].clip(lower=1e-12))
    differential = differential.sort_values(["priority", "cell_type", "pathway"], ascending=[False, True, True]).reset_index(drop=True)
    network_edges = differential.rename(columns={"cell_type": "source", "pathway": "target", "mean_difference": "weight"})[
        ["source", "target", "weight", "cohens_d", "fdr_bh", "priority"]
    ]
    cell_summary = differential.groupby("cell_type", as_index=False).agg(
        pathways=("pathway", "size"),
        mean_absolute_effect=("cohens_d", lambda x: float(np.nanmean(np.abs(x)))),
        strongest_priority=("priority", "max"),
    ).sort_values("strongest_priority", ascending=False)
    return {
        "differential_interactions": differential,
        "network_edges": network_edges,
        "cell_type_summary": cell_summary,
        "condition_mapping": {"control": control, "case": case},
        "scientific_boundary": BOUNDARY + " Cell-state scores must come from a separately validated preprocessing workflow.",
    }


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, np.ndarray, float]:
    if len(x) < 2 or np.ptp(x) <= 0:
        return 0.0, float(np.mean(y)), np.full_like(y, np.mean(y), dtype=float), 0.0
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    sse = float(np.sum((y - fitted) ** 2))
    return float(slope), float(intercept), fitted, sse


def cognitive_trajectory_analysis(
    data: pd.DataFrame,
    *,
    higher_is_better: bool = True,
    rapid_change_per_year: float = 2.0,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("subject_id", "time_months", "score"))
    frame["time_months"] = _numeric(frame["time_months"])
    frame["score"] = _numeric(frame["score"])
    frame["domain"] = frame.get("domain", "global").astype(str) if isinstance(frame.get("domain", "global"), pd.Series) else "global"
    frame = frame.dropna(subset=["subject_id", "time_months", "score"]).sort_values(["subject_id", "domain", "time_months"])
    summaries: list[dict[str, Any]] = []
    fitted_rows: list[pd.DataFrame] = []
    change_rows: list[dict[str, Any]] = []
    for (subject, domain), subset in frame.groupby(["subject_id", "domain"]):
        subset = subset.sort_values("time_months").copy()
        x = subset["time_months"].to_numpy(float)
        y = subset["score"].to_numpy(float)
        if len(subset) < 2:
            continue
        slope_month, intercept, fitted, base_sse = _linear_fit(x, y)
        subset["fitted_score"] = fitted
        fitted_rows.append(subset)
        best_index = None
        best_sse = base_sse
        if len(subset) >= 5:
            for index in range(2, len(subset) - 2):
                _, _, _, left_sse = _linear_fit(x[: index + 1], y[: index + 1])
                _, _, _, right_sse = _linear_fit(x[index:], y[index:])
                if left_sse + right_sse < best_sse * 0.75:
                    best_sse = left_sse + right_sse
                    best_index = index
        annual_slope = slope_month * 12.0
        oriented_change = annual_slope if higher_is_better else -annual_slope
        rapid_decline = oriented_change <= -abs(float(rapid_change_per_year))
        summaries.append(
            {
                "subject_id": str(subject),
                "domain": str(domain),
                "observations": int(len(subset)),
                "baseline_score": float(y[0]),
                "last_score": float(y[-1]),
                "annualized_slope": annual_slope,
                "rapid_decline_flag": bool(rapid_decline),
                "fit_sse": base_sse,
            }
        )
        if best_index is not None:
            change_rows.append(
                {
                    "subject_id": str(subject),
                    "domain": str(domain),
                    "change_time_months": float(x[best_index]),
                    "single_line_sse": base_sse,
                    "piecewise_sse": best_sse,
                    "relative_sse_improvement": float(1.0 - best_sse / max(base_sse, 1e-12)),
                }
            )
    summary = pd.DataFrame(summaries)
    if summary.empty:
        raise ValueError("At least two valid observations per subject/domain are required.")
    trajectories = pd.concat(fitted_rows, ignore_index=True) if fitted_rows else pd.DataFrame()
    changes = pd.DataFrame(change_rows)
    return {
        "subject_trajectories": trajectories,
        "subject_summary": summary.sort_values(["rapid_decline_flag", "annualized_slope"], ascending=[False, True]).reset_index(drop=True),
        "candidate_change_points": changes,
        "cohort_summary": {
            "subject_domain_series": int(len(summary)),
            "rapid_decline_flags": int(summary["rapid_decline_flag"].sum()),
            "median_annualized_slope": float(summary["annualized_slope"].median()),
        },
        "scientific_boundary": BOUNDARY + " Change points and slopes require clinical context, practice-effect review and validated instruments.",
    }


def neurorehabilitation_response_analysis(
    data: pd.DataFrame,
    *,
    baseline_col: str = "baseline",
    followup_col: str = "followup",
    higher_is_better: bool = True,
    mcid: float = 3.0,
    reliability: float = 0.90,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    baseline_col = baseline_col.lower().replace(" ", "_")
    followup_col = followup_col.lower().replace(" ", "_")
    _require(frame, (baseline_col, followup_col))
    frame[baseline_col] = _numeric(frame[baseline_col])
    frame[followup_col] = _numeric(frame[followup_col])
    frame["subject_id"] = frame.get("subject_id", pd.Series([f"subject_{i+1}" for i in range(len(frame))])).astype(str)
    frame = frame.dropna(subset=[baseline_col, followup_col]).copy()
    if frame.empty:
        raise ValueError("No complete baseline/follow-up pairs were found.")
    raw_change = frame[followup_col] - frame[baseline_col]
    oriented = raw_change if higher_is_better else -raw_change
    baseline_sd = float(frame[baseline_col].std(ddof=1)) if len(frame) > 1 else 0.0
    standard_error_measurement = baseline_sd * math.sqrt(max(0.0, 1.0 - float(reliability)))
    rci_denominator = math.sqrt(2.0) * standard_error_measurement
    rci = oriented / rci_denominator if rci_denominator > 0 else pd.Series(np.nan, index=frame.index)
    response = pd.DataFrame(
        {
            "subject_id": frame["subject_id"],
            "baseline": frame[baseline_col],
            "followup": frame[followup_col],
            "raw_change": raw_change,
            "oriented_improvement": oriented,
            "percent_change": 100.0 * raw_change / frame[baseline_col].replace(0, np.nan).abs(),
            "reliable_change_index": rci,
            "meets_mcid": oriented >= abs(float(mcid)),
            "reliable_improvement": rci >= 1.96,
            "reliable_deterioration": rci <= -1.96,
        }
    )
    response["response_class"] = np.select(
        [response["reliable_improvement"] & response["meets_mcid"], response["reliable_deterioration"], response["meets_mcid"]],
        ["reliable responder", "reliable deterioration", "MCID responder"],
        default="no clear change",
    )
    return {
        "participant_response": response.sort_values("oriented_improvement", ascending=False).reset_index(drop=True),
        "summary": {
            "participants": int(len(response)),
            "mcid_responders": int(response["meets_mcid"].sum()),
            "reliable_responders": int((response["response_class"] == "reliable responder").sum()),
            "reliable_deterioration": int(response["reliable_deterioration"].sum()),
            "median_oriented_improvement": float(response["oriented_improvement"].median()),
            "baseline_sd": baseline_sd,
            "standard_error_measurement": standard_error_measurement,
        },
        "parameters": {"higher_is_better": higher_is_better, "mcid": float(mcid), "reliability": float(reliability)},
        "scientific_boundary": BOUNDARY + " MCID and reliability must match the specific validated assessment instrument.",
    }


def polypharmacy_cns_burden(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("subject_id", "medication"))
    burden_columns = {
        "anticholinergic_burden": 0.0,
        "sedation_burden": 0.0,
        "qt_risk": 0.0,
        "serotonergic": 0.0,
        "seizure_threshold_risk": 0.0,
        "orthostatic_risk": 0.0,
    }
    for column, default in burden_columns.items():
        if column not in frame:
            frame[column] = default
        if column in {"serotonergic"}:
            frame[column] = _as_bool(frame[column]).astype(float)
        else:
            frame[column] = _numeric(frame[column]).fillna(default).clip(lower=0)
    frame["subject_id"] = frame["subject_id"].astype(str)
    frame["medication"] = frame["medication"].astype(str)
    aggregation = frame.groupby("subject_id", as_index=False).agg(
        medications=("medication", "nunique"),
        anticholinergic_burden=("anticholinergic_burden", "sum"),
        sedation_burden=("sedation_burden", "sum"),
        qt_risk=("qt_risk", "sum"),
        serotonergic_agents=("serotonergic", "sum"),
        seizure_threshold_risk=("seizure_threshold_risk", "sum"),
        orthostatic_risk=("orthostatic_risk", "sum"),
    )
    aggregation["composite_burden"] = (
        aggregation["anticholinergic_burden"]
        + aggregation["sedation_burden"]
        + aggregation["qt_risk"]
        + aggregation["serotonergic_agents"]
        + aggregation["seizure_threshold_risk"]
        + aggregation["orthostatic_risk"]
    )
    aggregation["burden_band"] = pd.cut(
        aggregation["composite_burden"], [-1, 3, 7, np.inf], labels=["lower", "moderate", "higher"]
    ).astype(str)
    flags: list[dict[str, Any]] = []
    for row in aggregation.itertuples(index=False):
        checks = [
            (row.medications >= 5, "polypharmacy_5_or_more", row.medications),
            (row.anticholinergic_burden >= 3, "anticholinergic_burden", row.anticholinergic_burden),
            (row.sedation_burden >= 3, "sedation_burden", row.sedation_burden),
            (row.qt_risk >= 2, "multiple_qt_risk_annotations", row.qt_risk),
            (row.serotonergic_agents >= 2, "multiple_serotonergic_annotations", row.serotonergic_agents),
            (row.seizure_threshold_risk >= 2, "seizure_threshold_burden", row.seizure_threshold_risk),
            (row.orthostatic_risk >= 2, "orthostatic_burden", row.orthostatic_risk),
        ]
        for triggered, flag, value in checks:
            if triggered:
                flags.append({"subject_id": row.subject_id, "flag": flag, "value": float(value), "review_required": True})
    medication_summary = frame.groupby("medication", as_index=False).agg(
        subjects=("subject_id", "nunique"),
        mean_anticholinergic=("anticholinergic_burden", "mean"),
        mean_sedation=("sedation_burden", "mean"),
        mean_qt_risk=("qt_risk", "mean"),
    ).sort_values("subjects", ascending=False)
    return {
        "subject_burden": aggregation.sort_values("composite_burden", ascending=False).reset_index(drop=True),
        "interaction_flags": pd.DataFrame(flags),
        "medication_summary": medication_summary,
        "scientific_boundary": BOUNDARY + " Burden annotations must be supplied or reviewed by qualified medication-safety sources.",
    }


def _global_efficiency(adjacency: np.ndarray) -> float:
    n = int(adjacency.shape[0])
    if n < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for source in range(n):
        distances = np.full(n, np.inf)
        distances[source] = 0
        queue: deque[int] = deque([source])
        while queue:
            node = queue.popleft()
            for neighbour in np.where(adjacency[node] > 0)[0]:
                if not math.isfinite(distances[neighbour]):
                    distances[neighbour] = distances[node] + 1
                    queue.append(int(neighbour))
        for target in range(source + 1, n):
            pairs += 1
            if math.isfinite(distances[target]) and distances[target] > 0:
                total += 1.0 / distances[target]
    return float(total / pairs) if pairs else 0.0


def brain_network_vulnerability_analysis(
    connectivity: pd.DataFrame,
    *,
    threshold: float = 0.30,
    max_nodes: int = 200,
) -> dict[str, Any]:
    matrix = connectivity.copy()
    if matrix.empty:
        raise ValueError("Connectivity matrix is empty.")
    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError("Connectivity input must be a square matrix.")
    if matrix.shape[0] > max_nodes:
        raise ValueError(f"Interactive network analysis supports at most {max_nodes} nodes.")
    if list(matrix.index.astype(str)) != list(matrix.columns.astype(str)):
        if matrix.index.equals(pd.RangeIndex(len(matrix))):
            matrix.index = matrix.columns.astype(str)
        else:
            matrix.index = matrix.index.astype(str)
            matrix.columns = matrix.columns.astype(str)
            if set(matrix.index) != set(matrix.columns):
                raise ValueError("Connectivity matrix row and column labels must represent the same nodes.")
            matrix = matrix.loc[matrix.columns, matrix.columns]
    values = matrix.apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(float)
    np.fill_diagonal(values, 0.0)
    absolute = np.abs(values)
    adjacency = (absolute >= abs(float(threshold))).astype(int)
    np.fill_diagonal(adjacency, 0)
    degree = adjacency.sum(axis=1).astype(float)
    strength = (absolute * adjacency).sum(axis=1)
    vector = np.ones(len(matrix), dtype=float) / math.sqrt(len(matrix))
    for _ in range(100):
        updated = absolute @ vector
        norm = float(np.linalg.norm(updated))
        if norm <= 0:
            break
        updated /= norm
        if np.linalg.norm(updated - vector) < 1e-8:
            vector = updated
            break
        vector = updated
    clustering: list[float] = []
    for node in range(len(matrix)):
        neighbours = np.where(adjacency[node] > 0)[0]
        k = len(neighbours)
        if k < 2:
            clustering.append(0.0)
            continue
        links = adjacency[np.ix_(neighbours, neighbours)].sum() / 2.0
        clustering.append(float(2.0 * links / (k * (k - 1))))
    baseline_efficiency = _global_efficiency(adjacency)
    vulnerability: list[float] = []
    for node in range(len(matrix)):
        reduced = np.delete(np.delete(adjacency, node, axis=0), node, axis=1)
        reduced_efficiency = _global_efficiency(reduced)
        vulnerability.append(float((baseline_efficiency - reduced_efficiency) / max(baseline_efficiency, 1e-12)))
    node_metrics = pd.DataFrame(
        {
            "node": matrix.columns.astype(str),
            "degree": degree,
            "strength": strength,
            "eigenvector_centrality": vector,
            "clustering_coefficient": clustering,
            "efficiency_loss_if_removed": vulnerability,
        }
    ).sort_values(["efficiency_loss_if_removed", "strength"], ascending=[False, False]).reset_index(drop=True)
    edge_rows: list[dict[str, Any]] = []
    names = list(matrix.columns.astype(str))
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            if adjacency[left, right]:
                edge_rows.append({"node_a": names[left], "node_b": names[right], "connectivity": float(values[left, right]), "absolute_connectivity": float(absolute[left, right])})
    edge_table = pd.DataFrame(edge_rows).sort_values("absolute_connectivity", ascending=False).reset_index(drop=True) if edge_rows else pd.DataFrame(columns=["node_a", "node_b", "connectivity", "absolute_connectivity"])
    order = node_metrics["node"].tolist()
    current_names = names.copy()
    current_adj = adjacency.copy()
    resilience_rows = [{"removed_nodes": 0, "global_efficiency": baseline_efficiency, "remaining_nodes": len(names)}]
    for step, name in enumerate(order[: min(20, max(0, len(names) - 2))], start=1):
        index = current_names.index(name)
        current_adj = np.delete(np.delete(current_adj, index, axis=0), index, axis=1)
        current_names.pop(index)
        resilience_rows.append({"removed_nodes": step, "global_efficiency": _global_efficiency(current_adj), "remaining_nodes": len(current_names)})
    return {
        "node_metrics": node_metrics,
        "edge_table": edge_table,
        "resilience_curve": pd.DataFrame(resilience_rows),
        "global_metrics": {
            "nodes": int(len(names)),
            "edges": int(len(edge_rows)),
            "density": float(adjacency.sum() / max(len(names) * (len(names) - 1), 1)),
            "global_efficiency": baseline_efficiency,
            "threshold": float(threshold),
        },
        "scientific_boundary": BOUNDARY + " Network vulnerability is mathematical and depends on preprocessing, parcellation and threshold choices.",
    }


def neurodevelopmental_trajectory_analysis(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("subject_id", "age_months", "domain", "score", "reference_mean", "reference_sd"))
    for column in ("age_months", "score", "reference_mean", "reference_sd"):
        frame[column] = _numeric(frame[column])
    frame = frame.dropna(subset=["subject_id", "age_months", "domain", "score", "reference_mean", "reference_sd"])
    frame = frame.loc[frame["reference_sd"] > 0].copy()
    if frame.empty:
        raise ValueError("No observations have complete values and positive reference SD.")
    frame["z_score"] = (frame["score"] - frame["reference_mean"]) / frame["reference_sd"]
    summaries: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    for (subject, domain), subset in frame.groupby(["subject_id", "domain"]):
        subset = subset.sort_values("age_months")
        x = subset["age_months"].to_numpy(float)
        z = subset["z_score"].to_numpy(float)
        slope, _, _, _ = _linear_fit(x, z)
        annual_z_velocity = slope * 12.0
        threshold_crossing = bool((z <= -1.5).any())
        marked_drop = bool(len(z) > 1 and np.nanmin(np.diff(z)) <= -1.0)
        summaries.append(
            {
                "subject_id": str(subject),
                "domain": str(domain),
                "observations": int(len(subset)),
                "first_z": float(z[0]),
                "last_z": float(z[-1]),
                "annual_z_velocity": annual_z_velocity,
                "below_minus_1_5_sd": threshold_crossing,
                "drop_of_1_sd_between_visits": marked_drop,
            }
        )
        if threshold_crossing or marked_drop or annual_z_velocity <= -0.75:
            flags.append(
                {
                    "subject_id": str(subject),
                    "domain": str(domain),
                    "flag": "trajectory_review",
                    "last_z": float(z[-1]),
                    "annual_z_velocity": annual_z_velocity,
                    "reason": "; ".join(
                        reason
                        for triggered, reason in (
                            (threshold_crossing, "z-score at/below -1.5"),
                            (marked_drop, "drop of at least 1 SD between visits"),
                            (annual_z_velocity <= -0.75, "rapid negative z-velocity"),
                        )
                        if triggered
                    ),
                }
            )
    summary = pd.DataFrame(summaries)
    domain_summary = summary.groupby("domain", as_index=False).agg(
        series=("subject_id", "size"),
        median_last_z=("last_z", "median"),
        median_annual_z_velocity=("annual_z_velocity", "median"),
        review_flags=("below_minus_1_5_sd", "sum"),
    )
    return {
        "observations": frame.sort_values(["subject_id", "domain", "age_months"]).reset_index(drop=True),
        "subject_domain_summary": summary,
        "review_flags": pd.DataFrame(flags),
        "domain_summary": domain_summary,
        "scientific_boundary": BOUNDARY + " Reference means/SDs must match age, instrument, population and administration conditions.",
    }


def _demo_timestamps(periods: int, frequency: str) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=periods, freq=frequency)


def demo_frame(feature_key: str, *, seed: int = 207) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if feature_key == "neurovascular_research":
        n = 80
        return pd.DataFrame(
            {
                "subject_id": [f"NV-{i+1:03d}" for i in range(n)],
                "age": rng.integers(40, 86, n),
                "systolic_bp": rng.normal(136, 18, n).round(1),
                "diastolic_bp": rng.normal(82, 11, n).round(1),
                "ldl": rng.normal(138, 35, n).round(1),
                "hba1c": rng.normal(5.9, 0.8, n).round(2),
                "smoking": rng.random(n) < 0.18,
                "atrial_fibrillation": rng.random(n) < 0.10,
            }
        )
    if feature_key == "sleep_circadian":
        timestamps = _demo_timestamps(7 * 24 * 4, "15min")
        hour = timestamps.hour.to_numpy(dtype=float) + timestamps.minute.to_numpy(dtype=float) / 60
        activity = 40 + 30 * np.sin((hour - 8) / 24 * 2 * np.pi) + rng.normal(0, 8, len(timestamps))
        activity[(hour >= 23) | (hour <= 6)] *= 0.12
        return pd.DataFrame({"timestamp": timestamps, "activity": np.clip(activity, 0, None), "heart_rate": 62 + activity * 0.12 + rng.normal(0, 2, len(timestamps))})
    if feature_key == "fluid_biomarkers":
        n = 120
        group = np.array(["reference"] * (n // 2) + ["condition"] * (n // 2))
        return pd.DataFrame(
            {
                "sample_id": [f"CSF-{i+1:03d}" for i in range(n)],
                "group": group,
                "nfl": rng.normal(20, 5, n) + (group == "condition") * 9,
                "gfap": rng.normal(100, 18, n) + (group == "condition") * 22,
                "ptau": rng.normal(18, 4, n) + (group == "condition") * 6,
                "abeta42": rng.normal(850, 110, n) - (group == "condition") * 130,
                "y_candidates": rng.normal(0, 1, n),
            }
        )
    if feature_key == "digital_neurology":
        timestamps = _demo_timestamps(60 * 20, "50ms")
        t = np.arange(len(timestamps)) / 20.0
        gait = 1.2 + 0.12 * np.sin(2 * np.pi * 1.7 * t) + rng.normal(0, 0.04, len(t))
        gait[500:560] *= 0.15
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "accel_x": gait + rng.normal(0, 0.03, len(t)),
                "accel_y": 0.3 * np.sin(2 * np.pi * 1.7 * t + 1.0) + rng.normal(0, 0.03, len(t)),
                "accel_z": 1.0 + 0.2 * np.sin(2 * np.pi * 1.7 * t + 2.0) + rng.normal(0, 0.03, len(t)),
                "gait_speed": np.clip(gait, 0, None),
            }
        )
    if feature_key == "neuroimmune_interactions":
        rows = []
        for condition in ("reference", "disease"):
            for cell in ("microglia", "astrocyte", "monocyte", "t_cell"):
                for pathway in ("complement", "inflammasome", "interferon", "phagocytosis"):
                    shift = 0.0
                    if condition == "disease":
                        shift = {"complement": 1.0, "inflammasome": 0.8, "interferon": 0.5, "phagocytosis": -0.3}[pathway]
                        if cell == "microglia":
                            shift *= 1.4
                    for replicate in range(12):
                        rows.append({"condition": condition, "cell_type": cell, "pathway": pathway, "score": rng.normal(shift, 0.7), "replicate": replicate + 1})
        return pd.DataFrame(rows)
    if feature_key == "cognitive_trajectory":
        rows = []
        for subject in range(30):
            slope = rng.normal(-0.05, 0.08)
            if subject < 5:
                slope -= 0.25
            for month in (0, 6, 12, 18, 24):
                rows.append({"subject_id": f"COG-{subject+1:03d}", "domain": "global", "time_months": month, "score": 28 + slope * month + rng.normal(0, 0.5)})
        return pd.DataFrame(rows)
    if feature_key == "neurorehabilitation":
        n = 64
        baseline = rng.normal(42, 8, n)
        change = rng.normal(4, 4, n)
        change[:10] += 5
        return pd.DataFrame({"subject_id": [f"REHAB-{i+1:03d}" for i in range(n)], "baseline": baseline.round(2), "followup": (baseline + change).round(2)})
    if feature_key == "polypharmacy_cns":
        medications = ["DrugA", "DrugB", "DrugC", "DrugD", "DrugE", "DrugF", "DrugG"]
        rows = []
        for subject in range(35):
            count = int(rng.integers(1, 7))
            for medication in rng.choice(medications, size=count, replace=False):
                rows.append(
                    {
                        "subject_id": f"MED-{subject+1:03d}",
                        "medication": medication,
                        "anticholinergic_burden": int(rng.integers(0, 3)),
                        "sedation_burden": int(rng.integers(0, 3)),
                        "qt_risk": int(rng.random() < 0.25),
                        "serotonergic": bool(rng.random() < 0.30),
                        "seizure_threshold_risk": int(rng.random() < 0.18),
                        "orthostatic_risk": int(rng.random() < 0.22),
                    }
                )
        return pd.DataFrame(rows)
    if feature_key == "brain_network_vulnerability":
        nodes = [f"ROI_{i+1:02d}" for i in range(18)]
        observations = rng.normal(size=(240, 4)) @ rng.normal(size=(4, 18)) + rng.normal(0, 0.35, size=(240, 18))
        matrix = np.corrcoef(observations, rowvar=False)
        matrix = np.nan_to_num(matrix)
        matrix = (matrix + matrix.T) / 2
        np.fill_diagonal(matrix, 1.0)
        return pd.DataFrame(matrix, index=nodes, columns=nodes)
    if feature_key == "neurodevelopmental_trajectory":
        rows = []
        for subject in range(24):
            for domain in ("language", "motor", "social"):
                drift = rng.normal(0, 0.03)
                if subject < 4 and domain == "language":
                    drift -= 0.12
                for age in (12, 18, 24, 30, 36):
                    reference_mean = 50 + 0.8 * age
                    reference_sd = 8 + 0.05 * age
                    score = reference_mean + reference_sd * (rng.normal(0, 0.45) + drift * (age - 12))
                    rows.append({"subject_id": f"DEV-{subject+1:03d}", "age_months": age, "domain": domain, "score": score, "reference_mean": reference_mean, "reference_sd": reference_sd})
        return pd.DataFrame(rows)
    raise KeyError(f"Unknown Step207 Neuro feature: {feature_key}")


FEATURES: tuple[tuple[str, str, str], ...] = (
    ("neurovascular_research", "Neurovascular & Stroke Research Profiler", "Transparent vascular-factor triage and cohort review."),
    ("sleep_circadian", "Sleep & Circadian Neurophysiology Lab", "Actigraphy-like rhythm stability, fragmentation and rest-consistency analytics."),
    ("fluid_biomarkers", "CSF/Blood Neurological Biomarker Panel", "Effect-size, AUC, missingness and internal panel-score analysis."),
    ("digital_neurology", "Digital Neurology & Wearable Sensor Lab", "Gait/activity signal windows, variability and candidate-event review."),
    ("neuroimmune_interactions", "Neuroimmune Cell-State Interaction Studio", "Cell-type/pathway differential scores and evidence-network edges."),
    ("cognitive_trajectory", "Cognitive Trajectory & Change-Point Lab", "Longitudinal slopes and candidate change-point review."),
    ("neurorehabilitation", "Neurorehabilitation Response Analytics", "MCID-aware and reliable-change research analysis."),
    ("polypharmacy_cns", "CNS Polypharmacy & Medication Burden Studio", "User-annotated CNS burden aggregation and interaction flags."),
    ("brain_network_vulnerability", "Brain Network Vulnerability & Resilience Lab", "Hub vulnerability, efficiency loss and resilience curves."),
    ("neurodevelopmental_trajectory", "Neurodevelopmental Trajectory Studio", "Age-referenced z-trajectories, velocity and review flags."),
)


__all__ = [
    "FEATURES",
    "BOUNDARY",
    "brain_network_vulnerability_analysis",
    "cognitive_trajectory_analysis",
    "demo_frame",
    "digital_neurology_sensor_analysis",
    "fluid_biomarker_panel",
    "neurodevelopmental_trajectory_analysis",
    "neuroimmune_interaction_analysis",
    "neurorehabilitation_response_analysis",
    "neurovascular_research_profile",
    "polypharmacy_cns_burden",
    "sleep_circadian_profile",
]
