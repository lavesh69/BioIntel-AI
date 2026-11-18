from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable

import pandas as pd


_ALLOWED_STRATEGIES = {
    "treatment policy",
    "hypothetical",
    "composite",
    "while on treatment",
    "principal stratum",
}


@dataclass(frozen=True)
class IntercurrentEvent:
    event: str
    strategy: str
    rationale: str = ""

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.event.strip():
            issues.append("Intercurrent event name is missing.")
        if self.strategy.strip().casefold() not in _ALLOWED_STRATEGIES:
            issues.append(f"Unsupported intercurrent-event strategy: {self.strategy}")
        return issues


@dataclass(frozen=True)
class Estimand:
    estimand_id: str
    objective: str
    treatment: str
    population: str
    variable: str
    population_summary: str
    estimator: str
    intercurrent_events: tuple[IntercurrentEvent, ...] = ()
    sensitivity_analyses: tuple[str, ...] = ()

    def validate(self) -> list[str]:
        issues: list[str] = []
        required = {
            "estimand_id": self.estimand_id,
            "objective": self.objective,
            "treatment": self.treatment,
            "population": self.population,
            "variable": self.variable,
            "population_summary": self.population_summary,
            "estimator": self.estimator,
        }
        for key, value in required.items():
            if not str(value).strip():
                issues.append(f"{key.replace('_', ' ').title()} is missing.")
        for event in self.intercurrent_events:
            issues.extend(event.validate())
        if not self.sensitivity_analyses:
            issues.append("At least one sensitivity analysis should be prespecified.")
        return issues

    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return sha256(payload.encode("utf-8")).hexdigest()


def estimands_from_frame(frame: pd.DataFrame) -> tuple[Estimand, ...]:
    if frame.empty:
        return ()
    required = {
        "estimand_id", "objective", "treatment", "population", "variable",
        "population_summary", "estimator",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Estimand table is missing columns: " + ", ".join(missing))
    items: list[Estimand] = []
    for _, row in frame.iterrows():
        events: list[IntercurrentEvent] = []
        raw_events = str(row.get("intercurrent_events", "")).strip()
        raw_strategies = str(row.get("intercurrent_strategies", "")).strip()
        event_values = [item.strip() for item in raw_events.split(";") if item.strip()]
        strategy_values = [item.strip() for item in raw_strategies.split(";") if item.strip()]
        for index, event in enumerate(event_values):
            strategy = strategy_values[index] if index < len(strategy_values) else "treatment policy"
            events.append(IntercurrentEvent(event, strategy))
        sensitivity = tuple(
            item.strip() for item in str(row.get("sensitivity_analyses", "")).split(";") if item.strip()
        )
        items.append(
            Estimand(
                estimand_id=str(row["estimand_id"]),
                objective=str(row["objective"]),
                treatment=str(row["treatment"]),
                population=str(row["population"]),
                variable=str(row["variable"]),
                population_summary=str(row["population_summary"]),
                estimator=str(row["estimator"]),
                intercurrent_events=tuple(events),
                sensitivity_analyses=sensitivity,
            )
        )
    return tuple(items)


def estimand_validation_table(estimands: Iterable[Estimand]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in estimands:
        issues = item.validate()
        rows.append(
            {
                "estimand_id": item.estimand_id,
                "objective": item.objective,
                "treatment": item.treatment,
                "population": item.population,
                "variable": item.variable,
                "population_summary": item.population_summary,
                "estimator": item.estimator,
                "intercurrent_events": len(item.intercurrent_events),
                "sensitivity_analyses": len(item.sensitivity_analyses),
                "status": "Ready" if not issues else "Needs review",
                "issues": " | ".join(issues) if issues else "—",
                "sha256": item.digest(),
            }
        )
    return pd.DataFrame(rows)


def estimand_flow(estimands: Iterable[Estimand]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in estimands:
        stages = [
            (f"Objective: {item.objective}", f"Treatment: {item.treatment}"),
            (f"Treatment: {item.treatment}", f"Population: {item.population}"),
            (f"Population: {item.population}", f"Variable: {item.variable}"),
            (f"Variable: {item.variable}", f"Summary: {item.population_summary}"),
            (f"Summary: {item.population_summary}", f"Estimator: {item.estimator}"),
        ]
        for source, target in stages:
            rows.append({"estimand_id": item.estimand_id, "source": source, "target": target, "weight": 1})
    return pd.DataFrame(rows)
