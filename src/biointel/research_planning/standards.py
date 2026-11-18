from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class StandardRequirement:
    standard: str
    section: str
    requirement: str
    evidence_keys: tuple[str, ...]
    severity: str = "Major"


# These are local readiness profiles, not claims of external certification.
REQUIREMENTS: tuple[StandardRequirement, ...] = (
    StandardRequirement("SPIRIT-style", "Administrative", "Protocol identifier and version are defined", ("protocol_id", "protocol_version"), "Critical"),
    StandardRequirement("SPIRIT-style", "Rationale", "Scientific background and rationale are documented", ("background", "rationale")),
    StandardRequirement("SPIRIT-style", "Objectives", "Primary and secondary objectives are explicit", ("primary_objective", "secondary_objectives"), "Critical"),
    StandardRequirement("SPIRIT-style", "Design", "Study design, allocation and blinding are specified", ("study_design", "allocation", "blinding"), "Critical"),
    StandardRequirement("SPIRIT-style", "Population", "Eligibility criteria and recruitment setting are specified", ("inclusion_criteria", "exclusion_criteria", "recruitment_setting")),
    StandardRequirement("SPIRIT-style", "Interventions", "Interventions, comparators and adherence are described", ("intervention", "comparator", "adherence_plan")),
    StandardRequirement("SPIRIT-style", "Outcomes", "Primary and secondary outcomes include timing and measurement method", ("primary_endpoint", "endpoint_timing", "measurement_method"), "Critical"),
    StandardRequirement("SPIRIT-style", "Sample size", "Sample-size rationale is linked to assumptions", ("sample_size", "effect_size", "alpha", "power"), "Critical"),
    StandardRequirement("SPIRIT-style", "Data", "Data collection, management and monitoring plans are defined", ("crf_plan", "data_management_plan", "monitoring_plan")),
    StandardRequirement("SPIRIT-style", "Ethics", "Consent, ethics and dissemination plans are recorded", ("ethics_status", "consent_plan", "dissemination_plan"), "Critical"),
    StandardRequirement("ICH E6(R3)-style", "Quality by design", "Critical-to-quality factors are identified", ("critical_to_quality",)),
    StandardRequirement("ICH E6(R3)-style", "Risk proportionality", "Risk controls are proportionate and assigned", ("risk_register", "risk_owner", "risk_trigger")),
    StandardRequirement("ICH E6(R3)-style", "Participant protection", "Participant safety, burden and rights are assessed", ("safety_plan", "participant_burden", "privacy_plan"), "Critical"),
    StandardRequirement("ICH E6(R3)-style", "Data reliability", "Source, traceability and data-quality controls are specified", ("source_data_plan", "audit_trail", "data_quality_controls")),
    StandardRequirement("ICH E9(R1)-style", "Treatment", "Treatment condition of interest is defined", ("estimand_treatment",), "Critical"),
    StandardRequirement("ICH E9(R1)-style", "Population", "Estimand population is defined", ("estimand_population",), "Critical"),
    StandardRequirement("ICH E9(R1)-style", "Variable", "Outcome variable is defined", ("estimand_variable",), "Critical"),
    StandardRequirement("ICH E9(R1)-style", "Intercurrent events", "Intercurrent events and strategies are prespecified", ("intercurrent_events", "intercurrent_strategy"), "Critical"),
    StandardRequirement("ICH E9(R1)-style", "Summary", "Population-level summary and estimator are specified", ("population_summary", "estimator"), "Critical"),
    StandardRequirement("ICH E9(R1)-style", "Sensitivity", "Sensitivity analyses address key assumptions", ("sensitivity_analyses",)),
    StandardRequirement("CDISC PRM-style", "Protocol model", "Objectives, endpoints, activities and epochs are machine-readable", ("objectives", "endpoints", "activities", "epochs")),
    StandardRequirement("CDASH-style", "Data collection", "CRF variables use controlled names, types and units", ("crf_variables", "controlled_terminology", "units")),
    StandardRequirement("SDTM-style", "Tabulation", "Collected variables have target domains and identifiers", ("sdtm_mapping", "unique_subject_id")),
    StandardRequirement("ADaM-style", "Analysis data", "Analysis variables have derivation, source and analysis role", ("adam_mapping", "derivations", "analysis_flags")),
    StandardRequirement("FHIR/eSource-style", "Source mapping", "Source resources and CRF destinations are linked", ("fhir_mapping", "source_provenance")),
)


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict, pd.DataFrame)):
        return len(value) > 0
    return True


def validate_readiness(plan: dict[str, Any], standards: Iterable[str] | None = None) -> pd.DataFrame:
    selected = {item.casefold() for item in standards or ()}
    rows: list[dict[str, Any]] = []
    for item in REQUIREMENTS:
        if selected and item.standard.casefold() not in selected:
            continue
        present = [key for key in item.evidence_keys if _present(plan.get(key))]
        missing = [key for key in item.evidence_keys if key not in present]
        if not missing:
            status = "Ready"
            score = 100.0
        elif present:
            status = "Partial"
            score = 100.0 * len(present) / len(item.evidence_keys)
        else:
            status = "Missing"
            score = 0.0
        rows.append(
            {
                "standard": item.standard,
                "section": item.section,
                "requirement": item.requirement,
                "severity": item.severity,
                "status": status,
                "score": round(score, 1),
                "evidence_present": ", ".join(present) or "—",
                "missing_evidence": ", ".join(missing) or "—",
            }
        )
    return pd.DataFrame(rows)


def readiness_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"requirements": 0, "ready": 0, "partial": 0, "missing": 0, "score": 0.0, "critical_missing": 0}
    statuses = frame["status"].value_counts()
    return {
        "requirements": int(len(frame)),
        "ready": int(statuses.get("Ready", 0)),
        "partial": int(statuses.get("Partial", 0)),
        "missing": int(statuses.get("Missing", 0)),
        "score": round(float(frame["score"].mean()), 1),
        "critical_missing": int(((frame["severity"] == "Critical") & (frame["status"] != "Ready")).sum()),
    }


def standards_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["standard", "section", "score"])
    return (
        frame.groupby(["standard", "section"], as_index=False)["score"]
        .mean()
        .sort_values(["standard", "score", "section"], ascending=[True, True, True])
    )
