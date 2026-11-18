from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from biointel.neuro_cns.schemas import table_quality_report


COLUMN_ALIASES = {
    "trial_id": ("trial_id", "nct_id", "study_id", "id"),
    "title": ("title", "study_title", "brief_title"),
    "phase": ("phase", "trial_phase"),
    "status": ("status", "overall_status"),
    "indication": ("indication", "condition", "disease"),
    "compound": ("compound", "drug", "intervention"),
    "target": ("target", "gene", "mechanism"),
    "endpoint": ("endpoint", "primary_endpoint", "outcome"),
    "failure_reason": ("failure_reason", "termination_reason", "why_stopped"),
    "evidence_date": ("evidence_date", "last_update", "date"),
    "eligibility": ("eligibility", "eligibility_criteria", "criteria"),
    "sponsor": ("sponsor", "lead_sponsor", "organization"),
    "enrollment": ("enrollment", "anticipated_enrollment", "participants"),
}


PHASE_ORDER = {"Early Phase 1": 0.5, "Phase 1": 1.0, "Phase 1/Phase 2": 1.5, "Phase 2": 2.0, "Phase 2/Phase 3": 2.5, "Phase 3": 3.0, "Phase 4": 4.0, "Not Applicable": 0.0, "Unspecified": -1.0}
ACTIVE_STATUS = {"recruiting", "active, not recruiting", "not yet recruiting", "enrolling by invitation"}
ATTRITION_STATUS = {"terminated", "withdrawn", "suspended", "failed"}


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def _canonical_phase(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).lower().replace("phase", "phase ")
    text = re.sub(r"\s+", " ", text).strip()
    mapping = {
        "phase  1": "Phase 1", "phase 1": "Phase 1", "1": "Phase 1",
        "phase  2": "Phase 2", "phase 2": "Phase 2", "2": "Phase 2",
        "phase  3": "Phase 3", "phase 3": "Phase 3", "3": "Phase 3",
        "phase  4": "Phase 4", "phase 4": "Phase 4", "4": "Phase 4",
        "phase  1/phase  2": "Phase 1/Phase 2", "phase 1/phase 2": "Phase 1/Phase 2", "phase 1/2": "Phase 1/Phase 2",
        "phase  2/phase  3": "Phase 2/Phase 3", "phase 2/phase 3": "Phase 2/Phase 3", "phase 2/3": "Phase 2/Phase 3",
        "early phase  1": "Early Phase 1", "early phase 1": "Early Phase 1",
        "n/a": "Not Applicable", "not applicable": "Not Applicable",
    }
    return mapping.get(text, str(value).strip() if str(value).strip() else "Unspecified")


def normalize_trials(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.DataFrame(index=frame.index)
    for canonical, aliases in COLUMN_ALIASES.items():
        source = _find_column(frame, aliases)
        normalized[canonical] = frame[source] if source else None
    normalized["phase"] = normalized["phase"].map(_canonical_phase)
    for column in ("status", "indication", "compound", "target", "title", "endpoint", "failure_reason", "eligibility", "sponsor"):
        normalized[column] = normalized[column].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    normalized["trial_id"] = normalized["trial_id"].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    normalized["evidence_date"] = pd.to_datetime(normalized["evidence_date"], errors="coerce", utc=True)
    normalized["enrollment"] = pd.to_numeric(normalized["enrollment"], errors="coerce")
    normalized["phase_numeric"] = normalized["phase"].map(PHASE_ORDER).fillna(-1.0)
    normalized["status_group"] = normalized["status"].str.lower().map(lambda value: "active" if value in ACTIVE_STATUS else "attrition" if any(token in value for token in ATTRITION_STATUS) else "completed/other")
    normalized["record_key"] = normalized["trial_id"].where(normalized["trial_id"] != "Unspecified", normalized["title"].str.lower() + "|" + normalized["compound"].str.lower())
    normalized["registry_url"] = normalized["trial_id"].map(lambda value: f"https://clinicaltrials.gov/study/{value}" if re.fullmatch(r"NCT\d{8}", str(value).upper()) else None)
    return normalized


def _eligibility_tags(text: str) -> list[str]:
    token = str(text or "").lower()
    tags = []
    for pattern, label in ((r"biomarker|amyloid|tau|genotyp", "biomarker-selected"), (r"mri|pet|imaging", "imaging-required"), (r"cognitive|mmse|moca", "cognitive-criteria"), (r"age|years old", "age-defined"), (r"prior treatment|washout|medication", "treatment-history")):
        if re.search(pattern, token):
            tags.append(label)
    return tags


def trial_intelligence(
    frame: pd.DataFrame,
    *,
    currency_warning_days: int = 365,
    source_name: str = "uploaded/offline evidence table",
    source_version: str = "unspecified",
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Trial/evidence table is empty.")
    quality = table_quality_report(frame, _find_column(frame, COLUMN_ALIASES["trial_id"]))
    trials = normalize_trials(frame)
    duplicate_mask = trials["record_key"].duplicated(keep=False)
    deduplicated = trials.sort_values("evidence_date", ascending=False, na_position="last").drop_duplicates("record_key", keep="first").reset_index(drop=True)
    status_counts = deduplicated["status"].value_counts(dropna=False).rename_axis("status").reset_index(name="count")
    phase_counts = deduplicated["phase"].value_counts(dropna=False).rename_axis("phase").reset_index(name="count")
    indication_counts = deduplicated["indication"].value_counts(dropna=False).rename_axis("indication").reset_index(name="count")
    target_counts = deduplicated["target"].value_counts(dropna=False).rename_axis("target").reset_index(name="count")
    failures = deduplicated.loc[deduplicated["status_group"] == "attrition"].copy()
    failures["failure_category"] = failures["failure_reason"].str.lower().map(lambda value: "safety" if "safety" in value or "adverse" in value else "efficacy" if "effic" in value or "futility" in value else "operational" if "recruit" in value or "business" in value else "unspecified")
    now = pd.Timestamp(datetime.now(UTC))
    age_days = (now - deduplicated["evidence_date"]).dt.total_seconds() / 86400.0
    stale = deduplicated.loc[age_days > currency_warning_days].copy()
    eligibility_rows = []
    for _, row in deduplicated.iterrows():
        for tag in _eligibility_tags(row["eligibility"]):
            eligibility_rows.append({"trial_id": row["trial_id"], "eligibility_tag": tag, "indication": row["indication"]})
    eligibility_summary = pd.DataFrame(eligibility_rows)
    if not eligibility_summary.empty:
        eligibility_summary = eligibility_summary.value_counts(["eligibility_tag"]).rename("count").reset_index()
    gaps: list[str] = []
    for column in ("trial_id", "phase", "status", "indication", "compound", "target", "endpoint", "evidence_date"):
        series = deduplicated[column]
        missing = int(series.isna().sum() + series.astype(str).str.strip().isin({"", "None", "nan", "NaT", "Unspecified"}).sum())
        if missing:
            gaps.append(f"{column}: {missing} missing/unspecified")
    phase_indication = pd.crosstab(deduplicated["indication"], deduplicated["phase"])
    sponsor_summary = deduplicated["sponsor"].value_counts(dropna=False).rename_axis("sponsor").reset_index(name="trial_count")
    compound_target = deduplicated.groupby(["compound", "target"], dropna=False).agg(
        trial_count=("record_key", "count"),
        active_trials=("status_group", lambda values: int((values == "active").sum())),
        attrition_trials=("status_group", lambda values: int((values == "attrition").sum())),
        maximum_phase_numeric=("phase_numeric", "max"),
    ).reset_index()
    endpoint_rows: list[dict[str, Any]] = []
    endpoint_patterns = (
        (r"cognit|memory|mmse|moca", "cognition"),
        (r"motor|updrs|movement", "motor"),
        (r"seizure|frequency", "seizure"),
        (r"biomarker|amyloid|tau|neurofilament", "biomarker"),
        (r"imaging|mri|pet", "imaging"),
        (r"safety|adverse|tolerability", "safety/tolerability"),
        (r"survival|progression|time to", "time-to-event"),
    )
    for _, row in deduplicated.iterrows():
        endpoint_text = str(row["endpoint"] or "").lower()
        categories = [label for pattern, label in endpoint_patterns if re.search(pattern, endpoint_text)] or ["uncategorized"]
        for category in categories:
            endpoint_rows.append({"trial_id": row["trial_id"], "endpoint_category": category, "endpoint": row["endpoint"], "indication": row["indication"]})
    endpoint_records = pd.DataFrame(endpoint_rows)
    endpoint_summary = endpoint_records["endpoint_category"].value_counts().rename_axis("endpoint_category").reset_index(name="count") if not endpoint_records.empty else pd.DataFrame()
    latest_evidence_date = deduplicated["evidence_date"].max() if deduplicated["evidence_date"].notna().any() else None
    source_refresh = retrieved_at or (latest_evidence_date.isoformat() if latest_evidence_date is not None else None)
    return {
        "normalized_trials": deduplicated,
        "duplicate_records": trials.loc[duplicate_mask],
        "status_summary": status_counts,
        "phase_summary": phase_counts,
        "indication_summary": indication_counts,
        "target_summary": target_counts,
        "sponsor_summary": sponsor_summary,
        "compound_target_summary": compound_target,
        "endpoint_records": endpoint_records,
        "endpoint_summary": endpoint_summary,
        "phase_by_indication": phase_indication,
        "eligibility_summary": eligibility_summary,
        "attrition_records": failures,
        "stale_records": stale,
        "portfolio_metrics": {
            "input_records": len(trials),
            "deduplicated_trial_records": len(deduplicated),
            "duplicate_records": int(duplicate_mask.sum()),
            "unique_compounds": int(deduplicated["compound"].nunique(dropna=True)),
            "unique_targets": int(deduplicated["target"].nunique(dropna=True)),
            "unique_indications": int(deduplicated["indication"].nunique(dropna=True)),
            "active_records": int((deduplicated["status_group"] == "active").sum()),
            "attrition_records": int((deduplicated["status_group"] == "attrition").sum()),
            "attrition_fraction": round(float((deduplicated["status_group"] == "attrition").mean()), 6),
            "stale_records": len(stale),
            "total_reported_enrollment": int(deduplicated["enrollment"].sum()) if deduplicated["enrollment"].notna().any() else None,
        },
        "evidence_gaps": gaps,
        "input_quality": quality.to_dict(),
        "source_provenance": {
            "source_name": source_name,
            "source_version": source_version,
            "retrieved_at": retrieved_at,
            "latest_evidence_date": latest_evidence_date.isoformat() if latest_evidence_date is not None else None,
            "source_refresh": source_refresh,
            "live_provider_connected": False,
        },
        "scientific_boundary": "Completeness and currency depend on the uploaded/approved evidence source; no live-trial completeness is implied.",
    }
