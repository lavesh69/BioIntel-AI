from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from statistics import NormalDist
from typing import Any

import pandas as pd
from scipy.stats import norm


@dataclass(frozen=True)
class VerificationResult:
    calculation: str
    primary_value: float
    independent_value: float
    absolute_difference: float
    relative_difference: float
    tolerance: float
    status: str
    formula: str
    python_script: str
    r_script: str
    sas_script: str


def verify_two_group_continuous(effect_size: float, alpha: float = 0.05, power: float = 0.80, allocation_ratio: float = 1.0) -> VerificationResult:
    if effect_size <= 0:
        raise ValueError("Effect size must be positive.")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("Alpha and power must be between 0 and 1.")
    if allocation_ratio <= 0:
        raise ValueError("Allocation ratio must be positive.")
    z_alpha_primary = NormalDist().inv_cdf(1 - alpha / 2)
    z_power_primary = NormalDist().inv_cdf(power)
    per_group_primary = ((z_alpha_primary + z_power_primary) ** 2 * (1 + 1 / allocation_ratio)) / (effect_size**2)
    primary = float(ceil(per_group_primary * (1 + allocation_ratio)))

    z_alpha_ind = float(norm.ppf(1 - alpha / 2))
    z_power_ind = float(norm.ppf(power))
    n1 = ((z_alpha_ind + z_power_ind) ** 2 * (1 + 1 / allocation_ratio)) / (effect_size**2)
    independent = float(ceil(n1 + ceil(n1 * allocation_ratio)))
    difference = abs(primary - independent)
    relative = difference / max(primary, independent, 1.0)
    tolerance = 0.02
    status = "Verified" if relative <= tolerance else "Needs review"
    formula = "N = (z_(1-alpha/2)+z_power)^2 * (1+1/r) / d^2, inflated for allocation ratio"
    python_script = f"from statsmodels.stats.power import TTestIndPower\nprint(TTestIndPower().solve_power(effect_size={effect_size}, alpha={alpha}, power={power}, ratio={allocation_ratio}, alternative='two-sided'))"
    r_script = f"power.t.test(delta={effect_size}, sd=1, sig.level={alpha}, power={power}, type='two.sample', alternative='two.sided')"
    sas_script = f"proc power; twosamplemeans test=diff_satt meandiff={effect_size} stddev=1 alpha={alpha} power={power}; run;"
    return VerificationResult("Two-group continuous sample size", primary, independent, difference, relative, tolerance, status, formula, python_script, r_script, sas_script)


def verification_table(results: list[VerificationResult] | tuple[VerificationResult, ...]) -> pd.DataFrame:
    return pd.DataFrame([result.__dict__ for result in results])


def boundary_tests() -> pd.DataFrame:
    cases: list[dict[str, Any]] = []
    for effect in (0.1, 0.2, 0.5, 1.0):
        for power in (0.70, 0.80, 0.90, 0.95):
            result = verify_two_group_continuous(effect, 0.05, power)
            cases.append({"effect_size": effect, "power": power, "sample_size": result.primary_value, "status": result.status})
    return pd.DataFrame(cases)
