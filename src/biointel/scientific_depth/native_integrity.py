from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
import zipfile
from typing import Any, Iterable

import numpy as np
import pandas as pd


FALSE_TOKENS = {"", "0", "false", "f", "no", "n", "off", "negative", "none", "null", "nan"}
TRUE_TOKENS = {"1", "true", "t", "yes", "y", "on", "positive"}


def parse_scientific_bool(value: Any, *, default: bool = False) -> bool:
    """Parse user/data-file booleans without Python's truthy-string trap.

    Unknown non-empty strings fail closed to ``default`` rather than becoming True.
    """
    if value is None or value is pd.NA:
        return default
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value) != 0
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return default
        return float(value) != 0.0
    token = str(value).strip().lower()
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    return default


def full_frame_sha256(frame: pd.DataFrame, *, chunk_rows: int = 50_000) -> str:
    """Deterministically hash every row, column, dtype and index value.

    Hashing is chunked for memory safety but never samples or truncates the input.
    """
    digest = sha256()
    digest.update(b"biointel.full-dataframe-sha256.v1\0")
    digest.update(json.dumps([str(column) for column in frame.columns], ensure_ascii=False).encode("utf-8"))
    digest.update(b"\0")
    digest.update(json.dumps([str(dtype) for dtype in frame.dtypes], ensure_ascii=False).encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(len(frame)).encode("ascii"))
    digest.update(b"\0")
    if frame.empty:
        return digest.hexdigest()
    step = max(1, int(chunk_rows))
    for start in range(0, len(frame), step):
        chunk = frame.iloc[start : start + step]
        hashed = pd.util.hash_pandas_object(chunk, index=True, categorize=True).to_numpy(dtype="uint64", copy=False)
        digest.update(hashed.tobytes(order="C"))
    return digest.hexdigest()


def ranked_numeric_features(
    frame: pd.DataFrame,
    *,
    exclude: Iterable[str] = (),
    limit: int = 100,
    minimum_numeric_fraction: float = 0.80,
) -> tuple[list[str], pd.DataFrame]:
    """Rank numeric features using completeness, variance and information content.

    This removes first-column order bias. The audit table records every candidate,
    including features that were not selected because of the configured limit.
    """
    excluded = {str(item) for item in exclude}
    rows: list[dict[str, Any]] = []
    for position, column in enumerate(frame.columns):
        name = str(column)
        if name in excluded:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        numeric_fraction = float(values.notna().mean()) if len(values) else 0.0
        unique = int(values.nunique(dropna=True))
        finite = values.replace([np.inf, -np.inf], np.nan).dropna()
        variance = float(finite.var(ddof=1)) if len(finite) > 1 else 0.0
        variance_score = math.log1p(max(variance, 0.0))
        unique_score = math.log1p(unique)
        score = numeric_fraction * 5.0 + variance_score + unique_score
        eligible = numeric_fraction >= minimum_numeric_fraction and unique > 1
        rows.append(
            {
                "feature": name,
                "source_position": position,
                "numeric_fraction": numeric_fraction,
                "unique_values": unique,
                "variance": variance,
                "selection_score": score,
                "eligible": eligible,
            }
        )
    audit = pd.DataFrame(rows)
    if audit.empty:
        return [], audit
    audit = audit.sort_values(
        ["eligible", "selection_score", "numeric_fraction", "unique_values", "feature"],
        ascending=[False, False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    selected = audit.loc[audit["eligible"], "feature"].head(max(0, int(limit))).astype(str).tolist()
    audit["selected"] = audit["feature"].isin(selected)
    audit["selection_rank"] = pd.NA
    rank = {feature: index + 1 for index, feature in enumerate(selected)}
    audit.loc[audit["selected"], "selection_rank"] = audit.loc[audit["selected"], "feature"].map(rank)
    return selected, audit


@dataclass(frozen=True)
class TableArtifact:
    name: str
    rows: int
    columns: int
    sha256: str
    preview_rows: int
    preview_complete: bool


def table_artifact(name: str, table: pd.DataFrame, *, preview_limit: int = 5_000) -> tuple[TableArtifact, list[dict[str, Any]]]:
    preview = table.head(max(0, int(preview_limit)))
    artifact = TableArtifact(
        name=str(name),
        rows=int(len(table)),
        columns=int(len(table.columns)),
        sha256=full_frame_sha256(table),
        preview_rows=int(len(preview)),
        preview_complete=bool(len(preview) == len(table)),
    )
    return artifact, preview.to_dict(orient="records")


def build_complete_result_bundle(manifest: dict[str, Any], tables: dict[str, pd.DataFrame]) -> bytes:
    """Create a ZIP containing the manifest and complete, non-truncated CSV tables."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str, ensure_ascii=False))
        for name, table in sorted(tables.items()):
            if not isinstance(table, pd.DataFrame):
                continue
            safe = "".join(character if character.isalnum() or character in "._-" else "_" for character in str(name)).strip("_") or "table"
            archive.writestr(f"tables/{safe}.csv", table.to_csv(index=False))
    return buffer.getvalue()


def manifest_table_payload(tables: dict[str, pd.DataFrame], *, preview_limit: int = 5_000) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    previews: dict[str, list[dict[str, Any]]] = {}
    artifacts: list[dict[str, Any]] = []
    for name, table in sorted(tables.items()):
        if not isinstance(table, pd.DataFrame):
            continue
        artifact, preview = table_artifact(name, table, preview_limit=preview_limit)
        previews[str(name)] = preview
        artifacts.append(asdict(artifact))
    return previews, artifacts
