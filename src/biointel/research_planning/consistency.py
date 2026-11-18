from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd


@dataclass(frozen=True)
class ConsistencyRule:
    rule_id: str
    title: str
    severity: str
    modules: tuple[str, ...]
    evaluate: Callable[[dict[str, Any]], tuple[bool, str]]


def _nonempty(plan: dict[str, Any], key: str) -> bool:
    value = plan.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict, pd.DataFrame)):
        return len(value) > 0
    return True


def _endpoint_crf(plan: dict[str, Any]) -> tuple[bool, str]:
    endpoints = {str(item).strip().casefold() for item in plan.get("endpoints", []) if str(item).strip()}
    variables = {str(item).strip().casefold() for item in plan.get("crf_variables", []) if str(item).strip()}
    missing = endpoints - variables
    return not missing, "Missing CRF variables: " + ", ".join(sorted(missing)) if missing else "All endpoints are represented in the CRF."


def _strata_crf(plan: dict[str, Any]) -> tuple[bool, str]:
    strata = {str(item).strip().casefold() for item in plan.get("randomization_strata", []) if str(item).strip()}
    variables = {str(item).strip().casefold() for item in plan.get("crf_variables", []) if str(item).strip()}
    missing = strata - variables
    return not missing, "Randomization strata unavailable in CRF: " + ", ".join(sorted(missing)) if missing else "Randomization strata are collectable."


def _sample_size_current(plan: dict[str, Any]) -> tuple[bool, str]:
    protocol_n = plan.get("protocol_sample_size")
    power_n = plan.get("power_sample_size")
    ok = protocol_n is not None and power_n is not None and int(protocol_n) == int(power_n)
    return ok, "Protocol and power sample sizes match." if ok else f"Protocol sample size ({protocol_n}) differs from power result ({power_n})."


def _visit_biospecimen(plan: dict[str, Any]) -> tuple[bool, str]:
    visits = {str(item) for item in plan.get("visits", [])}
    sample_visits = {str(item) for item in plan.get("biospecimen_visits", [])}
    missing = sample_visits - visits
    return not missing, "Biospecimen visits absent from protocol: " + ", ".join(sorted(missing)) if missing else "Biospecimen schedule aligns with protocol visits."


def _estimand_sap(plan: dict[str, Any]) -> tuple[bool, str]:
    estimands = {str(item) for item in plan.get("estimand_ids", [])}
    sap = {str(item) for item in plan.get("sap_estimand_ids", [])}
    missing = estimands - sap
    return not missing and bool(estimands), "Estimands missing from SAP: " + ", ".join(sorted(missing)) if missing else ("Estimands are mapped to the SAP." if estimands else "No estimands are defined.")


def _prereg_alignment(plan: dict[str, Any]) -> tuple[bool, str]:
    protocol_hash = plan.get("protocol_sha256")
    prereg_hash = plan.get("prereg_protocol_sha256")
    ok = bool(protocol_hash) and protocol_hash == prereg_hash
    return ok, "Preregistration is bound to the current protocol hash." if ok else "Preregistration protocol hash is absent or stale."


def _eligibility_feasibility(plan: dict[str, Any]) -> tuple[bool, str]:
    target = float(plan.get("power_sample_size") or 0)
    eligible = float(plan.get("estimated_eligible_population") or 0)
    ok = target > 0 and eligible >= target
    return ok, f"Estimated eligible population {eligible:g} supports target {target:g}." if ok else f"Estimated eligible population {eligible:g} is below target {target:g}."


def _budget_complete(plan: dict[str, Any]) -> tuple[bool, str]:
    ok = _nonempty(plan, "budget_total") and float(plan.get("budget_contingency_fraction") or 0) > 0
    return ok, "Budget includes total and contingency." if ok else "Budget total or contingency is missing."


RULES: tuple[ConsistencyRule, ...] = (
    ConsistencyRule("RP-C001", "Endpoints are represented in the CRF", "Critical", ("Endpoint & Outcome Strategy Studio", "Data Collection & CRF Designer"), _endpoint_crf),
    ConsistencyRule("RP-C002", "Randomization strata are collectable", "Critical", ("Randomization, Blinding & Allocation Studio", "Data Collection & CRF Designer"), _strata_crf),
    ConsistencyRule("RP-C003", "Sample size is synchronized", "Critical", ("Study Protocol Designer", "Sample Size & Statistical Power Studio"), _sample_size_current),
    ConsistencyRule("RP-C004", "Biospecimen visits align with protocol", "Major", ("Study Protocol Designer", "Sampling & Biospecimen Planning Studio"), _visit_biospecimen),
    ConsistencyRule("RP-C005", "Estimands are mapped into the SAP", "Critical", ("Endpoint & Outcome Strategy Studio", "Statistical Analysis Plan Studio"), _estimand_sap),
    ConsistencyRule("RP-C006", "Preregistration is synchronized", "Critical", ("Study Protocol Designer", "Pre-Registration & Reproducibility Studio"), _prereg_alignment),
    ConsistencyRule("RP-C007", "Eligibility supports recruitment target", "Major", ("Cohort Definition & Eligibility Builder", "Research Feasibility & Recruitment Planner"), _eligibility_feasibility),
    ConsistencyRule("RP-C008", "Budget includes contingency", "Major", ("Research Budget & Participant Burden Studio",), _budget_complete),
)


def audit_study_design(plan: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for rule in RULES:
        try:
            passed, message = rule.evaluate(plan)
        except Exception as exc:
            passed, message = False, f"Rule failed safely: {exc}"
        rows.append(
            {
                "rule_id": rule.rule_id,
                "check": rule.title,
                "severity": rule.severity,
                "status": "Pass" if passed else "Needs review",
                "message": message,
                "affected_modules": "; ".join(rule.modules),
            }
        )
    return pd.DataFrame(rows)


def consistency_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"checks": 0, "passed": 0, "needs_review": 0, "critical_open": 0, "score": 0.0}
    passed = int((frame["status"] == "Pass").sum())
    return {
        "checks": int(len(frame)),
        "passed": passed,
        "needs_review": int(len(frame) - passed),
        "critical_open": int(((frame["severity"] == "Critical") & (frame["status"] != "Pass")).sum()),
        "score": round(100.0 * passed / len(frame), 1),
    }
