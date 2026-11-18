from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

BOUNDARY = (
    "Internal research-software QC only. Results do not establish clinical, wet-lab, "
    "regulatory, assay or external scientific validity."
)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    if frame.empty:
        raise ValueError("Input table is empty.")
    output = frame.copy()
    output.columns = [
        str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for column in output.columns
    ]
    return output


def _find(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    lookup = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def _cramers_v(left: pd.Series, right: pd.Series) -> float | None:
    table = pd.crosstab(left.fillna("[missing]").astype(str), right.fillna("[missing]").astype(str))
    if table.empty or min(table.shape) < 2:
        return None
    observed = table.to_numpy(float)
    total = float(observed.sum())
    if total <= 1:
        return None
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    valid = expected > 0
    chi2 = float((((observed - expected) ** 2)[valid] / expected[valid]).sum())
    rows, columns = observed.shape
    phi2 = chi2 / total
    correction = ((columns - 1) * (rows - 1)) / max(total - 1, 1)
    phi2 = max(0.0, phi2 - correction)
    corrected_rows = rows - ((rows - 1) ** 2) / max(total - 1, 1)
    corrected_columns = columns - ((columns - 1) ** 2) / max(total - 1, 1)
    denominator = max(min(corrected_rows - 1, corrected_columns - 1), 1e-12)
    return float(min(1.0, math.sqrt(phi2 / denominator)))


def bioinformatics_cohort_readiness(
    metadata: pd.DataFrame,
    *,
    sample_col: str | None = None,
    group_col: str | None = None,
    batch_col: str | None = None,
    genome_build_col: str | None = None,
) -> dict[str, Any]:
    frame = _normalise(metadata)
    sample_col = sample_col or _find(frame.columns, ("sample_id", "sample", "subject_id", "cell_id", "barcode"))
    group_col = group_col or _find(frame.columns, ("group", "condition", "phenotype", "case_control", "label"))
    batch_col = batch_col or _find(frame.columns, ("batch", "batch_id", "site", "centre", "center", "run"))
    genome_build_col = genome_build_col or _find(frame.columns, ("genome_build", "reference_build", "assembly", "build"))

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    if sample_col:
        blank = int(frame[sample_col].isna().sum() + frame[sample_col].astype(str).str.strip().isin({"", "nan", "none"}).sum())
        duplicate = int(frame[sample_col].astype(str).duplicated().sum())
        checks.append({"check": "sample identifiers", "status": "fail" if blank else ("review" if duplicate else "pass"), "value": f"blank={blank}; duplicate={duplicate}"})
        if duplicate:
            warnings.append("Duplicate sample identifiers require explicit repeated-measure or aliquot metadata.")
    else:
        checks.append({"check": "sample identifiers", "status": "review", "value": "column not detected"})
        warnings.append("Sample identifier column was not detected.")

    if genome_build_col:
        builds = sorted({str(value).strip() for value in frame[genome_build_col].dropna() if str(value).strip()})
        status = "pass" if len(builds) == 1 else "fail"
        checks.append({"check": "reference build consistency", "status": status, "value": ", ".join(builds) or "missing"})
        if len(builds) != 1:
            warnings.append("Exactly one declared reference assembly is required before coordinate-aware analysis.")
    else:
        checks.append({"check": "reference build consistency", "status": "review", "value": "not declared"})
        warnings.append("Reference genome/assembly is not declared in metadata.")

    if batch_col:
        sizes = frame.groupby(batch_col, dropna=False).size()
        checks.append({"check": "batch sample coverage", "status": "review" if int(sizes.min()) < 2 else "pass", "value": f"batches={len(sizes)}; min={int(sizes.min())}; max={int(sizes.max())}"})
    if group_col:
        sizes = frame.groupby(group_col, dropna=False).size()
        checks.append({"check": "group sample coverage", "status": "review" if int(sizes.min()) < 3 else "pass", "value": f"groups={len(sizes)}; min={int(sizes.min())}; max={int(sizes.max())}"})
    association = _cramers_v(frame[batch_col], frame[group_col]) if batch_col and group_col else None
    if association is not None:
        checks.append({"check": "batch/group confounding", "status": "review" if association >= 0.7 else "pass", "value": round(association, 4)})
        if association >= 0.7:
            warnings.append("Batch/site and biological group are strongly associated; model estimates may be confounded.")

    missing_fraction = frame.isna().mean().sort_values(ascending=False)
    missingness = pd.DataFrame({"column": missing_fraction.index, "missing_fraction": missing_fraction.values})
    high_missing = missingness.loc[missingness["missing_fraction"] >= 0.25, "column"].tolist()
    if high_missing:
        warnings.append("Columns at least 25% missing: " + ", ".join(map(str, high_missing[:12])))
    check_frame = pd.DataFrame(checks)
    counts = check_frame["status"].value_counts().to_dict() if not check_frame.empty else {}
    score = max(0.0, 10.0 - 2.0 * counts.get("fail", 0) - 0.65 * counts.get("review", 0) - min(2.0, float(missing_fraction.mean()) * 5.0))
    return {
        "summary": {
            "samples": int(len(frame)),
            "columns": int(frame.shape[1]),
            "blocking_checks": int(counts.get("fail", 0)),
            "review_checks": int(counts.get("review", 0)),
            "readiness_score_internal": round(score, 2),
        },
        "checks": check_frame,
        "missingness": missingness,
        "warnings": warnings,
        "scientific_boundary": BOUNDARY,
    }


def count_matrix_quality(
    matrix: pd.DataFrame,
    *,
    feature_col: str | None = None,
) -> dict[str, Any]:
    frame = _normalise(matrix)
    feature_col = feature_col or _find(frame.columns, ("feature_id", "gene_id", "gene", "transcript_id", "protein_id", "taxon"))
    feature_ids = frame.pop(feature_col).astype(str) if feature_col and feature_col in frame else pd.Series([f"feature_{index + 1}" for index in range(len(frame))])
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    if numeric.shape[1] < 2:
        raise ValueError("At least two numeric sample columns are required.")
    valid_fraction = float(numeric.notna().mean().mean())
    negative = int((numeric < 0).sum().sum())
    zero_fraction = float((numeric.fillna(0) == 0).to_numpy().mean())
    sample_qc = pd.DataFrame({
        "sample": numeric.columns.astype(str),
        "library_total": numeric.clip(lower=0).sum(axis=0).to_numpy(float),
        "detected_features": (numeric.fillna(0) > 0).sum(axis=0).to_numpy(int),
        "missing_fraction": numeric.isna().mean(axis=0).to_numpy(float),
        "zero_fraction": (numeric.fillna(0) == 0).mean(axis=0).to_numpy(float),
    })
    sample_qc["library_size_ratio_to_median"] = sample_qc["library_total"] / max(float(sample_qc["library_total"].median()), 1e-12)
    feature_qc = pd.DataFrame({
        "feature_id": feature_ids,
        "mean_abundance": numeric.mean(axis=1).to_numpy(float),
        "detected_samples": (numeric.fillna(0) > 0).sum(axis=1).to_numpy(int),
        "missing_fraction": numeric.isna().mean(axis=1).to_numpy(float),
    }).sort_values(["detected_samples", "mean_abundance"], ascending=[False, False])
    warnings: list[str] = []
    if negative:
        warnings.append(f"{negative} negative count-like values were found.")
    if valid_fraction < 0.95:
        warnings.append("More than 5% of count-matrix cells are non-numeric or missing.")
    low_library = int(((sample_qc["library_size_ratio_to_median"] < 0.25) | (sample_qc["library_size_ratio_to_median"] > 4.0)).sum())
    if low_library:
        warnings.append(f"{low_library} sample(s) have library totals outside 0.25–4× the median.")
    return {
        "summary": {
            "features": int(len(numeric)),
            "samples": int(numeric.shape[1]),
            "valid_numeric_fraction": round(valid_fraction, 4),
            "negative_values": negative,
            "zero_fraction": round(zero_fraction, 4),
            "library_size_outliers": low_library,
        },
        "sample_qc": sample_qc.sort_values("library_total").reset_index(drop=True),
        "feature_qc": feature_qc.reset_index(drop=True),
        "warnings": warnings,
        "scientific_boundary": BOUNDARY,
    }


def discovery_assay_readiness(
    data: pd.DataFrame,
    *,
    compound_col: str | None = None,
    value_col: str | None = None,
    unit_col: str | None = None,
    assay_col: str | None = None,
) -> dict[str, Any]:
    frame = _normalise(data)
    compound_col = compound_col or _find(frame.columns, ("compound_id", "molecule_id", "ligand_id", "id"))
    value_col = value_col or _find(frame.columns, ("activity_value", "activity", "ic50", "ec50", "ki", "kd"))
    unit_col = unit_col or _find(frame.columns, ("activity_unit", "unit", "units"))
    assay_col = assay_col or _find(frame.columns, ("assay_id", "assay", "endpoint"))
    if not compound_col or not value_col:
        raise ValueError("Compound and activity columns are required.")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    invalid = int(values.isna().sum())
    nonpositive = int((values <= 0).fillna(False).sum())
    unit_map = {"m": 1e9, "mm": 1e6, "um": 1e3, "µm": 1e3, "nm": 1.0, "pm": 1e-3}
    units = frame[unit_col].astype(str).str.strip().str.lower() if unit_col else pd.Series(["nm"] * len(frame), index=frame.index)
    multiplier = units.map(unit_map)
    unknown_units = sorted({str(unit) for unit in units[multiplier.isna()].unique()})
    activity_nm = values * multiplier
    activity_nm[(values <= 0) | multiplier.isna()] = np.nan
    normalised = frame.copy()
    normalised["activity_nm"] = activity_nm
    normalised["pactivity"] = -np.log10(activity_nm * 1e-9)
    replicate_group = [compound_col] + ([assay_col] if assay_col else [])
    replicate = normalised.groupby(replicate_group, dropna=False)["pactivity"].agg(["count", "mean", "std"]).reset_index()
    replicate["replicate_range_log10"] = normalised.groupby(replicate_group, dropna=False)["pactivity"].agg(lambda series: float(series.max() - series.min()) if series.notna().any() else np.nan).to_numpy()
    discordant = int((replicate["replicate_range_log10"] > 1.0).sum())
    duplicate_rows = int(frame.duplicated().sum())
    warnings: list[str] = []
    if invalid:
        warnings.append(f"{invalid} activity values are non-numeric or missing.")
    if nonpositive:
        warnings.append(f"{nonpositive} activity values are non-positive and cannot be converted to pActivity.")
    if unknown_units:
        warnings.append("Unsupported activity units: " + ", ".join(unknown_units[:12]))
    if discordant:
        warnings.append(f"{discordant} compound/assay replicate groups span more than one log10 unit.")
    return {
        "summary": {
            "rows": int(len(frame)),
            "compounds": int(frame[compound_col].nunique(dropna=True)),
            "assays": int(frame[assay_col].nunique(dropna=True)) if assay_col else 1,
            "invalid_values": invalid,
            "nonpositive_values": nonpositive,
            "unsupported_units": len(unknown_units),
            "discordant_replicate_groups": discordant,
            "duplicate_rows": duplicate_rows,
        },
        "normalised_records": normalised,
        "replicate_qc": replicate.sort_values(["replicate_range_log10", "count"], ascending=[False, False]).reset_index(drop=True),
        "warnings": warnings,
        "scientific_boundary": BOUNDARY,
    }


def pareto_rank_candidates(
    data: pd.DataFrame,
    *,
    id_col: str | None = None,
    maximize: Iterable[str] = (),
    minimize: Iterable[str] = (),
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    frame = _normalise(data)
    id_col = id_col or _find(frame.columns, ("compound_id", "candidate_id", "molecule_id", "id"))
    if not id_col:
        frame.insert(0, "candidate_id", [f"candidate_{i + 1}" for i in range(len(frame))])
        id_col = "candidate_id"
    maximize = [str(column).lower().replace(" ", "_") for column in maximize]
    minimize = [str(column).lower().replace(" ", "_") for column in minimize]
    objectives = [column for column in maximize + minimize if column in frame.columns]
    if not objectives:
        raise ValueError("At least one valid numeric objective is required.")
    numeric = frame[objectives].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().all(axis=1)
    if int(valid.sum()) < 2:
        raise ValueError("At least two complete candidates are required for Pareto ranking.")
    oriented = numeric.loc[valid].copy()
    for column in minimize:
        if column in oriented:
            oriented[column] = -oriented[column]
    scaled = pd.DataFrame(index=oriented.index)
    for column in objectives:
        minimum, maximum = oriented[column].min(), oriented[column].max()
        scaled[column] = 0.5 if maximum == minimum else (oriented[column] - minimum) / (maximum - minimum)
    weights = weights or {}
    weight_vector = np.array([max(float(weights.get(column, 1.0)), 0.0) for column in objectives], dtype=float)
    if float(weight_vector.sum()) <= 0:
        weight_vector[:] = 1.0
    weight_vector /= weight_vector.sum()
    scores = scaled.to_numpy(float) @ weight_vector
    values = oriented.to_numpy(float)
    dominated = np.zeros(len(oriented), dtype=bool)
    dominance_count = np.zeros(len(oriented), dtype=int)
    for i in range(len(oriented)):
        for j in range(len(oriented)):
            if i == j:
                continue
            if np.all(values[j] >= values[i]) and np.any(values[j] > values[i]):
                dominated[i] = True
                dominance_count[i] += 1
    ranked = frame.loc[valid].copy()
    ranked["pareto_front"] = ~dominated
    ranked["dominance_count"] = dominance_count
    ranked["weighted_internal_score"] = scores
    ranked = ranked.sort_values(["pareto_front", "dominance_count", "weighted_internal_score"], ascending=[False, True, False]).reset_index(drop=True)
    ranked["internal_rank"] = np.arange(1, len(ranked) + 1)
    excluded = frame.loc[~valid, [id_col]].copy()
    excluded["reason"] = "Missing or non-numeric objective value"
    return {
        "summary": {"candidates": int(len(frame)), "ranked": int(len(ranked)), "pareto_front": int(ranked["pareto_front"].sum()), "excluded": int(len(excluded))},
        "ranking": ranked,
        "excluded": excluded,
        "objective_orientation": {column: "maximize" if column in maximize else "minimize" for column in objectives},
        "scientific_boundary": BOUNDARY + " Ranking is decision support, not proof of efficacy, safety, novelty or developability.",
    }


def lab_assay_quality(
    data: pd.DataFrame,
    *,
    value_col: str | None = None,
    sample_col: str | None = None,
    batch_col: str | None = None,
    role_col: str | None = None,
) -> dict[str, Any]:
    frame = _normalise(data)
    value_col = value_col or _find(frame.columns, ("value", "signal", "response", "concentration", "ct", "cq"))
    sample_col = sample_col or _find(frame.columns, ("sample_id", "sample", "well_id", "specimen_id"))
    batch_col = batch_col or _find(frame.columns, ("batch", "batch_id", "plate", "plate_id", "run_id"))
    role_col = role_col or _find(frame.columns, ("role", "control_type", "sample_type", "control"))
    if not value_col:
        raise ValueError("A numeric measurement column is required.")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    invalid = int(values.isna().sum())
    working = frame.assign(_value=values)
    replicate_qc = pd.DataFrame()
    if sample_col:
        replicate_qc = working.groupby(sample_col, dropna=False)["_value"].agg(["count", "mean", "std", "min", "max"]).reset_index()
        replicate_qc["cv"] = replicate_qc["std"] / replicate_qc["mean"].abs().replace(0, np.nan)
        replicate_qc["range"] = replicate_qc["max"] - replicate_qc["min"]
        replicate_qc = replicate_qc.sort_values(["cv", "count"], ascending=[False, False]).reset_index(drop=True)
    batch_qc = pd.DataFrame()
    if batch_col:
        batch_qc = working.groupby(batch_col, dropna=False)["_value"].agg(["count", "mean", "std", "median"]).reset_index()
        global_median = float(values.median()) if values.notna().any() else np.nan
        scale = float(values.std(ddof=1)) if values.notna().sum() > 1 else np.nan
        batch_qc["drift_z"] = (batch_qc["median"] - global_median) / scale if math.isfinite(scale) and scale > 0 else 0.0
        batch_qc = batch_qc.sort_values("drift_z", key=lambda series: series.abs(), ascending=False).reset_index(drop=True)
    control_qc = pd.DataFrame()
    z_prime = float("nan")
    if role_col:
        roles = frame[role_col].astype(str).str.lower().str.strip()
        positive = working[roles.str.contains(r"positive|high|stimulated", regex=True, na=False)]["_value"].dropna()
        negative = working[roles.str.contains(r"negative|low|vehicle|blank", regex=True, na=False)]["_value"].dropna()
        if len(positive) >= 2 and len(negative) >= 2:
            denominator = abs(float(positive.mean() - negative.mean()))
            z_prime = 1.0 - 3.0 * (float(positive.std(ddof=1)) + float(negative.std(ddof=1))) / denominator if denominator > 0 else float("-inf")
            control_qc = pd.DataFrame([
                {"control": "positive/high", "n": len(positive), "mean": float(positive.mean()), "sd": float(positive.std(ddof=1))},
                {"control": "negative/low", "n": len(negative), "mean": float(negative.mean()), "sd": float(negative.std(ddof=1))},
            ])
    high_cv = int((replicate_qc.get("cv", pd.Series(dtype=float)) > 0.20).sum()) if not replicate_qc.empty else 0
    batch_drift = int((batch_qc.get("drift_z", pd.Series(dtype=float)).abs() > 2.0).sum()) if not batch_qc.empty else 0
    warnings: list[str] = []
    if invalid:
        warnings.append(f"{invalid} measurements are non-numeric or missing.")
    if high_cv:
        warnings.append(f"{high_cv} replicate groups have CV above 20%.")
    if batch_drift:
        warnings.append(f"{batch_drift} batch/plate medians exceed ±2 SD from the global median.")
    if math.isfinite(z_prime) and z_prime < 0.5:
        warnings.append(f"Z-prime is {z_prime:.3f}; control separation requires review.")
    if role_col and not math.isfinite(z_prime):
        warnings.append("Positive and negative controls with at least two observations each were not identified.")
    return {
        "summary": {
            "rows": int(len(frame)),
            "invalid_measurements": invalid,
            "replicate_groups": int(len(replicate_qc)),
            "high_cv_groups": high_cv,
            "batches": int(len(batch_qc)),
            "batch_drift_flags": batch_drift,
            "z_prime": z_prime,
        },
        "replicate_qc": replicate_qc,
        "batch_qc": batch_qc,
        "control_qc": control_qc,
        "warnings": warnings,
        "scientific_boundary": BOUNDARY + " Laboratory acceptance limits must be defined and approved by the operating laboratory.",
    }


def demo_frame(kind: str, seed: int = 207) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if kind == "bioinformatics_metadata":
        samples = 24
        return pd.DataFrame({
            "sample_id": [f"S{i+1:03d}" for i in range(samples)],
            "group": ["case"] * 12 + ["control"] * 12,
            "batch": np.tile(["B1", "B2", "B3", "B4"], 6),
            "genome_build": ["GRCh38"] * samples,
            "sex": rng.choice(["F", "M"], size=samples),
        })
    if kind == "count_matrix":
        values = rng.poisson(lam=rng.uniform(3, 40, size=(80, 1)), size=(80, 12))
        return pd.DataFrame(values, columns=[f"sample_{i+1}" for i in range(12)]).assign(feature_id=[f"gene_{i+1}" for i in range(80)])[ ["feature_id"] + [f"sample_{i+1}" for i in range(12)] ]
    if kind == "discovery_assay":
        compounds = np.repeat([f"CMPD_{i+1:03d}" for i in range(18)], 3)
        base = np.repeat(rng.uniform(5, 800, size=18), 3)
        values = base * rng.lognormal(0, 0.15, size=len(base))
        return pd.DataFrame({"compound_id": compounds, "assay_id": "binding_A", "activity_value": values, "activity_unit": "nM"})
    if kind == "pareto":
        return pd.DataFrame({
            "compound_id": [f"CMPD_{i+1:03d}" for i in range(30)],
            "potency": rng.uniform(5.0, 9.0, size=30),
            "selectivity": rng.uniform(0.0, 1.0, size=30),
            "clearance": rng.uniform(1.0, 80.0, size=30),
            "toxicity_proxy": rng.uniform(0.0, 1.0, size=30),
        })
    if kind == "lab_assay":
        rows: list[dict[str, Any]] = []
        for plate in ("P1", "P2"):
            for sample_index in range(12):
                role = "positive" if sample_index < 2 else ("negative" if sample_index < 4 else "sample")
                mean = 90 if role == "positive" else (10 if role == "negative" else 45 + sample_index)
                for replicate in range(3):
                    rows.append({"plate_id": plate, "sample_id": f"{plate}_S{sample_index+1:02d}", "replicate": replicate + 1, "role": role, "signal": float(rng.normal(mean, 3))})
        return pd.DataFrame(rows)
    raise KeyError(f"Unknown demo kind: {kind}")


__all__ = [
    "BOUNDARY",
    "bioinformatics_cohort_readiness",
    "count_matrix_quality",
    "discovery_assay_readiness",
    "pareto_rank_candidates",
    "lab_assay_quality",
    "demo_frame",
]
