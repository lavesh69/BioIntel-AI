from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ReferenceReleaseDiff:
    added: pd.DataFrame
    removed: pd.DataFrame
    changed: pd.DataFrame
    unchanged: int
    summary: dict[str, object]


def compare_reference_releases(old: pd.DataFrame, new: pd.DataFrame, *, key_columns: Iterable[str] | None = None) -> ReferenceReleaseDiff:
    if old.empty and new.empty:
        empty = pd.DataFrame()
        return ReferenceReleaseDiff(empty, empty, empty, 0, {"added": 0, "removed": 0, "changed": 0, "unchanged": 0, "keys": []})
    common = [column for column in old.columns if column in new.columns]
    candidates = list(key_columns or ())
    keys = [column for column in candidates if column in common]
    if not keys:
        preferred = ("id", "gene", "variant", "transcript", "feature_id", "name", "term_id", "allele", "lineage", "chrom", "start", "end")
        keys = [column for column in preferred if column in common][:3]
    if not keys:
        raise ValueError("Reference release comparison requires at least one shared identifier column.")
    old_work = old.copy(); new_work = new.copy()
    old_work["_release_key"] = old_work[keys].astype(str).agg("|".join, axis=1)
    new_work["_release_key"] = new_work[keys].astype(str).agg("|".join, axis=1)
    old_work = old_work.drop_duplicates("_release_key", keep="last").set_index("_release_key", drop=False)
    new_work = new_work.drop_duplicates("_release_key", keep="last").set_index("_release_key", drop=False)
    old_keys = set(old_work.index); new_keys = set(new_work.index)
    added = new_work.loc[sorted(new_keys - old_keys)].reset_index(drop=True) if new_keys - old_keys else pd.DataFrame(columns=new.columns)
    removed = old_work.loc[sorted(old_keys - new_keys)].reset_index(drop=True) if old_keys - new_keys else pd.DataFrame(columns=old.columns)
    changed_rows = []
    unchanged = 0
    comparison_columns = [column for column in common if column not in keys]
    for key in sorted(old_keys & new_keys):
        left = old_work.loc[key]; right = new_work.loc[key]
        differences = []
        for column in comparison_columns:
            left_value = "" if pd.isna(left[column]) else str(left[column])
            right_value = "" if pd.isna(right[column]) else str(right[column])
            if left_value != right_value:
                differences.append({"column": column, "old": left_value, "new": right_value})
        if differences:
            changed_rows.append({"release_key": key, "changed_columns": ", ".join(item["column"] for item in differences), "changes": differences})
        else:
            unchanged += 1
    changed = pd.DataFrame(changed_rows)
    summary = {"added": len(added), "removed": len(removed), "changed": len(changed), "unchanged": unchanged, "keys": keys}
    return ReferenceReleaseDiff(added, removed, changed, unchanged, summary)


__all__ = ["ReferenceReleaseDiff", "compare_reference_releases"]
