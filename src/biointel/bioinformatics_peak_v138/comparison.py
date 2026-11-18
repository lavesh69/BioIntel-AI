from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RunComparison:
    summary: dict[str, Any]
    metric_changes: pd.DataFrame
    record_changes: pd.DataFrame
    identifiers: tuple[str, ...]


def _numeric_summary(frame: pd.DataFrame) -> dict[str, float]:
    summary: dict[str, float] = {}
    preferred = ("priority_score", "p_value", "q_value", "frequency", "activity", "signal", "support", "expression", "binding_score")
    columns = [column for column in preferred if column in frame.columns]
    if not columns:
        columns = list(frame.select_dtypes(include=[np.number]).columns[:8])
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().any():
            summary[f"{column}.mean"] = float(values.mean())
            summary[f"{column}.median"] = float(values.median())
            summary[f"{column}.non_missing"] = float(values.notna().sum())
    return summary


def compare_frames(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    *,
    identifier_candidates: Iterable[str] = (),
    maximum_changed_records: int = 25_000,
) -> RunComparison:
    if current.empty or previous.empty:
        raise ValueError("Both current and previous runs must contain records.")
    current_clean = current.loc[:, ~current.columns.astype(str).duplicated()].copy()
    previous_clean = previous.loc[:, ~previous.columns.astype(str).duplicated()].copy()
    identifiers = tuple(
        column for column in identifier_candidates
        if column in current_clean.columns and column in previous_clean.columns
    )
    if not identifiers:
        shared = [column for column in current_clean.columns if column in previous_clean.columns]
        identifiers = tuple(shared[:1])

    current_metrics = {"rows": float(len(current_clean)), "columns": float(len(current_clean.columns)), **_numeric_summary(current_clean)}
    previous_metrics = {"rows": float(len(previous_clean)), "columns": float(len(previous_clean.columns)), **_numeric_summary(previous_clean)}
    metric_names = sorted(set(current_metrics) | set(previous_metrics))
    metric_rows: list[dict[str, Any]] = []
    for metric in metric_names:
        before = previous_metrics.get(metric, np.nan)
        after = current_metrics.get(metric, np.nan)
        delta = after - before if np.isfinite(before) and np.isfinite(after) else np.nan
        percent = (delta / abs(before) * 100.0) if np.isfinite(delta) and before not in {0, 0.0} else np.nan
        metric_rows.append({"metric": metric, "previous": before, "current": after, "delta": delta, "percent_change": percent})
    metric_changes = pd.DataFrame(metric_rows)

    record_changes = pd.DataFrame()
    overlap = 0
    added = len(current_clean)
    removed = len(previous_clean)
    changed = 0
    if identifiers:
        for frame in (current_clean, previous_clean):
            for column in identifiers:
                frame[column] = frame[column].astype(str)
        current_dedup = current_clean.drop_duplicates(list(identifiers), keep="last")
        previous_dedup = previous_clean.drop_duplicates(list(identifiers), keep="last")
        merged = current_dedup.merge(previous_dedup, on=list(identifiers), how="outer", suffixes=("_current", "_previous"), indicator=True)
        overlap = int((merged["_merge"] == "both").sum())
        added = int((merged["_merge"] == "left_only").sum())
        removed = int((merged["_merge"] == "right_only").sum())
        compare_columns = [
            column for column in current_dedup.columns
            if column in previous_dedup.columns and column not in identifiers
        ][:30]
        if compare_columns:
            difference_flags = pd.Series(False, index=merged.index)
            delta_columns: list[str] = []
            for column in compare_columns:
                current_col = f"{column}_current"
                previous_col = f"{column}_previous"
                if current_col not in merged or previous_col not in merged:
                    continue
                current_num = pd.to_numeric(merged[current_col], errors="coerce")
                previous_num = pd.to_numeric(merged[previous_col], errors="coerce")
                if current_num.notna().any() or previous_num.notna().any():
                    delta_name = f"{column}_delta"
                    merged[delta_name] = current_num - previous_num
                    delta_columns.append(delta_name)
                    difference_flags |= merged[delta_name].abs().fillna(0).gt(1e-12)
                else:
                    difference_flags |= merged[current_col].fillna("<NA>").astype(str).ne(merged[previous_col].fillna("<NA>").astype(str))
            changed = int(((merged["_merge"] == "both") & difference_flags).sum())
            keep_columns = [*identifiers, "_merge", *delta_columns]
            priority_columns = [
                column for column in merged.columns
                if column.endswith(("priority_score_current", "priority_score_previous", "status_current", "status_previous"))
            ]
            keep_columns.extend(column for column in priority_columns if column not in keep_columns)
            record_changes = merged.loc[(merged["_merge"] != "both") | difference_flags, keep_columns].head(maximum_changed_records).reset_index(drop=True)
        else:
            record_changes = merged.loc[merged["_merge"] != "both", [*identifiers, "_merge"]].head(maximum_changed_records).reset_index(drop=True)

    summary = {
        "schema": "biointel.bioinformatics.run_comparison.v139",
        "current_rows": len(current_clean),
        "previous_rows": len(previous_clean),
        "row_delta": len(current_clean) - len(previous_clean),
        "identifiers": list(identifiers),
        "overlap_records": overlap,
        "added_records": added,
        "removed_records": removed,
        "changed_records": changed,
        "current_columns": len(current_clean.columns),
        "previous_columns": len(previous_clean.columns),
    }
    return RunComparison(summary=summary, metric_changes=metric_changes, record_changes=record_changes, identifiers=identifiers)


__all__ = ["RunComparison", "compare_frames"]
