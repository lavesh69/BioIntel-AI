from __future__ import annotations

"""Deterministic specialist planning engines used by the Research Planning suite.

The functions in this module are deliberately local-first and bounded.  They are
planning and verification utilities, not regulatory certification or a
replacement for qualified scientific/statistical review.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import platform
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm


MAX_INTERACTIVE_ROWS = 250_000
MAX_SIMULATIONS = 50_000
MAX_TASKS = 2_000
MAX_SPECIMENS = 250_000


@dataclass(frozen=True)
class EngineOutput:
    engine_key: str
    primary: pd.DataFrame
    tables: Mapping[str, pd.DataFrame]
    summary: Mapping[str, Any]
    warnings: tuple[str, ...] = ()

    def manifest(self) -> dict[str, Any]:
        table_hashes = {
            name: dataframe_digest(table)
            for name, table in {"primary": self.primary, **dict(self.tables)}.items()
        }
        payload = {
            "engine_key": self.engine_key,
            "summary": dict(self.summary),
            "warnings": list(self.warnings),
            "table_hashes": table_hashes,
        }
        payload["manifest_sha256"] = sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return payload


def dataframe_digest(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256(payload).hexdigest()


def _bounded_rows(frame: pd.DataFrame, *, limit: int = MAX_INTERACTIVE_ROWS) -> pd.DataFrame:
    if len(frame) > limit:
        raise ValueError(f"Input contains {len(frame):,} rows; specialist workspace limit is {limit:,}.")
    return frame.copy()


def _numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(float)


def _normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalise_identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalise_text(value).lower())


def normalise_doi(value: Any) -> str:
    text = _normalise_text(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.strip().rstrip(".")


# ---------------------------------------------------------------------------
# Evidence gap and literature planning
# ---------------------------------------------------------------------------


def _title_signature(title: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    stop = {"a", "an", "the", "of", "for", "to", "and", "in", "on", "with", "by"}
    return tuple(sorted(token for token in tokens if token not in stop))


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def literature_evidence_workbench(studies: pd.DataFrame) -> EngineOutput:
    required = {
        "study_id", "title", "doi", "year", "design", "quality", "effect",
        "standard_error", "screening_status", "population", "outcome",
    }
    missing = required - set(studies.columns)
    if missing:
        raise ValueError("Literature table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(studies, limit=50_000)
    if data.empty:
        raise ValueError("At least one literature record is required.")

    data["study_id"] = data["study_id"].map(_normalise_text)
    if data["study_id"].eq("").any() or data["study_id"].duplicated().any():
        raise ValueError("Study identifiers must be non-empty and unique.")
    data["title"] = data["title"].map(_normalise_text)
    data["normalised_title"] = data["title"].map(_normalise_identifier)
    data["normalised_doi"] = data["doi"].map(normalise_doi)
    data["year"] = _numeric(data["year"], 0).round().astype(int)
    data["effect"] = _numeric(data["effect"], np.nan)
    data["standard_error"] = _numeric(data["standard_error"], np.nan)
    data["quality"] = data["quality"].map(_normalise_text)
    data["screening_status"] = data["screening_status"].map(_normalise_text)

    duplicate_group = pd.Series("", index=data.index, dtype="object")
    duplicate_reason = pd.Series("", index=data.index, dtype="object")
    seen: dict[tuple[str, str], int] = {}
    group_counter = 0
    for idx, row in data.iterrows():
        keys: list[tuple[str, str]] = []
        if row["normalised_doi"]:
            keys.append(("doi", row["normalised_doi"]))
        if row["normalised_title"]:
            keys.append(("title", f"{row['year']}:{row['normalised_title']}"))
        found = next((seen[key] for key in keys if key in seen), None)
        if found is None:
            group_counter += 1
            found = group_counter
        for key in keys:
            seen.setdefault(key, found)
        duplicate_group.at[idx] = f"DUP-{found:05d}"
        duplicate_reason.at[idx] = "Exact DOI/title" if any(key in seen and seen[key] == found for key in keys) else ""

    # Bounded near-title duplicate review within publication year.
    candidate_rows = data.loc[data["title"].ne(""), ["year", "title"]].head(5_000)
    signatures = {idx: _title_signature(title) for idx, title in candidate_rows["title"].items()}
    near_pairs: list[dict[str, Any]] = []
    for _, group in candidate_rows.groupby("year"):
        indices = list(group.index)
        # Limit comparisons per year to protect interactive runtime.
        if len(indices) > 300:
            indices = indices[:300]
        for pos, left_idx in enumerate(indices):
            for right_idx in indices[pos + 1:]:
                if duplicate_group.at[left_idx] == duplicate_group.at[right_idx]:
                    continue
                score = _jaccard(signatures[left_idx], signatures[right_idx])
                if score >= 0.86:
                    near_pairs.append({
                        "study_id_a": data.at[left_idx, "study_id"],
                        "study_id_b": data.at[right_idx, "study_id"],
                        "year": int(data.at[left_idx, "year"]),
                        "title_similarity": round(score, 4),
                        "review_status": "Potential duplicate",
                    })
                    if len(near_pairs) >= 2_000:
                        break
            if len(near_pairs) >= 2_000:
                break
        if len(near_pairs) >= 2_000:
            break

    data["duplicate_group"] = duplicate_group
    group_sizes = data.groupby("duplicate_group")["study_id"].transform("size")
    data["duplicate_cluster_size"] = group_sizes
    data["is_duplicate"] = data.duplicated("duplicate_group", keep="first")
    data["duplicate_reason"] = np.where(data["is_duplicate"], "Exact DOI or normalized title", "")

    usable = data.loc[
        data["screening_status"].str.lower().isin({"included", "include", "eligible"})
        & data["effect"].notna()
        & data["standard_error"].gt(0)
        & ~data["is_duplicate"]
    ].copy()
    if usable.empty:
        meta = pd.DataFrame(columns=["pooled_effect", "ci_low", "ci_high", "q", "i2", "studies"])
        pooled_effect = np.nan
        i2 = np.nan
    else:
        weights = 1.0 / np.square(usable["standard_error"].to_numpy(float))
        effects = usable["effect"].to_numpy(float)
        pooled_effect = float(np.sum(weights * effects) / np.sum(weights))
        pooled_se = float(math.sqrt(1.0 / np.sum(weights)))
        q = float(np.sum(weights * np.square(effects - pooled_effect)))
        df = max(1, len(usable) - 1)
        i2 = max(0.0, 100.0 * (q - df) / q) if q > 0 else 0.0
        meta = pd.DataFrame([{
            "pooled_effect": pooled_effect,
            "standard_error": pooled_se,
            "ci_low": pooled_effect - 1.96 * pooled_se,
            "ci_high": pooled_effect + 1.96 * pooled_se,
            "q": q,
            "i2": i2,
            "studies": int(len(usable)),
            "model": "Inverse-variance fixed effect",
        }])

    quality_weights = data["quality"].str.lower().map({
        "high": 1.0, "moderate": 0.75, "low": 0.45, "very low": 0.2,
    }).fillna(0.35)
    design_weights = data["design"].astype(str).str.lower().map({
        "randomized trial": 1.0, "randomised trial": 1.0, "rct": 1.0,
        "prospective cohort": 0.8, "cohort": 0.75, "case-control": 0.65,
        "cross-sectional": 0.5, "case series": 0.25,
    }).fillna(0.4)
    data["evidence_weight"] = (quality_weights * design_weights).round(4)
    if np.isfinite(pooled_effect):
        data["direction_conflict"] = data["effect"].notna() & (np.sign(data["effect"]) != np.sign(pooled_effect))
    else:
        data["direction_conflict"] = False

    contradiction = data.groupby(["population", "outcome"], dropna=False).agg(
        studies=("study_id", "count"),
        positive=("effect", lambda s: int((pd.to_numeric(s, errors="coerce") > 0).sum())),
        negative=("effect", lambda s: int((pd.to_numeric(s, errors="coerce") < 0).sum())),
        mean_weight=("evidence_weight", "mean"),
    ).reset_index()
    contradiction["contradiction_flag"] = contradiction["positive"].gt(0) & contradiction["negative"].gt(0)

    status = data["screening_status"].str.lower()
    prisma = pd.DataFrame([
        {"stage": "Imported", "records": int(len(data))},
        {"stage": "Duplicates", "records": int(data["is_duplicate"].sum())},
        {"stage": "Screened", "records": int(status.isin({"screened", "excluded", "included", "include", "eligible"}).sum())},
        {"stage": "Excluded", "records": int(status.eq("excluded").sum())},
        {"stage": "Included", "records": int(status.isin({"included", "include", "eligible"}).sum())},
        {"stage": "Meta-analysis", "records": int(len(usable))},
    ])

    certainty_points = 4.0
    if float(quality_weights.mean()) < 0.7:
        certainty_points -= 1
    if np.isfinite(i2) and i2 > 50:
        certainty_points -= 1
    if len(usable) < 5:
        certainty_points -= 1
    if contradiction["contradiction_flag"].any():
        certainty_points -= 1
    certainty = {4: "High", 3: "Moderate", 2: "Low", 1: "Very low", 0: "Very low"}.get(max(0, round(certainty_points)), "Very low")

    summary = {
        "records": int(len(data)),
        "exact_duplicate_records": int(data["is_duplicate"].sum()),
        "potential_duplicate_pairs": int(len(near_pairs)),
        "included_unique_studies": int(len(usable)),
        "pooled_effect": None if not np.isfinite(pooled_effect) else round(pooled_effect, 6),
        "heterogeneity_i2": None if not np.isfinite(i2) else round(float(i2), 2),
        "certainty": certainty,
        "contradictory_questions": int(contradiction["contradiction_flag"].sum()),
    }
    warnings = []
    if data["is_duplicate"].any():
        warnings.append("Exact duplicate records were excluded from pooled calculations.")
    if len(usable) < 2:
        warnings.append("Fewer than two unique included studies have usable effect estimates.")
    if np.isfinite(i2) and i2 > 75:
        warnings.append("Very high heterogeneity: investigate population, intervention and outcome differences.")
    return EngineOutput(
        "evidence_gap_literature_specialist",
        data,
        {
            "prisma": prisma,
            "near_duplicates": pd.DataFrame(near_pairs),
            "meta_analysis": meta,
            "contradiction_matrix": contradiction,
        },
        summary,
        tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Preregistration and reproducibility
# ---------------------------------------------------------------------------


def preregistration_integrity_audit(items: pd.DataFrame, artifacts: pd.DataFrame | None = None) -> EngineOutput:
    required = {"item", "section", "planned_value", "executed_value", "reported_value", "locked", "deviation_reason"}
    missing = required - set(items.columns)
    if missing:
        raise ValueError("Preregistration table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(items, limit=100_000)
    if data.empty:
        raise ValueError("At least one preregistration item is required.")
    data["item"] = data["item"].map(_normalise_text)
    if data["item"].eq("").any() or data["item"].duplicated().any():
        raise ValueError("Preregistration item names must be non-empty and unique.")
    for column in ["section", "planned_value", "executed_value", "reported_value", "deviation_reason"]:
        data[column] = data[column].map(_normalise_text)
    data["locked"] = data["locked"].astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "locked"})
    data["plan_execution_match"] = data["planned_value"].eq(data["executed_value"])
    data["plan_report_match"] = data["planned_value"].eq(data["reported_value"])
    data["execution_report_match"] = data["executed_value"].eq(data["reported_value"])
    data["outcome_switch"] = (
        data["section"].str.lower().str.contains("outcome|endpoint", regex=True)
        & ~data["plan_report_match"]
    )
    data["undisclosed_deviation"] = (~data["plan_execution_match"] | ~data["plan_report_match"]) & data["deviation_reason"].eq("")
    data["severity"] = np.select(
        [data["outcome_switch"] & data["undisclosed_deviation"], data["undisclosed_deviation"], ~data["plan_report_match"]],
        ["Critical", "High", "Moderate"],
        default="None",
    )
    canonical_columns = ["item", "section", "planned_value", "locked"]
    data["item_lock_sha256"] = data[canonical_columns].astype(str).agg("|".join, axis=1).map(lambda value: sha256(value.encode()).hexdigest())

    artifact_table = pd.DataFrame(columns=["artifact", "declared_sha256", "verified", "status"])
    if artifacts is not None and not artifacts.empty:
        artifact_table = _bounded_rows(artifacts, limit=10_000)
        required_artifacts = {"artifact", "declared_sha256"}
        missing_artifacts = required_artifacts - set(artifact_table.columns)
        if missing_artifacts:
            raise ValueError("Artifact table is missing: " + ", ".join(sorted(missing_artifacts)))
        artifact_table["artifact"] = artifact_table["artifact"].map(_normalise_text)
        artifact_table["declared_sha256"] = artifact_table["declared_sha256"].astype(str).str.lower().str.strip()
        artifact_table["verified"] = artifact_table["declared_sha256"].str.fullmatch(r"[0-9a-f]{64}", na=False)
        artifact_table["status"] = np.where(artifact_table["verified"], "Hash format valid", "Invalid or missing SHA-256")

    environment = pd.DataFrame([
        {"component": "python", "version": platform.python_version(), "detail": sys.executable},
        {"component": "platform", "version": platform.platform(), "detail": platform.machine()},
        {"component": "numpy", "version": np.__version__, "detail": "runtime"},
        {"component": "pandas", "version": pd.__version__, "detail": "runtime"},
    ])
    lock_payload = data[canonical_columns].sort_values("item").to_dict(orient="records")
    prereg_hash = sha256(json.dumps(lock_payload, sort_keys=True).encode()).hexdigest()
    alignment = pd.DataFrame([
        {"comparison": "Planned vs executed", "aligned": int(data["plan_execution_match"].sum()), "changed": int((~data["plan_execution_match"]).sum())},
        {"comparison": "Planned vs reported", "aligned": int(data["plan_report_match"].sum()), "changed": int((~data["plan_report_match"]).sum())},
        {"comparison": "Executed vs reported", "aligned": int(data["execution_report_match"].sum()), "changed": int((~data["execution_report_match"]).sum())},
    ])
    summary = {
        "items": int(len(data)),
        "locked_items": int(data["locked"].sum()),
        "outcome_switches": int(data["outcome_switch"].sum()),
        "undisclosed_deviations": int(data["undisclosed_deviation"].sum()),
        "plan_report_alignment": round(float(data["plan_report_match"].mean()), 4),
        "preregistration_sha256": prereg_hash,
        "verified_artifacts": int(artifact_table["verified"].sum()) if not artifact_table.empty else 0,
    }
    warnings = []
    if summary["outcome_switches"]:
        warnings.append("Outcome or endpoint changes require transparent amendment and interpretation.")
    if summary["undisclosed_deviations"]:
        warnings.append("Some deviations do not have a recorded reason.")
    return EngineOutput(
        "preregistration_reproducibility_specialist",
        data,
        {"alignment": alignment, "artifacts": artifact_table, "environment": environment},
        summary,
        tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Clinical trial operating characteristics and dose escalation
# ---------------------------------------------------------------------------


def alpha_spending_boundaries(alpha: float, information_fractions: Sequence[float], method: str = "OBrien-Fleming") -> pd.DataFrame:
    if not 0 < alpha < 0.5:
        raise ValueError("Alpha must be between 0 and 0.5.")
    fractions = np.asarray(information_fractions, dtype=float)
    if fractions.size < 1 or np.any(fractions <= 0) or np.any(fractions > 1) or np.any(np.diff(fractions) <= 0):
        raise ValueError("Information fractions must be strictly increasing in (0, 1].")
    name = method.strip().lower().replace("'", "").replace("-", "")
    if name in {"obrienfleming", "obf"}:
        z_final = norm.ppf(1 - alpha / 2)
        cumulative_alpha = 2 * (1 - norm.cdf(z_final / np.sqrt(fractions)))
    elif name == "pocock":
        cumulative_alpha = alpha * np.log(1 + (math.e - 1) * fractions)
    else:
        raise ValueError("Supported spending methods are OBrien-Fleming and Pocock.")
    cumulative_alpha = np.maximum.accumulate(np.clip(cumulative_alpha, 1e-12, alpha))
    boundaries = norm.ppf(1 - cumulative_alpha / 2)
    incremental = np.diff(np.r_[0.0, cumulative_alpha])
    return pd.DataFrame({
        "look": np.arange(1, len(fractions) + 1),
        "information_fraction": fractions,
        "cumulative_alpha": cumulative_alpha,
        "incremental_alpha": incremental,
        "two_sided_z_boundary": boundaries,
        "spending_method": method,
    })


def simulate_group_sequential_trial(
    effect_size: float,
    total_sample_size: int,
    alpha: float = 0.05,
    information_fractions: Sequence[float] = (0.33, 0.67, 1.0),
    method: str = "OBrien-Fleming",
    simulations: int = 10_000,
    seed: int = 144,
) -> EngineOutput:
    if total_sample_size < 4 or total_sample_size > 10_000_000:
        raise ValueError("Total sample size must be between 4 and 10,000,000.")
    if simulations < 500 or simulations > MAX_SIMULATIONS:
        raise ValueError(f"Simulations must be between 500 and {MAX_SIMULATIONS:,}.")
    boundaries = alpha_spending_boundaries(alpha, information_fractions, method)
    fractions = boundaries["information_fraction"].to_numpy(float)
    boundary = boundaries["two_sided_z_boundary"].to_numpy(float)
    rng = np.random.default_rng(seed)

    def run(true_effect: float) -> tuple[np.ndarray, np.ndarray]:
        increments = np.diff(np.r_[0.0, fractions])
        brownian = np.cumsum(rng.normal(0, np.sqrt(increments), size=(simulations, len(fractions))), axis=1)
        z = brownian / np.sqrt(fractions)[None, :] + true_effect * math.sqrt(total_sample_size / 4) * np.sqrt(fractions)[None, :]
        crossed = np.abs(z) >= boundary[None, :]
        first = np.where(crossed.any(axis=1), crossed.argmax(axis=1), len(fractions) - 1)
        rejected = crossed.any(axis=1)
        return first, rejected

    effect_look, effect_reject = run(effect_size)
    null_look, null_reject = run(0.0)
    expected_n = float(np.mean(total_sample_size * fractions[effect_look]))
    oc = pd.DataFrame([
        {"scenario": "Null", "true_effect": 0.0, "rejection_probability": float(null_reject.mean()), "expected_sample_size": float(np.mean(total_sample_size * fractions[null_look]))},
        {"scenario": "Alternative", "true_effect": effect_size, "rejection_probability": float(effect_reject.mean()), "expected_sample_size": expected_n},
    ])
    stopping = pd.DataFrame({
        "look": boundaries["look"],
        "information_fraction": fractions,
        "alternative_stop_probability": [float(np.mean((effect_look == idx) & effect_reject)) for idx in range(len(fractions))],
        "null_stop_probability": [float(np.mean((null_look == idx) & null_reject)) for idx in range(len(fractions))],
    })
    summary = {
        "simulations": simulations,
        "estimated_power": round(float(effect_reject.mean()), 5),
        "estimated_type1_error": round(float(null_reject.mean()), 5),
        "expected_sample_size_under_alternative": round(expected_n, 2),
        "maximum_sample_size": int(total_sample_size),
        "seed": int(seed),
    }
    warnings = []
    if summary["estimated_type1_error"] > alpha + 0.01:
        warnings.append("Estimated type-I error exceeds the configured alpha by more than one percentage point.")
    return EngineOutput("group_sequential_trial", oc, {"boundaries": boundaries, "stopping": stopping}, summary, tuple(warnings))


def dose_escalation_decisions(doses: pd.DataFrame) -> EngineOutput:
    required = {"dose", "participants", "dose_limiting_toxicities"}
    missing = required - set(doses.columns)
    if missing:
        raise ValueError("Dose table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(doses, limit=500).copy()
    data["dose"] = _numeric(data["dose"], np.nan)
    data["participants"] = _numeric(data["participants"], 0).round().astype(int)
    data["dose_limiting_toxicities"] = _numeric(data["dose_limiting_toxicities"], 0).round().astype(int)
    if data["dose"].isna().any() or data["participants"].le(0).any():
        raise ValueError("Every dose must be numeric and have at least one participant.")
    if (data["dose_limiting_toxicities"] > data["participants"]).any():
        raise ValueError("Dose-limiting toxicities cannot exceed participants.")
    data = data.sort_values("dose").reset_index(drop=True)
    rate = data["dose_limiting_toxicities"] / data["participants"]
    data["toxicity_rate"] = rate
    data["decision_3plus3"] = np.select(
        [
            (data["participants"] <= 3) & data["dose_limiting_toxicities"].eq(0),
            (data["participants"] <= 3) & data["dose_limiting_toxicities"].eq(1),
            data["dose_limiting_toxicities"].ge(2),
            (data["participants"] >= 6) & data["dose_limiting_toxicities"].le(1),
        ],
        ["Escalate", "Expand to 6", "Stop / de-escalate", "Escalate"],
        default="Review",
    )
    # Wilson interval for toxicity probability.
    z = 1.96
    n = data["participants"].astype(float)
    p = rate.astype(float)
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    half = z * np.sqrt((p * (1 - p) / n) + z**2 / (4 * n**2)) / denominator
    data["toxicity_ci_low"] = np.maximum(0, center - half)
    data["toxicity_ci_high"] = np.minimum(1, center + half)
    stop_rows = data.index[data["decision_3plus3"].eq("Stop / de-escalate")]
    recommended = None
    if len(stop_rows):
        idx = int(stop_rows[0])
        recommended = float(data.iloc[max(0, idx - 1)]["dose"])
    else:
        acceptable = data.loc[data["toxicity_rate"].le(0.33)]
        recommended = float(acceptable.iloc[-1]["dose"]) if not acceptable.empty else None
    summary = {
        "dose_levels": int(len(data)),
        "participants": int(data["participants"].sum()),
        "total_dlts": int(data["dose_limiting_toxicities"].sum()),
        "recommended_mtd_screening": recommended,
    }
    return EngineOutput("dose_escalation_3plus3", data, {}, summary, ("3+3 is a screening rule and not a model-based dose-finding method.",))


# ---------------------------------------------------------------------------
# Design of experiments
# ---------------------------------------------------------------------------


def generate_factorial_design(factors: Mapping[str, Sequence[float]], center_points: int = 0, seed: int = 144) -> pd.DataFrame:
    if not factors:
        raise ValueError("At least one factor is required.")
    if len(factors) > 10:
        raise ValueError("Interactive factorial generation supports at most 10 factors.")
    names = list(factors)
    levels = []
    for name, values in factors.items():
        clean = [float(value) for value in values]
        if len(clean) < 2 or len(clean) > 10:
            raise ValueError(f"Factor {name} must have between 2 and 10 levels.")
        levels.append(clean)
    total = int(np.prod([len(item) for item in levels])) + max(0, int(center_points))
    if total > 100_000:
        raise ValueError("Generated design would exceed 100,000 runs.")
    import itertools
    rows = [dict(zip(names, values)) for values in itertools.product(*levels)]
    if center_points:
        centre = {name: float(np.mean(values)) for name, values in factors.items()}
        rows.extend([dict(centre) for _ in range(int(center_points))])
    design = pd.DataFrame(rows)
    rng = np.random.default_rng(seed)
    design.insert(0, "run_order", rng.permutation(np.arange(1, len(design) + 1)))
    design = design.sort_values("run_order").reset_index(drop=True)
    design.insert(0, "run_id", [f"RUN-{idx + 1:05d}" for idx in range(len(design))])
    return design


def generate_central_composite_design(factor_names: Sequence[str], alpha: float | None = None, center_points: int = 5, seed: int = 144) -> pd.DataFrame:
    names = [str(name).strip() for name in factor_names if str(name).strip()]
    if len(names) < 2 or len(names) > 6:
        raise ValueError("Central composite design supports 2 to 6 factors.")
    k = len(names)
    alpha_value = float(alpha) if alpha is not None else float((2**k) ** 0.25)
    import itertools
    factorial = [dict(zip(names, values)) for values in itertools.product([-1.0, 1.0], repeat=k)]
    axial = []
    for name in names:
        plus = {factor: 0.0 for factor in names}
        minus = dict(plus)
        plus[name] = alpha_value
        minus[name] = -alpha_value
        axial.extend([plus, minus])
    centers = [{factor: 0.0 for factor in names} for _ in range(max(1, int(center_points)))]
    design = pd.DataFrame([*factorial, *axial, *centers])
    rng = np.random.default_rng(seed)
    design.insert(0, "run_order", rng.permutation(np.arange(1, len(design) + 1)))
    design = design.sort_values("run_order").reset_index(drop=True)
    design.insert(0, "run_id", [f"CCD-{idx + 1:05d}" for idx in range(len(design))])
    design["design_region"] = ["factorial"] * len(factorial) + ["axial"] * len(axial) + ["center"] * len(centers)
    # Region labels must follow the randomized rows.
    region_lookup = pd.Series(["factorial"] * len(factorial) + ["axial"] * len(axial) + ["center"] * len(centers))
    design["design_region"] = region_lookup.iloc[design["run_order"].to_numpy() - 1].to_numpy()
    return design


def fit_response_surface(design: pd.DataFrame, response_column: str, factor_columns: Sequence[str] | None = None) -> EngineOutput:
    data = _bounded_rows(design, limit=100_000)
    if response_column not in data.columns:
        raise ValueError(f"Response column {response_column!r} was not found.")
    factors = list(factor_columns or [column for column in data.select_dtypes(include="number").columns if column not in {response_column, "run_order"}])
    if not factors:
        raise ValueError("At least one numeric factor is required.")
    if len(factors) > 12:
        raise ValueError("Response-surface fitting supports at most 12 factors interactively.")
    clean = data[factors + [response_column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(clean) < len(factors) + 3:
        raise ValueError("Insufficient complete runs for model fitting.")
    columns = [np.ones(len(clean))]
    terms = ["Intercept"]
    for factor in factors:
        columns.append(clean[factor].to_numpy(float))
        terms.append(factor)
    for left_pos, left in enumerate(factors):
        for right in factors[left_pos + 1:]:
            columns.append((clean[left] * clean[right]).to_numpy(float))
            terms.append(f"{left}:{right}")
    for factor in factors:
        columns.append(np.square(clean[factor].to_numpy(float)))
        terms.append(f"{factor}^2")
    x = np.column_stack(columns)
    y = clean[response_column].to_numpy(float)
    if len(y) <= x.shape[1] + 1:
        # Drop interaction terms first to keep the model estimable.
        x = np.column_stack([np.ones(len(clean)), *[clean[factor].to_numpy(float) for factor in factors]])
        terms = ["Intercept", *factors]
    coefficients, _, rank, singular = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ coefficients
    residual = y - fitted
    sse = float(np.sum(residual**2))
    sst = float(np.sum((y - y.mean())**2))
    r2 = 1 - sse / sst if sst > 0 else 1.0
    n, p = x.shape
    adjusted = 1 - (1 - r2) * (n - 1) / max(1, n - p)
    mse = sse / max(1, n - p)
    aic = n * math.log(max(sse / n, 1e-15)) + 2 * p
    aicc = aic + (2 * p * (p + 1)) / max(1, n - p - 1)
    xtx = x.T @ x
    determinant = max(float(np.linalg.det(xtx)), 0.0) if xtx.shape[0] <= 40 else 0.0
    d_efficiency = (determinant ** (1 / max(1, p))) / n if determinant > 0 else 0.0
    coefficient_table = pd.DataFrame({"term": terms, "coefficient": coefficients})
    fitted_table = clean.copy()
    fitted_table["predicted_response"] = fitted
    fitted_table["residual"] = residual
    correlation = pd.DataFrame(x[:, 1:], columns=terms[1:]).corr().fillna(0)
    alias_rows = []
    for i, left in enumerate(correlation.columns):
        for right in correlation.columns[i + 1:]:
            value = float(correlation.loc[left, right])
            if abs(value) >= 0.6:
                alias_rows.append({"term_a": left, "term_b": right, "correlation": value, "severity": "High" if abs(value) >= 0.9 else "Moderate"})
    summary = {
        "runs": int(n),
        "parameters": int(p),
        "rank": int(rank),
        "r_squared": round(float(r2), 6),
        "adjusted_r_squared": round(float(adjusted), 6),
        "rmse": round(float(math.sqrt(max(0.0, mse))), 6),
        "aicc": round(float(aicc), 6),
        "condition_number": round(float(np.linalg.cond(x)), 4),
        "d_efficiency": round(float(d_efficiency), 8),
    }
    warnings = []
    if rank < p:
        warnings.append("The design matrix is rank deficient; some effects are aliased.")
    if summary["condition_number"] > 1_000:
        warnings.append("The model is ill-conditioned; scale factors or simplify the model.")
    return EngineOutput("doe_response_surface", coefficient_table, {"fitted": fitted_table, "alias": pd.DataFrame(alias_rows), "correlation": correlation.reset_index(names="term")}, summary, tuple(warnings))


# ---------------------------------------------------------------------------
# Biomarker validation planning
# ---------------------------------------------------------------------------


def _wilson_interval(successes: float, total: float, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (np.nan, np.nan)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def biomarker_validation_workbench(candidates: pd.DataFrame) -> EngineOutput:
    required = {
        "biomarker", "validation_n", "prevalence", "sensitivity", "specificity",
        "analytical_cv", "external_validation", "cutoff_locked",
    }
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError("Biomarker table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(candidates, limit=10_000)
    if data.empty:
        raise ValueError("At least one biomarker candidate is required.")
    data["biomarker"] = data["biomarker"].map(_normalise_text)
    if data["biomarker"].eq("").any() or data["biomarker"].duplicated().any():
        raise ValueError("Biomarker names must be non-empty and unique.")
    data["validation_n"] = _numeric(data["validation_n"], 0).round().astype(int).clip(lower=0)
    for column in ["prevalence", "sensitivity", "specificity"]:
        data[column] = _numeric(data[column], np.nan).clip(0, 1)
    data["analytical_cv"] = _numeric(data["analytical_cv"], np.nan).clip(lower=0)
    data["external_validation"] = data["external_validation"].astype(str).str.lower().isin({"1", "true", "yes", "y", "external"})
    data["cutoff_locked"] = data["cutoff_locked"].astype(str).str.lower().isin({"1", "true", "yes", "y", "locked"})
    if data[["prevalence", "sensitivity", "specificity"]].isna().any().any():
        raise ValueError("Prevalence, sensitivity and specificity must be numeric probabilities.")

    n = data["validation_n"].astype(float)
    diseased = n * data["prevalence"]
    nondiseased = n - diseased
    data["expected_tp"] = diseased * data["sensitivity"]
    data["expected_fn"] = diseased - data["expected_tp"]
    data["expected_tn"] = nondiseased * data["specificity"]
    data["expected_fp"] = nondiseased - data["expected_tn"]
    denom_ppv = data["expected_tp"] + data["expected_fp"]
    denom_npv = data["expected_tn"] + data["expected_fn"]
    data["ppv"] = np.divide(data["expected_tp"], denom_ppv, out=np.zeros(len(data)), where=denom_ppv.gt(0))
    data["npv"] = np.divide(data["expected_tn"], denom_npv, out=np.zeros(len(data)), where=denom_npv.gt(0))
    data["positive_lr"] = data["sensitivity"] / np.maximum(1e-9, 1 - data["specificity"])
    data["negative_lr"] = (1 - data["sensitivity"]) / np.maximum(1e-9, data["specificity"])
    data["youden_j"] = data["sensitivity"] + data["specificity"] - 1

    ci_rows = []
    for _, row in data.iterrows():
        sensitivity_ci = _wilson_interval(row["expected_tp"], max(row["expected_tp"] + row["expected_fn"], 1))
        specificity_ci = _wilson_interval(row["expected_tn"], max(row["expected_tn"] + row["expected_fp"], 1))
        ci_rows.append({
            "biomarker": row["biomarker"],
            "sensitivity_ci_low": sensitivity_ci[0], "sensitivity_ci_high": sensitivity_ci[1],
            "specificity_ci_low": specificity_ci[0], "specificity_ci_high": specificity_ci[1],
        })
    ci = pd.DataFrame(ci_rows)
    data = data.merge(ci, on="biomarker", how="left")
    data["maturity_score"] = (
        25 * data["external_validation"].astype(float)
        + 15 * data["cutoff_locked"].astype(float)
        + 25 * data["youden_j"].clip(0, 1)
        + 20 * (1 - np.minimum(1, data["analytical_cv"] / 0.2))
        + 15 * np.minimum(1, data["validation_n"] / 300)
    ).clip(0, 100)
    data["readiness"] = pd.cut(data["maturity_score"], [-1, 49.999, 74.999, 100.001], labels=["Discovery", "Verification", "Validation-ready"])

    # Planning curves: prevalence changes predictive values while sensitivity/specificity stay fixed.
    prevalence_rows = []
    for _, row in data.iterrows():
        for prevalence in np.linspace(0.01, 0.8, 40):
            ppv = row["sensitivity"] * prevalence / max(1e-12, row["sensitivity"] * prevalence + (1 - row["specificity"]) * (1 - prevalence))
            npv = row["specificity"] * (1 - prevalence) / max(1e-12, (1 - row["sensitivity"]) * prevalence + row["specificity"] * (1 - prevalence))
            prevalence_rows.append({"biomarker": row["biomarker"], "prevalence": prevalence, "metric": "PPV", "value": ppv})
            prevalence_rows.append({"biomarker": row["biomarker"], "prevalence": prevalence, "metric": "NPV", "value": npv})
    leakage = pd.DataFrame({
        "check": ["Participant-level split", "Site separation", "Cut-off locked before external validation", "Feature selection nested", "External cohort independent"],
        "status": ["Required", "Required", "Pass" if data["cutoff_locked"].all() else "Review", "Required", "Pass" if data["external_validation"].all() else "Review"],
    })
    summary = {
        "candidates": int(len(data)),
        "validation_ready": int(data["readiness"].astype(str).eq("Validation-ready").sum()),
        "externally_validated": int(data["external_validation"].sum()),
        "locked_cutoffs": int(data["cutoff_locked"].sum()),
        "top_candidate": str(data.sort_values("maturity_score", ascending=False).iloc[0]["biomarker"]),
    }
    warnings = []
    if not data["external_validation"].all():
        warnings.append("One or more candidates do not have independent external validation.")
    if (data["analytical_cv"] > 0.2).any():
        warnings.append("Analytical CV exceeds 20% for at least one candidate.")
    return EngineOutput("biomarker_validation_specialist", data.sort_values("maturity_score", ascending=False), {"predictive_values": pd.DataFrame(prevalence_rows), "leakage_checks": leakage}, summary, tuple(warnings))


# ---------------------------------------------------------------------------
# Advanced sample-size and assurance
# ---------------------------------------------------------------------------


def bayesian_assurance(
    effect_mean: float,
    effect_sd: float,
    sample_sizes: Sequence[int],
    alpha: float = 0.05,
    outcome_sd: float = 1.0,
    draws: int = 20_000,
    seed: int = 144,
) -> pd.DataFrame:
    if effect_sd < 0 or outcome_sd <= 0:
        raise ValueError("Effect SD must be non-negative and outcome SD positive.")
    if draws < 1_000 or draws > MAX_SIMULATIONS:
        raise ValueError(f"Draws must be between 1,000 and {MAX_SIMULATIONS:,}.")
    sizes = [int(value) for value in sample_sizes]
    if not sizes or min(sizes) < 4 or max(sizes) > 10_000_000:
        raise ValueError("Sample sizes must be between 4 and 10,000,000.")
    rng = np.random.default_rng(seed)
    effects = rng.normal(effect_mean, effect_sd, draws)
    critical = norm.ppf(1 - alpha / 2)
    rows = []
    for total_n in sizes:
        noncentral = effects * math.sqrt(total_n / 4) / outcome_sd
        power = 1 - norm.cdf(critical - noncentral) + norm.cdf(-critical - noncentral)
        rows.append({
            "total_sample_size": total_n,
            "assurance": float(np.mean(power)),
            "median_conditional_power": float(np.median(power)),
            "p10_conditional_power": float(np.quantile(power, 0.10)),
            "p90_conditional_power": float(np.quantile(power, 0.90)),
            "draws": draws,
            "seed": seed,
        })
    return pd.DataFrame(rows)


def cluster_design_effect(mean_cluster_size: float, icc: float, cluster_size_cv: float = 0.0) -> float:
    if mean_cluster_size <= 0 or not 0 <= icc < 1 or cluster_size_cv < 0:
        raise ValueError("Cluster size, ICC or coefficient of variation is outside the supported range.")
    return float(1 + (((cluster_size_cv**2 + 1) * mean_cluster_size) - 1) * icc)


def stepped_wedge_variance(
    clusters: int,
    periods: int,
    participants_per_cluster_period: int,
    icc: float,
) -> dict[str, float]:
    if clusters < 4 or periods < 3 or participants_per_cluster_period < 1:
        raise ValueError("Stepped-wedge planning requires at least 4 clusters, 3 periods and one participant per cluster-period.")
    if clusters > 500 or periods > 50 or not 0 <= icc < 1:
        raise ValueError("Stepped-wedge dimensions or ICC are outside the supported range.")
    # Cluster-period mean covariance under a cross-sectional exchangeable correlation model.
    variance_mean = icc + (1 - icc) / participants_per_cluster_period
    covariance = icc
    block = np.full((periods, periods), covariance, dtype=float)
    np.fill_diagonal(block, variance_mean)
    inv_block = np.linalg.pinv(block)
    rows = []
    for cluster in range(clusters):
        sequence = cluster % (periods - 1) + 1
        for period in range(periods):
            treated = 1.0 if period >= sequence else 0.0
            row = [1.0, *[1.0 if period == p else 0.0 for p in range(1, periods)], treated]
            rows.append(row)
    x = np.asarray(rows, dtype=float)
    p = x.shape[1]
    information = np.zeros((p, p), dtype=float)
    for cluster in range(clusters):
        block_x = x[cluster * periods:(cluster + 1) * periods]
        information += block_x.T @ inv_block @ block_x
    covariance_beta = np.linalg.pinv(information)
    treatment_variance = float(covariance_beta[-1, -1])
    treatment_se = math.sqrt(max(0.0, treatment_variance))
    return {
        "treatment_variance_standardized": treatment_variance,
        "treatment_standard_error_standardized": treatment_se,
        "clusters": clusters,
        "periods": periods,
        "participants_per_cluster_period": participants_per_cluster_period,
        "total_participants": clusters * periods * participants_per_cluster_period,
    }


# ---------------------------------------------------------------------------
# Recruitment feasibility
# ---------------------------------------------------------------------------


def simulate_recruitment(
    sites: pd.DataFrame,
    target: int,
    months: int = 24,
    simulations: int = 5_000,
    seed: int = 144,
) -> EngineOutput:
    required = {"site", "activation_mean", "activation_sd", "monthly_rate", "rate_cv", "screen_success", "retention", "capacity"}
    missing = required - set(sites.columns)
    if missing:
        raise ValueError("Site table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(sites, limit=2_000)
    if data.empty or target < 1 or months < 1 or months > 240:
        raise ValueError("Recruitment inputs are outside the supported range.")
    if simulations < 500 or simulations > 20_000:
        raise ValueError("Recruitment simulations must be between 500 and 20,000.")
    data["site"] = data["site"].map(_normalise_text)
    if data["site"].eq("").any() or data["site"].duplicated().any():
        raise ValueError("Site names must be non-empty and unique.")
    for column in ["activation_mean", "activation_sd", "monthly_rate", "rate_cv", "screen_success", "retention", "capacity"]:
        data[column] = _numeric(data[column], 0)
    if (data[["activation_mean", "activation_sd", "monthly_rate", "rate_cv", "capacity"]] < 0).any().any():
        raise ValueError("Activation, rate and capacity inputs cannot be negative.")
    if not data["screen_success"].between(0, 1).all() or not data["retention"].between(0, 1).all():
        raise ValueError("Screen success and retention must be probabilities.")

    rng = np.random.default_rng(seed)
    month_grid = np.arange(1, months + 1)
    cumulative = np.zeros((simulations, months), dtype=float)
    site_totals = np.zeros((simulations, len(data)), dtype=float)
    for site_pos, row in data.reset_index(drop=True).iterrows():
        activation = np.maximum(0, rng.normal(row["activation_mean"], row["activation_sd"], simulations))
        cv = max(0.0001, row["rate_cv"])
        shape = 1 / (cv**2)
        scale = max(1e-12, row["monthly_rate"] / shape)
        rates = rng.gamma(shape, scale, simulations)
        screened_success = row["screen_success"] * row["retention"]
        site_cumulative = np.zeros((simulations, months), dtype=float)
        for month_pos, month in enumerate(month_grid):
            active_fraction = np.clip(month - activation, 0, 1)
            recruits = rates * active_fraction * screened_success
            site_cumulative[:, month_pos] = recruits if month_pos == 0 else site_cumulative[:, month_pos - 1] + recruits
        site_cumulative = np.minimum(site_cumulative, row["capacity"])
        cumulative += site_cumulative
        site_totals[:, site_pos] = site_cumulative[:, -1]
    cumulative = np.minimum(cumulative, target * 2.0)
    forecast = pd.DataFrame({
        "month": month_grid,
        "p10": np.quantile(cumulative, 0.10, axis=0),
        "median": np.quantile(cumulative, 0.50, axis=0),
        "p90": np.quantile(cumulative, 0.90, axis=0),
        "completion_probability": np.mean(cumulative >= target, axis=0),
    })
    site_summary = data[["site"]].copy()
    site_summary["p10_total"] = np.quantile(site_totals, 0.10, axis=0)
    site_summary["median_total"] = np.quantile(site_totals, 0.50, axis=0)
    site_summary["p90_total"] = np.quantile(site_totals, 0.90, axis=0)
    site_summary["probability_below_half_capacity"] = np.mean(site_totals < (data["capacity"].to_numpy(float) / 2), axis=0)
    completed = cumulative >= target
    completion_month = np.where(completed.any(axis=1), completed.argmax(axis=1) + 1, months + 1)
    summary = {
        "sites": int(len(data)),
        "target": int(target),
        "completion_probability_by_horizon": round(float(np.mean(cumulative[:, -1] >= target)), 5),
        "median_completion_month": int(np.median(completion_month)),
        "median_enrolled_by_horizon": round(float(np.median(cumulative[:, -1])), 1),
        "simulations": simulations,
        "seed": seed,
    }
    rescue = site_summary.loc[site_summary["probability_below_half_capacity"].ge(0.5)].copy()
    rescue["recommended_action"] = "Activate backup site or revise referral strategy"
    warnings = []
    if summary["completion_probability_by_horizon"] < 0.8:
        warnings.append("Probability of meeting the target by the selected horizon is below 80%.")
    return EngineOutput("recruitment_monte_carlo", forecast, {"site_summary": site_summary, "rescue_triggers": rescue}, summary, tuple(warnings))


def bayesian_recruitment_update(observed: pd.DataFrame, prior_shape: float = 2.0, prior_rate: float = 1.0) -> pd.DataFrame:
    required = {"site", "observed_months", "observed_recruits"}
    missing = required - set(observed.columns)
    if missing:
        raise ValueError("Observed recruitment table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(observed, limit=5_000)
    months = _numeric(data["observed_months"], 0)
    recruits = _numeric(data["observed_recruits"], 0)
    if (months <= 0).any() or (recruits < 0).any() or prior_shape <= 0 or prior_rate <= 0:
        raise ValueError("Observed months and prior parameters must be positive; recruits cannot be negative.")
    posterior_shape = prior_shape + recruits
    posterior_rate = prior_rate + months
    result = data.copy()
    result["posterior_mean_monthly_rate"] = posterior_shape / posterior_rate
    # Gamma quantiles use a Wilson-Hilferty approximation for portable bounded output.
    shape = posterior_shape.to_numpy(float)
    rate = posterior_rate.to_numpy(float)
    z_low, z_high = norm.ppf([0.025, 0.975])
    result["posterior_rate_ci_low"] = np.maximum(0, shape / rate * np.power(np.maximum(1e-9, 1 - 1/(9*shape) + z_low/(3*np.sqrt(shape))), 3))
    result["posterior_rate_ci_high"] = np.maximum(0, shape / rate * np.power(np.maximum(1e-9, 1 - 1/(9*shape) + z_high/(3*np.sqrt(shape))), 3))
    return result


# ---------------------------------------------------------------------------
# Biospecimen lifecycle
# ---------------------------------------------------------------------------


def build_biospecimen_inventory(plan: pd.DataFrame, max_participants: int = 50_000) -> EngineOutput:
    required = {"sample_type", "visit", "participants", "volume_ml", "aliquots", "storage_temp", "assay_volume_ml", "reserve_fraction"}
    missing = required - set(plan.columns)
    if missing:
        raise ValueError("Biospecimen plan is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(plan, limit=10_000)
    if data.empty:
        raise ValueError("At least one biospecimen plan row is required.")
    for column in ["sample_type", "visit", "storage_temp"]:
        data[column] = data[column].map(_normalise_text)
    data["participants"] = _numeric(data["participants"], 0).round().astype(int)
    data["volume_ml"] = _numeric(data["volume_ml"], 0)
    data["aliquots"] = _numeric(data["aliquots"], 1).round().astype(int)
    data["assay_volume_ml"] = _numeric(data["assay_volume_ml"], 0)
    data["reserve_fraction"] = _numeric(data["reserve_fraction"], 0).clip(0, 1)
    if (data[["participants", "volume_ml", "aliquots"]] <= 0).any().any():
        raise ValueError("Participants, collection volume and aliquot counts must be positive.")
    total_participants = int(data["participants"].max())
    if total_participants > max_participants:
        raise ValueError(f"Inventory generation supports at most {max_participants:,} participant identifiers.")
    estimated_specimens = int((data["participants"] * data["aliquots"]).sum())
    if estimated_specimens > MAX_SPECIMENS:
        raise ValueError(f"Inventory would contain {estimated_specimens:,} aliquots; limit is {MAX_SPECIMENS:,}.")

    lineage_rows = []
    for row_pos, row in data.reset_index(drop=True).iterrows():
        per_aliquot = row["volume_ml"] / row["aliquots"]
        for participant in range(1, row["participants"] + 1):
            parent_key = f"P{participant:06d}|{row['visit']}|{row['sample_type']}|{row_pos}"
            parent_id = "SPC-" + sha256(parent_key.encode()).hexdigest()[:14].upper()
            for aliquot in range(1, row["aliquots"] + 1):
                aliquot_key = f"{parent_id}|{aliquot}"
                aliquot_id = "ALQ-" + sha256(aliquot_key.encode()).hexdigest()[:14].upper()
                required_assay = row["assay_volume_ml"]
                reserve = per_aliquot * row["reserve_fraction"]
                remaining = per_aliquot - required_assay - reserve
                lineage_rows.append({
                    "participant_id": f"P{participant:06d}",
                    "parent_specimen_id": parent_id,
                    "aliquot_id": aliquot_id,
                    "sample_type": row["sample_type"],
                    "visit": row["visit"],
                    "storage_temp": row["storage_temp"],
                    "initial_volume_ml": per_aliquot,
                    "planned_assay_volume_ml": required_assay,
                    "reserved_volume_ml": reserve,
                    "remaining_volume_ml": remaining,
                    "volume_status": "Insufficient" if remaining < 0 else ("Low" if remaining < 0.1 * per_aliquot else "Adequate"),
                })
    inventory = pd.DataFrame(lineage_rows)
    storage = inventory.groupby(["storage_temp", "sample_type"], as_index=False).agg(
        aliquots=("aliquot_id", "count"),
        total_volume_ml=("initial_volume_ml", "sum"),
        insufficient=("volume_status", lambda s: int((s == "Insufficient").sum())),
    )
    custody = pd.DataFrame([
        {"event_order": 1, "event": "Collected", "custodian": "Collection site", "status": "Planned"},
        {"event_order": 2, "event": "Processed", "custodian": "Processing laboratory", "status": "Planned"},
        {"event_order": 3, "event": "Aliquoted", "custodian": "Biobank", "status": "Planned"},
        {"event_order": 4, "event": "Stored", "custodian": "Biobank", "status": "Planned"},
        {"event_order": 5, "event": "Released for assay", "custodian": "Analytical laboratory", "status": "Controlled"},
    ])
    summary = {
        "participants": total_participants,
        "parent_specimens": int(inventory["parent_specimen_id"].nunique()),
        "aliquots": int(len(inventory)),
        "insufficient_aliquots": int(inventory["volume_status"].eq("Insufficient").sum()),
        "total_volume_l": round(float(inventory["initial_volume_ml"].sum() / 1000), 4),
    }
    warnings = []
    if summary["insufficient_aliquots"]:
        warnings.append("Some aliquots do not have enough volume for the planned assay plus reserve.")
    return EngineOutput("biospecimen_lifecycle", inventory, {"storage": storage, "custody": custody}, summary, tuple(warnings))


def detect_temperature_excursions(logger: pd.DataFrame, lower_c: float, upper_c: float, minimum_minutes: float = 0.0) -> pd.DataFrame:
    required = {"timestamp", "container_id", "temperature_c"}
    missing = required - set(logger.columns)
    if missing:
        raise ValueError("Temperature log is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(logger, limit=1_000_000)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise", utc=True)
    data["temperature_c"] = _numeric(data["temperature_c"], np.nan)
    data = data.sort_values(["container_id", "timestamp"]).reset_index(drop=True)
    data["outside_range"] = ~data["temperature_c"].between(lower_c, upper_c)
    events = []
    for container, group in data.groupby("container_id"):
        group = group.reset_index(drop=True)
        run_id = (group["outside_range"] != group["outside_range"].shift()).cumsum()
        for _, run in group.loc[group["outside_range"]].groupby(run_id[group["outside_range"]]):
            duration = max(0.0, (run["timestamp"].iloc[-1] - run["timestamp"].iloc[0]).total_seconds() / 60)
            if duration >= minimum_minutes:
                events.append({
                    "container_id": container,
                    "start": run["timestamp"].iloc[0],
                    "end": run["timestamp"].iloc[-1],
                    "duration_minutes": duration,
                    "minimum_temperature_c": float(run["temperature_c"].min()),
                    "maximum_temperature_c": float(run["temperature_c"].max()),
                    "severity": "Critical" if (run["temperature_c"] < lower_c - 5).any() or (run["temperature_c"] > upper_c + 5).any() else "Review",
                })
    return pd.DataFrame(events)


# ---------------------------------------------------------------------------
# Timeline / schedule risk
# ---------------------------------------------------------------------------


def _parse_predecessors(value: Any) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", str(value or "")) if item.strip()]


def _topological_order(tasks: Sequence[str], predecessors: Mapping[str, Sequence[str]]) -> list[str]:
    task_set = set(tasks)
    missing = sorted({pred for values in predecessors.values() for pred in values if pred not in task_set})
    if missing:
        raise ValueError("Unknown predecessor tasks: " + ", ".join(missing))
    indegree = {task: 0 for task in tasks}
    children = {task: [] for task in tasks}
    for task in tasks:
        for pred in predecessors[task]:
            indegree[task] += 1
            children[pred].append(task)
    queue = [task for task in tasks if indegree[task] == 0]
    order = []
    while queue:
        task = queue.pop(0)
        order.append(task)
        for child in children[task]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(tasks):
        raise ValueError("Task dependencies contain a cycle.")
    return order


def pert_schedule_simulation(tasks: pd.DataFrame, simulations: int = 5_000, seed: int = 144) -> EngineOutput:
    required = {"task", "predecessor", "optimistic_days", "most_likely_days", "pessimistic_days", "owner"}
    missing = required - set(tasks.columns)
    if missing:
        raise ValueError("Timeline table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(tasks, limit=MAX_TASKS)
    if data.empty:
        raise ValueError("At least one task is required.")
    if simulations < 500 or simulations > 20_000:
        raise ValueError("Schedule simulations must be between 500 and 20,000.")
    data["task"] = data["task"].map(_normalise_text)
    if data["task"].eq("").any() or data["task"].duplicated().any():
        raise ValueError("Task names must be non-empty and unique.")
    for column in ["optimistic_days", "most_likely_days", "pessimistic_days"]:
        data[column] = _numeric(data[column], np.nan)
    if data[["optimistic_days", "most_likely_days", "pessimistic_days"]].isna().any().any():
        raise ValueError("All PERT durations must be numeric.")
    if (data["optimistic_days"] <= 0).any() or (data["most_likely_days"] < data["optimistic_days"]).any() or (data["pessimistic_days"] < data["most_likely_days"]).any():
        raise ValueError("Require 0 < optimistic <= most likely <= pessimistic for every task.")
    predecessors = {task: _parse_predecessors(pred) for task, pred in zip(data["task"], data["predecessor"])}
    order = _topological_order(data["task"].tolist(), predecessors)
    index = {task: pos for pos, task in enumerate(data["task"])}
    o = data["optimistic_days"].to_numpy(float)
    m = data["most_likely_days"].to_numpy(float)
    p = data["pessimistic_days"].to_numpy(float)
    expected = (o + 4 * m + p) / 6

    def forward(durations: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        start = np.zeros(len(data), dtype=float)
        finish = np.zeros(len(data), dtype=float)
        for task in order:
            pos = index[task]
            start[pos] = max([finish[index[pred]] for pred in predecessors[task]], default=0.0)
            finish[pos] = start[pos] + durations[pos]
        return start, finish, float(finish.max())

    base_start, base_finish, base_duration = forward(expected)
    # Backward pass for deterministic slack.
    children = {task: [] for task in order}
    for task, preds in predecessors.items():
        for pred in preds:
            children[pred].append(task)
    latest_finish = np.full(len(data), base_duration)
    latest_start = np.zeros(len(data))
    for task in reversed(order):
        pos = index[task]
        if children[task]:
            latest_finish[pos] = min(latest_start[index[child]] for child in children[task])
        latest_start[pos] = latest_finish[pos] - expected[pos]
    slack = latest_start - base_start

    rng = np.random.default_rng(seed)
    duration_samples = np.empty((simulations, len(data)), dtype=float)
    for pos in range(len(data)):
        if p[pos] == o[pos]:
            duration_samples[:, pos] = o[pos]
        else:
            alpha = 1 + 4 * (m[pos] - o[pos]) / (p[pos] - o[pos])
            beta_param = 1 + 4 * (p[pos] - m[pos]) / (p[pos] - o[pos])
            duration_samples[:, pos] = o[pos] + (p[pos] - o[pos]) * rng.beta(alpha, beta_param, simulations)
    project_durations = np.zeros(simulations)
    critical_counts = np.zeros(len(data), dtype=int)
    finish_samples = np.zeros((simulations, len(data)), dtype=float)
    for sim in range(simulations):
        start, finish, total = forward(duration_samples[sim])
        finish_samples[sim] = finish
        project_durations[sim] = total
        # Tasks ending on the project-max path (within numerical tolerance) are counted as critical.
        # Use sampled backward pass for a more useful criticality index.
        latest_finish_sim = np.full(len(data), total)
        latest_start_sim = np.zeros(len(data))
        for task in reversed(order):
            pos = index[task]
            if children[task]:
                latest_finish_sim[pos] = min(latest_start_sim[index[child]] for child in children[task])
            latest_start_sim[pos] = latest_finish_sim[pos] - duration_samples[sim, pos]
        critical_counts += np.isclose(latest_start_sim, start, atol=1e-7)

    schedule = data.copy()
    schedule["pert_expected_days"] = expected
    schedule["baseline_start_day"] = base_start
    schedule["baseline_finish_day"] = base_finish
    schedule["slack_days"] = slack
    schedule["critical_baseline"] = np.isclose(slack, 0, atol=1e-7)
    schedule["criticality_index"] = critical_counts / simulations
    schedule["finish_p50"] = np.quantile(finish_samples, 0.50, axis=0)
    schedule["finish_p90"] = np.quantile(finish_samples, 0.90, axis=0)
    distribution = pd.DataFrame({"project_duration_days": project_durations})
    resource = schedule.groupby("owner", as_index=False).agg(
        tasks=("task", "count"),
        expected_work_days=("pert_expected_days", "sum"),
        critical_tasks=("critical_baseline", "sum"),
    )
    summary = {
        "tasks": int(len(schedule)),
        "baseline_duration_days": round(base_duration, 2),
        "p50_duration_days": round(float(np.quantile(project_durations, 0.50)), 2),
        "p90_duration_days": round(float(np.quantile(project_durations, 0.90)), 2),
        "critical_tasks": int(schedule["critical_baseline"].sum()),
        "simulations": simulations,
        "seed": seed,
    }
    warnings = []
    if summary["p90_duration_days"] > 1.25 * summary["baseline_duration_days"]:
        warnings.append("P90 schedule duration is more than 25% above the deterministic baseline.")
    return EngineOutput("timeline_pert_monte_carlo", schedule, {"duration_distribution": distribution, "resource_load": resource}, summary, tuple(warnings))


# ---------------------------------------------------------------------------
# Risk / FMEA / KRI
# ---------------------------------------------------------------------------


def fmea_risk_workbench(risks: pd.DataFrame, simulations: int = 10_000, seed: int = 144) -> EngineOutput:
    required = {"risk", "category", "probability", "impact", "detectability", "control_effectiveness", "financial_impact", "time_impact_days", "owner"}
    missing = required - set(risks.columns)
    if missing:
        raise ValueError("Risk table is missing: " + ", ".join(sorted(missing)))
    data = _bounded_rows(risks, limit=20_000)
    if data.empty:
        raise ValueError("At least one risk is required.")
    if simulations < 1_000 or simulations > MAX_SIMULATIONS:
        raise ValueError(f"Risk simulations must be between 1,000 and {MAX_SIMULATIONS:,}.")
    data["risk"] = data["risk"].map(_normalise_text)
    if data["risk"].eq("").any() or data["risk"].duplicated().any():
        raise ValueError("Risk names must be non-empty and unique.")
    for column in ["category", "owner"]:
        data[column] = data[column].map(_normalise_text)
    for column in ["probability", "impact", "detectability"]:
        data[column] = _numeric(data[column], np.nan)
        if not data[column].between(1, 5).all():
            raise ValueError(f"{column} must be scored from 1 to 5.")
    data["control_effectiveness"] = _numeric(data["control_effectiveness"], 0).clip(0, 1)
    data["financial_impact"] = _numeric(data["financial_impact"], 0).clip(lower=0)
    data["time_impact_days"] = _numeric(data["time_impact_days"], 0).clip(lower=0)
    data["rpn"] = data["probability"] * data["impact"] * data["detectability"]
    data["residual_rpn"] = data["rpn"] * (1 - data["control_effectiveness"])
    data["risk_band"] = pd.cut(data["residual_rpn"], [-1, 20, 50, 125.001], labels=["Low", "Moderate", "High"])
    data["kri_status"] = np.select(
        [data["residual_rpn"].ge(50), data["residual_rpn"].ge(20)],
        ["Red", "Amber"],
        default="Green",
    )

    rng = np.random.default_rng(seed)
    occurrence_probability = np.clip(data["probability"].to_numpy(float) / 5, 0, 1)
    occurrences = rng.random((simulations, len(data))) < occurrence_probability[None, :]
    control_failure = rng.random((simulations, len(data))) > data["control_effectiveness"].to_numpy(float)[None, :]
    active = occurrences & control_failure
    severity_noise = rng.triangular(0.75, 1.0, 1.5, size=(simulations, len(data)))
    financial = np.sum(active * data["financial_impact"].to_numpy(float)[None, :] * severity_noise, axis=1)
    delay = np.sum(active * data["time_impact_days"].to_numpy(float)[None, :] * severity_noise, axis=1)
    exposure = pd.DataFrame({"financial_exposure": financial, "schedule_delay_days": delay})
    category = data.groupby("category", as_index=False).agg(
        risks=("risk", "count"),
        gross_rpn=("rpn", "sum"),
        residual_rpn=("residual_rpn", "sum"),
        red_kri=("kri_status", lambda s: int((s == "Red").sum())),
    )
    bow_tie_rows = [
        {"source": f"Threat: {row['risk']}", "target": f"Control: {row['owner'] or 'Unassigned'}", "relationship": "mitigated by", "weight": float(row["rpn"])}
        for _, row in data.iterrows()
    ]
    bow_tie_rows.extend([
        {"source": f"Control: {row['owner'] or 'Unassigned'}", "target": f"Consequence: {row['category']}", "relationship": "reduces", "weight": float(row["residual_rpn"])}
        for _, row in data.iterrows()
    ])
    bow_tie = pd.DataFrame(bow_tie_rows)
    summary = {
        "risks": int(len(data)),
        "high_residual_risks": int(data["risk_band"].astype(str).eq("High").sum()),
        "gross_rpn": round(float(data["rpn"].sum()), 2),
        "residual_rpn": round(float(data["residual_rpn"].sum()), 2),
        "financial_exposure_p50": round(float(np.quantile(financial, 0.50)), 2),
        "financial_exposure_p90": round(float(np.quantile(financial, 0.90)), 2),
        "schedule_delay_p90_days": round(float(np.quantile(delay, 0.90)), 2),
        "simulations": simulations,
        "seed": seed,
    }
    warnings = []
    if summary["high_residual_risks"]:
        warnings.append("One or more risks remain high after planned controls.")
    if data["owner"].eq("").any():
        warnings.append("Every risk should have a named owner.")
    return EngineOutput("risk_fmea_monte_carlo", data.sort_values("residual_rpn", ascending=False), {"category": category, "exposure": exposure, "bow_tie": bow_tie}, summary, tuple(warnings))


SPECIALIST_ENGINE_CATALOG: dict[str, dict[str, Any]] = {
    "sample_size_power_studio": {"engine": "Assurance, group-sequential and cluster/stepped-wedge planning", "version": "1.0.0"},
    "clinical_trial_design_studio": {"engine": "Operating-characteristic simulation and dose escalation", "version": "1.0.0"},
    "experimental_design_doe": {"engine": "Factorial/CCD generation and response-surface fitting", "version": "1.0.0"},
    "biomarker_study_planning": {"engine": "Diagnostic performance and validation-readiness planning", "version": "1.0.0"},
    "sampling_biospecimen_planning": {"engine": "Barcode lineage, volume and excursion lifecycle", "version": "1.0.0"},
    "research_feasibility_recruitment": {"engine": "Monte Carlo recruitment and Bayesian site updating", "version": "1.0.0"},
    "research_timeline_dependencies": {"engine": "PERT/CPM Monte Carlo schedule risk", "version": "1.0.0"},
    "research_risk_mitigation": {"engine": "FMEA, KRI, bow-tie and aggregate exposure", "version": "1.0.0"},
    "evidence_gap_literature_planning": {"engine": "Deduplication, PRISMA, contradiction and meta-analysis", "version": "1.0.0"},
    "preregistration_reproducibility": {"engine": "Outcome-switching, artifact integrity and environment lock", "version": "1.0.0"},
}


def specialist_engine_contract(module_key: str) -> dict[str, Any]:
    record = SPECIALIST_ENGINE_CATALOG.get(module_key)
    if record is None:
        return {"module_key": module_key, "specialist_engine": False, "status": "Shared planning workspace"}
    payload = {"module_key": module_key, "specialist_engine": True, **record, "execution": "local_bounded_deterministic"}
    payload["contract_sha256"] = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload
