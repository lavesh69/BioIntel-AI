from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Scenario:
    name: str
    target_sample_size: int
    sites: int
    monthly_rate_per_site: float
    site_activation_mean_months: float
    dropout_fraction: float
    screen_failure_fraction: float
    missing_fraction: float
    assay_failure_fraction: float
    effect_size: float
    outcome_sd: float
    fixed_cost: float
    site_cost: float
    participant_cost: float

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.target_sample_size <= 0:
            issues.append("Target sample size must be positive.")
        if self.sites <= 0:
            issues.append("At least one site is required.")
        if self.monthly_rate_per_site <= 0:
            issues.append("Recruitment rate must be positive.")
        for label, value in {
            "dropout_fraction": self.dropout_fraction,
            "screen_failure_fraction": self.screen_failure_fraction,
            "missing_fraction": self.missing_fraction,
            "assay_failure_fraction": self.assay_failure_fraction,
        }.items():
            if not 0 <= value < 1:
                issues.append(f"{label} must be between 0 and 1.")
        if self.outcome_sd <= 0:
            issues.append("Outcome SD must be positive.")
        return issues


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("Optimistic", 200, 12, 2.4, 1.5, 0.08, 0.18, 0.05, 0.03, 0.42, 1.0, 250000, 18000, 3800),
    Scenario("Base", 200, 10, 1.8, 2.5, 0.15, 0.28, 0.10, 0.06, 0.35, 1.0, 250000, 18000, 3800),
    Scenario("Conservative", 200, 8, 1.2, 3.5, 0.22, 0.38, 0.16, 0.10, 0.28, 1.0, 250000, 18000, 3800),
    Scenario("Stress", 200, 6, 0.8, 5.0, 0.30, 0.50, 0.22, 0.16, 0.20, 1.0, 250000, 18000, 3800),
)


def simulate_scenarios(
    scenarios: tuple[Scenario, ...] | list[Scenario],
    iterations: int = 2000,
    seed: int = 142,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    iterations = max(100, min(int(iterations), 100_000))
    rng = np.random.default_rng(int(seed))
    summary_rows: list[dict[str, Any]] = []
    trajectory_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        issues = scenario.validate()
        if issues:
            raise ValueError(f"Invalid scenario {scenario.name}: {'; '.join(issues)}")
        activation = np.maximum(0.05, rng.lognormal(np.log(max(scenario.site_activation_mean_months, 0.1)), 0.30, iterations))
        rate = np.maximum(0.05, rng.lognormal(np.log(scenario.monthly_rate_per_site), 0.25, iterations))
        effective_rate = scenario.sites * rate * max(1e-6, 1 - scenario.screen_failure_fraction)
        gross_target = ceil(scenario.target_sample_size / max(1e-6, 1 - scenario.dropout_fraction))
        recruitment_months = gross_target / effective_rate
        total_months = activation + recruitment_months
        completed = rng.binomial(gross_target, 1 - scenario.dropout_fraction, iterations)
        analyzable_probability = (1 - scenario.missing_fraction) * (1 - scenario.assay_failure_fraction)
        analyzable = rng.binomial(completed, analyzable_probability)
        observed_effect = rng.normal(scenario.effect_size, scenario.outcome_sd / np.sqrt(np.maximum(analyzable, 1)))
        success_probability = 1 / (1 + np.exp(-(observed_effect * np.sqrt(np.maximum(analyzable, 1)) - 1.96)))
        cost = (
            scenario.fixed_cost
            + scenario.site_cost * scenario.sites
            + scenario.participant_cost * gross_target
            + rng.normal(0, max(1.0, scenario.fixed_cost * 0.06), iterations)
        )
        summary_rows.append(
            {
                "scenario": scenario.name,
                "target_sample_size": scenario.target_sample_size,
                "gross_recruitment_target": gross_target,
                "median_completion_months": float(np.median(total_months)),
                "p10_completion_months": float(np.quantile(total_months, 0.10)),
                "p90_completion_months": float(np.quantile(total_months, 0.90)),
                "median_analyzable": float(np.median(analyzable)),
                "probability_target_analyzable": float(np.mean(analyzable >= scenario.target_sample_size)),
                "mean_success_probability": float(np.mean(success_probability)),
                "median_cost": float(np.median(cost)),
                "p90_cost": float(np.quantile(cost, 0.90)),
            }
        )
        for month in range(0, int(np.ceil(np.quantile(total_months, 0.95))) + 1):
            fraction = np.clip((month - activation) / np.maximum(recruitment_months, 1e-6), 0, 1)
            enrolled = gross_target * fraction
            trajectory_rows.append(
                {
                    "scenario": scenario.name,
                    "month": month,
                    "p10_enrolled": float(np.quantile(enrolled, 0.10)),
                    "median_enrolled": float(np.quantile(enrolled, 0.50)),
                    "p90_enrolled": float(np.quantile(enrolled, 0.90)),
                }
            )
        risk_rows.extend(
            [
                {"scenario": scenario.name, "risk": "Recruitment delay", "probability": float(np.mean(total_months > np.median(total_months) * 1.25))},
                {"scenario": scenario.name, "risk": "Insufficient analyzable sample", "probability": float(np.mean(analyzable < scenario.target_sample_size))},
                {"scenario": scenario.name, "risk": "Cost exceeds p50 by 20%", "probability": float(np.mean(cost > np.median(cost) * 1.20))},
                {"scenario": scenario.name, "risk": "Low observed effect", "probability": float(np.mean(observed_effect < scenario.effect_size * 0.70))},
            ]
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(trajectory_rows), pd.DataFrame(risk_rows)


def scenarios_from_frame(frame: pd.DataFrame) -> tuple[Scenario, ...]:
    required = {field.name for field in Scenario.__dataclass_fields__.values()}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Scenario table is missing columns: " + ", ".join(missing))
    return tuple(Scenario(**{key: row[key] for key in required}) for _, row in frame.iterrows())
