from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class HarmonizationBundle:
    harmonized: pd.DataFrame
    audit: pd.DataFrame
    sample_map: pd.DataFrame
    summary: dict[str, object]


def _normal_sample(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "_", text)
    return text.upper()


def harmonize_samples(frames: Iterable[pd.DataFrame], *, sample_column_candidates: tuple[str, ...] = ("sample", "sample_id", "subject", "cell", "id")) -> HarmonizationBundle:
    frames = list(frames)
    normalized_frames = []
    audit_rows = []
    map_rows = []
    for index, frame in enumerate(frames):
        if frame is None or frame.empty:
            audit_rows.append({"source": index, "status": "Empty", "rows": 0, "sample_column": ""})
            continue
        sample_column = next((column for column in sample_column_candidates if column in frame.columns), None)
        work = frame.copy()
        work["_source_index"] = index
        if sample_column:
            work["canonical_sample_id"] = work[sample_column].map(_normal_sample)
            for original, canonical in work[[sample_column, "canonical_sample_id"]].drop_duplicates().itertuples(index=False):
                map_rows.append({"source": index, "original_sample_id": original, "canonical_sample_id": canonical})
            duplicates = int(work["canonical_sample_id"].duplicated().sum())
            audit_rows.append({"source": index, "status": "Ready", "rows": len(work), "sample_column": sample_column, "duplicate_sample_rows": duplicates, "missing_sample_ids": int(work["canonical_sample_id"].eq("").sum())})
        else:
            work["canonical_sample_id"] = ""
            audit_rows.append({"source": index, "status": "Review", "rows": len(work), "sample_column": "", "duplicate_sample_rows": 0, "missing_sample_ids": len(work)})
        normalized_frames.append(work)
    harmonized = pd.concat(normalized_frames, ignore_index=True, sort=False) if normalized_frames else pd.DataFrame()
    sample_map = pd.DataFrame(map_rows).drop_duplicates() if map_rows else pd.DataFrame(columns=["source", "original_sample_id", "canonical_sample_id"])
    audit = pd.DataFrame(audit_rows)
    canonical_counts = sample_map.groupby("canonical_sample_id")["source"].nunique() if not sample_map.empty else pd.Series(dtype=int)
    summary = {
        "sources": len(frames),
        "rows": len(harmonized),
        "unique_samples": int(sample_map["canonical_sample_id"].nunique()) if not sample_map.empty else 0,
        "samples_shared_across_sources": int((canonical_counts > 1).sum()) if len(canonical_counts) else 0,
        "missing_sample_ids": int((harmonized.get("canonical_sample_id", pd.Series(dtype=str)) == "").sum()) if not harmonized.empty else 0,
    }
    return HarmonizationBundle(harmonized, audit, sample_map, summary)


__all__ = ["HarmonizationBundle", "harmonize_samples"]
