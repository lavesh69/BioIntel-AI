from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
import zipfile
from io import BytesIO

import numpy as np
import pandas as pd


@dataclass
class OnlineNumericState:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def update(self, values: pd.Series) -> None:
        numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if numeric.empty:
            return
        arr = numeric.to_numpy(dtype=float, copy=False)
        chunk_count = int(arr.size)
        chunk_mean = float(arr.mean())
        chunk_m2 = float(((arr - chunk_mean) ** 2).sum())
        chunk_min = float(arr.min())
        chunk_max = float(arr.max())
        if self.count == 0:
            self.count = chunk_count
            self.mean = chunk_mean
            self.m2 = chunk_m2
            self.minimum = chunk_min
            self.maximum = chunk_max
            return
        total = self.count + chunk_count
        delta = chunk_mean - self.mean
        self.mean += delta * chunk_count / total
        self.m2 += chunk_m2 + delta * delta * self.count * chunk_count / total
        self.count = total
        self.minimum = chunk_min if self.minimum is None else min(self.minimum, chunk_min)
        self.maximum = chunk_max if self.maximum is None else max(self.maximum, chunk_max)

    def summary(self) -> dict[str, Any]:
        variance = self.m2 / (self.count - 1) if self.count > 1 else 0.0
        return {
            "count": self.count,
            "mean": self.mean if self.count else None,
            "standard_deviation": math.sqrt(max(variance, 0.0)) if self.count else None,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class StreamingProfileResult:
    schema: str
    source_path: str
    source_sha256: str
    source_size_bytes: int
    separator: str
    rows: int
    columns: int
    chunks: int
    chunk_rows: int
    completed: bool
    resumed_from_chunk: int
    expected_columns: tuple[str, ...]
    missing_expected_columns: tuple[str, ...]
    schema_drift_detected: bool
    schema_events: tuple[dict[str, Any], ...]
    column_profile: tuple[dict[str, Any], ...]
    recommendations: tuple[str, ...]
    checkpoint_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def bundle(self) -> bytes:
        payload = self.to_dict()
        profile = pd.DataFrame(payload["column_profile"])
        events = pd.DataFrame(payload["schema_events"])
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("streaming_profile.json", json.dumps(payload, indent=2, sort_keys=True, default=str))
            archive.writestr("column_profile.csv", profile.to_csv(index=False))
            archive.writestr("schema_events.csv", events.to_csv(index=False))
        return buffer.getvalue()


def _sha256(path: Path, *, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(block_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _separator(path: Path, supplied: str | None) -> str:
    if supplied:
        if supplied not in {",", "\t", ";", "|"}:
            raise ValueError("Unsupported delimiter")
        return supplied
    return "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","


def profile_tabular_file(
    source: str | Path,
    *,
    separator: str | None = None,
    chunk_rows: int = 100_000,
    checkpoint_path: str | Path | None = None,
    expected_columns: Iterable[str] = (),
    resume: bool = True,
    unique_value_cap: int = 10_000,
) -> StreamingProfileResult:
    """Profile a complete CSV/TSV using bounded memory and atomic checkpoints.

    Every byte is SHA-256 hashed before analysis. Checkpoint resumption is accepted
    only when the exact source checksum, delimiter and chunk size match.
    """

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    chunk_rows = max(1_000, min(int(chunk_rows), 1_000_000))
    unique_value_cap = max(100, min(int(unique_value_cap), 100_000))
    sep = _separator(path, separator)
    digest = _sha256(path)
    checkpoint = Path(checkpoint_path).expanduser().resolve() if checkpoint_path else path.with_suffix(path.suffix + ".biointel-profile.json")
    expected = tuple(dict.fromkeys(str(column) for column in expected_columns if str(column).strip()))

    state: dict[str, Any] = {
        "source_sha256": digest,
        "source_size_bytes": path.stat().st_size,
        "separator": sep,
        "chunk_rows": chunk_rows,
        "chunks_processed": 0,
        "rows_processed": 0,
        "columns": [],
        "missing": {},
        "non_null": {},
        "dtype_observations": {},
        "numeric": {},
        "unique_values": {},
        "unique_overflow": {},
        "schema_events": [],
        "completed": False,
    }
    resumed_from = 0
    if resume and checkpoint.is_file():
        try:
            candidate = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            candidate = {}
        compatible = (
            candidate.get("source_sha256") == digest
            and candidate.get("separator") == sep
            and int(candidate.get("chunk_rows", 0)) == chunk_rows
            and not bool(candidate.get("completed"))
        )
        if compatible:
            state.update(candidate)
            resumed_from = int(state.get("chunks_processed", 0))

    numeric_states: dict[str, OnlineNumericState] = {}
    for column, payload in dict(state.get("numeric", {})).items():
        numeric_states[str(column)] = OnlineNumericState(
            count=int(payload.get("count", 0)),
            mean=float(payload.get("mean", 0.0) or 0.0),
            m2=float(payload.get("m2", 0.0) or 0.0),
            minimum=payload.get("minimum"),
            maximum=payload.get("maximum"),
        )
    unique_values: dict[str, set[str]] = {
        str(column): set(map(str, values)) for column, values in dict(state.get("unique_values", {})).items()
    }
    initial_columns = list(state.get("columns", []))

    reader = pd.read_csv(path, sep=sep, chunksize=chunk_rows, low_memory=False)
    for chunk_index, chunk in enumerate(reader):
        if chunk_index < resumed_from:
            continue
        columns = [str(column) for column in chunk.columns]
        if not initial_columns:
            initial_columns = columns
            state["columns"] = columns
        elif columns != initial_columns:
            state["schema_events"].append({
                "chunk": chunk_index,
                "event": "column-order-or-membership-change",
                "expected": initial_columns,
                "observed": columns,
            })
        state["rows_processed"] = int(state.get("rows_processed", 0)) + len(chunk)
        for column in columns:
            series = chunk[column]
            state["missing"][column] = int(state["missing"].get(column, 0)) + int(series.isna().sum())
            state["non_null"][column] = int(state["non_null"].get(column, 0)) + int(series.notna().sum())
            observed = state["dtype_observations"].setdefault(column, {})
            dtype_name = str(series.dtype)
            observed[dtype_name] = int(observed.get(dtype_name, 0)) + 1

            numeric = pd.to_numeric(series, errors="coerce")
            numeric_fraction = float(numeric.notna().mean()) if len(series) else 0.0
            if numeric_fraction >= 0.80:
                numeric_states.setdefault(column, OnlineNumericState()).update(numeric)

            values = unique_values.setdefault(column, set())
            if not state["unique_overflow"].get(column, False):
                for value in series.dropna().astype(str).unique():
                    values.add(value)
                    if len(values) > unique_value_cap:
                        state["unique_overflow"][column] = True
                        values.clear()
                        break

        state["chunks_processed"] = chunk_index + 1
        state["numeric"] = {
            column: {
                "count": item.count,
                "mean": item.mean,
                "m2": item.m2,
                "minimum": item.minimum,
                "maximum": item.maximum,
            }
            for column, item in numeric_states.items()
        }
        state["unique_values"] = {column: sorted(values) for column, values in unique_values.items() if values}
        _atomic_json(checkpoint, state)

    state["completed"] = True
    _atomic_json(checkpoint, state)
    total_rows = int(state["rows_processed"])
    profile_rows: list[dict[str, Any]] = []
    for position, column in enumerate(initial_columns):
        missing = int(state["missing"].get(column, 0))
        non_null = int(state["non_null"].get(column, 0))
        numeric_summary = numeric_states[column].summary() if column in numeric_states else {}
        dtype_counts = dict(state["dtype_observations"].get(column, {}))
        profile_rows.append({
            "column": column,
            "source_position": position,
            "rows": total_rows,
            "non_null": non_null,
            "missing": missing,
            "missing_fraction": missing / max(total_rows, 1),
            "dtype_observations": json.dumps(dtype_counts, sort_keys=True),
            "numeric_count": numeric_summary.get("count", 0),
            "mean": numeric_summary.get("mean"),
            "standard_deviation": numeric_summary.get("standard_deviation"),
            "minimum": numeric_summary.get("minimum"),
            "maximum": numeric_summary.get("maximum"),
            "unique_values": None if state["unique_overflow"].get(column, False) else len(unique_values.get(column, set())),
            "unique_count_capped": bool(state["unique_overflow"].get(column, False)),
        })

    missing_expected = tuple(column for column in expected if column not in initial_columns)
    recommendations: list[str] = []
    if missing_expected:
        recommendations.append("Add required columns before confirmatory execution: " + ", ".join(missing_expected))
    high_missing = [row["column"] for row in profile_rows if row["missing_fraction"] > 0.20]
    if high_missing:
        recommendations.append("Review columns with >20% missingness: " + ", ".join(high_missing[:20]))
    if state["schema_events"]:
        recommendations.append("Resolve schema drift across chunks before model training or release.")
    if not recommendations:
        recommendations.append("Streaming profile completed; preserve this checksum-bound report with the analysis bundle.")

    return StreamingProfileResult(
        schema="biointel.step157.streaming-profile.v1",
        source_path=str(path),
        source_sha256=digest,
        source_size_bytes=int(path.stat().st_size),
        separator=sep,
        rows=total_rows,
        columns=len(initial_columns),
        chunks=int(state["chunks_processed"]),
        chunk_rows=chunk_rows,
        completed=True,
        resumed_from_chunk=resumed_from,
        expected_columns=expected,
        missing_expected_columns=missing_expected,
        schema_drift_detected=bool(state["schema_events"]),
        schema_events=tuple(state["schema_events"]),
        column_profile=tuple(profile_rows),
        recommendations=tuple(recommendations),
        checkpoint_path=str(checkpoint),
    )


__all__ = ["OnlineNumericState", "StreamingProfileResult", "profile_tabular_file"]
