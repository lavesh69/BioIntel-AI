from __future__ import annotations

import numpy as np
import pandas as pd


def bioprocess_advanced_metrics(
    frame: pd.DataFrame,
    *,
    time_column: str = "time",
    biomass_column: str = "biomass",
    substrate_column: str = "substrate",
    product_column: str = "product",
    batch_column: str | None = None,
    process_mode: str = "Batch",
    volume_column: str | None = None,
    feed_column: str | None = None,
    bleed_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Calculate process metrics per batch and add transparent mode-specific terms."""

    required = {time_column, biomass_column, substrate_column, product_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing bioprocess columns: " + ", ".join(sorted(missing)))
    mode = str(process_mode).strip().lower().replace("-", "_")
    if mode not in {"batch", "fed_batch", "continuous", "perfusion"}:
        raise ValueError("process_mode must be Batch, Fed-batch, Continuous or Perfusion.")
    if batch_column and batch_column in frame.columns and frame[batch_column].nunique(dropna=False) > 1:
        trajectories = []
        batch_rows = []
        for batch, part in frame.groupby(batch_column, dropna=False):
            trajectory, summary = bioprocess_advanced_metrics(
                part,
                time_column=time_column,
                biomass_column=biomass_column,
                substrate_column=substrate_column,
                product_column=product_column,
                batch_column=None,
                process_mode=process_mode,
                volume_column=volume_column,
                feed_column=feed_column,
                bleed_column=bleed_column,
            )
            trajectory[batch_column] = batch
            trajectories.append(trajectory)
            batch_rows.append({batch_column: batch, **summary})
        combined = pd.concat(trajectories, ignore_index=True)
        batch_summary = pd.DataFrame(batch_rows)
        numeric = batch_summary.select_dtypes(include=[np.number])
        aggregate: dict[str, object] = {
            "process_mode": process_mode,
            "batch_count": int(len(batch_summary)),
            "batch_summary": batch_rows,
        }
        for column in numeric.columns:
            values = pd.to_numeric(numeric[column], errors="coerce")
            aggregate[f"median_{column}"] = float(values.median()) if values.notna().any() else None
            aggregate[f"range_{column}"] = [float(values.min()), float(values.max())] if values.notna().any() else None
        return combined, aggregate

    data = frame.copy()
    for column in required:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=list(required)).sort_values(time_column)
    if len(data) < 3 or np.any(np.diff(data[time_column].to_numpy(float)) <= 0):
        raise ValueError("Each bioprocess batch requires at least three strictly increasing time points.")
    t = data[time_column].to_numpy(float)
    x = data[biomass_column].to_numpy(float)
    substrate = data[substrate_column].to_numpy(float)
    product = data[product_column].to_numpy(float)
    data["biomass_rate"] = np.gradient(x, t)
    data["substrate_consumption_rate"] = -np.gradient(substrate, t)
    data["product_formation_rate"] = np.gradient(product, t)
    data["specific_growth_rate"] = np.divide(data["biomass_rate"], x, out=np.full(len(x), np.nan), where=x > 0)
    data["specific_productivity"] = np.divide(data["product_formation_rate"], x, out=np.full(len(x), np.nan), where=x > 0)
    data["instantaneous_biomass_yield"] = np.divide(data["biomass_rate"], data["substrate_consumption_rate"], out=np.full(len(x), np.nan), where=data["substrate_consumption_rate"] > 0)
    data["instantaneous_product_yield"] = np.divide(data["product_formation_rate"], data["substrate_consumption_rate"], out=np.full(len(x), np.nan), where=data["substrate_consumption_rate"] > 0)
    summary: dict[str, object] = {
        "process_mode": process_mode,
        "maximum_specific_growth_rate": float(np.nanmax(data["specific_growth_rate"])),
        "maximum_volumetric_productivity": float(np.nanmax(data["product_formation_rate"])),
        "maximum_specific_productivity": float(np.nanmax(data["specific_productivity"])),
        "final_titer": float(product[-1]),
        "overall_biomass_yield": float((x[-1] - x[0]) / (substrate[0] - substrate[-1])) if substrate[0] > substrate[-1] else None,
        "overall_product_yield": float((product[-1] - product[0]) / (substrate[0] - substrate[-1])) if substrate[0] > substrate[-1] else None,
        "mode_specific_status": "complete",
    }
    if volume_column and volume_column in data.columns:
        volume = pd.to_numeric(data[volume_column], errors="coerce")
        if (volume > 0).all():
            data["biomass_mass"] = x * volume
            data["product_mass"] = product * volume
            data["substrate_mass"] = substrate * volume
            summary["final_volume"] = float(volume.iloc[-1])
            summary["final_product_mass"] = float(data["product_mass"].iloc[-1])
    elif mode in {"fed_batch", "continuous", "perfusion"}:
        summary["mode_specific_status"] = "Review: volume column required for corrected mass balances"
    if feed_column and feed_column in data.columns:
        feed = pd.to_numeric(data[feed_column], errors="coerce").fillna(0.0)
        data["cumulative_feed"] = np.concatenate([[0.0], np.cumsum(np.diff(t) * (feed.iloc[:-1].to_numpy(float) + feed.iloc[1:].to_numpy(float)) / 2)])
        if volume_column and volume_column in data.columns:
            volume = pd.to_numeric(data[volume_column], errors="coerce")
            data["dilution_rate"] = np.divide(feed, volume, out=np.full(len(data), np.nan), where=volume > 0)
            summary["mean_dilution_rate"] = float(np.nanmean(data["dilution_rate"]))
    if mode == "perfusion":
        if bleed_column and bleed_column in data.columns and volume_column and volume_column in data.columns:
            bleed = pd.to_numeric(data[bleed_column], errors="coerce").fillna(0.0)
            volume = pd.to_numeric(data[volume_column], errors="coerce")
            data["bleed_rate_fraction"] = np.divide(bleed, volume, out=np.full(len(data), np.nan), where=volume > 0)
            summary["mean_bleed_rate_fraction"] = float(np.nanmean(data["bleed_rate_fraction"]))
        else:
            summary["mode_specific_status"] = "Review: perfusion requires volume and bleed columns"
    if {"our", "cer"}.issubset(data.columns):
        our = pd.to_numeric(data["our"], errors="coerce")
        cer = pd.to_numeric(data["cer"], errors="coerce")
        data["respiratory_quotient"] = np.divide(cer, our, out=np.full(len(data), np.nan), where=our > 0)
        summary["mean_respiratory_quotient"] = float(np.nanmean(data["respiratory_quotient"]))
    return data, summary


def elisa_assay_qc(
    frame: pd.DataFrame,
    *,
    type_column: str = "type",
    response_column: str = "absorbance",
    expected_column: str | None = None,
    measured_column: str | None = None,
) -> dict[str, object]:
    """Calculate control separation, replicate precision and optional recovery QC."""
    if type_column not in frame.columns or response_column not in frame.columns:
        raise ValueError("ELISA QC requires type and response columns.")
    data = frame.copy()
    data[response_column] = pd.to_numeric(data[response_column], errors="coerce")
    labels = data[type_column].astype(str).str.lower()
    positive = data[labels.isin(["positive", "positive_control", "high_control"])][response_column].dropna()
    negative = data[labels.isin(["negative", "negative_control", "blank", "low_control"])][response_column].dropna()
    z_prime = None
    if len(positive) >= 2 and len(negative) >= 2:
        separation = abs(float(positive.mean() - negative.mean()))
        z_prime = 1 - 3 * (float(positive.std(ddof=1)) + float(negative.std(ddof=1))) / separation if separation > 0 else None
    replicate_rows = []
    grouping = [column for column in ("name", "concentration") if column in data.columns]
    if grouping:
        for keys, part in data.groupby(grouping, dropna=False):
            values = part[response_column].dropna().to_numpy(float)
            key_values = keys if isinstance(keys, tuple) else (keys,)
            row = dict(zip(grouping, key_values))
            row.update(
                {
                    "replicates": len(values),
                    "mean_response": float(values.mean()) if len(values) else np.nan,
                    "sd_response": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                    "cv_percent": float(100 * values.std(ddof=1) / abs(values.mean())) if len(values) > 1 and values.mean() else 0.0,
                }
            )
            replicate_rows.append(row)
    recovery = pd.DataFrame()
    if expected_column and measured_column and {expected_column, measured_column}.issubset(data.columns):
        recovery = data[[expected_column, measured_column]].apply(pd.to_numeric, errors="coerce").dropna()
        recovery["recovery_percent"] = 100 * recovery[measured_column] / recovery[expected_column].replace(0, np.nan)
        recovery["recovery_status"] = np.where(recovery["recovery_percent"].between(80, 120), "Pass", "Review")
    return {
        "z_prime": z_prime,
        "z_prime_status": "Pass" if z_prime is not None and z_prime >= 0.5 else "Review",
        "positive_controls": int(len(positive)),
        "negative_controls": int(len(negative)),
        "replicate_qc": pd.DataFrame(replicate_rows),
        "recovery": recovery,
    }


def bioprocess_batch_comparison(
    frame: pd.DataFrame,
    *,
    batch_column: str = "replicate",
    time_column: str = "time",
    variable_columns: list[str] | None = None,
    grid_points: int = 101,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align batches to normalized process time and calculate golden-batch deviation."""
    if batch_column not in frame.columns or time_column not in frame.columns:
        raise ValueError("Batch comparison requires batch and time columns.")
    variables = variable_columns or [column for column in frame.columns if column not in {batch_column, time_column} and pd.api.types.is_numeric_dtype(frame[column])]
    if not variables:
        raise ValueError("No numeric process variables are available for batch comparison.")
    grid = np.linspace(0, 1, grid_points)
    aligned_rows = []
    for batch, part in frame.groupby(batch_column, dropna=False):
        data = part.sort_values(time_column)
        time = pd.to_numeric(data[time_column], errors="coerce").to_numpy(float)
        if len(time) < 3 or time[-1] <= time[0]:
            continue
        normalized = (time - time[0]) / (time[-1] - time[0])
        for variable in variables:
            values = pd.to_numeric(data[variable], errors="coerce").to_numpy(float)
            valid = np.isfinite(normalized) & np.isfinite(values)
            if valid.sum() < 3:
                continue
            interpolated = np.interp(grid, normalized[valid], values[valid])
            aligned_rows.extend({"batch": str(batch), "normalized_time": float(point), "variable": variable, "value": float(value)} for point, value in zip(grid, interpolated))
    aligned = pd.DataFrame(aligned_rows)
    if aligned.empty:
        return aligned, pd.DataFrame()
    golden = aligned.groupby(["normalized_time", "variable"])["value"].agg(["mean", "std"]).reset_index()
    enriched = aligned.merge(golden, on=["normalized_time", "variable"], how="left")
    enriched["z_deviation"] = np.where(enriched["std"] > 0, (enriched["value"] - enriched["mean"]) / enriched["std"], 0.0)
    summary = enriched.groupby(["batch", "variable"]).agg(
        mean_absolute_z=("z_deviation", lambda values: float(np.mean(np.abs(values)))),
        maximum_absolute_z=("z_deviation", lambda values: float(np.max(np.abs(values)))),
        points_outside_3sd=("z_deviation", lambda values: int((np.abs(values) > 3).sum())),
    ).reset_index()
    return enriched, summary


def qpcr_reference_gene_stability(
    frame: pd.DataFrame,
    *,
    sample_column: str = "sample",
    gene_column: str = "gene",
    ct_column: str = "ct",
    candidate_genes: list[str] | None = None,
) -> pd.DataFrame:
    """Transparent geNorm-style pairwise stability screen for reference genes."""
    required = {sample_column, gene_column, ct_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing reference-stability columns: " + ", ".join(sorted(missing)))
    data = frame.copy()
    data[ct_column] = pd.to_numeric(data[ct_column], errors="coerce")
    data = data.dropna(subset=[sample_column, gene_column, ct_column])
    candidates = [str(gene) for gene in (candidate_genes or sorted(data[gene_column].astype(str).unique()))]
    matrix = (
        data[data[gene_column].astype(str).isin(candidates)]
        .groupby([sample_column, gene_column])[ct_column]
        .mean()
        .unstack()
    )
    matrix = matrix[[gene for gene in candidates if gene in matrix.columns]].dropna(axis=0, how="any")
    if matrix.shape[0] < 3 or matrix.shape[1] < 2:
        raise ValueError("Reference stability requires at least three complete samples and two candidate genes.")
    rows = []
    for gene in matrix.columns:
        pairwise_sd = [(matrix[gene] - matrix[other]).std(ddof=1) for other in matrix.columns if other != gene]
        ct_values = matrix[gene]
        rows.append(
            {
                "gene": str(gene),
                "complete_samples": int(len(matrix)),
                "stability_m": float(np.mean(pairwise_sd)),
                "ct_mean": float(ct_values.mean()),
                "ct_sd": float(ct_values.std(ddof=1)),
                "ct_cv_percent": float(100 * ct_values.std(ddof=1) / max(abs(ct_values.mean()), 1e-12)),
            }
        )
    output = pd.DataFrame(rows).sort_values(["stability_m", "ct_sd"]).reset_index(drop=True)
    output["stability_rank"] = np.arange(1, len(output) + 1)
    output["screening_status"] = np.where(output["stability_m"] <= 0.5, "Preferred", np.where(output["stability_m"] <= 1.0, "Review", "Unstable"))
    return output


def qpcr_control_qc(
    frame: pd.DataFrame,
    *,
    role_column: str = "role",
    ct_column: str = "ct",
    maximum_negative_control_ct: float = 38.0,
) -> pd.DataFrame:
    """Audit NTC, no-RT, positive and extraction-control measurements."""
    if role_column not in frame.columns or ct_column not in frame.columns:
        raise ValueError("qPCR control QC requires role and Ct columns.")
    data = frame.copy()
    data[ct_column] = pd.to_numeric(data[ct_column], errors="coerce")
    rows = []
    negative_labels = {"ntc", "negative", "no_template", "no-template", "no_rt", "no-rt"}
    positive_labels = {"positive", "positive_control", "extraction_control", "ipc"}
    for role, part in data.groupby(data[role_column].astype(str).str.lower(), dropna=False):
        ct_values = part[ct_column].dropna()
        if role in negative_labels:
            pass_count = int((ct_values >= maximum_negative_control_ct).sum()) + int(part[ct_column].isna().sum())
            status = "Pass" if pass_count == len(part) else "Review"
            detail = "Negative controls should be undetermined or above the configured late-Ct threshold."
        elif role in positive_labels:
            status = "Pass" if len(ct_values) == len(part) else "Review"
            detail = "Positive/extraction controls should amplify consistently."
        else:
            status = "Informational"
            detail = "No default acceptance rule is assigned to this role."
        rows.append(
            {
                "role": str(role),
                "wells": int(len(part)),
                "detected_ct": int(len(ct_values)),
                "mean_ct": float(ct_values.mean()) if len(ct_values) else np.nan,
                "minimum_ct": float(ct_values.min()) if len(ct_values) else np.nan,
                "qc_status": status,
                "acceptance_rule": detail,
            }
        )
    return pd.DataFrame(rows)


def bioprocess_sensor_metrics(
    frame: pd.DataFrame,
    *,
    time_column: str = "time",
    our_column: str = "our",
    cer_column: str = "cer",
    do_column: str = "do",
    kla_column: str = "kla",
    oxygen_saturation_column: str = "oxygen_saturation",
    feed_column: str = "feed",
) -> tuple[pd.DataFrame, dict[str, float | None]]:
    """Add off-gas, oxygen-transfer and feed-aware process diagnostics when available."""
    if time_column not in frame.columns:
        raise ValueError("Bioprocess sensor analysis requires a time column.")
    output = frame.copy().sort_values(time_column).reset_index(drop=True)
    time = pd.to_numeric(output[time_column], errors="coerce")
    if our_column in output.columns and cer_column in output.columns:
        our = pd.to_numeric(output[our_column], errors="coerce")
        cer = pd.to_numeric(output[cer_column], errors="coerce")
        output["respiratory_quotient"] = cer / our.replace(0, np.nan)
    if kla_column in output.columns and do_column in output.columns and oxygen_saturation_column in output.columns:
        kla = pd.to_numeric(output[kla_column], errors="coerce")
        dissolved = pd.to_numeric(output[do_column], errors="coerce")
        saturation = pd.to_numeric(output[oxygen_saturation_column], errors="coerce")
        output["oxygen_transfer_rate"] = kla * (saturation - dissolved)
    if feed_column in output.columns:
        feed = pd.to_numeric(output[feed_column], errors="coerce").fillna(0)
        increments = np.diff(time, prepend=time.iloc[0]).clip(min=0)
        output["cumulative_feed"] = np.cumsum(feed.to_numpy(float) * increments)
    summary: dict[str, float | None] = {
        "maximum_our": float(pd.to_numeric(output[our_column], errors="coerce").max()) if our_column in output.columns else None,
        "maximum_cer": float(pd.to_numeric(output[cer_column], errors="coerce").max()) if cer_column in output.columns else None,
        "median_respiratory_quotient": float(output["respiratory_quotient"].median()) if "respiratory_quotient" in output.columns else None,
        "maximum_oxygen_transfer_rate": float(output["oxygen_transfer_rate"].max()) if "oxygen_transfer_rate" in output.columns else None,
        "final_cumulative_feed": float(output["cumulative_feed"].iloc[-1]) if "cumulative_feed" in output.columns and len(output) else None,
    }
    return output, summary


def elisa_parallelism_recovery_qc(
    frame: pd.DataFrame,
    *,
    sample_column: str = "name",
    concentration_column: str = "estimated_concentration",
    dilution_column: str = "dilution_factor",
    expected_column: str = "expected_concentration",
    maximum_parallelism_cv_percent: float = 20.0,
    minimum_recovery_percent: float = 80.0,
    maximum_recovery_percent: float = 120.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit dilution parallelism and nominal/spike recovery for quantified samples."""
    required = {sample_column, concentration_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("ELISA parallelism requires: " + ", ".join(sorted(missing)))
    data = frame.copy()
    data[concentration_column] = pd.to_numeric(data[concentration_column], errors="coerce")
    if dilution_column not in data.columns:
        data[dilution_column] = 1.0
    data[dilution_column] = pd.to_numeric(data[dilution_column], errors="coerce").fillna(1.0)
    data["dilution_corrected_concentration"] = data[concentration_column]
    parallel_rows = []
    for sample, part in data.groupby(sample_column, dropna=False):
        values = part["dilution_corrected_concentration"].dropna().to_numpy(float)
        mean = float(values.mean()) if len(values) else np.nan
        cv = float(100 * values.std(ddof=1) / max(abs(mean), 1e-12)) if len(values) > 1 else 0.0
        parallel_rows.append(
            {
                "sample": str(sample),
                "dilutions": int(len(values)),
                "mean_dilution_corrected_concentration": mean,
                "parallelism_cv_percent": cv,
                "parallelism_status": "Pass" if len(values) >= 2 and cv <= maximum_parallelism_cv_percent else "Review",
            }
        )
    recovery = pd.DataFrame()
    if expected_column in data.columns:
        expected = pd.to_numeric(data[expected_column], errors="coerce")
        valid = expected > 0
        recovery = data.loc[valid, [sample_column, concentration_column, expected_column, dilution_column]].copy()
        recovery["recovery_percent"] = 100 * recovery[concentration_column] / expected[valid]
        recovery["recovery_status"] = np.where(
            recovery["recovery_percent"].between(minimum_recovery_percent, maximum_recovery_percent),
            "Pass",
            "Review",
        )
    return pd.DataFrame(parallel_rows), recovery


def elisa_hook_effect_screen(
    standards: pd.DataFrame,
    *,
    concentration_column: str = "concentration",
    response_column: str = "absorbance",
    relative_drop_threshold: float = 0.10,
) -> dict[str, object]:
    """Screen the high-standard range for a prozone/hook-like response decline."""
    data = standards[[concentration_column, response_column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 4:
        return {"hook_flag": False, "status": "Insufficient standards", "largest_high_range_drop_percent": 0.0}
    grouped = data.groupby(concentration_column, as_index=False)[response_column].mean().sort_values(concentration_column)
    high = grouped.tail(max(3, len(grouped) // 3))
    changes = high[response_column].pct_change().dropna()
    largest_drop = float(abs(min(changes.min(), 0.0)) * 100) if len(changes) else 0.0
    flag = bool((changes < -abs(relative_drop_threshold)).any())
    return {
        "hook_flag": flag,
        "status": "Review" if flag else "Pass",
        "largest_high_range_drop_percent": largest_drop,
        "threshold_percent": 100 * abs(relative_drop_threshold),
    }


def qpcr_amplification_curve_qc(
    frame: pd.DataFrame,
    *,
    reaction_column: str = "reaction",
    cycle_column: str = "cycle",
    fluorescence_column: str = "fluorescence",
    baseline_cycles: int = 10,
    threshold_fraction: float = 0.20,
    minimum_signal_to_noise: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Inspect raw qPCR amplification curves and estimate a transparent Cq crossing.

    This is a screening implementation rather than a replacement for validated
    instrument algorithms. It preserves per-cycle corrected fluorescence and
    reports the threshold, interpolated crossing, signal-to-noise and curve QC.
    """

    required = {reaction_column, cycle_column, fluorescence_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Raw qPCR curve QC requires: " + ", ".join(sorted(missing)))
    if baseline_cycles < 3:
        raise ValueError("At least three baseline cycles are required.")
    if not 0 < threshold_fraction < 1:
        raise ValueError("threshold_fraction must be between zero and one.")

    detail_parts: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for reaction, part in frame.groupby(reaction_column, dropna=False):
        data = part[[cycle_column, fluorescence_column]].copy()
        data[cycle_column] = pd.to_numeric(data[cycle_column], errors="coerce")
        data[fluorescence_column] = pd.to_numeric(data[fluorescence_column], errors="coerce")
        data = data.dropna().sort_values(cycle_column).drop_duplicates(cycle_column, keep="last")
        if len(data) < baseline_cycles + 5:
            summaries.append({
                "reaction": str(reaction),
                "cycles": int(len(data)),
                "estimated_cq": np.nan,
                "signal_to_noise": np.nan,
                "curve_qc_status": "Review",
                "curve_qc_detail": "Insufficient cycles for baseline and amplification assessment.",
            })
            continue
        fluorescence = data[fluorescence_column].to_numpy(float)
        cycles = data[cycle_column].to_numpy(float)
        baseline_values = fluorescence[:baseline_cycles]
        baseline_mean = float(np.mean(baseline_values))
        baseline_sd = float(np.std(baseline_values, ddof=1)) if len(baseline_values) > 1 else 0.0
        corrected = fluorescence - baseline_mean
        plateau_count = max(3, int(np.ceil(len(corrected) * 0.10)))
        plateau = float(np.nanmedian(corrected[-plateau_count:]))
        noise_floor = max(baseline_sd, np.finfo(float).eps)
        signal_to_noise = float(max(plateau, 0.0) / noise_floor)
        threshold_corrected = max(10 * noise_floor, threshold_fraction * max(plateau, 0.0))
        crossing_indices = np.flatnonzero(corrected >= threshold_corrected)
        cq = np.nan
        if len(crossing_indices):
            index = int(crossing_indices[0])
            if index == 0:
                cq = float(cycles[0])
            else:
                x0, x1 = cycles[index - 1], cycles[index]
                y0, y1 = corrected[index - 1], corrected[index]
                cq = float(x1 if y1 == y0 else x0 + (threshold_corrected - y0) * (x1 - x0) / (y1 - y0))
        positive_steps = float(np.mean(np.diff(corrected) >= 0)) if len(corrected) > 1 else 0.0
        flags: list[str] = []
        if not np.isfinite(cq):
            flags.append("No threshold crossing")
        if signal_to_noise < minimum_signal_to_noise:
            flags.append("Low signal-to-noise")
        if plateau <= 0:
            flags.append("No positive amplification plateau")
        if positive_steps < 0.55:
            flags.append("Irregular/non-monotonic curve")
        status = "Pass" if not flags else "Review"
        enriched = data.copy()
        enriched.insert(0, reaction_column, reaction)
        enriched["baseline_corrected_fluorescence"] = corrected
        enriched["threshold_corrected_fluorescence"] = threshold_corrected
        enriched["above_threshold"] = corrected >= threshold_corrected
        detail_parts.append(enriched)
        summaries.append({
            "reaction": str(reaction),
            "cycles": int(len(data)),
            "baseline_mean": baseline_mean,
            "baseline_sd": baseline_sd,
            "plateau_corrected_fluorescence": plateau,
            "threshold_corrected_fluorescence": threshold_corrected,
            "estimated_cq": cq,
            "signal_to_noise": signal_to_noise,
            "monotonic_step_fraction": positive_steps,
            "curve_qc_status": status,
            "curve_qc_detail": "; ".join(flags) if flags else "Curve crossed threshold with acceptable screening diagnostics.",
        })
    detail = pd.concat(detail_parts, ignore_index=True) if detail_parts else pd.DataFrame()
    return detail, pd.DataFrame(summaries)


def elisa_validation_summary(
    calibration: dict[str, object],
    quantified_samples: pd.DataFrame | None = None,
    *,
    maximum_standard_cv_percent: float = 20.0,
    minimum_r_squared: float = 0.98,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build an explicit research-use ELISA run-acceptance summary."""

    fit_table = pd.DataFrame(calibration.get("fit_table", pd.DataFrame()))
    standards = pd.DataFrame(calibration.get("standard_qc", pd.DataFrame()))
    selected_model = str(calibration.get("selected_model", "unknown"))
    selected = fit_table[fit_table.get("model", pd.Series(dtype=str)).astype(str) == selected_model] if not fit_table.empty else pd.DataFrame()
    selected_row = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    levels = int(calibration.get("distinct_standard_levels", 0))
    minimum_levels = 8 if selected_model == "5PL" else 6 if selected_model == "4PL" else 4
    checks: list[dict[str, object]] = []

    def add_check(name: str, value: object, passed: bool, action: str) -> None:
        checks.append({"check": name, "value": value, "status": "Pass" if passed else "Review", "recommended_action": action})

    add_check("Standard levels", levels, levels >= minimum_levels, f"Use at least {minimum_levels} distinct positive concentration levels for {selected_model}.")
    r_squared = float(selected_row.get("r_squared", np.nan)) if len(selected_row) else np.nan
    add_check("Calibration fit R²", r_squared, np.isfinite(r_squared) and r_squared >= minimum_r_squared, "Review residuals, curve range and model choice.")
    covariance_ok = bool(selected_row.get("covariance_ok", False)) if len(selected_row) else False
    add_check("Parameter covariance", covariance_ok, covariance_ok, "Collect additional standards or simplify the curve model.")
    monotonic = bool(selected_row.get("monotonic", False)) if len(selected_row) else False
    add_check("Calibration monotonicity", monotonic, monotonic, "Investigate preparation errors, hook effect or unsuitable model direction.")
    if not standards.empty and "cv_percent" in standards:
        maximum_cv = float(pd.to_numeric(standards["cv_percent"], errors="coerce").max())
        add_check("Maximum standard replicate CV (%)", maximum_cv, maximum_cv <= maximum_standard_cv_percent, "Repeat imprecise standards or review plate handling.")
    if quantified_samples is not None and not quantified_samples.empty and "quantification_status" in quantified_samples:
        in_range_fraction = float((quantified_samples["quantification_status"] == "In range").mean())
        add_check("Unknowns inside calibration range", in_range_fraction, in_range_fraction >= 0.80, "Dilute/repeat out-of-range unknowns and do not report extrapolated values.")
    check_table = pd.DataFrame(checks)
    review_count = int((check_table["status"] == "Review").sum()) if not check_table.empty else 0
    summary = {
        "selected_model": selected_model,
        "checks": int(len(check_table)),
        "passed_checks": int((check_table["status"] == "Pass").sum()) if not check_table.empty else 0,
        "review_checks": review_count,
        "run_acceptance": "Pass" if review_count == 0 else "Review",
        "boundary": "Research-use run screening; full accuracy, precision, selectivity, stability and matrix validation require protocol-specific studies.",
    }
    return check_table, summary


def bioprocess_pat_monitor(
    frame: pd.DataFrame,
    *,
    time_column: str = "time",
    variables: list[str] | tuple[str, ...] | None = None,
    batch_column: str | None = None,
    sigma_limit: float = 3.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create robust retrospective PAT-style control limits and anomaly flags.

    Median/MAD limits are intentionally transparent and should be replaced by
    process-validated CPP/CQA limits for production control.
    """

    if time_column not in frame.columns:
        raise ValueError("PAT monitoring requires a time column.")
    if sigma_limit <= 0:
        raise ValueError("sigma_limit must be positive.")
    selected = list(variables or [column for column in frame.columns if column != time_column and pd.api.types.is_numeric_dtype(frame[column])])
    selected = [column for column in selected if column in frame.columns and column != time_column]
    if not selected:
        raise ValueError("Select at least one numeric PAT variable.")
    id_columns = [time_column] + ([batch_column] if batch_column and batch_column in frame.columns else [])
    long = frame[id_columns + selected].melt(id_vars=id_columns, value_vars=selected, var_name="variable", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    group_columns = ["variable"] + ([batch_column] if batch_column and batch_column in long.columns else [])
    parts: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for keys, part in long.groupby(group_columns, dropna=False):
        data = part.dropna(subset=["value"]).copy()
        if data.empty:
            continue
        center = float(data["value"].median())
        mad = float(np.median(np.abs(data["value"].to_numpy(float) - center)))
        robust_sigma = max(1.4826 * mad, float(data["value"].std(ddof=1)) if len(data) > 1 and mad == 0 else 0.0, np.finfo(float).eps)
        lower = center - sigma_limit * robust_sigma
        upper = center + sigma_limit * robust_sigma
        data["robust_center"] = center
        data["robust_sigma"] = robust_sigma
        data["lower_control_limit"] = lower
        data["upper_control_limit"] = upper
        data["robust_z_score"] = (data["value"] - center) / robust_sigma
        data["pat_status"] = np.where(data["value"].between(lower, upper), "In control", "Review")
        parts.append(data)
        variable_name = data["variable"].iloc[0]
        batch_name = data[batch_column].iloc[0] if batch_column and batch_column in data.columns else "all"
        summary_rows.append({
            "variable": variable_name,
            "batch": str(batch_name),
            "observations": int(len(data)),
            "center": center,
            "lower_control_limit": lower,
            "upper_control_limit": upper,
            "review_points": int((data["pat_status"] == "Review").sum()),
            "status": "Pass" if (data["pat_status"] == "Review").sum() == 0 else "Review",
        })
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), pd.DataFrame(summary_rows)

def convert_absorbance_slope_to_rate(
    slope,
    *,
    extinction_coefficient: float,
    path_length_cm: float,
    dilution_factor: float = 1.0,
) -> np.ndarray:
    """Convert absorbance/time slopes to concentration/time using Beer-Lambert."""

    if extinction_coefficient <= 0 or path_length_cm <= 0 or dilution_factor <= 0:
        raise ValueError("Extinction coefficient, path length and dilution factor must be positive.")
    return np.asarray(slope, dtype=float) * float(dilution_factor) / (float(extinction_coefficient) * float(path_length_cm))


def extract_initial_rates(
    frame: pd.DataFrame,
    *,
    time_column: str = "time",
    signal_column: str = "signal",
    reaction_column: str = "reaction",
    minimum_points: int = 4,
    maximum_points: int | None = None,
    expected_direction: str = "increasing",
    minimum_r_squared: float = 0.95,
    rate_convention: str = "positive",
) -> pd.DataFrame:
    required = {time_column, signal_column, reaction_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing progress-curve columns: " + ", ".join(sorted(missing)))
    if expected_direction not in {"increasing", "decreasing", "auto"}:
        raise ValueError("expected_direction must be increasing, decreasing or auto.")
    if rate_convention not in {"positive", "signed"}:
        raise ValueError("rate_convention must be positive or signed.")
    rows = []
    for reaction, part in frame.groupby(reaction_column, dropna=False):
        data = part[[time_column, signal_column]].apply(pd.to_numeric, errors="coerce").dropna().sort_values(time_column)
        if len(data) < minimum_points:
            rows.append({reaction_column: reaction, "initial_rate": np.nan, "qc_status": "Review", "warning": "insufficient_points"})
            continue
        if np.any(np.diff(data[time_column].to_numpy(float)) <= 0):
            rows.append({reaction_column: reaction, "initial_rate": np.nan, "qc_status": "Review", "warning": "time_not_strictly_increasing"})
            continue
        max_width = min(len(data), maximum_points or max(minimum_points + 4, minimum_points))
        candidates = []
        for width in range(minimum_points, max_width + 1):
            x = data[time_column].to_numpy(float)[:width]
            y = data[signal_column].to_numpy(float)[:width]
            slope, intercept = np.polyfit(x, y, 1)
            predicted = slope * x + intercept
            ss_res = np.square(y - predicted).sum()
            ss_tot = np.square(y - y.mean()).sum()
            r_squared = 1 - ss_res / ss_tot if ss_tot else 1.0
            candidates.append((r_squared - 0.001 * width, slope, intercept, r_squared, width, float(x[-1] - x[0])))
        _, slope, intercept, r_squared, width, span = max(candidates, key=lambda item: item[0])
        direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
        direction_ok = expected_direction == "auto" or direction == expected_direction
        qc_status = "Pass" if direction_ok and r_squared >= minimum_r_squared else "Review"
        warnings = []
        if not direction_ok:
            warnings.append(f"unexpected_{direction}_signal")
        if r_squared < minimum_r_squared:
            warnings.append("weak_linear_window")
        rate = abs(float(slope)) if rate_convention == "positive" and direction_ok else float(slope)
        if not direction_ok:
            rate = np.nan
        rows.append({
            reaction_column: reaction,
            "initial_rate": rate,
            "raw_slope": float(slope),
            "signal_direction": direction,
            "expected_direction": expected_direction,
            "intercept": float(intercept),
            "r_squared": float(r_squared),
            "points_used": int(width),
            "window_time_span": span,
            "qc_status": qc_status,
            "warning": ", ".join(warnings),
        })
    return pd.DataFrame(rows)
