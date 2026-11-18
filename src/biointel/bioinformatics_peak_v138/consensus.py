from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ConsensusBundle:
    consensus: pd.DataFrame
    agreement_matrix: pd.DataFrame
    caller_summary: pd.DataFrame
    unique_calls: pd.DataFrame


def _existing(frame: pd.DataFrame, candidates: Iterable[str]) -> list[str]:
    return [column for column in candidates if column in frame.columns]


def _event_key(frame: pd.DataFrame, *, tolerance: int = 50) -> pd.Series:
    columns = _existing(frame, ("chrom", "position", "start", "end", "ref", "alt", "event_type", "gene", "variant", "event_id"))
    if not columns:
        return frame.index.to_series().map(lambda value: f"row:{value}")
    parts = []
    for column in columns:
        series = frame[column]
        if column in {"position", "start", "end"}:
            numeric = pd.to_numeric(series, errors="coerce")
            series = (numeric // max(1, tolerance)).fillna(-1).astype(int)
        parts.append(series.astype(str).fillna(""))
    key = parts[0]
    for part in parts[1:]:
        key = key + "|" + part
    return key


def build_consensus(frame: pd.DataFrame, *, caller_column: str = "caller", minimum_callers: int = 2, tolerance: int = 50) -> ConsensusBundle:
    if frame.empty:
        empty = pd.DataFrame()
        return ConsensusBundle(empty, empty, empty, empty)
    if caller_column not in frame.columns:
        raise ValueError(f"Caller/method column '{caller_column}' was not found.")
    if minimum_callers < 1:
        raise ValueError("minimum_callers must be positive.")
    work = frame.copy().reset_index(drop=True)
    work["_event_key"] = _event_key(work, tolerance=tolerance)
    work[caller_column] = work[caller_column].fillna("Unknown").astype(str)
    numeric_columns = [column for column in work.select_dtypes(include="number").columns if column not in {"_event_key"}]
    rows = []
    for event_key, group in work.groupby("_event_key", sort=False):
        callers = sorted(group[caller_column].unique().tolist())
        record = {"consensus_key": event_key, "caller_count": len(callers), "callers": ", ".join(callers), "records": len(group), "consensus_status": "Consensus" if len(callers) >= minimum_callers else "Unique/review"}
        for column in _existing(group, ("chrom", "position", "start", "end", "ref", "alt", "event_type", "gene", "variant", "event_id", "sample")):
            record[column] = group[column].iloc[0]
        for column in numeric_columns[:25]:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            if len(values):
                record[f"{column}_median"] = float(values.median())
                record[f"{column}_range"] = float(values.max() - values.min())
        record["ensemble_confidence"] = float(min(1.0, len(callers) / max(minimum_callers + 1, 3)))
        rows.append(record)
    consensus = pd.DataFrame(rows).sort_values(["caller_count", "records"], ascending=False)
    callers = sorted(work[caller_column].unique().tolist())
    matrix = pd.DataFrame(np.eye(len(callers)), index=callers, columns=callers)
    caller_sets = {caller: set(work.loc[work[caller_column] == caller, "_event_key"]) for caller in callers}
    for left, right in combinations(callers, 2):
        union = caller_sets[left] | caller_sets[right]
        score = len(caller_sets[left] & caller_sets[right]) / len(union) if union else 1.0
        matrix.loc[left, right] = matrix.loc[right, left] = score
    caller_summary = pd.DataFrame([
        {"caller": caller, "records": int((work[caller_column] == caller).sum()), "unique_events": len(caller_sets[caller]), "exclusive_events": len(caller_sets[caller] - set().union(*(caller_sets[x] for x in callers if x != caller)))}
        for caller in callers
    ])
    unique = consensus[consensus["caller_count"] < minimum_callers].copy()
    return ConsensusBundle(consensus.reset_index(drop=True), matrix.reset_index(names="caller"), caller_summary, unique.reset_index(drop=True))


__all__ = ["ConsensusBundle", "build_consensus"]
