from __future__ import annotations

from collections import defaultdict
from math import ceil
from random import Random
from secrets import randbelow
from statistics import NormalDist

import numpy as np
import pandas as pd


def two_group_sample_size(
    effect_size: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    allocation_ratio: float = 1.0,
    two_sided: bool = True,
    dropout_fraction: float = 0.0,
) -> dict:
    if effect_size <= 0:
        raise ValueError("Effect size must be positive.")
    if not 0 < alpha < 1 or not 0 < power < 1 or allocation_ratio <= 0:
        raise ValueError("Invalid alpha, power or allocation ratio.")
    if not 0 <= dropout_fraction < 0.8:
        raise ValueError("Dropout fraction must be between 0 and 0.8.")
    z_alpha = NormalDist().inv_cdf(1 - alpha / (2 if two_sided else 1))
    z_power = NormalDist().inv_cdf(power)
    n1 = ceil(((1 + 1 / allocation_ratio) * (z_alpha + z_power) ** 2) / (effect_size**2))
    n2 = ceil(n1 * allocation_ratio)
    adjusted_n1 = ceil(n1 / (1 - dropout_fraction))
    adjusted_n2 = ceil(n2 / (1 - dropout_fraction))
    return {
        "group_1": adjusted_n1,
        "group_2": adjusted_n2,
        "total": adjusted_n1 + adjusted_n2,
        "complete_case_group_1": n1,
        "complete_case_group_2": n2,
        "effect_size": effect_size,
        "alpha": alpha,
        "power": power,
        "allocation_ratio": allocation_ratio,
        "dropout_fraction": dropout_fraction,
        "method": "normal approximation for standardized mean difference",
    }


def paired_sample_size(
    effect_size: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = True,
    dropout_fraction: float = 0.0,
) -> dict:
    if effect_size <= 0:
        raise ValueError("Paired standardized effect must be positive.")
    z_alpha = NormalDist().inv_cdf(1 - alpha / (2 if two_sided else 1))
    z_power = NormalDist().inv_cdf(power)
    complete = ceil(((z_alpha + z_power) / effect_size) ** 2)
    total = ceil(complete / (1 - dropout_fraction))
    return {
        "pairs": total,
        "complete_case_pairs": complete,
        "total_measurements": 2 * total,
        "effect_size": effect_size,
        "alpha": alpha,
        "power": power,
        "dropout_fraction": dropout_fraction,
        "method": "normal approximation for paired standardized mean difference",
    }


def two_proportion_sample_size(
    proportion_1: float,
    proportion_2: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    allocation_ratio: float = 1.0,
    dropout_fraction: float = 0.0,
) -> dict:
    if not (0 < proportion_1 < 1 and 0 < proportion_2 < 1) or proportion_1 == proportion_2:
        raise ValueError("Proportions must be different and strictly between 0 and 1.")
    pooled = (proportion_1 + proportion_2) / 2
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    numerator = (z_alpha * np.sqrt(2 * pooled * (1 - pooled)) + z_power * np.sqrt(proportion_1 * (1 - proportion_1) + proportion_2 * (1 - proportion_2))) ** 2
    n1 = ceil(float(numerator / (proportion_1 - proportion_2) ** 2))
    n2 = ceil(n1 * allocation_ratio)
    n1 = ceil(n1 / (1 - dropout_fraction))
    n2 = ceil(n2 / (1 - dropout_fraction))
    return {
        "group_1": n1,
        "group_2": n2,
        "total": n1 + n2,
        "proportion_1": proportion_1,
        "proportion_2": proportion_2,
        "absolute_difference": abs(proportion_1 - proportion_2),
        "method": "normal approximation for two independent proportions",
    }


def one_way_anova_sample_size(
    effect_size_f: float,
    groups: int,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout_fraction: float = 0.0,
    maximum_total: int = 100_000,
) -> dict:
    from scipy.stats import f as f_distribution
    from scipy.stats import ncf

    if effect_size_f <= 0 or groups < 2:
        raise ValueError("ANOVA effect size must be positive and groups must be at least two.")
    for total in range(groups * 2, maximum_total + 1):
        df1 = groups - 1
        df2 = total - groups
        critical = f_distribution.ppf(1 - alpha, df1, df2)
        noncentrality = total * effect_size_f**2
        achieved = 1 - ncf.cdf(critical, df1, df2, noncentrality)
        if achieved >= power:
            adjusted = ceil(total / (1 - dropout_fraction))
            per_group = ceil(adjusted / groups)
            return {
                "groups": groups,
                "per_group": per_group,
                "total": per_group * groups,
                "complete_case_total": total,
                "effect_size_f": effect_size_f,
                "alpha": alpha,
                "power": power,
                "method": "noncentral-F one-way ANOVA approximation",
            }
    raise ValueError("Requested ANOVA power exceeds the configured sample-size search range.")


def sensitivity_curve(
    design: str,
    effect_sizes: list[float],
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    groups: int = 2,
    dropout_fraction: float = 0.0,
) -> pd.DataFrame:
    rows = []
    for effect in effect_sizes:
        if design == "two_group":
            result = two_group_sample_size(effect, alpha=alpha, power=power, dropout_fraction=dropout_fraction)
        elif design == "paired":
            result = paired_sample_size(effect, alpha=alpha, power=power, dropout_fraction=dropout_fraction)
        elif design == "anova":
            result = one_way_anova_sample_size(effect, groups, alpha=alpha, power=power, dropout_fraction=dropout_fraction)
        else:
            raise ValueError("Sensitivity design must be two_group, paired or anova.")
        rows.append({"effect_size": effect, "total_sample_size": result.get("total", result.get("pairs")), "design": design})
    return pd.DataFrame(rows)


def randomized_assignment(
    samples: list[str],
    groups: list[str],
    *,
    seed: int = 42,
    blocks: dict[str, str] | None = None,
    allocation_weights: dict[str, float] | None = None,
    variable_block_sizes: tuple[int, ...] = (4, 6),
    blind_labels: bool = False,
) -> pd.DataFrame:
    if not samples or len(groups) < 2:
        raise ValueError("Samples and at least two groups are required.")
    clean_groups = [str(group).strip() for group in groups if str(group).strip()]
    if len(clean_groups) < 2 or len(set(clean_groups)) != len(clean_groups):
        raise ValueError("At least two unique, non-empty group names are required.")
    if len(set(samples)) != len(samples):
        raise ValueError("Sample identifiers must be unique.")
    if any(size < len(clean_groups) or size % len(clean_groups) for size in variable_block_sizes):
        raise ValueError("Each block size must be a multiple of the number of groups.")
    rng = Random(seed)
    block_map = blocks or {sample: "all" for sample in samples}
    bucket: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        bucket[str(block_map.get(sample, "unassigned"))].append(sample)
    if allocation_weights:
        weights = {group: float(allocation_weights.get(group, 0)) for group in clean_groups}
        if any(value <= 0 for value in weights.values()):
            raise ValueError("Allocation weights must be positive for every group.")
    else:
        weights = {group: 1.0 for group in clean_groups}
    rows = []
    allocation_sequence = []
    total_weight = sum(weights.values())
    minimum_units = len(clean_groups)
    for group in clean_groups:
        allocation_sequence.extend([group] * max(1, round(minimum_units * weights[group] / total_weight)))
    if set(allocation_sequence) != set(clean_groups):
        allocation_sequence = clean_groups.copy()
    for stratum, items in sorted(bucket.items()):
        items = items.copy()
        rng.shuffle(items)
        index = 0
        block_number = 0
        while index < len(items):
            block_number += 1
            requested = rng.choice(variable_block_sizes)
            current = items[index : index + requested]
            sequence = []
            while len(sequence) < len(current):
                cycle = allocation_sequence.copy()
                rng.shuffle(cycle)
                sequence.extend(cycle)
            for sample, group in zip(current, sequence[: len(current)]):
                rows.append({
                    "sample": sample,
                    "stratum": stratum,
                    "randomization_block": block_number,
                    "group": group,
                    "blinded_group": f"Arm {clean_groups.index(group) + 1}" if blind_labels else group,
                    "randomization_seed": seed,
                })
            index += len(current)
    return pd.DataFrame(rows)


def _well_coordinates(well: str) -> tuple[int, int]:
    row = ord(str(well)[0].upper()) - ord("A")
    column = int(str(well)[1:]) - 1
    return row, column


def _adjacent_layout_violations(layout: list[tuple[str, tuple[str, int, str]]]) -> int:
    by_sample: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for well, (sample, _, role) in layout:
        if role == "sample":
            by_sample[str(sample)].append(_well_coordinates(well))
    violations = 0
    for coordinates in by_sample.values():
        for index, left in enumerate(coordinates):
            for right in coordinates[index + 1 :]:
                if abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1:
                    violations += 1
    return violations


def plate_randomization(
    samples: list[str],
    *,
    plate_format: int = 96,
    replicates: int = 1,
    seed: int | None = 42,
    controls: dict[str, int] | None = None,
    avoid_adjacent_replicates: bool = True,
    maximum_layout_attempts: int = 500,
) -> pd.DataFrame:
    if plate_format not in {96, 384}:
        raise ValueError("Plate format must be 96 or 384.")
    if replicates < 1:
        raise ValueError("Replicates must be positive.")
    if len(set(samples)) != len(samples):
        raise ValueError("Sample identifiers must be unique before replicate expansion.")
    resolved_seed = int(seed) if seed is not None else randbelow(2**31 - 1) + 1
    rows = list("ABCDEFGH") if plate_format == 96 else [chr(code) for code in range(ord("A"), ord("P") + 1)]
    columns = range(1, 13) if plate_format == 96 else range(1, 25)
    wells = [f"{row}{column}" for row in rows for column in columns]
    assignments = [(sample, replicate + 1, "sample") for sample in samples for replicate in range(replicates)]
    for control, count in (controls or {}).items():
        assignments.extend((control, index + 1, "control") for index in range(int(count)))
    if len(assignments) > len(wells):
        raise ValueError("Requested samples, replicates and controls exceed plate capacity.")
    rng = Random(resolved_seed)
    best_layout: list[tuple[str, tuple[str, int, str]]] | None = None
    best_violations: int | None = None
    attempts = max(1, int(maximum_layout_attempts)) if avoid_adjacent_replicates and replicates > 1 else 1
    for _ in range(attempts):
        candidate_wells = wells.copy()
        candidate_assignments = assignments.copy()
        rng.shuffle(candidate_wells)
        rng.shuffle(candidate_assignments)
        layout = list(zip(candidate_wells[: len(candidate_assignments)], candidate_assignments))
        violations = _adjacent_layout_violations(layout) if avoid_adjacent_replicates else 0
        if best_violations is None or violations < best_violations:
            best_layout, best_violations = layout, violations
        if violations == 0:
            break
    assert best_layout is not None and best_violations is not None
    output = []
    for well, (sample, replicate, role) in best_layout:
        output.append({
            "well": well,
            "sample": sample,
            "replicate": replicate,
            "role": role,
            "plate_format": plate_format,
            "randomization_seed": resolved_seed,
            "adjacency_violations": best_violations,
            "layout_qc": "Pass" if best_violations == 0 else "Review",
        })
    return pd.DataFrame(output).sort_values("well").reset_index(drop=True)


def noninferiority_sample_size(
    noninferiority_margin: float,
    *,
    assumed_standard_deviation: float = 1.0,
    alpha: float = 0.025,
    power: float = 0.8,
    allocation_ratio: float = 1.0,
    dropout_fraction: float = 0.0,
) -> dict:
    """Two-group continuous-outcome non-inferiority approximation."""
    if noninferiority_margin <= 0 or assumed_standard_deviation <= 0:
        raise ValueError("Non-inferiority margin and standard deviation must be positive.")
    standardized_margin = noninferiority_margin / assumed_standard_deviation
    result = two_group_sample_size(
        standardized_margin,
        alpha=alpha,
        power=power,
        allocation_ratio=allocation_ratio,
        two_sided=False,
        dropout_fraction=dropout_fraction,
    )
    result.update(
        {
            "noninferiority_margin": noninferiority_margin,
            "assumed_standard_deviation": assumed_standard_deviation,
            "standardized_margin": standardized_margin,
            "method": "one-sided normal approximation for continuous non-inferiority",
        }
    )
    return result


def equivalence_sample_size(
    equivalence_margin: float,
    *,
    assumed_standard_deviation: float = 1.0,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout_fraction: float = 0.0,
) -> dict:
    """Conservative TOST-style two-group equivalence approximation."""
    if equivalence_margin <= 0 or assumed_standard_deviation <= 0:
        raise ValueError("Equivalence margin and standard deviation must be positive.")
    standardized_margin = equivalence_margin / assumed_standard_deviation
    result = two_group_sample_size(
        standardized_margin,
        alpha=2 * alpha,
        power=power,
        two_sided=False,
        dropout_fraction=dropout_fraction,
    )
    result.update(
        {
            "equivalence_margin": equivalence_margin,
            "assumed_standard_deviation": assumed_standard_deviation,
            "standardized_margin": standardized_margin,
            "method": "conservative two-one-sided-tests normal approximation",
        }
    )
    return result


def correlation_sample_size(
    expected_correlation: float,
    *,
    null_correlation: float = 0.0,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout_fraction: float = 0.0,
) -> dict:
    if not -0.99 < expected_correlation < 0.99 or not -0.99 < null_correlation < 0.99:
        raise ValueError("Correlations must be between -0.99 and 0.99.")
    if expected_correlation == null_correlation:
        raise ValueError("Expected and null correlations must differ.")
    fisher_difference = abs(np.arctanh(expected_correlation) - np.arctanh(null_correlation))
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    complete = ceil(3 + ((z_alpha + z_power) / fisher_difference) ** 2)
    adjusted = ceil(complete / (1 - dropout_fraction))
    return {
        "participants": adjusted,
        "complete_case_participants": complete,
        "expected_correlation": expected_correlation,
        "null_correlation": null_correlation,
        "alpha": alpha,
        "power": power,
        "method": "Fisher-z correlation approximation",
    }


def cluster_adjusted_sample_size(
    individually_randomized_total: int,
    *,
    average_cluster_size: float,
    intracluster_correlation: float,
    cluster_size_cv: float = 0.0,
    dropout_fraction: float = 0.0,
) -> dict:
    if individually_randomized_total <= 0 or average_cluster_size <= 1:
        raise ValueError("Base sample size must be positive and average cluster size must exceed one.")
    if not 0 <= intracluster_correlation < 1 or cluster_size_cv < 0:
        raise ValueError("ICC must be in [0,1) and cluster-size CV cannot be negative.")
    design_effect = 1 + (((1 + cluster_size_cv**2) * average_cluster_size) - 1) * intracluster_correlation
    adjusted = ceil(individually_randomized_total * design_effect / (1 - dropout_fraction))
    clusters = ceil(adjusted / average_cluster_size)
    return {
        "base_individual_total": int(individually_randomized_total),
        "design_effect": float(design_effect),
        "adjusted_individual_total": int(clusters * ceil(average_cluster_size)),
        "clusters": int(clusters),
        "average_cluster_size": float(average_cluster_size),
        "intracluster_correlation": float(intracluster_correlation),
        "cluster_size_cv": float(cluster_size_cv),
        "method": "cluster-randomized design-effect approximation",
    }


def repeated_measures_sample_size(
    standardized_effect: float,
    *,
    measurements: int,
    within_subject_correlation: float = 0.5,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout_fraction: float = 0.0,
) -> dict:
    if measurements < 2 or not -0.9 < within_subject_correlation < 0.99:
        raise ValueError("Repeated-measures design requires at least two measurements and a valid correlation.")
    effective_effect = standardized_effect * np.sqrt(measurements / (1 + (measurements - 1) * within_subject_correlation))
    paired = paired_sample_size(
        effective_effect,
        alpha=alpha,
        power=power,
        dropout_fraction=dropout_fraction,
    )
    paired.update(
        {
            "measurements": int(measurements),
            "within_subject_correlation": float(within_subject_correlation),
            "effective_standardized_effect": float(effective_effect),
            "method": "correlation-adjusted repeated-measures approximation",
        }
    )
    return paired
