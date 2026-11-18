from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import ceil, isfinite, log, sqrt
from secrets import randbits
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StudyDesignResult:
    design: str
    total_sample_size: int
    group_sizes: dict[str, int]
    complete_case_total: int
    alpha: float
    target_power: float
    dropout_fraction: float
    method: str
    assumptions: dict[str, Any]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_probability(value: float, name: str) -> float:
    value = float(value)
    if not isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{name} must be strictly between 0 and 1.")
    return value


def _validate_positive(value: float, name: str) -> float:
    value = float(value)
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite value.")
    return value


def _adjust_dropout(n: int, dropout_fraction: float) -> int:
    if int(n) < 0:
        raise ValueError("Sample size cannot be negative.")
    if not 0 <= dropout_fraction < 0.8:
        raise ValueError("Dropout fraction must be between 0 and 0.8.")
    return int(ceil(n / (1.0 - dropout_fraction)))


def _z_alpha(alpha: float, two_sided: bool = True) -> float:
    alpha = _validate_probability(alpha, "Alpha")
    return NormalDist().inv_cdf(1 - alpha / (2 if two_sided else 1))


def _z_power(power: float) -> float:
    return NormalDist().inv_cdf(_validate_probability(power, "Power"))


def _split_total(total: int, allocation_ratio: float) -> tuple[int, int]:
    total = int(total)
    if total < 2:
        raise ValueError("At least two observations are required for a two-group design.")
    allocation_ratio = _validate_positive(allocation_ratio, "Allocation ratio")
    # Preserve the requested total exactly. The previous ceil/ceil implementation
    # could silently create one or more extra observations and made simulation
    # results disagree with the sample size shown in the UI.
    n1 = int(round(total / (1 + allocation_ratio)))
    n1 = min(max(n1, 1), total - 1)
    n2 = total - n1
    return n1, n2


def _anova_power(total: int, groups: int, effect_size: float, alpha: float) -> float:
    from scipy.stats import f as f_distribution
    from scipy.stats import ncf

    df1, df2 = groups - 1, total - groups
    if df2 <= 0:
        return 0.0
    critical = f_distribution.ppf(1 - alpha, df1, df2)
    achieved = 1 - ncf.cdf(critical, df1, df2, total * effect_size**2)
    return float(achieved) if isfinite(float(achieved)) else 0.0


def calculate_design(
    design: str,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout_fraction: float = 0.0,
    two_sided: bool = True,
    allocation_ratio: float = 1.0,
    effect_size: float | None = None,
    proportion_1: float | None = None,
    proportion_2: float | None = None,
    groups: int = 2,
    correlation: float | None = None,
    hazard_ratio: float | None = None,
    event_fraction: float = 0.7,
    margin: float | None = None,
    standard_deviation: float = 1.0,
    half_width: float | None = None,
    cluster_size: int = 1,
    intraclass_correlation: float = 0.0,
    repeated_measure_correlation: float = 0.5,
    measurements: int = 2,
    multiplicity: int = 1,
    multiplicity_method: str = "none",
) -> StudyDesignResult:
    """Calculate transparent planning-level sample sizes for common study designs.

    The implementation deliberately exposes assumptions and warnings. It is intended
    for research planning and must not replace a statistician's confirmatory design.
    """
    design_key = str(design).strip().lower()
    alpha = _validate_probability(alpha, "Alpha")
    power = _validate_probability(power, "Power")
    allocation_ratio = _validate_positive(allocation_ratio, "Allocation ratio")
    dropout_fraction = float(dropout_fraction)
    if not isfinite(dropout_fraction):
        raise ValueError("Dropout fraction must be finite.")
    if multiplicity < 1:
        raise ValueError("Multiplicity must be at least one.")
    multiplicity_key = str(multiplicity_method).strip().lower()
    if multiplicity_key not in {"none", "bonferroni", "sidak"}:
        raise ValueError("Multiplicity method must be none, Bonferroni, or Sidak.")
    if multiplicity_key == "bonferroni" and multiplicity > 1:
        adjusted_alpha = alpha / multiplicity
    elif multiplicity_key == "sidak" and multiplicity > 1:
        adjusted_alpha = 1 - (1 - alpha) ** (1 / multiplicity)
    else:
        adjusted_alpha = alpha
    za = _z_alpha(adjusted_alpha, two_sided)
    zp = _z_power(power)
    warnings: list[str] = []
    assumptions: dict[str, Any] = {
        "requested_alpha": alpha,
        "adjusted_alpha": adjusted_alpha,
        "two_sided": bool(two_sided),
        "allocation_ratio": float(allocation_ratio),
        "multiplicity": int(multiplicity),
        "multiplicity_method": multiplicity_key,
    }

    if design_key in {"two_group_continuous", "independent_means", "two_group"}:
        if not effect_size or effect_size <= 0:
            raise ValueError("A positive standardized effect size is required.")
        n1_complete = ceil(((1 + 1 / allocation_ratio) * (za + zp) ** 2) / effect_size**2)
        n2_complete = ceil(n1_complete * allocation_ratio)
        n1, n2 = _adjust_dropout(n1_complete, dropout_fraction), _adjust_dropout(n2_complete, dropout_fraction)
        assumptions.update(effect_size=effect_size)
        return StudyDesignResult("Two independent means", n1 + n2, {"Group 1": n1, "Group 2": n2}, n1_complete + n2_complete, alpha, power, dropout_fraction, "Normal approximation for standardized mean difference", assumptions, tuple(warnings))

    if design_key in {"paired_continuous", "paired"}:
        if not effect_size or effect_size <= 0:
            raise ValueError("A positive paired standardized effect size is required.")
        complete = ceil(((za + zp) / effect_size) ** 2)
        adjusted = _adjust_dropout(complete, dropout_fraction)
        assumptions.update(effect_size=effect_size)
        return StudyDesignResult("Paired continuous outcome", adjusted, {"Pairs": adjusted}, complete, alpha, power, dropout_fraction, "Normal approximation for paired standardized mean difference", assumptions, tuple(warnings))

    if design_key in {"two_proportions", "proportions"}:
        if proportion_1 is None or proportion_2 is None:
            raise ValueError("Both expected proportions are required.")
        p1, p2 = float(proportion_1), float(proportion_2)
        if not (0 < p1 < 1 and 0 < p2 < 1) or p1 == p2:
            raise ValueError("Expected proportions must be different and between zero and one.")
        pooled = (p1 + p2) / 2
        numerator = (za * sqrt(2 * pooled * (1 - pooled)) + zp * sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
        n1_complete = ceil(numerator / (p1 - p2) ** 2)
        n2_complete = ceil(n1_complete * allocation_ratio)
        n1, n2 = _adjust_dropout(n1_complete, dropout_fraction), _adjust_dropout(n2_complete, dropout_fraction)
        assumptions.update(proportion_1=p1, proportion_2=p2, absolute_difference=abs(p1 - p2))
        return StudyDesignResult("Two independent proportions", n1 + n2, {"Group 1": n1, "Group 2": n2}, n1_complete + n2_complete, alpha, power, dropout_fraction, "Normal approximation for two independent proportions", assumptions, tuple(warnings))

    if design_key in {"one_way_anova", "anova"}:
        if not effect_size or effect_size <= 0 or groups < 2:
            raise ValueError("A positive Cohen f effect size and at least two groups are required.")
        try:
            import scipy.stats  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("SciPy is required for ANOVA power calculations.") from exc
        # Non-central F calculations are expensive. Find an upper bound by
        # doubling, then use binary search instead of scanning up to 200,000
        # candidate sample sizes on every Streamlit rerun.
        lower = groups * 2
        upper = lower
        while upper < 200_000 and _anova_power(upper, groups, float(effect_size), adjusted_alpha) < power:
            upper = min(200_000, upper * 2)
        if _anova_power(upper, groups, float(effect_size), adjusted_alpha) < power:
            raise ValueError("Requested ANOVA power exceeds the search range.")
        while lower < upper:
            midpoint = (lower + upper) // 2
            if _anova_power(midpoint, groups, float(effect_size), adjusted_alpha) >= power:
                upper = midpoint
            else:
                lower = midpoint + 1
        complete = lower
        adjusted = _adjust_dropout(complete, dropout_fraction)
        per_group = ceil(adjusted / groups)
        assumptions.update(effect_size_f=effect_size, groups=groups)
        return StudyDesignResult("One-way ANOVA", per_group * groups, {f"Group {index + 1}": per_group for index in range(groups)}, complete, alpha, power, dropout_fraction, "Noncentral-F one-way ANOVA approximation", assumptions, tuple(warnings))

    if design_key in {"correlation", "pearson_correlation"}:
        if correlation is None or not 0 < abs(correlation) < 1:
            raise ValueError("Expected absolute correlation must be between zero and one.")
        fisher = abs(0.5 * log((1 + correlation) / (1 - correlation)))
        complete = ceil(3 + ((za + zp) / fisher) ** 2)
        adjusted = _adjust_dropout(complete, dropout_fraction)
        assumptions.update(correlation=correlation)
        return StudyDesignResult("Correlation", adjusted, {"Participants": adjusted}, complete, alpha, power, dropout_fraction, "Fisher z transformation for a non-zero correlation", assumptions, tuple(warnings))

    if design_key in {"survival", "logrank"}:
        if hazard_ratio is None or hazard_ratio <= 0 or hazard_ratio == 1:
            raise ValueError("Hazard ratio must be positive and different from one.")
        event_fraction = _validate_probability(event_fraction, "Event fraction")
        ratio_term = ((1 + allocation_ratio) ** 2) / allocation_ratio
        required_events = ceil(ratio_term * (za + zp) ** 2 / (log(hazard_ratio) ** 2))
        complete = ceil(required_events / event_fraction)
        adjusted = _adjust_dropout(complete, dropout_fraction)
        n1, n2 = _split_total(adjusted, allocation_ratio)
        assumptions.update(hazard_ratio=hazard_ratio, event_fraction=event_fraction, required_events=required_events)
        return StudyDesignResult("Time-to-event / log-rank", n1 + n2, {"Group 1": n1, "Group 2": n2}, complete, alpha, power, dropout_fraction, "Schoenfeld-style log-rank approximation", assumptions, tuple(warnings))

    if design_key in {"precision_mean", "confidence_interval_precision"}:
        if half_width is None or half_width <= 0 or standard_deviation <= 0:
            raise ValueError("Positive standard deviation and confidence-interval half-width are required.")
        standard_deviation = _validate_positive(standard_deviation, "Standard deviation")
        complete = ceil((za * standard_deviation / half_width) ** 2)
        adjusted = _adjust_dropout(complete, dropout_fraction)
        assumptions.update(standard_deviation=standard_deviation, half_width=half_width)
        return StudyDesignResult("Precision for a mean", adjusted, {"Participants": adjusted}, complete, alpha, power, dropout_fraction, "Normal confidence-interval precision approximation", assumptions, tuple(warnings))

    if design_key in {"noninferiority", "equivalence"}:
        if margin is None or margin <= 0 or standard_deviation <= 0:
            raise ValueError("Positive margin and standard deviation are required.")
        standard_deviation = _validate_positive(standard_deviation, "Standard deviation")
        standardized = margin / standard_deviation
        if design_key == "noninferiority":
            za_local = _z_alpha(adjusted_alpha, False)
            method = "One-sided non-inferiority approximation"
            label = "Non-inferiority"
        else:
            za_local = _z_alpha(adjusted_alpha, True)
            method = "Two one-sided tests equivalence approximation"
            label = "Equivalence"
        n1_complete = ceil(((1 + 1 / allocation_ratio) * (za_local + zp) ** 2) / standardized**2)
        n2_complete = ceil(n1_complete * allocation_ratio)
        n1, n2 = _adjust_dropout(n1_complete, dropout_fraction), _adjust_dropout(n2_complete, dropout_fraction)
        assumptions.update(margin=margin, standard_deviation=standard_deviation, standardized_margin=standardized)
        warnings.append("The clinical/scientific relevance of the margin must be independently justified.")
        return StudyDesignResult(label, n1 + n2, {"Group 1": n1, "Group 2": n2}, n1_complete + n2_complete, alpha, power, dropout_fraction, method, assumptions, tuple(warnings))

    if design_key in {"repeated_measures", "longitudinal"}:
        if not effect_size or effect_size <= 0 or measurements < 2:
            raise ValueError("A positive effect size and at least two measurements are required.")
        lower_correlation = -1 / (measurements - 1)
        if not lower_correlation < repeated_measure_correlation < 0.999:
            raise ValueError(
                "Repeated-measure correlation is incompatible with the number of measurements."
            )
        # Compound-symmetry planning approximation for the variance of the
        # participant-level mean. This makes the number of measurements affect
        # the result and remains transparent about the simplifying assumption.
        variance_factor = (1 + (measurements - 1) * repeated_measure_correlation) / measurements
        effective_effect = effect_size / sqrt(max(variance_factor, 1e-9))
        complete = ceil(((za + zp) / effective_effect) ** 2)
        adjusted = _adjust_dropout(complete, dropout_fraction)
        assumptions.update(
            effect_size=effect_size,
            measurements=measurements,
            repeated_measure_correlation=repeated_measure_correlation,
            compound_symmetry_variance_factor=variance_factor,
        )
        warnings.append("A full mixed-effects simulation is recommended when visit timing, attrition, or covariance is complex.")
        return StudyDesignResult("Repeated measures", adjusted, {"Participants": adjusted}, complete, alpha, power, dropout_fraction, "Compound-symmetry repeated-measure planning approximation", assumptions, tuple(warnings))

    if design_key in {"cluster_randomized", "cluster"}:
        if not effect_size or effect_size <= 0 or cluster_size < 2:
            raise ValueError("A positive effect size and cluster size of at least two are required.")
        if not 0 <= intraclass_correlation < 1:
            raise ValueError("Intraclass correlation must be between zero and one.")
        individual = calculate_design(
            "two_group_continuous",
            alpha=alpha,
            power=power,
            dropout_fraction=0,
            two_sided=two_sided,
            allocation_ratio=allocation_ratio,
            effect_size=effect_size,
            multiplicity=multiplicity,
            multiplicity_method=multiplicity_method,
        )
        design_effect = 1 + (cluster_size - 1) * intraclass_correlation
        required_individuals = ceil(individual.complete_case_total * design_effect)
        complete_clusters = max(2, ceil(required_individuals / cluster_size))
        if complete_clusters < 8:
            warnings.append("Very few clusters can make asymptotic power approximations unreliable.")
        adjusted_clusters = _adjust_dropout(complete_clusters, dropout_fraction)
        cluster_group_1, cluster_group_2 = _split_total(adjusted_clusters, allocation_ratio)
        n1 = cluster_group_1 * cluster_size
        n2 = cluster_group_2 * cluster_size
        assumptions.update(
            effect_size=effect_size,
            cluster_size=cluster_size,
            intraclass_correlation=intraclass_correlation,
            design_effect=design_effect,
            complete_case_clusters=complete_clusters,
            recruited_clusters=adjusted_clusters,
            clusters_by_group={"Group 1": cluster_group_1, "Group 2": cluster_group_2},
        )
        return StudyDesignResult("Cluster-randomized design", n1 + n2, {"Group 1": n1, "Group 2": n2}, complete_clusters * cluster_size, alpha, power, dropout_fraction, "Individual-level approximation inflated by the cluster design effect and rounded to whole clusters", assumptions, tuple(warnings))

    raise ValueError(f"Unsupported design: {design}")


def approximate_power(
    design: str,
    total_sample_size: int,
    *,
    alpha: float = 0.05,
    effect_size: float = 0.5,
    allocation_ratio: float = 1.0,
    two_sided: bool = True,
) -> float:
    if total_sample_size < 4 or effect_size <= 0 or not isfinite(float(effect_size)):
        return 0.0
    za = _z_alpha(alpha, two_sided)
    design_key = design.lower()
    if design_key in {"correlation", "pearson_correlation"}:
        if not 0 < abs(effect_size) < 1 or total_sample_size <= 3:
            return 0.0
        noncentral = abs(0.5 * log((1 + effect_size) / (1 - effect_size))) * sqrt(total_sample_size - 3)
    elif design_key in {"paired_continuous", "paired"}:
        noncentral = effect_size * sqrt(total_sample_size)
    else:
        n1, n2 = _split_total(total_sample_size, allocation_ratio)
        noncentral = effect_size / sqrt(1 / max(n1, 1) + 1 / max(n2, 1))
    return float(max(0.0, min(1.0, NormalDist().cdf(noncentral - za))))


def power_sensitivity(
    design: str,
    values: list[float],
    *,
    vary: str = "effect_size",
    base: dict[str, Any] | None = None,
) -> pd.DataFrame:
    base = dict(base or {})
    rows: list[dict[str, Any]] = []
    for value in values:
        params = dict(base)
        params[vary] = float(value)
        try:
            result = calculate_design(design, **params)
            rows.append({
                vary: float(value),
                "total_sample_size": result.total_sample_size,
                "complete_case_total": result.complete_case_total,
                "target_power": result.target_power,
                "method": result.method,
                "status": "ok",
            })
        except Exception as exc:
            rows.append({vary: float(value), "status": "error", "error": str(exc)})
    return pd.DataFrame(rows)


def simulate_power(
    design: str,
    *,
    total_sample_size: int,
    effect_size: float = 0.5,
    proportion_1: float = 0.5,
    proportion_2: float = 0.7,
    alpha: float = 0.05,
    allocation_ratio: float = 1.0,
    simulations: int = 2000,
    seed: int = 42,
) -> dict[str, Any]:
    """Monte-Carlo check for simple two-group continuous/proportion designs."""
    if not 100 <= simulations <= 100_000:
        raise ValueError("Simulations must be between 100 and 100,000.")
    n1, n2 = _split_total(int(total_sample_size), allocation_ratio)
    rng = np.random.default_rng(int(seed))
    significant = 0
    p_values: list[float] = []
    from scipy import stats

    if design.lower() in {"two_group_continuous", "two_group", "independent_means"}:
        # Vectorise in bounded chunks to avoid both slow Python loops and very
        # large temporary arrays for high simulation counts/sample sizes.
        max_values_per_chunk = 2_000_000
        chunk_size = max(1, min(simulations, max_values_per_chunk // max(n1 + n2, 1)))
        completed = 0
        while completed < simulations:
            current = min(chunk_size, simulations - completed)
            left = rng.normal(0, 1, (current, n1))
            right = rng.normal(effect_size, 1, (current, n2))
            p = np.asarray(stats.ttest_ind(left, right, equal_var=False, axis=1).pvalue, dtype=float)
            p_values.extend(p.tolist())
            significant += int(np.sum(p < alpha))
            completed += current
    elif design.lower() in {"two_proportions", "proportions"}:
        proportion_1 = _validate_probability(proportion_1, "Proportion 1")
        proportion_2 = _validate_probability(proportion_2, "Proportion 2")
        counts_1 = rng.binomial(n1, proportion_1, simulations)
        counts_2 = rng.binomial(n2, proportion_2, simulations)
        pooled = (counts_1 + counts_2) / (n1 + n2)
        se = np.sqrt(np.maximum(pooled * (1 - pooled) * (1 / n1 + 1 / n2), 1e-12))
        z = (counts_1 / n1 - counts_2 / n2) / se
        p = 2 * stats.norm.sf(np.abs(z))
        p_values = p.astype(float).tolist()
        significant = int(np.sum(p < alpha))
    else:
        raise ValueError("Simulation currently supports two-group continuous and two-proportion designs.")
    estimate = significant / simulations
    standard_error = sqrt(max(estimate * (1 - estimate) / simulations, 0))
    return {
        "design": design,
        "simulations": simulations,
        "seed": int(seed),
        "estimated_power": estimate,
        "monte_carlo_standard_error": standard_error,
        "confidence_interval_95": [max(0.0, estimate - 1.96 * standard_error), min(1.0, estimate + 1.96 * standard_error)],
        "median_p_value": float(np.median(p_values)),
        "n_group_1": n1,
        "n_group_2": n2,
    }


def build_randomization_schedule(
    sample_ids: list[str],
    groups: list[str],
    *,
    strata: dict[str, str] | None = None,
    block_sizes: tuple[int, ...] = (4, 6),
    seed: int | None = None,
    blind_labels: bool = True,
) -> pd.DataFrame:
    clean_samples = [str(item).strip() for item in sample_ids if str(item).strip()]
    clean_groups = [str(item).strip() for item in groups if str(item).strip()]
    if not clean_samples:
        raise ValueError("At least one sample identifier is required.")
    if len(clean_samples) != len(set(clean_samples)):
        raise ValueError("Sample identifiers must be unique.")
    if len(clean_groups) < 2 or len(clean_groups) != len(set(clean_groups)):
        raise ValueError("At least two unique group names are required.")
    if not block_sizes:
        raise ValueError("At least one block size is required.")
    if any(size < len(clean_groups) or size % len(clean_groups) for size in block_sizes):
        raise ValueError("Each block size must be a multiple of the number of groups.")
    resolved_seed = int(seed if seed is not None else randbits(31))
    rng = np.random.default_rng(resolved_seed)
    strata = strata or {sample: "All" for sample in clean_samples}
    blind_order = list(rng.permutation(clean_groups))
    blind_map = {group: f"Arm {index + 1}" for index, group in enumerate(blind_order)}
    rows: list[dict[str, Any]] = []
    for stratum in sorted(set(strata.get(sample, "Unassigned") for sample in clean_samples)):
        members = [sample for sample in clean_samples if strata.get(sample, "Unassigned") == stratum]
        members = list(rng.permutation(members))
        cursor = 0
        block_number = 0
        while cursor < len(members):
            block_number += 1
            block_size = int(rng.choice(block_sizes))
            block_members = members[cursor : cursor + block_size]
            allocation: list[str] = []
            while len(allocation) < len(block_members):
                allocation.extend(list(rng.permutation(clean_groups)))
            for sample, group in zip(block_members, allocation[: len(block_members)]):
                rows.append({
                    "sample_id": sample,
                    "stratum": stratum,
                    "block": block_number,
                    "assigned_group": group,
                    "blinded_label": blind_map[group] if blind_labels else group,
                    "seed": resolved_seed,
                })
            cursor += len(block_members)
    frame = pd.DataFrame(rows)
    frame["allocation_order"] = np.arange(1, len(frame) + 1)
    return frame


def build_design_manifest(
    result: StudyDesignResult,
    *,
    endpoint: str,
    estimand: str,
    inclusion_criteria: str,
    exclusion_criteria: str,
    missing_data_policy: str,
    multiplicity_policy: str,
    randomization_seed: int | None = None,
) -> dict[str, Any]:
    payload = {
        "endpoint": endpoint.strip(),
        "estimand": estimand.strip(),
        "inclusion_criteria": inclusion_criteria.strip(),
        "exclusion_criteria": exclusion_criteria.strip(),
        "missing_data_policy": missing_data_policy.strip(),
        "multiplicity_policy": multiplicity_policy.strip(),
        "randomization_seed": randomization_seed,
        "design_result": result.to_dict(),
        "scientific_boundary": "Planning-level calculation; confirmatory use requires protocol-specific statistical review.",
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    payload["manifest_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return payload
