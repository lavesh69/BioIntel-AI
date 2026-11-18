from __future__ import annotations

"""Research lifecycle specialist engines.

These utilities extend Research Planning beyond protocol design into ethics,
FAIR data management, interim monitoring and dissemination.  They are bounded,
deterministic planning aids.  They do not replace ethics committees, data
protection officers, safety-monitoring boards, journals or regulators.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

MAX_ROWS = 100_000
MAX_MONTE_CARLO = 50_000


@dataclass(frozen=True)
class LifecycleOutput:
    module_key: str
    primary: pd.DataFrame
    tables: Mapping[str, pd.DataFrame]
    summary: Mapping[str, Any]
    warnings: tuple[str, ...] = ()

    def all_tables(self) -> dict[str, pd.DataFrame]:
        return {"primary": self.primary, **dict(self.tables)}

    def manifest(self) -> dict[str, Any]:
        hashes = {name: dataframe_sha256(frame) for name, frame in self.all_tables().items()}
        payload = {
            "module_key": self.module_key,
            "summary": dict(self.summary),
            "warnings": list(self.warnings),
            "table_sha256": hashes,
        }
        payload["manifest_sha256"] = sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return payload


def dataframe_sha256(frame: pd.DataFrame) -> str:
    return sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def _bounded(frame: pd.DataFrame, *, limit: int = MAX_ROWS) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("A pandas DataFrame is required.")
    if len(frame) > limit:
        raise ValueError(f"Input contains {len(frame):,} rows; limit is {limit:,} rows.")
    return frame.copy()


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: " + ", ".join(sorted(missing)))


def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return _text(series).str.lower().isin({"1", "true", "yes", "y", "required", "present"})


def _numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(float)


def _unique_nonempty(frame: pd.DataFrame, column: str, label: str) -> None:
    values = _text(frame[column])
    if values.eq("").any():
        raise ValueError(f"{label} identifiers must not be blank.")
    if values.duplicated().any():
        duplicates = values[values.duplicated(keep=False)].drop_duplicates().tolist()[:10]
        raise ValueError(f"{label} identifiers must be unique. Duplicates: {', '.join(duplicates)}")


def ethics_consent_workbench(items: pd.DataFrame) -> LifecycleOutput:
    required = {
        "item_id", "domain", "requirement", "status", "risk_level", "vulnerable_group",
        "consent_required", "privacy_sensitive", "owner", "evidence_reference",
    }
    data = _bounded(items, limit=25_000)
    _require(data, required, "Ethics and consent table")
    if data.empty:
        raise ValueError("At least one ethics/consent requirement is required.")
    _unique_nonempty(data, "item_id", "Ethics item")

    for column in ("domain", "requirement", "status", "risk_level", "vulnerable_group", "owner", "evidence_reference"):
        data[column] = _text(data[column])
    data["consent_required"] = _bool(data["consent_required"])
    data["privacy_sensitive"] = _bool(data["privacy_sensitive"])

    status_map = {
        "complete": 100.0,
        "approved": 100.0,
        "ready": 100.0,
        "in review": 70.0,
        "draft": 45.0,
        "not started": 0.0,
        "blocked": 0.0,
    }
    risk_weight = {"critical": 1.5, "high": 1.25, "moderate": 1.0, "low": 0.75}
    data["readiness_score"] = data["status"].str.lower().map(status_map).fillna(35.0)
    data["risk_weight"] = data["risk_level"].str.lower().map(risk_weight).fillna(1.0)
    data["evidence_present"] = data["evidence_reference"].ne("")
    data["owner_present"] = data["owner"].ne("")
    data["weighted_gap"] = ((100.0 - data["readiness_score"]) * data["risk_weight"]).round(2)
    data["blocking_issue"] = (
        data["risk_level"].str.lower().isin({"critical", "high"})
        & data["status"].str.lower().isin({"blocked", "not started", "draft"})
    )

    issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        if not row["owner_present"]:
            issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "No accountable owner", "action": "Assign an ethics/consent owner."})
        if not row["evidence_present"]:
            issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "Evidence reference missing", "action": "Attach the relevant document, decision or policy reference."})
        if bool(row["consent_required"]) and row["domain"].lower() == "consent" and row["status"].lower() not in {"complete", "approved", "ready"}:
            issues.append({"item_id": row["item_id"], "severity": "Critical", "issue": "Required consent element is not ready", "action": "Resolve before participant-facing activity."})
        if bool(row["privacy_sensitive"]) and row["domain"].lower() not in {"privacy", "data protection", "consent"}:
            issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "Privacy-sensitive item lacks explicit privacy domain ownership", "action": "Link to data-protection review."})
        if row["status"].lower() not in status_map:
            issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "Unrecognised readiness status", "action": "Use Complete, Approved, Ready, In review, Draft, Not started or Blocked."})
        if bool(row["blocking_issue"]):
            issues.append({"item_id": row["item_id"], "severity": "Critical", "issue": "High-risk requirement is unresolved", "action": "Escalate for formal review."})
    issues_frame = pd.DataFrame(issues, columns=["item_id", "severity", "issue", "action"])

    domain_summary = data.groupby("domain", dropna=False).agg(
        requirements=("item_id", "count"),
        mean_readiness=("readiness_score", "mean"),
        unresolved=("readiness_score", lambda s: int((s < 100).sum())),
        blockers=("blocking_issue", "sum"),
        evidence_coverage=("evidence_present", "mean"),
    ).reset_index()
    domain_summary["mean_readiness"] = domain_summary["mean_readiness"].round(1)
    domain_summary["evidence_coverage"] = (100 * domain_summary["evidence_coverage"]).round(1)

    subgroup_summary = data.groupby("vulnerable_group", dropna=False).agg(
        requirements=("item_id", "count"),
        consent_items=("consent_required", "sum"),
        privacy_items=("privacy_sensitive", "sum"),
        readiness=("readiness_score", "mean"),
        unresolved_high_risk=("blocking_issue", "sum"),
    ).reset_index()
    subgroup_summary["readiness"] = subgroup_summary["readiness"].round(1)

    overall = float(np.average(data["readiness_score"], weights=data["risk_weight"]))
    summary = {
        "requirements": int(len(data)),
        "overall_readiness": round(overall, 1),
        "critical_blockers": int((issues_frame.get("severity", pd.Series(dtype=str)) == "Critical").sum()),
        "unresolved_items": int((data["readiness_score"] < 100).sum()),
        "evidence_coverage_percent": round(100 * float(data["evidence_present"].mean()), 1),
        "consent_coverage_percent": round(100 * float(data.loc[data["consent_required"], "readiness_score"].eq(100).mean()) if data["consent_required"].any() else 100.0, 1),
    }
    warnings = []
    if summary["critical_blockers"]:
        warnings.append("Critical participant-protection blockers remain open.")
    if summary["evidence_coverage_percent"] < 100:
        warnings.append("Some requirements do not have evidence references.")
    return _enhance_ethics_output(LifecycleOutput(
        "research_ethics_consent",
        data,
        {"issues": issues_frame, "domain_summary": domain_summary, "subgroup_summary": subgroup_summary},
        summary,
        tuple(warnings),
    ))


def fair_data_management_workbench(assets: pd.DataFrame) -> LifecycleOutput:
    required = {
        "asset_id", "data_type", "format", "metadata_standard", "persistent_id", "access_level",
        "retention_years", "repository", "licence", "owner", "backup_copies", "encryption",
    }
    data = _bounded(assets, limit=50_000)
    _require(data, required, "Research data-management table")
    if data.empty:
        raise ValueError("At least one research data asset is required.")
    _unique_nonempty(data, "asset_id", "Data asset")
    for column in ("data_type", "format", "metadata_standard", "persistent_id", "access_level", "repository", "licence", "owner", "encryption"):
        data[column] = _text(data[column])
    data["retention_years"] = _numeric(data["retention_years"], -1)
    data["backup_copies"] = _numeric(data["backup_copies"], -1).round().astype(int)
    if (data["retention_years"] < 0).any():
        raise ValueError("Retention years must be zero or greater.")
    if (data["backup_copies"] < 0).any():
        raise ValueError("Backup copies must be zero or greater.")

    preferred_formats = {
        "csv", "tsv", "json", "xml", "parquet", "txt", "fasta", "fastq", "vcf", "bcf", "bam", "cram",
        "gff", "gtf", "h5ad", "mudata", "mzml", "cif", "mmcif", "pdf/a", "odm", "xpt",
    }
    data["findable"] = (
        data["persistent_id"].ne("").astype(int) * 50
        + data["metadata_standard"].ne("").astype(int) * 30
        + data["repository"].ne("").astype(int) * 20
    )
    access_known = data["access_level"].str.lower().isin({"open", "controlled", "restricted", "embargoed", "internal"})
    data["accessible"] = (
        access_known.astype(int) * 40
        + data["repository"].ne("").astype(int) * 35
        + data["encryption"].str.lower().isin({"yes", "true", "aes-256", "at rest", "encrypted"}).astype(int) * 25
    )
    data["interoperable"] = (
        data["format"].str.lower().isin(preferred_formats).astype(int) * 60
        + data["metadata_standard"].ne("").astype(int) * 40
    )
    data["reusable"] = (
        data["licence"].ne("").astype(int) * 35
        + data["owner"].ne("").astype(int) * 20
        + data["retention_years"].gt(0).astype(int) * 20
        + data["backup_copies"].ge(2).astype(int) * 25
    )
    data["fair_score"] = data[["findable", "accessible", "interoperable", "reusable"]].mean(axis=1).round(1)
    data["backup_risk"] = np.select(
        [data["backup_copies"].eq(0), data["backup_copies"].eq(1)],
        ["Critical", "High"],
        default="Controlled",
    )
    data["retention_risk"] = np.where(data["retention_years"].eq(0), "Review", "Defined")

    issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        checks = [
            (row["persistent_id"] == "", "Major", "Persistent identifier is missing", "Assign a stable local or repository identifier."),
            (row["metadata_standard"] == "", "Major", "Metadata standard is missing", "Select a domain-appropriate metadata schema."),
            (row["repository"] == "", "Major", "Repository is not selected", "Define archive/repository destination."),
            (row["licence"] == "", "Major", "Reuse licence is missing", "Record permitted reuse and access terms."),
            (row["owner"] == "", "Critical", "Data steward is missing", "Assign an accountable owner."),
            (row["access_level"].lower() not in {"open", "controlled", "restricted", "embargoed", "internal"}, "Major", "Access level is not recognised", "Use an explicit open, controlled, restricted, embargoed or internal access state."),
            (int(row["backup_copies"]) < 2, "Critical" if int(row["backup_copies"]) == 0 else "Major", "Backup coverage is insufficient", "Plan at least two independent copies where appropriate."),
            (float(row["fair_score"]) < 60, "Major", "FAIR readiness is below 60", "Resolve metadata, format, access and reuse gaps."),
        ]
        for condition, severity, issue, action in checks:
            if condition:
                issues.append({"asset_id": row["asset_id"], "severity": severity, "issue": issue, "action": action})
    issues_frame = pd.DataFrame(issues, columns=["asset_id", "severity", "issue", "action"])

    fair_dimensions = pd.DataFrame([
        {"dimension": "Findable", "score": round(float(data["findable"].mean()), 1)},
        {"dimension": "Accessible", "score": round(float(data["accessible"].mean()), 1)},
        {"dimension": "Interoperable", "score": round(float(data["interoperable"].mean()), 1)},
        {"dimension": "Reusable", "score": round(float(data["reusable"].mean()), 1)},
    ])
    type_summary = data.groupby("data_type", dropna=False).agg(
        assets=("asset_id", "count"),
        mean_fair_score=("fair_score", "mean"),
        retention_years=("retention_years", "mean"),
        backup_copies=("backup_copies", "mean"),
    ).reset_index()
    type_summary[["mean_fair_score", "retention_years", "backup_copies"]] = type_summary[["mean_fair_score", "retention_years", "backup_copies"]].round(1)

    summary = {
        "assets": int(len(data)),
        "overall_fair_score": round(float(data["fair_score"].mean()), 1),
        "critical_issues": int((issues_frame.get("severity", pd.Series(dtype=str)) == "Critical").sum()),
        "persistent_id_coverage_percent": round(100 * float(data["persistent_id"].ne("").mean()), 1),
        "metadata_coverage_percent": round(100 * float(data["metadata_standard"].ne("").mean()), 1),
        "two_copy_backup_coverage_percent": round(100 * float(data["backup_copies"].ge(2).mean()), 1),
    }
    warnings = []
    if summary["critical_issues"]:
        warnings.append("Critical data stewardship or backup issues remain unresolved.")
    if summary["overall_fair_score"] < 70:
        warnings.append("Overall FAIR readiness is below 70.")
    return _enhance_fair_output(LifecycleOutput(
        "research_data_fair_planning",
        data,
        {"issues": issues_frame, "fair_dimensions": fair_dimensions, "data_type_summary": type_summary},
        summary,
        tuple(warnings),
    ))


def _rate_ratio_ci(events_a: int, exposure_a: int, events_b: int, exposure_b: int) -> tuple[float, float, float]:
    # Haldane-Anscombe correction prevents division by zero while remaining deterministic.
    a = events_a + 0.5
    b = max(exposure_a - events_a, 0) + 0.5
    c = events_b + 0.5
    d = max(exposure_b - events_b, 0) + 0.5
    risk_a = a / (a + b)
    risk_b = c / (c + d)
    rr = risk_a / risk_b
    se = math.sqrt((1 / a) - (1 / (a + b)) + (1 / c) - (1 / (c + d)))
    return rr, math.exp(math.log(rr) - 1.96 * se), math.exp(math.log(rr) + 1.96 * se)


def interim_monitoring_safety_workbench(events: pd.DataFrame, *, serious_rate_threshold: float = 0.10) -> LifecycleOutput:
    required = {
        "participant_id", "arm", "event_id", "event_type", "severity", "serious", "relatedness",
        "event_day", "resolved", "reportable",
    }
    data = _bounded(events, limit=100_000)
    _require(data, required, "Interim monitoring and safety table")
    if data.empty:
        raise ValueError("At least one monitoring/safety event is required.")
    _unique_nonempty(data, "event_id", "Event")
    for column in ("participant_id", "arm", "event_type", "severity", "relatedness"):
        data[column] = _text(data[column])
    if data["participant_id"].eq("").any() or data["arm"].eq("").any():
        raise ValueError("Participant and arm values must not be blank.")
    data["serious"] = _bool(data["serious"])
    data["resolved"] = _bool(data["resolved"])
    data["reportable"] = _bool(data["reportable"])
    data["event_day"] = _numeric(data["event_day"], -1)
    if (data["event_day"] < 0).any():
        raise ValueError("Event day must be zero or greater.")
    if not 0 <= serious_rate_threshold <= 1:
        raise ValueError("Serious-rate threshold must be between 0 and 1.")

    severity_weight = {"mild": 1.0, "moderate": 2.0, "severe": 3.0, "life-threatening": 4.0, "fatal": 5.0}
    relation_weight = {"unrelated": 0.0, "unlikely": 0.25, "possible": 0.5, "probable": 0.75, "related": 1.0}
    data["severity_weight"] = data["severity"].str.lower().map(severity_weight).fillna(2.0)
    data["relatedness_weight"] = data["relatedness"].str.lower().map(relation_weight).fillna(0.5)
    data["safety_signal_score"] = (
        data["severity_weight"]
        * (1.0 + data["serious"].astype(float))
        * (0.5 + data["relatedness_weight"])
        * (1.0 + data["reportable"].astype(float) * 0.5)
    ).round(2)
    data["requires_immediate_review"] = data["serious"] & (~data["resolved"] | data["reportable"])

    denominator_source = "participants represented in event table"
    if "arm_population" in data.columns:
        data["arm_population"] = _numeric(data["arm_population"], -1).round().astype(int)
        if (data["arm_population"] <= 0).any():
            raise ValueError("Arm population values must be positive when supplied.")
        inconsistent = data.groupby("arm")["arm_population"].nunique().gt(1)
        if inconsistent.any():
            raise ValueError("Arm population must be constant within each arm.")
        participant_by_arm = data.groupby("arm")["arm_population"].max().rename("participants")
        denominator_source = "supplied arm population"
    else:
        participant_by_arm = data.groupby("arm")["participant_id"].nunique().rename("participants")
    arm_summary = data.groupby("arm", dropna=False).agg(
        events=("event_id", "count"),
        participants_with_events=("participant_id", "nunique"),
        serious_events=("serious", "sum"),
        unresolved_events=("resolved", lambda s: int((~s).sum())),
        reportable_events=("reportable", "sum"),
        mean_signal_score=("safety_signal_score", "mean"),
    ).reset_index()
    arm_summary = arm_summary.merge(participant_by_arm.reset_index(), on="arm", how="left")
    arm_summary["serious_event_rate"] = (arm_summary["serious_events"] / arm_summary["participants"].clip(lower=1)).round(4)
    arm_summary["threshold_exceeded"] = arm_summary["serious_event_rate"] > serious_rate_threshold
    arm_summary["mean_signal_score"] = arm_summary["mean_signal_score"].round(2)

    comparisons: list[dict[str, Any]] = []
    arms = arm_summary["arm"].tolist()
    if len(arms) >= 2:
        reference = arms[0]
        ref_row = arm_summary.loc[arm_summary["arm"] == reference].iloc[0]
        for arm in arms[1:]:
            row = arm_summary.loc[arm_summary["arm"] == arm].iloc[0]
            rr, low, high = _rate_ratio_ci(
                int(row["serious_events"]), int(row["participants"]),
                int(ref_row["serious_events"]), int(ref_row["participants"]),
            )
            comparisons.append({
                "comparison": f"{arm} vs {reference}",
                "rate_ratio": round(rr, 4),
                "ci_low": round(low, 4),
                "ci_high": round(high, 4),
                "signal": "Review" if low > 1 or row["threshold_exceeded"] else "No threshold signal",
            })
    comparison_frame = pd.DataFrame(comparisons, columns=["comparison", "rate_ratio", "ci_low", "ci_high", "signal"])

    severity_summary = data.groupby(["arm", "severity"], dropna=False).size().reset_index(name="events")
    timeline = data.groupby(["event_day", "arm"], dropna=False).agg(
        events=("event_id", "count"),
        serious_events=("serious", "sum"),
        signal_score=("safety_signal_score", "sum"),
    ).reset_index().sort_values(["event_day", "arm"])
    timeline["cumulative_events"] = timeline.groupby("arm")["events"].cumsum()
    timeline["cumulative_serious"] = timeline.groupby("arm")["serious_events"].cumsum()

    issues: list[dict[str, Any]] = []
    allowed_severity = set(severity_weight)
    allowed_relatedness = set(relation_weight)
    for _, row in data.iterrows():
        if row["severity"].lower() not in allowed_severity:
            issues.append({"event_id": row["event_id"], "severity": "Major", "issue": "Unrecognised event severity", "action": "Map severity to a controlled term before review."})
        if row["relatedness"].lower() not in allowed_relatedness:
            issues.append({"event_id": row["event_id"], "severity": "Major", "issue": "Unrecognised relatedness category", "action": "Map relatedness to a controlled term before review."})
        if bool(row["requires_immediate_review"]):
            issues.append({"event_id": row["event_id"], "severity": "Critical", "issue": "Serious unresolved/reportable event", "action": "Escalate to the responsible safety-review process."})
    for _, row in arm_summary.loc[arm_summary["threshold_exceeded"]].iterrows():
        issues.append({"event_id": f"ARM:{row['arm']}", "severity": "Critical", "issue": "Serious-event threshold exceeded", "action": "Trigger prespecified interim review."})
    issues_frame = pd.DataFrame(issues, columns=["event_id", "severity", "issue", "action"])

    summary = {
        "events": int(len(data)),
        "participants_with_events": int(data["participant_id"].nunique()),
        "serious_events": int(data["serious"].sum()),
        "immediate_reviews": int(data["requires_immediate_review"].sum()),
        "arms_over_threshold": int(arm_summary["threshold_exceeded"].sum()),
        "serious_rate_threshold": float(serious_rate_threshold),
        "denominator_source": denominator_source,
    }
    warnings = []
    if denominator_source != "supplied arm population":
        warnings.append("Arm population was not supplied; rates use participants represented in the event table and may not equal enrolled-arm incidence.")
    if summary["immediate_reviews"]:
        warnings.append("Immediate safety review items are present.")
    if summary["arms_over_threshold"]:
        warnings.append("At least one arm exceeds the configured planning threshold.")
    return _enhance_safety_output(LifecycleOutput(
        "research_interim_monitoring_safety",
        data,
        {
            "arm_summary": arm_summary,
            "arm_comparisons": comparison_frame,
            "severity_summary": severity_summary,
            "timeline": timeline,
            "issues": issues_frame,
        },
        summary,
        tuple(warnings),
    ))


def publication_dissemination_workbench(outputs: pd.DataFrame, *, today: str | pd.Timestamp | None = None) -> LifecycleOutput:
    required = {
        "output_id", "title", "audience", "channel", "owner", "target_date", "status", "open_access",
        "lay_summary", "data_statement", "code_available", "accessibility_review", "priority",
    }
    data = _bounded(outputs, limit=25_000)
    _require(data, required, "Publication and dissemination table")
    if data.empty:
        raise ValueError("At least one dissemination output is required.")
    _unique_nonempty(data, "output_id", "Dissemination output")
    for column in ("title", "audience", "channel", "owner", "target_date", "status", "priority"):
        data[column] = _text(data[column])
    for column in ("open_access", "lay_summary", "data_statement", "code_available", "accessibility_review"):
        data[column] = _bool(data[column])
    if data["title"].eq("").any():
        raise ValueError("Dissemination titles must not be blank.")
    dates = pd.to_datetime(data["target_date"], errors="coerce", utc=True)
    if dates.isna().any():
        bad = data.loc[dates.isna(), "output_id"].tolist()[:10]
        raise ValueError("Invalid target dates for: " + ", ".join(map(str, bad)))
    now = pd.Timestamp(today if today is not None else pd.Timestamp.utcnow())
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    data["target_date_parsed"] = dates
    data["days_to_target"] = (dates - now).dt.days
    data["completed"] = data["status"].str.lower().isin({"complete", "completed", "published", "released"})
    data["overdue"] = data["days_to_target"].lt(0) & ~data["completed"]
    data["open_science_score"] = (
        data["open_access"].astype(int)
        + data["lay_summary"].astype(int)
        + data["data_statement"].astype(int)
        + data["code_available"].astype(int)
        + data["accessibility_review"].astype(int)
    ) * 20
    priority_weight = data["priority"].str.lower().map({"critical": 1.5, "high": 1.25, "medium": 1.0, "low": 0.75}).fillna(1.0)
    data["readiness_score"] = (
        data["completed"].astype(float) * 40
        + data["owner"].ne("").astype(float) * 15
        + data["open_science_score"] * 0.45
    ).clip(0, 100).round(1)
    data["weighted_gap"] = ((100 - data["readiness_score"]) * priority_weight).round(1)

    issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        checks = [
            (row["owner"] == "", "Critical", "Output owner missing", "Assign an accountable owner."),
            (row["status"].lower() not in {"not started", "planned", "draft", "in progress", "in review", "complete", "completed", "published", "released"}, "Major", "Unrecognised dissemination status", "Use a controlled dissemination status."),
            (bool(row["overdue"]), "Major", "Target date is overdue", "Replan, escalate or document the delay."),
            (not bool(row["data_statement"]), "Major", "Data availability statement not planned", "Define data access and availability language."),
            (not bool(row["accessibility_review"]), "Major", "Accessibility review not planned", "Review plain language, formats and accessibility."),
            (float(row["open_science_score"]) < 60, "Minor", "Open-science readiness below 60", "Increase access, lay summary, data or code availability."),
        ]
        for condition, severity, issue, action in checks:
            if condition:
                issues.append({"output_id": row["output_id"], "severity": severity, "issue": issue, "action": action})
    issues_frame = pd.DataFrame(issues, columns=["output_id", "severity", "issue", "action"])

    audience_summary = data.groupby("audience", dropna=False).agg(
        outputs=("output_id", "count"),
        completed=("completed", "sum"),
        mean_readiness=("readiness_score", "mean"),
        mean_open_science=("open_science_score", "mean"),
        overdue=("overdue", "sum"),
    ).reset_index()
    audience_summary[["mean_readiness", "mean_open_science"]] = audience_summary[["mean_readiness", "mean_open_science"]].round(1)
    channel_summary = data.groupby("channel", dropna=False).agg(
        outputs=("output_id", "count"),
        completed=("completed", "sum"),
        overdue=("overdue", "sum"),
        readiness=("readiness_score", "mean"),
    ).reset_index()
    channel_summary["readiness"] = channel_summary["readiness"].round(1)
    timeline = data[["output_id", "title", "channel", "audience", "target_date_parsed", "days_to_target", "status", "overdue"]].sort_values("target_date_parsed")

    summary = {
        "outputs": int(len(data)),
        "completed_outputs": int(data["completed"].sum()),
        "overdue_outputs": int(data["overdue"].sum()),
        "mean_readiness": round(float(data["readiness_score"].mean()), 1),
        "mean_open_science_score": round(float(data["open_science_score"].mean()), 1),
        "audiences_covered": int(data["audience"].replace("", np.nan).nunique()),
    }
    warnings = []
    if summary["overdue_outputs"]:
        warnings.append("One or more dissemination outputs are overdue.")
    if summary["mean_open_science_score"] < 60:
        warnings.append("Open-science readiness is below 60.")
    return _enhance_publication_output(LifecycleOutput(
        "research_publication_dissemination",
        data,
        {"issues": issues_frame, "audience_summary": audience_summary, "channel_summary": channel_summary, "timeline": timeline},
        summary,
        tuple(warnings),
    ))


LIFECYCLE_ENGINE_CATALOG = {
    "research_ethics_consent": {
        "title": "Research Ethics, Consent & Participant Protection Studio",
        "function": ethics_consent_workbench,
        "record_id": "item_id",
    },
    "research_data_fair_planning": {
        "title": "Research Data Management & FAIR Planning Studio",
        "function": fair_data_management_workbench,
        "record_id": "asset_id",
    },
    "research_interim_monitoring_safety": {
        "title": "Data Monitoring, Interim Review & Safety Studio",
        "function": interim_monitoring_safety_workbench,
        "record_id": "event_id",
    },
    "research_publication_dissemination": {
        "title": "Publication, Dissemination & Knowledge Translation Studio",
        "function": publication_dissemination_workbench,
        "record_id": "output_id",
    },
}

# ---------------------------------------------------------------------------
# Step 147 operational lifecycle enrichments
# ---------------------------------------------------------------------------


def _optional_text(frame: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="object")
    return _text(frame[column])


def _optional_bool(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="bool")
    return _bool(frame[column])


def _optional_numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return _numeric(frame[column], default)


def _optional_date(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame[column], errors="coerce", utc=True)


def _append_issues(existing: pd.DataFrame, rows: list[dict[str, Any]], id_column: str) -> pd.DataFrame:
    columns = [id_column, "severity", "issue", "action"]
    extra = pd.DataFrame(rows, columns=columns)
    if existing.empty:
        return extra
    if extra.empty:
        return existing.copy()
    return pd.concat([existing[columns], extra], ignore_index=True).drop_duplicates()


def _readability_metrics(text: str) -> tuple[float, float, float]:
    words = [token.strip(".,;:!?()[]{}\"'") for token in str(text).split() if token.strip()]
    sentences = max(1, sum(str(text).count(mark) for mark in ".!?"))
    if not words:
        return 0.0, 0.0, 0.0
    avg_word = sum(len(word) for word in words) / len(words)
    words_per_sentence = len(words) / sentences
    score = max(0.0, min(100.0, 100.0 - max(0.0, words_per_sentence - 18.0) * 2.0 - max(0.0, avg_word - 6.0) * 8.0))
    return round(score, 1), round(words_per_sentence, 1), round(avg_word, 1)


def _enhance_ethics_output(output: LifecycleOutput) -> LifecycleOutput:
    data = output.primary.copy()
    tables = dict(output.tables)
    summary = dict(output.summary)
    warnings = list(output.warnings)

    defaults: dict[str, Any] = {
        "consent_version": "",
        "consent_language": "",
        "effective_date": "",
        "approval_expiry": "",
        "participant_id": "",
        "consent_option": "",
        "consent_decision": "",
        "signed_date": "",
        "withdrawal_date": "",
        "reconsent_due_date": "",
        "submission_id": "",
        "submission_status": "",
        "submission_date": "",
        "approval_date": "",
        "query_id": "",
        "query_status": "",
        "query_due_date": "",
        "withdrawal_scope": "",
        "data_category": "",
        "data_destination": "",
    }
    for column, default in defaults.items():
        if column not in data.columns:
            data[column] = default
        data[column] = _text(data[column])

    readability = data["requirement"].map(_readability_metrics)
    data["readability_score"] = readability.map(lambda value: value[0])
    data["words_per_sentence"] = readability.map(lambda value: value[1])
    data["average_word_length"] = readability.map(lambda value: value[2])
    data["effective_date_parsed"] = _optional_date(data, "effective_date")
    data["approval_expiry_parsed"] = _optional_date(data, "approval_expiry")
    data["reconsent_due_parsed"] = _optional_date(data, "reconsent_due_date")
    data["query_due_parsed"] = _optional_date(data, "query_due_date")
    now = pd.Timestamp.utcnow()
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    data["reconsent_due"] = data["reconsent_due_parsed"].notna() & (data["reconsent_due_parsed"] <= now + pd.Timedelta(days=30))
    data["approval_expiring"] = data["approval_expiry_parsed"].notna() & (data["approval_expiry_parsed"] <= now + pd.Timedelta(days=60))
    data["query_open"] = data["query_id"].ne("") & ~data["query_status"].str.lower().isin({"closed", "resolved", "approved"})
    data["query_overdue"] = data["query_open"] & data["query_due_parsed"].notna() & (data["query_due_parsed"] < now)

    consent_rows = data.loc[data["consent_required"] | data["domain"].str.lower().eq("consent")].copy()
    consent_registry = (
        consent_rows.groupby(["consent_version", "consent_language"], dropna=False)
        .agg(
            requirements=("item_id", "count"),
            approved_items=("readiness_score", lambda s: int((s == 100).sum())),
            mean_readiness=("readiness_score", "mean"),
            earliest_effective=("effective_date_parsed", "min"),
            latest_expiry=("approval_expiry_parsed", "max"),
        )
        .reset_index()
    )
    if not consent_registry.empty:
        consent_registry["mean_readiness"] = consent_registry["mean_readiness"].round(1)
        consent_registry["version_complete"] = consent_registry["approved_items"].eq(consent_registry["requirements"])

    participant_rows = data.loc[data["participant_id"].ne("") & data["consent_option"].ne("")].copy()
    if participant_rows.empty:
        consent_matrix = pd.DataFrame(columns=["participant_id", "consent_option", "consent_decision", "consent_version", "signed_date", "withdrawal_date"])
    else:
        consent_matrix = participant_rows[["participant_id", "consent_option", "consent_decision", "consent_version", "signed_date", "withdrawal_date"]].drop_duplicates()
        consent_matrix["decision_normalized"] = consent_matrix["consent_decision"].str.lower()
        consent_matrix["active_consent"] = consent_matrix["decision_normalized"].isin({"signed", "accepted", "consented", "yes"}) & consent_matrix["withdrawal_date"].eq("")

    reconsent_schedule = data.loc[data["reconsent_due_parsed"].notna(), ["item_id", "consent_version", "vulnerable_group", "reconsent_due_parsed", "owner", "status"]].copy()
    if not reconsent_schedule.empty:
        reconsent_schedule["days_to_due"] = (reconsent_schedule["reconsent_due_parsed"] - now).dt.days
        reconsent_schedule["urgency"] = pd.cut(
            reconsent_schedule["days_to_due"],
            bins=[-10**9, -1, 7, 30, 10**9],
            labels=["Overdue", "Within 7 days", "Within 30 days", "Later"],
        ).astype(str)

    submissions = data.loc[data["submission_id"].ne("")].copy()
    if submissions.empty:
        submission_summary = pd.DataFrame(columns=["submission_id", "submission_status", "items", "open_queries", "readiness", "submission_date", "approval_date"])
    else:
        submission_summary = submissions.groupby(["submission_id", "submission_status"], dropna=False).agg(
            items=("item_id", "count"),
            open_queries=("query_open", "sum"),
            readiness=("readiness_score", "mean"),
            submission_date=("submission_date", "max"),
            approval_date=("approval_date", "max"),
        ).reset_index()
        submission_summary["readiness"] = submission_summary["readiness"].round(1)

    query_tracker = data.loc[data["query_id"].ne(""), ["query_id", "item_id", "submission_id", "query_status", "query_due_parsed", "query_open", "query_overdue", "owner"]].drop_duplicates()
    privacy_flow = data.loc[data["privacy_sensitive"], ["item_id", "data_category", "data_destination", "owner", "status", "risk_level"]].copy()
    privacy_flow["data_category"] = privacy_flow["data_category"].replace("", "Unspecified category")
    privacy_flow["data_destination"] = privacy_flow["data_destination"].replace("", "Unspecified destination")
    withdrawal_impact = data.loc[data["withdrawal_scope"].ne(""), ["item_id", "withdrawal_scope", "data_category", "data_destination", "owner", "status"]].copy()
    readability_summary = data.groupby("domain", dropna=False).agg(
        requirements=("item_id", "count"),
        mean_readability=("readability_score", "mean"),
        long_sentence_items=("words_per_sentence", lambda s: int((s > 25).sum())),
        technical_word_items=("average_word_length", lambda s: int((s > 7).sum())),
    ).reset_index()
    readability_summary["mean_readability"] = readability_summary["mean_readability"].round(1)

    impacts: list[dict[str, Any]] = []
    if data["reconsent_due"].any():
        impacts.append({"trigger": "Re-consent due", "source_module": "Ethics & Consent", "affected_module": "Study Protocol Designer", "required_action": "Review amendment and participant-facing materials", "priority": "High"})
    if data["privacy_sensitive"].any() and (data["data_destination"].eq("").any() or data["data_category"].eq("").any()):
        impacts.append({"trigger": "Incomplete privacy flow", "source_module": "Ethics & Consent", "affected_module": "FAIR Data Management", "required_action": "Complete data classification and transfer plan", "priority": "High"})
    if data["withdrawal_scope"].ne("").any():
        impacts.append({"trigger": "Withdrawal conditions defined", "source_module": "Ethics & Consent", "affected_module": "CRF & Data Management", "required_action": "Implement withdrawal and specimen-disposition rules", "priority": "Medium"})
    impact_rules = pd.DataFrame(impacts, columns=["trigger", "source_module", "affected_module", "required_action", "priority"])

    extra_issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        if float(row["readability_score"]) < 55 and bool(row["consent_required"]):
            extra_issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "Participant-facing requirement may be difficult to read", "action": "Simplify language and perform participant readability review."})
        if bool(row["query_overdue"]):
            extra_issues.append({"item_id": row["item_id"], "severity": "Critical", "issue": "Ethics committee query is overdue", "action": "Escalate the response and record the resolution."})
        if bool(row["reconsent_due"]):
            extra_issues.append({"item_id": row["item_id"], "severity": "Critical", "issue": "Re-consent is due or approaching", "action": "Prepare approved re-consent materials and participant tracking."})
        if bool(row["privacy_sensitive"]) and (row["data_category"] == "" or row["data_destination"] == ""):
            extra_issues.append({"item_id": row["item_id"], "severity": "Major", "issue": "Privacy-sensitive item lacks a complete data flow", "action": "Record data category, destination and transfer safeguards."})
    tables["issues"] = _append_issues(tables.get("issues", pd.DataFrame()), extra_issues, "item_id")
    tables.update({
        "consent_version_registry": consent_registry,
        "participant_consent_matrix": consent_matrix,
        "reconsent_schedule": reconsent_schedule,
        "ethics_submission_summary": submission_summary,
        "committee_query_tracker": query_tracker,
        "privacy_data_flow": privacy_flow,
        "withdrawal_impact": withdrawal_impact,
        "readability_summary": readability_summary,
        "cross_module_impacts": impact_rules,
    })
    operational_components = [
        int(not consent_registry.empty), int(not reconsent_schedule.empty), int(not submission_summary.empty),
        int(not query_tracker.empty), int(not privacy_flow.empty), int(not readability_summary.empty),
    ]
    summary.update({
        "consent_versions": int(consent_registry.loc[consent_registry["consent_version"].ne(""), "consent_version"].nunique()) if not consent_registry.empty else 0,
        "participant_consent_records": int(len(consent_matrix)),
        "reconsent_due_items": int(data["reconsent_due"].sum()),
        "open_committee_queries": int(data["query_open"].sum()),
        "overdue_committee_queries": int(data["query_overdue"].sum()),
        "mean_readability_score": round(float(data["readability_score"].mean()), 1),
        "operational_coverage_percent": round(100 * sum(operational_components) / len(operational_components), 1),
    })
    if summary["overdue_committee_queries"]:
        warnings.append("Overdue ethics committee queries require escalation.")
    if summary["reconsent_due_items"]:
        warnings.append("Re-consent actions are due or approaching.")
    return LifecycleOutput(output.module_key, data, tables, summary, tuple(dict.fromkeys(warnings)))


def _enhance_fair_output(output: LifecycleOutput) -> LifecycleOutput:
    data = output.primary.copy()
    tables = dict(output.tables)
    summary = dict(output.summary)
    warnings = list(output.warnings)

    text_defaults = {
        "checksum": "", "checksum_algorithm": "SHA-256", "schema_name": "", "deposit_status": "Not started",
        "access_request_status": "Not applicable", "legal_hold": "No", "destruction_date": "", "embargo_until": "",
        "last_restore_test": "", "data_dictionary_status": "", "provenance_status": "", "consent_restriction": "",
        "repository_policy": "", "storage_location": "", "backup_location": "",
    }
    for column, default in text_defaults.items():
        if column not in data.columns:
            data[column] = default
        data[column] = _text(data[column])
    numeric_defaults = {
        "file_size_mb": 0.0, "monthly_growth_mb": 0.0, "schema_required_fields": 0.0,
        "schema_present_fields": 0.0, "restore_rto_hours": 0.0, "restore_rpo_hours": 0.0,
    }
    for column, default in numeric_defaults.items():
        data[column] = _optional_numeric(data, column, default)
    bool_defaults = {"checksum_verified": False, "format_validated": False, "data_dictionary_complete": False, "provenance_complete": False}
    for column, default in bool_defaults.items():
        data[column] = _optional_bool(data, column, default)

    if (data["file_size_mb"] < 0).any() or (data["monthly_growth_mb"] < 0).any():
        raise ValueError("File size and monthly growth values must be zero or greater.")
    if (data["schema_required_fields"] < 0).any() or (data["schema_present_fields"] < 0).any():
        raise ValueError("Schema field counts must be zero or greater.")
    if (data["schema_present_fields"] > data["schema_required_fields"]).any() and data["schema_required_fields"].gt(0).any():
        raise ValueError("Schema present fields cannot exceed required fields.")

    required = data["schema_required_fields"].replace(0, np.nan)
    data["metadata_completeness"] = (100 * data["schema_present_fields"] / required).fillna(data["metadata_standard"].ne("").astype(float) * 100).clip(0, 100).round(1)
    data["technical_integrity"] = (
        data["checksum"].ne("").astype(float) * 25
        + data["checksum_verified"].astype(float) * 25
        + data["format_validated"].astype(float) * 20
        + data["data_dictionary_complete"].astype(float) * 15
        + data["provenance_complete"].astype(float) * 15
    ).round(1)
    data["access_governance"] = (
        data["access_level"].ne("").astype(float) * 25
        + data["licence"].ne("").astype(float) * 25
        + data["owner"].ne("").astype(float) * 20
        + data["consent_restriction"].ne("").astype(float) * 15
        + data["repository_policy"].ne("").astype(float) * 15
    ).round(1)
    data["preservation_readiness"] = (
        data["backup_copies"].clip(0, 3) / 3 * 35
        + data["retention_years"].gt(0).astype(float) * 20
        + data["repository"].ne("").astype(float) * 20
        + data["last_restore_test"].ne("").astype(float) * 15
        + data["encryption"].str.lower().isin({"yes", "true", "aes-256", "at rest", "encrypted"}).astype(float) * 10
    ).round(1)
    data["reproducibility_readiness"] = (
        data["data_dictionary_complete"].astype(float) * 30
        + data["provenance_complete"].astype(float) * 30
        + data["persistent_id"].ne("").astype(float) * 20
        + data["checksum_verified"].astype(float) * 20
    ).round(1)
    data["operational_data_score"] = data[["fair_score", "metadata_completeness", "technical_integrity", "access_governance", "preservation_readiness", "reproducibility_readiness"]].mean(axis=1).round(1)
    data["integrity_state"] = np.select(
        [data["checksum"].eq(""), ~data["checksum_verified"], ~data["format_validated"]],
        ["Checksum missing", "Checksum unverified", "Format unvalidated"],
        default="Verified",
    )
    data["deposit_ready"] = (
        data["repository"].ne("") & data["metadata_standard"].ne("") & data["licence"].ne("")
        & data["checksum_verified"] & data["data_dictionary_complete"] & data["provenance_complete"]
    )
    data["destruction_date_parsed"] = _optional_date(data, "destruction_date")
    data["embargo_until_parsed"] = _optional_date(data, "embargo_until")
    data["last_restore_test_parsed"] = _optional_date(data, "last_restore_test")
    now = pd.Timestamp.utcnow()
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    data["restore_test_age_days"] = (now - data["last_restore_test_parsed"]).dt.days
    data["restore_test_overdue"] = data["last_restore_test_parsed"].isna() | data["restore_test_age_days"].gt(365)

    operational_dimensions = pd.DataFrame([
        {"dimension": "Metadata completeness", "score": round(float(data["metadata_completeness"].mean()), 1)},
        {"dimension": "Technical integrity", "score": round(float(data["technical_integrity"].mean()), 1)},
        {"dimension": "Access governance", "score": round(float(data["access_governance"].mean()), 1)},
        {"dimension": "Preservation readiness", "score": round(float(data["preservation_readiness"].mean()), 1)},
        {"dimension": "Reproducibility", "score": round(float(data["reproducibility_readiness"].mean()), 1)},
        {"dimension": "Repository readiness", "score": round(100 * float(data["deposit_ready"].mean()), 1)},
        {"dimension": "Restore verification", "score": round(100 * float((~data["restore_test_overdue"]).mean()), 1)},
    ])
    file_integrity = data[["asset_id", "data_type", "format", "checksum_algorithm", "checksum", "checksum_verified", "format_validated", "integrity_state", "operational_data_score"]].copy()
    repository_readiness = data.groupby(["repository", "deposit_status"], dropna=False).agg(
        assets=("asset_id", "count"),
        ready_assets=("deposit_ready", "sum"),
        mean_operational_score=("operational_data_score", "mean"),
        total_size_mb=("file_size_mb", "sum"),
    ).reset_index()
    repository_readiness["mean_operational_score"] = repository_readiness["mean_operational_score"].round(1)
    repository_readiness["readiness_percent"] = (100 * repository_readiness["ready_assets"] / repository_readiness["assets"].clip(lower=1)).round(1)

    storage_rows: list[dict[str, Any]] = []
    for month in range(13):
        for _, row in data.iterrows():
            storage_rows.append({
                "month": month,
                "asset_id": row["asset_id"],
                "projected_size_mb": round(float(row["file_size_mb"] + month * row["monthly_growth_mb"]), 3),
                "replicated_storage_mb": round(float((row["file_size_mb"] + month * row["monthly_growth_mb"]) * max(int(row["backup_copies"]), 1)), 3),
            })
    storage_forecast = pd.DataFrame(storage_rows)
    storage_summary = storage_forecast.groupby("month", as_index=False).agg(projected_size_mb=("projected_size_mb", "sum"), replicated_storage_mb=("replicated_storage_mb", "sum"))

    access_matrix = data[["asset_id", "access_level", "access_request_status", "consent_restriction", "licence", "owner"]].copy()
    retention_calendar = data.loc[data["destruction_date_parsed"].notna(), ["asset_id", "data_type", "retention_years", "destruction_date_parsed", "legal_hold", "owner"]].copy()
    if not retention_calendar.empty:
        retention_calendar["days_to_action"] = (retention_calendar["destruction_date_parsed"] - now).dt.days
        retention_calendar["action_state"] = np.where(retention_calendar["legal_hold"].str.lower().isin({"yes", "true", "active"}), "Legal hold", np.where(retention_calendar["days_to_action"] < 0, "Overdue", "Scheduled"))

    licence_compatibility = data[["asset_id", "licence", "consent_restriction", "access_level", "repository_policy"]].copy()
    licence_compatibility["compatibility_state"] = np.select(
        [licence_compatibility["licence"].eq(""), licence_compatibility["consent_restriction"].ne("") & licence_compatibility["access_level"].str.lower().eq("open")],
        ["Licence missing", "Review consent vs open access"],
        default="No obvious conflict",
    )

    impacts = []
    if (~data["deposit_ready"]).any():
        impacts.append({"trigger": "Repository package incomplete", "source_module": "FAIR Data Management", "affected_module": "Publication & Dissemination", "required_action": "Resolve data/code availability dependencies", "priority": "High"})
    if data["consent_restriction"].ne("").any():
        impacts.append({"trigger": "Consent-limited data use", "source_module": "FAIR Data Management", "affected_module": "Ethics & Consent", "required_action": "Verify repository and access conditions match participant permissions", "priority": "High"})
    if data["restore_test_overdue"].any():
        impacts.append({"trigger": "Restore verification overdue", "source_module": "FAIR Data Management", "affected_module": "Study Closeout", "required_action": "Run and document a recovery test", "priority": "Medium"})
    impact_rules = pd.DataFrame(impacts, columns=["trigger", "source_module", "affected_module", "required_action", "priority"])

    extra_issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        if row["checksum"] == "":
            extra_issues.append({"asset_id": row["asset_id"], "severity": "Major", "issue": "File checksum is missing", "action": "Generate and verify a SHA-256 checksum."})
        elif not bool(row["checksum_verified"]):
            extra_issues.append({"asset_id": row["asset_id"], "severity": "Major", "issue": "Checksum has not been verified", "action": "Verify file integrity before analysis or deposition."})
        if not bool(row["data_dictionary_complete"]):
            extra_issues.append({"asset_id": row["asset_id"], "severity": "Major", "issue": "Data dictionary is incomplete", "action": "Complete variable definitions, units and controlled terminology."})
        if bool(row["restore_test_overdue"]):
            extra_issues.append({"asset_id": row["asset_id"], "severity": "Major", "issue": "Backup restore test is missing or overdue", "action": "Run a documented recovery drill."})
        if not bool(row["deposit_ready"]):
            extra_issues.append({"asset_id": row["asset_id"], "severity": "Minor", "issue": "Repository deposit package is incomplete", "action": "Complete metadata, licence, checksums, dictionary and provenance."})
    tables["issues"] = _append_issues(tables.get("issues", pd.DataFrame()), extra_issues, "asset_id")
    tables.update({
        "operational_dimensions": operational_dimensions,
        "file_integrity": file_integrity,
        "repository_readiness": repository_readiness,
        "storage_forecast": storage_forecast,
        "storage_summary": storage_summary,
        "access_governance_matrix": access_matrix,
        "retention_calendar": retention_calendar,
        "licence_compatibility": licence_compatibility,
        "cross_module_impacts": impact_rules,
    })
    summary.update({
        "overall_operational_data_score": round(float(data["operational_data_score"].mean()), 1),
        "checksum_verified_percent": round(100 * float(data["checksum_verified"].mean()), 1),
        "deposit_ready_percent": round(100 * float(data["deposit_ready"].mean()), 1),
        "restore_test_current_percent": round(100 * float((~data["restore_test_overdue"]).mean()), 1),
        "projected_12_month_storage_mb": round(float(storage_summary.loc[storage_summary["month"] == 12, "replicated_storage_mb"].sum()), 2),
        "licence_conflicts": int(licence_compatibility["compatibility_state"].ne("No obvious conflict").sum()),
    })
    if summary["checksum_verified_percent"] < 100:
        warnings.append("Some data assets do not have verified checksums.")
    if summary["deposit_ready_percent"] < 100:
        warnings.append("Some repository deposit packages remain incomplete.")
    return LifecycleOutput(output.module_key, data, tables, summary, tuple(dict.fromkeys(warnings)))


def _enhance_safety_output(output: LifecycleOutput) -> LifecycleOutput:
    data = output.primary.copy()
    tables = dict(output.tables)
    summary = dict(output.summary)
    warnings = list(output.warnings)

    text_defaults = {
        "site_id": "Unspecified", "system_organ_class": "Unclassified", "preferred_term": "",
        "expectedness": "Unknown", "action_taken": "None recorded", "outcome": "Unknown", "awareness_date": "",
        "report_due_date": "", "submitted_date": "", "dose_level": "", "lab_test": "", "baseline_grade": "",
        "worst_grade": "", "monitoring_committee_action": "", "data_access_state": "Blinded",
    }
    for column, default in text_defaults.items():
        if column not in data.columns:
            data[column] = default
        data[column] = _text(data[column])
    for column, default in {"person_time_days": 0.0, "followup_days": 0.0, "information_fraction": np.nan, "efficacy_z": np.nan, "efficacy_boundary": np.nan, "futility_boundary": np.nan, "conditional_power": np.nan}.items():
        if column not in data.columns:
            data[column] = default
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["treatment_emergent"] = _optional_bool(data, "treatment_emergent", True)
    data["adverse_event_of_special_interest"] = _optional_bool(data, "adverse_event_of_special_interest", False)
    data["preferred_term"] = data["preferred_term"].where(data["preferred_term"].ne(""), data["event_type"])
    data["person_time_days"] = data["person_time_days"].fillna(0.0)
    data["followup_days"] = data["followup_days"].fillna(data["event_day"].clip(lower=1))
    if (data["person_time_days"] < 0).any() or (data["followup_days"] < 0).any():
        raise ValueError("Person-time and follow-up values must be zero or greater.")
    data["effective_person_time_days"] = np.where(data["person_time_days"] > 0, data["person_time_days"], data["followup_days"].clip(lower=1))
    data["awareness_date_parsed"] = _optional_date(data, "awareness_date")
    data["report_due_parsed"] = _optional_date(data, "report_due_date")
    data["submitted_date_parsed"] = _optional_date(data, "submitted_date")
    calculated_due = data["awareness_date_parsed"] + pd.to_timedelta(np.where(data["serious"] | data["reportable"], 7, 30), unit="D")
    data["effective_report_due"] = data["report_due_parsed"].where(data["report_due_parsed"].notna(), calculated_due)
    now = pd.Timestamp.utcnow()
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    data["report_late"] = data["effective_report_due"].notna() & data["submitted_date_parsed"].isna() & (data["effective_report_due"] < now)
    data["report_delay_days"] = (data["submitted_date_parsed"].fillna(now) - data["effective_report_due"]).dt.days.clip(lower=0)

    participant_exposure = data.groupby(["arm", "participant_id"], dropna=False).agg(
        person_time_days=("effective_person_time_days", "max"),
        followup_days=("followup_days", "max"),
        first_event_day=("event_day", "min"),
        events=("event_id", "count"),
        serious_events=("serious", "sum"),
        event_observed=("event_id", lambda s: True),
    ).reset_index()
    exposure_by_arm = participant_exposure.groupby("arm", dropna=False).agg(
        participants=("participant_id", "nunique"),
        person_time_days=("person_time_days", "sum"),
        participants_with_events=("event_observed", "sum"),
        events=("events", "sum"),
        serious_events=("serious_events", "sum"),
    ).reset_index()
    exposure_by_arm["person_years"] = exposure_by_arm["person_time_days"] / 365.25
    exposure_by_arm["events_per_100_person_years"] = (100 * exposure_by_arm["events"] / exposure_by_arm["person_years"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)
    exposure_by_arm["serious_events_per_100_person_years"] = (100 * exposure_by_arm["serious_events"] / exposure_by_arm["person_years"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)

    recurrent = participant_exposure[["arm", "participant_id", "events", "serious_events", "followup_days"]].copy()
    recurrent["recurrent_event_burden"] = np.select([recurrent["events"].ge(3), recurrent["events"].eq(2)], ["High", "Moderate"], default="Single event")
    first_event = participant_exposure[["arm", "participant_id", "first_event_day", "followup_days", "event_observed"]].copy().sort_values(["arm", "first_event_day"])
    first_event["at_risk_rank"] = first_event.groupby("arm").cumcount() + 1
    first_event["cumulative_event_fraction"] = first_event.groupby("arm")["event_observed"].cumsum() / first_event.groupby("arm")["participant_id"].transform("count")

    organ_severity = data.groupby(["system_organ_class", "severity"], dropna=False).agg(events=("event_id", "count"), serious_events=("serious", "sum"), unresolved=("resolved", lambda s: int((~s).sum()))).reset_index()
    participant_timeline = data[["participant_id", "arm", "event_id", "event_day", "preferred_term", "severity", "serious", "resolved", "dose_level", "action_taken", "outcome"]].sort_values(["participant_id", "event_day"])
    deadline_monitor = data[["event_id", "participant_id", "site_id", "serious", "reportable", "awareness_date_parsed", "effective_report_due", "submitted_date_parsed", "report_late", "report_delay_days"]].copy()

    site_summary = data.groupby("site_id", dropna=False).agg(
        participants=("participant_id", "nunique"),
        events=("event_id", "count"),
        serious_events=("serious", "sum"),
        late_reports=("report_late", "sum"),
        unresolved_events=("resolved", lambda s: int((~s).sum())),
        mean_followup_days=("followup_days", "mean"),
    ).reset_index()
    site_summary["events_per_participant"] = (site_summary["events"] / site_summary["participants"].clip(lower=1)).round(2)
    median_rate = float(site_summary["events_per_participant"].median()) if not site_summary.empty else 0.0
    site_summary["signal_state"] = np.select(
        [site_summary["late_reports"].gt(0), site_summary["events_per_participant"].gt(max(1.5 * median_rate, median_rate + 1)), site_summary["events_per_participant"].lt(0.25 * median_rate)],
        ["Late reporting", "High reporting rate", "Possible under-reporting"],
        default="Within review range",
    )

    lab_rows = data.loc[data["lab_test"].ne(""), ["participant_id", "arm", "lab_test", "baseline_grade", "worst_grade", "event_day"]].copy()
    if lab_rows.empty:
        lab_shift = pd.DataFrame(columns=["lab_test", "baseline_grade", "worst_grade", "participants"])
    else:
        lab_shift = lab_rows.groupby(["lab_test", "baseline_grade", "worst_grade"], dropna=False)["participant_id"].nunique().reset_index(name="participants")

    interim_columns = ["arm", "information_fraction", "efficacy_z", "efficacy_boundary", "futility_boundary", "conditional_power"]
    interim = data[interim_columns].dropna(how="all", subset=interim_columns[1:]).drop_duplicates().copy()
    if not interim.empty:
        interim["interim_decision_signal"] = np.select(
            [interim["efficacy_z"].notna() & interim["efficacy_boundary"].notna() & interim["efficacy_z"].ge(interim["efficacy_boundary"]),
             interim["efficacy_z"].notna() & interim["futility_boundary"].notna() & interim["efficacy_z"].le(interim["futility_boundary"]),
             interim["conditional_power"].notna() & interim["conditional_power"].lt(0.2)],
            ["Efficacy boundary crossed", "Futility boundary crossed", "Low conditional power review"],
            default="Continue prespecified review",
        )

    arm_summary = tables.get("arm_summary", pd.DataFrame()).copy()
    benefit_risk = arm_summary.merge(exposure_by_arm[["arm", "events_per_100_person_years", "serious_events_per_100_person_years"]], on="arm", how="left")
    if not benefit_risk.empty:
        benefit_risk["efficacy_signal"] = benefit_risk["arm"].map(interim.groupby("arm")["efficacy_z"].max() if not interim.empty else {}).fillna(0.0)
        benefit_risk["benefit_risk_index"] = (benefit_risk["efficacy_signal"] - benefit_risk["serious_events_per_100_person_years"] / 100).round(3)

    impacts = []
    if data["requires_immediate_review"].any() or data["report_late"].any():
        impacts.append({"trigger": "Safety escalation", "source_module": "Interim Monitoring & Safety", "affected_module": "Ethics & Consent", "required_action": "Assess participant information and re-consent implications", "priority": "Critical"})
        impacts.append({"trigger": "Safety escalation", "source_module": "Interim Monitoring & Safety", "affected_module": "Study Protocol Designer", "required_action": "Assess protocol amendment and monitoring changes", "priority": "Critical"})
    if not interim.empty and interim["interim_decision_signal"].ne("Continue prespecified review").any():
        impacts.append({"trigger": "Interim boundary signal", "source_module": "Interim Monitoring & Safety", "affected_module": "Statistical Analysis Plan", "required_action": "Document prespecified decision process and alpha implications", "priority": "High"})
    impact_rules = pd.DataFrame(impacts, columns=["trigger", "source_module", "affected_module", "required_action", "priority"])

    extra_issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        if bool(row["report_late"]):
            extra_issues.append({"event_id": row["event_id"], "severity": "Critical", "issue": "Safety reporting deadline is overdue", "action": "Escalate immediately and document the reporting response."})
        if row["system_organ_class"] == "Unclassified":
            extra_issues.append({"event_id": row["event_id"], "severity": "Major", "issue": "System organ class is missing", "action": "Code the event using the study-controlled safety terminology."})
        if row["expectedness"].lower() == "unknown" and bool(row["serious"]):
            extra_issues.append({"event_id": row["event_id"], "severity": "Major", "issue": "Serious event expectedness is unknown", "action": "Complete expectedness assessment before expedited reporting review."})
    tables["issues"] = _append_issues(tables.get("issues", pd.DataFrame()), extra_issues, "event_id")
    tables.update({
        "exposure_adjusted_rates": exposure_by_arm,
        "time_to_first_event": first_event,
        "recurrent_event_summary": recurrent,
        "organ_system_severity": organ_severity,
        "participant_safety_timeline": participant_timeline,
        "reporting_deadlines": deadline_monitor,
        "site_signal_summary": site_summary,
        "laboratory_shift_summary": lab_shift,
        "interim_boundary_review": interim,
        "benefit_risk_summary": benefit_risk,
        "cross_module_impacts": impact_rules,
    })
    summary.update({
        "late_safety_reports": int(data["report_late"].sum()),
        "person_years_observed": round(float(exposure_by_arm["person_years"].sum()), 3),
        "recurrent_event_participants": int((recurrent["events"] > 1).sum()),
        "sites_with_signals": int(site_summary["signal_state"].ne("Within review range").sum()),
        "coded_organ_system_percent": round(100 * float(data["system_organ_class"].ne("Unclassified").mean()), 1),
        "interim_reviews_configured": int(len(interim)),
    })
    if summary["late_safety_reports"]:
        warnings.append("One or more safety reporting deadlines are overdue.")
    if summary["sites_with_signals"]:
        warnings.append("Site-level reporting patterns require review.")
    return LifecycleOutput(output.module_key, data, tables, summary, tuple(dict.fromkeys(warnings)))


def _enhance_publication_output(output: LifecycleOutput) -> LifecycleOutput:
    data = output.primary.copy()
    tables = dict(output.tables)
    summary = dict(output.summary)
    warnings = list(output.warnings)

    text_defaults = {
        "manuscript_section": "", "section_status": "", "claim_id": "", "source_analysis_id": "",
        "figure_table_id": "", "evidence_status": "", "guideline": "", "reporting_item": "",
        "reporting_item_status": "", "author": "", "contribution_role": "", "journal": "",
        "review_comment_id": "", "review_status": "", "manuscript_version": "", "planned_endpoint": "",
        "reported_endpoint": "", "submission_status": "", "preprint_status": "", "embargo_date": "",
    }
    for column, default in text_defaults.items():
        if column not in data.columns:
            data[column] = default
        data[column] = _text(data[column])
    for column, default in {"section_word_count": 0.0, "target_word_count": 0.0, "journal_scope_fit": 0.0, "open_access_fee": 0.0}.items():
        data[column] = _optional_numeric(data, column, default)
    for column, default in {"author_approved": False, "conflict_declared": False, "figure_accessibility_complete": False}.items():
        data[column] = _optional_bool(data, column, default)
    if (data["section_word_count"] < 0).any() or (data["target_word_count"] < 0).any() or (data["open_access_fee"] < 0).any():
        raise ValueError("Word counts and open-access fees must be zero or greater.")
    if ((data["journal_scope_fit"] < 0) | (data["journal_scope_fit"] > 100)).any():
        raise ValueError("Journal scope-fit scores must be between 0 and 100.")

    section_rows = data.loc[data["manuscript_section"].ne("")].copy()
    if section_rows.empty:
        manuscript_progress = pd.DataFrame(columns=["manuscript_section", "items", "completed_items", "word_count", "target_word_count", "completion_percent"])
    else:
        manuscript_progress = section_rows.groupby("manuscript_section", dropna=False).agg(
            items=("output_id", "count"),
            completed_items=("section_status", lambda s: int(s.str.lower().isin({"complete", "approved", "final"}).sum())),
            word_count=("section_word_count", "sum"),
            target_word_count=("target_word_count", "sum"),
        ).reset_index()
        manuscript_progress["completion_percent"] = np.where(
            manuscript_progress["target_word_count"] > 0,
            100 * manuscript_progress["word_count"] / manuscript_progress["target_word_count"],
            100 * manuscript_progress["completed_items"] / manuscript_progress["items"].clip(lower=1),
        ).clip(0, 100).round(1)

    claims = data.loc[data["claim_id"].ne(""), ["claim_id", "title", "source_analysis_id", "figure_table_id", "evidence_status", "planned_endpoint", "reported_endpoint", "owner"]].drop_duplicates().copy()
    if not claims.empty:
        claims["traceability_complete"] = claims[["source_analysis_id", "figure_table_id", "evidence_status"]].ne("").all(axis=1)
        claims["endpoint_changed"] = claims["planned_endpoint"].ne("") & claims["reported_endpoint"].ne("") & claims["planned_endpoint"].str.casefold().ne(claims["reported_endpoint"].str.casefold())

    guideline_rows = data.loc[data["reporting_item"].ne("")].copy()
    if guideline_rows.empty:
        reporting_checklist = pd.DataFrame(columns=["guideline", "reporting_item", "reporting_item_status", "output_id"])
        guideline_summary = pd.DataFrame(columns=["guideline", "items", "complete_items", "completion_percent"])
    else:
        reporting_checklist = guideline_rows[["guideline", "reporting_item", "reporting_item_status", "output_id", "manuscript_section"]].drop_duplicates()
        guideline_summary = reporting_checklist.groupby("guideline", dropna=False).agg(
            items=("reporting_item", "count"),
            complete_items=("reporting_item_status", lambda s: int(s.str.lower().isin({"complete", "addressed", "approved"}).sum())),
        ).reset_index()
        guideline_summary["completion_percent"] = (100 * guideline_summary["complete_items"] / guideline_summary["items"].clip(lower=1)).round(1)

    author_rows = data.loc[data["author"].ne("")].copy()
    if author_rows.empty:
        authorship = pd.DataFrame(columns=["author", "contribution_role", "author_approved", "conflict_declared", "outputs"])
    else:
        authorship = author_rows.groupby(["author", "contribution_role"], dropna=False).agg(
            author_approved=("author_approved", "all"),
            conflict_declared=("conflict_declared", "all"),
            outputs=("output_id", "nunique"),
        ).reset_index()

    journal_rows = data.loc[data["journal"].ne("")].copy()
    if journal_rows.empty:
        journal_selection = pd.DataFrame(columns=["journal", "scope_fit", "open_access_fee", "outputs", "open_access_planned", "selection_state"])
    else:
        journal_selection = journal_rows.groupby("journal", dropna=False).agg(
            scope_fit=("journal_scope_fit", "mean"),
            open_access_fee=("open_access_fee", "max"),
            outputs=("output_id", "nunique"),
            open_access_planned=("open_access", "any"),
        ).reset_index()
        journal_selection["scope_fit"] = journal_selection["scope_fit"].round(1)
        journal_selection["selection_state"] = np.select([journal_selection["scope_fit"].ge(80), journal_selection["scope_fit"].ge(60)], ["Strong fit", "Review fit"], default="Weak or unscored fit")

    figure_inventory = data.loc[data["figure_table_id"].ne(""), ["figure_table_id", "title", "source_analysis_id", "evidence_status", "figure_accessibility_complete", "status", "owner"]].drop_duplicates()
    review_rows = data.loc[data["review_comment_id"].ne("")].copy()
    if review_rows.empty:
        peer_review = pd.DataFrame(columns=["review_comment_id", "output_id", "review_status", "owner", "title"])
        review_burndown = pd.DataFrame(columns=["review_status", "comments"])
    else:
        peer_review = review_rows[["review_comment_id", "output_id", "review_status", "owner", "title"]].drop_duplicates()
        review_burndown = peer_review.groupby("review_status", dropna=False).size().reset_index(name="comments")

    version_rows = data.loc[data["manuscript_version"].ne(""), ["manuscript_version", "output_id", "status", "target_date_parsed", "submission_status", "preprint_status", "embargo_date"]].drop_duplicates()
    deviations = claims.loc[claims.get("endpoint_changed", pd.Series(False, index=claims.index))] if not claims.empty else pd.DataFrame(columns=claims.columns)
    if not deviations.empty:
        deviations = deviations[["claim_id", "planned_endpoint", "reported_endpoint", "source_analysis_id", "evidence_status"]].copy()
        deviations["deviation_state"] = "Endpoint changed — justification required"

    audience_channel = data.groupby(["audience", "channel"], dropna=False).agg(outputs=("output_id", "count"), completed=("completed", "sum"), readiness=("readiness_score", "mean")).reset_index()
    audience_channel["readiness"] = audience_channel["readiness"].round(1)

    impacts = []
    if not claims.empty and (~claims["traceability_complete"]).any():
        impacts.append({"trigger": "Unlinked publication claim", "source_module": "Publication & Dissemination", "affected_module": "Statistical Analysis Plan", "required_action": "Link claim to analysis, output and evidence status", "priority": "High"})
    if not deviations.empty:
        impacts.append({"trigger": "Protocol-to-publication deviation", "source_module": "Publication & Dissemination", "affected_module": "Pre-Registration & Reproducibility", "required_action": "Document and approve endpoint or analysis change", "priority": "Critical"})
    if (data["data_statement"] & ~data["code_available"]).any():
        impacts.append({"trigger": "Data/code availability mismatch", "source_module": "Publication & Dissemination", "affected_module": "FAIR Data Management", "required_action": "Resolve repository, licence and code-release dependencies", "priority": "Medium"})
    impact_rules = pd.DataFrame(impacts, columns=["trigger", "source_module", "affected_module", "required_action", "priority"])

    extra_issues: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        if row["claim_id"] and (not row["source_analysis_id"] or not row["evidence_status"]):
            extra_issues.append({"output_id": row["output_id"], "severity": "Critical", "issue": "Claim lacks complete evidence traceability", "action": "Link the claim to an analysis, figure/table and evidence status."})
        if row["author"] and (not bool(row["author_approved"]) or not bool(row["conflict_declared"])):
            extra_issues.append({"output_id": row["output_id"], "severity": "Major", "issue": "Authorship approval or conflict declaration is incomplete", "action": "Complete contributor approval and conflict-of-interest records."})
        if row["figure_table_id"] and not bool(row["figure_accessibility_complete"]):
            extra_issues.append({"output_id": row["output_id"], "severity": "Major", "issue": "Figure/table accessibility review is incomplete", "action": "Add accessible captions, alt text and source-data linkage."})
    tables["issues"] = _append_issues(tables.get("issues", pd.DataFrame()), extra_issues, "output_id")
    tables.update({
        "manuscript_progress": manuscript_progress,
        "claim_evidence_traceability": claims,
        "reporting_checklist": reporting_checklist,
        "reporting_guideline_summary": guideline_summary,
        "authorship_contributions": authorship,
        "journal_selection": journal_selection,
        "figure_table_inventory": figure_inventory,
        "peer_review_workspace": peer_review,
        "peer_review_burndown": review_burndown,
        "publication_version_lineage": version_rows,
        "protocol_publication_deviations": deviations,
        "audience_channel_matrix": audience_channel,
        "cross_module_impacts": impact_rules,
    })
    summary.update({
        "manuscript_sections": int(manuscript_progress["manuscript_section"].nunique()) if not manuscript_progress.empty else 0,
        "mean_manuscript_completion": round(float(manuscript_progress["completion_percent"].mean()), 1) if not manuscript_progress.empty else 0.0,
        "claims": int(len(claims)),
        "traceable_claim_percent": round(100 * float(claims["traceability_complete"].mean()), 1) if not claims.empty else 100.0,
        "reporting_guidelines": int(guideline_summary["guideline"].replace("", np.nan).nunique()) if not guideline_summary.empty else 0,
        "authors_pending_approval": int((~authorship["author_approved"]).sum()) if not authorship.empty else 0,
        "open_peer_review_comments": int((~peer_review["review_status"].str.lower().isin({"resolved", "closed", "accepted"})).sum()) if not peer_review.empty else 0,
        "protocol_publication_deviations": int(len(deviations)),
    })
    if summary["traceable_claim_percent"] < 100:
        warnings.append("Some manuscript claims are not fully linked to source analyses and evidence status.")
    if summary["protocol_publication_deviations"]:
        warnings.append("Protocol-to-publication deviations require documented justification.")
    return LifecycleOutput(output.module_key, data, tables, summary, tuple(dict.fromkeys(warnings)))
