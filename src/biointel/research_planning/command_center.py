from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .consistency import audit_study_design, consistency_summary
from .standards import readiness_summary, validate_readiness


BASE_READINESS_DIMENSIONS = (
    "Protocol readiness",
    "Statistical readiness",
    "Operational feasibility",
    "Data readiness",
    "Reproducibility",
    "Risk control",
    "Participant protection",
    "Budget readiness",
)

LIFECYCLE_READINESS_DIMENSIONS = (
    "Ethics and consent",
    "FAIR data management",
    "Interim monitoring",
    "Dissemination readiness",
)

# Backwards-compatible public constant. Existing integrations continue to see
# the original eight dimensions unless full lifecycle scores are supplied.
READINESS_DIMENSIONS = BASE_READINESS_DIMENSIONS



def build_command_center(
    plan: dict[str, Any],
    assumptions: pd.DataFrame | None = None,
    reviews: pd.DataFrame | None = None,
    collaboration_threads: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    standards = validate_readiness(plan)
    consistency = audit_study_design(plan)
    std = readiness_summary(standards)
    con = consistency_summary(consistency)
    assumptions = assumptions if isinstance(assumptions, pd.DataFrame) else pd.DataFrame()
    reviews = reviews if isinstance(reviews, pd.DataFrame) else pd.DataFrame()
    collaboration_threads = collaboration_threads if isinstance(collaboration_threads, pd.DataFrame) else pd.DataFrame()

    assumption_score = 100.0
    if not assumptions.empty:
        sourced = assumptions.get("source", pd.Series(index=assumptions.index, dtype="object")).fillna("").astype(str).str.strip().ne("")
        bounded = assumptions.get("sensitivity_low", pd.Series(index=assumptions.index, dtype="float")).notna() & assumptions.get("sensitivity_high", pd.Series(index=assumptions.index, dtype="float")).notna()
        assumption_score = 50.0 * float(sourced.mean()) + 50.0 * float(bounded.mean())
    review_score = 100.0 if reviews.empty else 100.0 * float(reviews.get("decision", pd.Series(index=reviews.index, dtype="object")).isin(["Accepted"]).mean())
    open_threads = 0 if collaboration_threads.empty else int((collaboration_threads.get("status", "") != "Resolved").sum())
    thread_score = max(0.0, 100.0 - open_threads * 5.0)

    raw_scores = {
        "Protocol readiness": std["score"],
        "Statistical readiness": con["score"],
        "Operational feasibility": float(plan.get("operational_readiness_score", 70.0)),
        "Data readiness": float(plan.get("data_readiness_score", 70.0)),
        "Reproducibility": float(plan.get("reproducibility_score", 70.0)),
        "Risk control": float(plan.get("risk_control_score", 70.0)),
        "Participant protection": float(plan.get("participant_protection_score", 70.0)),
        "Budget readiness": float(plan.get("budget_readiness_score", 70.0)),
        "Ethics and consent": float(plan.get("ethics_consent_score", plan.get("participant_protection_score", 70.0))),
        "FAIR data management": float(plan.get("fair_data_score", plan.get("data_readiness_score", 70.0))),
        "Interim monitoring": float(plan.get("monitoring_readiness_score", 60.0)),
        "Dissemination readiness": float(plan.get("dissemination_readiness_score", 55.0)),
    }
    lifecycle_keys = {
        "ethics_consent_score", "fair_data_score", "monitoring_readiness_score",
        "dissemination_readiness_score", "include_full_lifecycle",
    }
    active_dimensions = BASE_READINESS_DIMENSIONS
    if lifecycle_keys.intersection(plan):
        active_dimensions = BASE_READINESS_DIMENSIONS + LIFECYCLE_READINESS_DIMENSIONS
    readiness = pd.DataFrame(
        [{"dimension": dimension, "score": round(float(np.clip(raw_scores[dimension], 0, 100)), 1)} for dimension in active_dimensions]
    )
    blockers: list[dict[str, Any]] = []
    for _, row in standards[standards["status"] != "Ready"].iterrows():
        blockers.append({"source": "Standards", "severity": row["severity"], "issue": row["requirement"], "owner": "Unassigned", "status": row["status"]})
    for _, row in consistency[consistency["status"] != "Pass"].iterrows():
        blockers.append({"source": "Consistency", "severity": row["severity"], "issue": row["check"], "owner": "Unassigned", "status": row["status"]})
    if open_threads:
        blockers.append({"source": "Collaboration", "severity": "Major", "issue": f"{open_threads} unresolved review threads", "owner": "Review team", "status": "Open"})
    if lifecycle_keys.intersection(plan):
        lifecycle_owner = {
            "Ethics and consent": "Ethics lead",
            "FAIR data management": "Data steward",
            "Interim monitoring": "Monitoring lead",
            "Dissemination readiness": "Publication lead",
        }
        for dimension in LIFECYCLE_READINESS_DIMENSIONS:
            score = float(raw_scores[dimension])
            if score < 75:
                blockers.append({
                    "source": "Research lifecycle",
                    "severity": "Critical" if score < 50 else "Major",
                    "issue": f"{dimension} readiness is {score:.1f}% (target 75%)",
                    "owner": lifecycle_owner[dimension],
                    "status": "Open",
                })
    blockers_frame = pd.DataFrame(blockers)
    summary = {
        "overall_readiness": round(float(readiness["score"].mean()), 1),
        "critical_blockers": int((blockers_frame.get("severity", pd.Series(dtype="object")) == "Critical").sum()) if not blockers_frame.empty else 0,
        "open_blockers": int(len(blockers_frame)),
        "standards_score": std["score"],
        "consistency_score": con["score"],
        "assumption_quality": round(assumption_score, 1),
        "review_acceptance": round(review_score, 1),
        "collaboration_resolution": round(thread_score, 1),
    }
    return readiness, blockers_frame, standards, summary


def recommended_actions(blockers: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    if blockers.empty:
        return pd.DataFrame([{"priority": 1, "action": "Lock the current planning version and generate a reproducibility package.", "reason": "No open blockers were detected."}])
    order = {"Critical": 0, "Major": 1, "Minor": 2}
    frame = blockers.copy()
    frame["_order"] = frame["severity"].map(order).fillna(3)
    frame = frame.sort_values(["_order", "source", "issue"]).head(max(1, min(int(limit), 100))).reset_index(drop=True)
    frame["priority"] = frame.index + 1
    frame["action"] = "Resolve: " + frame["issue"].astype(str)
    frame["reason"] = frame["source"].astype(str) + " · " + frame["severity"].astype(str)
    return frame[["priority", "action", "reason"]]
