from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict, deque
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

from .native_integrity import parse_scientific_bool


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    direct = {str(column).lower(): str(column) for column in frame.columns}
    normalized = {re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in direct:
            return direct[name.lower()]
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def _check(rows: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    rows.append({"check": name, "status": status, "detail": str(detail)})


def _metric(rows: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    rows.append({"metric": name, "value": value, "unit": unit})


def _autonomous_lab(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    step = _column(frame, "step_id", "protocol_step", "operation_id")
    predecessor = _column(frame, "predecessor", "depends_on", "parent_step")
    resource = _column(frame, "resource", "instrument", "device")
    slot = _column(frame, "deck_slot", "slot", "position")
    volume = _column(frame, "volume_ul", "volume", "transfer_volume")
    capacity = _column(frame, "capacity_ul", "well_capacity", "container_capacity")
    duration = _column(frame, "duration_min", "duration", "runtime_minutes")
    approval = _column(frame, "human_approved", "approved", "approval_status")
    if not step:
        _check(checks, "Executable protocol schema", "review", "No step/dependency schema supplied; trial-table analysis is not robot execution")
        return
    work = frame.copy()
    work["step_key"] = work[step].astype(str)
    duplicate_steps = work.step_key.duplicated(keep=False)
    _check(checks, "Unique protocol steps", "fail" if duplicate_steps.any() else "pass", f"{int(duplicate_steps.sum())} duplicate step records")
    if volume:
        work["volume_numeric"] = pd.to_numeric(work[volume], errors="coerce")
        invalid_volume = work.volume_numeric.le(0) | work.volume_numeric.isna()
    else:
        work["volume_numeric"] = np.nan
        invalid_volume = pd.Series(False, index=work.index)
    if capacity:
        work["capacity_numeric"] = pd.to_numeric(work[capacity], errors="coerce")
        over_capacity = work.volume_numeric.gt(work.capacity_numeric) if volume else pd.Series(False, index=work.index)
    else:
        work["capacity_numeric"] = np.nan
        over_capacity = pd.Series(False, index=work.index)
    work["volume_invalid"] = invalid_volume
    work["capacity_exceeded"] = over_capacity
    _check(checks, "Liquid-volume constraints", "fail" if (invalid_volume | over_capacity).any() else ("review" if not volume else "pass"), f"{int(invalid_volume.sum())} invalid volumes; {int(over_capacity.sum())} capacity violations")
    if slot and resource:
        collision = work.duplicated([resource, slot], keep=False)
        work["resource_slot_collision"] = collision
        _check(checks, "Deck/resource collision", "fail" if collision.any() else "pass", f"{int(collision.sum())} rows share the same resource and deck slot")
    else:
        work["resource_slot_collision"] = False
        _check(checks, "Deck/resource collision", "review", "Resource and deck-slot columns not both supplied")
    graph: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = {value: 0 for value in work.step_key}
    if predecessor:
        for _, row in work.iterrows():
            child = str(row[step])
            values = [token.strip() for token in re.split(r"[,;|]", str(row[predecessor] or "")) if token.strip() and token.strip().lower() not in {"nan", "none"}]
            for parent in values:
                if parent not in indegree:
                    continue
                graph[parent].add(child)
                indegree[child] = indegree.get(child, 0) + 1
    queue = deque(sorted(key for key, degree in indegree.items() if degree == 0))
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in sorted(graph.get(node, set())):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    cycle = len(order) != len(indegree)
    _check(checks, "Protocol dependency graph", "fail" if cycle else "pass", "Cycle detected" if cycle else f"Acyclic schedule with {len(order)} steps")
    if duration:
        work["duration_numeric"] = pd.to_numeric(work[duration], errors="coerce")
        _metric(metrics, "planned_protocol_duration", float(work.duration_numeric.clip(lower=0).sum()), "minutes")
    if approval:
        approved = work[approval].map(parse_scientific_bool)
        _check(checks, "Human approval before execution", "fail" if not approved.all() else "pass", f"{int(approved.sum())}/{len(work)} steps approved")
    else:
        _check(checks, "Human approval before execution", "fail", "No approval field supplied; autonomous physical execution must remain blocked")
    work["execution_blocked"] = work.volume_invalid | work.capacity_exceeded | work.resource_slot_collision
    tables["autonomous_lab_protocol_safety_audit"] = work
    tables["autonomous_lab_topological_schedule"] = pd.DataFrame({"sequence": range(1, len(order) + 1), "step_id": order})


def _federated(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    site = _column(frame, "site", "client", "institution")
    round_col = _column(frame, "round", "federated_round", "iteration")
    accuracy = _column(frame, "accuracy", "metric", "validation_accuracy")
    sample_count = _column(frame, "sample_count", "n", "records")
    epsilon = _column(frame, "epsilon", "privacy_epsilon")
    update_norm = _column(frame, "update_norm", "gradient_norm", "model_delta_norm")
    signed = _column(frame, "signed_update", "signature_valid", "authenticated")
    if not site:
        return
    work = frame.copy()
    work["site_key"] = work[site].astype(str)
    if accuracy:
        work["accuracy_numeric"] = pd.to_numeric(work[accuracy], errors="coerce")
        site_perf = work.groupby("site_key").accuracy_numeric.agg(["count", "mean", "std", "min", "max"]).reset_index()
        site_perf["performance_gap_from_best"] = site_perf["mean"].max() - site_perf["mean"]
        tables["federated_site_equity_audit"] = site_perf
        largest_gap = float(site_perf.performance_gap_from_best.max()) if len(site_perf) else np.nan
        _check(checks, "Cross-site performance equity", "review" if pd.notna(largest_gap) and largest_gap > float(metadata.get("maximum_site_performance_gap", 0.10)) else "pass", f"Largest site gap={largest_gap:.3f}")
    if update_norm:
        work["update_norm_numeric"] = pd.to_numeric(work[update_norm], errors="coerce")
        median = work.update_norm_numeric.median()
        mad = (work.update_norm_numeric - median).abs().median()
        scale = max(1e-12, 1.4826 * mad)
        work["robust_update_z"] = (work.update_norm_numeric - median) / scale
        work["poisoning_outlier"] = work.robust_update_z.abs() > float(metadata.get("maximum_update_robust_z", 4.0))
        tables["federated_update_poisoning_audit"] = work[[column for column in (site, round_col, update_norm) if column] + ["robust_update_z", "poisoning_outlier"]]
        _check(checks, "Client-update poisoning screen", "fail" if work.poisoning_outlier.any() else "pass", f"{int(work.poisoning_outlier.sum())} update-norm outliers")
    else:
        _check(checks, "Client-update poisoning screen", "review", "No update/gradient norm supplied")
    if signed:
        authenticated = work[signed].map(parse_scientific_bool)
        _check(checks, "Authenticated client updates", "fail" if not authenticated.all() else "pass", f"{int(authenticated.sum())}/{len(work)} updates authenticated")
    else:
        _check(checks, "Authenticated client updates", "review", "No update authentication/signature field supplied")
    if epsilon:
        eps = pd.to_numeric(work[epsilon], errors="coerce")
        round_total = work.assign(_eps=eps).groupby(round_col if round_col else site)._eps.max().sum()
        _metric(metrics, "conservative_composed_epsilon", float(round_total), "epsilon")
        _check(checks, "Formal privacy budget", "review" if round_total > float(metadata.get("maximum_composed_epsilon", 10.0)) else "pass", f"Conservative composed ε={round_total:.3f}")


def _pharmacovigilance(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    report = _column(frame, "report_id", "case_id", "safety_report_id")
    drug = _column(frame, "drug", "product", "medication")
    event = _column(frame, "event", "adverse_event", "meddra_term")
    date = _column(frame, "report_date", "date", "received_date")
    onset = _column(frame, "onset_date", "event_date")
    serious = _column(frame, "serious", "is_serious")
    if not (drug and event):
        return
    work = frame.copy()
    if report:
        duplicate = work.duplicated([report, drug, event], keep=False)
        work["potential_duplicate"] = duplicate
        _check(checks, "Duplicate safety reports", "review" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicated report-drug-event records")
    else:
        work["potential_duplicate"] = False
        _check(checks, "Duplicate safety reports", "review", "No report/case identifier supplied")
    if date:
        work["report_date_parsed"] = pd.to_datetime(work[date], errors="coerce", utc=True)
        time_series = work.dropna(subset=["report_date_parsed"]).assign(period=lambda data: data.report_date_parsed.dt.tz_convert(None).dt.to_period("M").astype(str)).groupby([drug, event, "period"]).size().rename("reports").reset_index()
        time_series["rolling_3_period_mean"] = time_series.groupby([drug, event]).reports.transform(lambda series: series.rolling(3, min_periods=1).mean())
        time_series["signal_acceleration"] = time_series.reports / time_series.rolling_3_period_mean.replace(0, np.nan)
        tables["pharmacovigilance_temporal_signal"] = time_series
        accelerated = int(time_series.signal_acceleration.gt(float(metadata.get("temporal_acceleration_threshold", 2.0))).sum())
        _check(checks, "Temporal signal acceleration", "review" if accelerated else "pass", f"{accelerated} drug-event periods exceed acceleration threshold")
    else:
        _check(checks, "Temporal signal detection", "review", "No report date supplied")
    if onset and date:
        onset_date = pd.to_datetime(work[onset], errors="coerce", utc=True)
        report_date = pd.to_datetime(work[date], errors="coerce", utc=True)
        work["reporting_delay_days"] = (report_date - onset_date).dt.total_seconds() / 86400
        _check(checks, "Chronology consistency", "fail" if work.reporting_delay_days.lt(0).any() else "pass", f"{int(work.reporting_delay_days.lt(0).sum())} negative reporting delays")
    if serious:
        work["serious_flag"] = work[serious].map(parse_scientific_bool)
    tables["pharmacovigilance_case_quality_audit"] = work


def _model_assurance(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    truth = _column(frame, "y_true", "truth", "outcome", "label")
    probability = _column(frame, "probability", "prediction_probability", "score")
    prediction = _column(frame, "prediction", "y_pred", "predicted_label")
    subgroup = _column(frame, "subgroup", "group", "site", "sex", "ancestry")
    if not truth or not subgroup or not (probability or prediction):
        return
    work = frame.copy()
    work["truth_numeric"] = pd.to_numeric(work[truth], errors="coerce")
    if probability:
        work["probability_numeric"] = pd.to_numeric(work[probability], errors="coerce").clip(0, 1)
        work["prediction_numeric"] = work.probability_numeric.ge(float(metadata.get("classification_threshold", 0.5))).astype(float)
    else:
        work["probability_numeric"] = np.nan
        work["prediction_numeric"] = pd.to_numeric(work[prediction], errors="coerce")
    rows = []
    for group, subset in work.groupby(subgroup, dropna=False):
        subset = subset.dropna(subset=["truth_numeric", "prediction_numeric"])
        if not len(subset):
            continue
        record = {"subgroup": str(group), "n": len(subset), "prevalence": subset.truth_numeric.mean(), "accuracy": accuracy_score(subset.truth_numeric, subset.prediction_numeric)}
        if probability and subset.truth_numeric.nunique() == 2:
            record["roc_auc"] = roc_auc_score(subset.truth_numeric, subset.probability_numeric)
            record["brier_score"] = brier_score_loss(subset.truth_numeric, subset.probability_numeric)
        rows.append(record)
    audit = pd.DataFrame(rows)
    if audit.empty:
        return
    for metric in ("accuracy", "roc_auc", "brier_score"):
        if metric in audit:
            values = audit[metric].dropna()
            audit[f"{metric}_gap_from_best"] = (values.max() - audit[metric]) if metric != "brier_score" else (audit[metric] - values.min())
    tables["model_subgroup_assurance"] = audit
    accuracy_gap = float(audit.accuracy.max() - audit.accuracy.min()) if len(audit) > 1 else 0.0
    _check(checks, "Subgroup performance gap", "review" if accuracy_gap > float(metadata.get("maximum_subgroup_accuracy_gap", 0.10)) else "pass", f"Accuracy gap={accuracy_gap:.3f}")
    _metric(metrics, "subgroups_evaluated", len(audit), "subgroups")


def _clinical_survival(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    time = _column(frame, "time", "duration", "follow_up")
    event = _column(frame, "event", "status", "outcome")
    site = _column(frame, "site", "center", "institution")
    subject = _column(frame, "subject_id", "patient_id", "id")
    if not (time and event):
        return
    work = frame.copy()
    work["time_numeric"] = pd.to_numeric(work[time], errors="coerce")
    work["event_numeric"] = pd.to_numeric(work[event], errors="coerce")
    invalid = work.time_numeric.le(0) | ~work.event_numeric.isin([0, 1])
    _check(checks, "Time-to-event schema", "fail" if invalid.any() else "pass", f"{int(invalid.sum())} invalid time/event records")
    if subject:
        duplicates = work[subject].duplicated(keep=False)
        _check(checks, "Unique participant rows", "review" if duplicates.any() else "pass", f"{int(duplicates.sum())} rows have duplicate participant IDs")
    if site:
        site_summary = work.groupby(site, dropna=False).agg(records=(event, "count"), events=("event_numeric", "sum"), median_followup=("time_numeric", "median")).reset_index()
        site_summary["event_fraction"] = site_summary.events / site_summary.records
        tables["clinical_site_heterogeneity"] = site_summary
        if len(site_summary) > 1:
            gap = float(site_summary.event_fraction.max() - site_summary.event_fraction.min())
            _check(checks, "Site event-rate heterogeneity", "review" if gap > float(metadata.get("maximum_site_event_rate_gap", 0.20)) else "pass", f"Event-rate gap={gap:.3f}")
    missing = work.isna().mean().sort_values(ascending=False).rename("missing_fraction").reset_index(name="missing_fraction").rename(columns={"index": "field"})
    tables["clinical_missingness_audit"] = missing
    high_missing = int((missing.missing_fraction > float(metadata.get("maximum_field_missingness", 0.20))).sum())
    _check(checks, "Clinical missing-data burden", "review" if high_missing else "pass", f"{high_missing} fields exceed missingness threshold")


def apply_step156_operational(
    *,
    module_key: str,
    family: str,
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    if module_key == "autonomous_lab_planner":
        _autonomous_lab(frame, metadata, tables, checks, metrics)
    if family == "federated-ai":
        _federated(frame, metadata, tables, checks, metrics)
    if family == "pharmacovigilance":
        _pharmacovigilance(frame, metadata, tables, checks, metrics)
    if family == "model-assurance":
        _model_assurance(frame, metadata, tables, checks, metrics)
    if family == "clinical-survival":
        _clinical_survival(frame, metadata, tables, checks, metrics)


__all__ = ["apply_step156_operational"]
