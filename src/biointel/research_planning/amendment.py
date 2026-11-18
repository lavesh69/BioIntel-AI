from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

import pandas as pd


IMPACT_RULES: dict[str, tuple[str, ...]] = {
    "primary_objective": ("Study Protocol Designer", "Endpoint & Outcome Strategy Studio", "Statistical Analysis Plan Studio", "Pre-Registration & Reproducibility Studio"),
    "primary_endpoint": ("Sample Size & Statistical Power Studio", "Data Collection & CRF Designer", "Statistical Analysis Plan Studio", "Pre-Registration & Reproducibility Studio"),
    "effect_size": ("Sample Size & Statistical Power Studio", "Research Feasibility & Recruitment Planner", "Research Budget & Participant Burden Studio"),
    "sample_size": ("Research Feasibility & Recruitment Planner", "Research Timeline, Milestones & Dependencies Studio", "Research Budget & Participant Burden Studio"),
    "inclusion_criteria": ("Cohort Definition & Eligibility Builder", "Research Feasibility & Recruitment Planner", "Synthetic Cohort & Trial Simulation Lab"),
    "exclusion_criteria": ("Cohort Definition & Eligibility Builder", "Research Feasibility & Recruitment Planner", "Synthetic Cohort & Trial Simulation Lab"),
    "visit_schedule": ("Sampling & Biospecimen Planning Studio", "Data Collection & CRF Designer", "Research Timeline, Milestones & Dependencies Studio", "Research Budget & Participant Burden Studio"),
    "randomization_strata": ("Randomization, Blinding & Allocation Studio", "Data Collection & CRF Designer", "Statistical Analysis Plan Studio"),
    "biospecimen_plan": ("Sampling & Biospecimen Planning Studio", "Biomarker Study Planning Studio", "Research Budget & Participant Burden Studio"),
    "analysis_method": ("Statistical Analysis Plan Studio", "Sample Size & Statistical Power Studio", "Pre-Registration & Reproducibility Studio"),
    "intercurrent_events": ("Endpoint & Outcome Strategy Studio", "Statistical Analysis Plan Studio", "Pre-Registration & Reproducibility Studio"),
    "site_count": ("Research Feasibility & Recruitment Planner", "Research Timeline, Milestones & Dependencies Studio", "Research Budget & Participant Burden Studio"),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def compare_plans(previous: dict[str, Any], current: dict[str, Any]) -> pd.DataFrame:
    keys = sorted(set(previous) | set(current))
    rows: list[dict[str, Any]] = []
    for key in keys:
        old = previous.get(key)
        new = current.get(key)
        if _canonical(old) == _canonical(new):
            continue
        modules = IMPACT_RULES.get(key, ("Study Protocol Designer",))
        if key not in previous:
            change_type = "Added"
        elif key not in current:
            change_type = "Removed"
        else:
            change_type = "Changed"
        severity = "Critical" if key in {"primary_endpoint", "sample_size", "analysis_method", "inclusion_criteria", "intercurrent_events"} else "Major"
        rows.append(
            {
                "field": key,
                "change_type": change_type,
                "previous_value": old,
                "current_value": new,
                "severity": severity,
                "affected_modules": "; ".join(modules),
                "requires_revalidation": True,
                "change_sha256": sha256(f"{key}|{_canonical(old)}|{_canonical(new)}".encode()).hexdigest(),
            }
        )
    return pd.DataFrame(rows)


def impact_summary(changes: pd.DataFrame) -> dict[str, Any]:
    if changes.empty:
        return {"changes": 0, "critical": 0, "major": 0, "affected_modules": 0, "revalidation_required": False}
    modules: set[str] = set()
    for raw in changes["affected_modules"].fillna(""):
        modules.update(item.strip() for item in str(raw).split(";") if item.strip())
    return {
        "changes": int(len(changes)),
        "critical": int((changes["severity"] == "Critical").sum()),
        "major": int((changes["severity"] == "Major").sum()),
        "affected_modules": len(modules),
        "revalidation_required": bool(changes["requires_revalidation"].any()),
    }
