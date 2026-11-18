from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BurdenItem:
    activity: str
    visits: int
    minutes_per_visit: float
    travel_minutes_per_visit: float
    blood_ml_per_visit: float
    questionnaire_minutes_per_visit: float
    digital_access_required: bool
    discomfort_score: float

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.visits < 0:
            issues.append("Visits cannot be negative.")
        for name, value in {
            "minutes_per_visit": self.minutes_per_visit,
            "travel_minutes_per_visit": self.travel_minutes_per_visit,
            "blood_ml_per_visit": self.blood_ml_per_visit,
            "questionnaire_minutes_per_visit": self.questionnaire_minutes_per_visit,
        }.items():
            if value < 0:
                issues.append(f"{name} cannot be negative.")
        if not 0 <= self.discomfort_score <= 10:
            issues.append("Discomfort score must be between 0 and 10.")
        return issues


@dataclass(frozen=True)
class BudgetItem:
    category: str
    unit: str
    quantity: float
    unit_cost: float
    uncertainty_fraction: float = 0.10
    owner: str = "Unassigned"

    @property
    def base_cost(self) -> float:
        return float(self.quantity * self.unit_cost)


def calculate_participant_burden(items: list[BurdenItem] | tuple[BurdenItem, ...]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        issues = item.validate()
        if issues:
            raise ValueError(f"Invalid burden item {item.activity}: {'; '.join(issues)}")
        on_site_minutes = item.visits * item.minutes_per_visit
        travel_minutes = item.visits * item.travel_minutes_per_visit
        questionnaire_minutes = item.visits * item.questionnaire_minutes_per_visit
        blood_ml = item.visits * item.blood_ml_per_visit
        burden_score = (
            on_site_minutes / 60
            + travel_minutes / 90
            + questionnaire_minutes / 45
            + blood_ml / 50
            + item.discomfort_score * item.visits / 5
            + (2.0 if item.digital_access_required else 0.0)
        )
        rows.append(
            {
                "activity": item.activity,
                "visits": item.visits,
                "on_site_hours": on_site_minutes / 60,
                "travel_hours": travel_minutes / 60,
                "questionnaire_hours": questionnaire_minutes / 60,
                "blood_ml": blood_ml,
                "digital_access_required": item.digital_access_required,
                "discomfort_score": item.discomfort_score,
                "burden_score": burden_score,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, {"total_burden_score": 0.0, "risk_level": "Not assessed"}
    total = float(frame["burden_score"].sum())
    risk = "Low" if total < 20 else "Moderate" if total < 50 else "High"
    summary = {
        "total_burden_score": round(total, 2),
        "risk_level": risk,
        "total_visits": int(frame["visits"].sum()),
        "total_time_hours": round(float(frame[["on_site_hours", "travel_hours", "questionnaire_hours"]].sum().sum()), 2),
        "total_blood_ml": round(float(frame["blood_ml"].sum()), 2),
        "digital_access_activities": int(frame["digital_access_required"].sum()),
    }
    return frame, summary


def simulate_budget(items: list[BudgetItem] | tuple[BudgetItem, ...], iterations: int = 5000, seed: int = 142, contingency_fraction: float = 0.12) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not 0 <= contingency_fraction < 1:
        raise ValueError("Contingency fraction must be between 0 and 1.")
    iterations = max(100, min(int(iterations), 100_000))
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, Any]] = []
    simulations: list[np.ndarray] = []
    for item in items:
        if item.quantity < 0 or item.unit_cost < 0 or not 0 <= item.uncertainty_fraction < 1:
            raise ValueError(f"Invalid budget item: {item.category}")
        base = item.base_cost
        sigma = max(1e-9, item.uncertainty_fraction)
        draws = np.maximum(0, rng.normal(base, base * sigma, iterations))
        simulations.append(draws)
        rows.append(
            {
                "category": item.category,
                "unit": item.unit,
                "quantity": item.quantity,
                "unit_cost": item.unit_cost,
                "base_cost": base,
                "uncertainty_fraction": item.uncertainty_fraction,
                "owner": item.owner,
                "p10_cost": float(np.quantile(draws, 0.10)),
                "median_cost": float(np.median(draws)),
                "p90_cost": float(np.quantile(draws, 0.90)),
            }
        )
    table = pd.DataFrame(rows)
    total_draws = np.sum(simulations, axis=0) if simulations else np.zeros(iterations)
    total_with_contingency = total_draws * (1 + contingency_fraction)
    distribution = pd.DataFrame({"iteration": np.arange(iterations), "total_cost": total_draws, "total_with_contingency": total_with_contingency})
    summary = {
        "base_total": round(float(table["base_cost"].sum()) if not table.empty else 0.0, 2),
        "contingency_fraction": contingency_fraction,
        "median_total": round(float(np.median(total_with_contingency)), 2),
        "p10_total": round(float(np.quantile(total_with_contingency, 0.10)), 2),
        "p90_total": round(float(np.quantile(total_with_contingency, 0.90)), 2),
        "maximum_simulated": round(float(np.max(total_with_contingency)), 2),
    }
    return table, distribution, summary


def site_workload_simulation(site_frame: pd.DataFrame, visits_per_participant: int, minutes_per_visit: float) -> pd.DataFrame:
    required = {"site", "participants", "staff_fte", "working_hours_per_month"}
    missing = sorted(required - set(site_frame.columns))
    if missing:
        raise ValueError("Site workload table is missing: " + ", ".join(missing))
    frame = site_frame.copy()
    frame["required_hours"] = pd.to_numeric(frame["participants"], errors="coerce").fillna(0) * visits_per_participant * minutes_per_visit / 60
    frame["available_hours"] = pd.to_numeric(frame["staff_fte"], errors="coerce").fillna(0) * pd.to_numeric(frame["working_hours_per_month"], errors="coerce").fillna(0)
    frame["utilization"] = frame["required_hours"] / frame["available_hours"].replace(0, np.nan)
    frame["status"] = np.select([frame["utilization"] > 1, frame["utilization"] > 0.85], ["Overloaded", "At risk"], default="Within capacity")
    return frame
