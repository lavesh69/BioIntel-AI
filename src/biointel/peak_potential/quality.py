from __future__ import annotations

import hashlib
import json
import math
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FrameAudit:
    rows: int
    columns: int
    audited_rows: int
    missing_cells: int
    missing_percent: float
    duplicate_rows: int
    duplicate_columns: tuple[str, ...]
    infinite_cells: int
    constant_columns: tuple[str, ...]
    mixed_object_columns: tuple[str, ...]
    numeric_columns: int
    categorical_columns: int
    sampled: bool
    score: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualAudit:
    trace_count: int
    visible_trace_count: int
    point_count: int
    finite_point_count: int
    sampled: bool
    has_data: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_frame(frame: Any) -> pd.DataFrame:
    if isinstance(frame, pd.DataFrame):
        return frame.copy(deep=False)
    if isinstance(frame, pd.Series):
        return frame.to_frame()
    try:
        return pd.DataFrame(frame)
    except (TypeError, ValueError):
        if isinstance(frame, dict):
            return pd.DataFrame([frame])
        return pd.DataFrame({"value": [frame]})


def _unique_columns(columns: Iterable[Any]) -> list[str]:
    counts: dict[str, int] = {}
    output: list[str] = []
    for value in columns:
        name = str(value)
        seen = counts.get(name, 0)
        counts[name] = seen + 1
        output.append(name if seen == 0 else f"{name}__{seen + 1}")
    return output


def _deterministic_sample(data: pd.DataFrame, limit: int) -> tuple[pd.DataFrame, bool]:
    rows = len(data)
    cap = max(1, int(limit))
    if rows <= cap:
        return data, False
    # Evenly-spaced sampling avoids first-chunk bias while remaining deterministic.
    indices = np.linspace(0, rows - 1, num=cap, dtype=np.int64)
    return data.iloc[indices], True


def _normalise_nested(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set, np.ndarray)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def audit_frame(frame: pd.DataFrame | Iterable[dict[str, Any]], *, sample_rows: int = 50_000) -> FrameAudit:
    data = _coerce_frame(frame)
    rows = int(len(data))
    columns = int(data.shape[1])
    original_columns = list(data.columns)
    duplicate_names = tuple(
        dict.fromkeys(str(name) for name in data.columns[data.columns.duplicated(keep=False)].tolist())
    )

    # Duplicate names are audited positionally so the audit itself cannot crash.
    working = data.copy(deep=False)
    working.columns = _unique_columns(original_columns)
    sample, sampled = _deterministic_sample(working, sample_rows)
    audited_rows = int(len(sample))

    audited_cells = max(1, audited_rows * columns)
    sample_missing = int(sample.isna().sum().sum()) if audited_rows and columns else 0
    missing_percent = round(100.0 * sample_missing / audited_cells, 4)
    missing_cells = int(round((missing_percent / 100.0) * rows * columns)) if rows and columns else 0

    duplicate_rows = 0
    if not sample.empty:
        comparable = sample.copy()
        for column in comparable.columns:
            if pd.api.types.is_object_dtype(comparable[column]):
                comparable[column] = comparable[column].map(_normalise_nested)
        try:
            duplicate_rows = int(comparable.duplicated().sum())
        except (TypeError, ValueError):
            # Last-resort stable string representation; never interrupt a module.
            duplicate_rows = int(comparable.astype(str).duplicated().sum())

    numeric = sample.select_dtypes(include=[np.number])
    infinite_cells = 0
    if not numeric.empty:
        try:
            values = numeric.to_numpy(dtype=float, na_value=np.nan)
            infinite_cells = int(np.isinf(values).sum())
        except (TypeError, ValueError, OverflowError):
            for column in numeric.columns:
                converted = pd.to_numeric(numeric[column], errors="coerce")
                infinite_cells += int(np.isinf(converted.to_numpy(dtype=float, na_value=np.nan)).sum())

    constant_columns: list[str] = []
    mixed_columns: list[str] = []
    for column in sample.columns:
        series = sample[column]
        comparable = series.map(_normalise_nested) if pd.api.types.is_object_dtype(series) else series
        try:
            unique_count = int(comparable.nunique(dropna=True))
        except (TypeError, ValueError):
            unique_count = int(comparable.astype(str).nunique(dropna=True))
        if unique_count <= 1 and len(series) > 1:
            constant_columns.append(str(column))
        if pd.api.types.is_object_dtype(series):
            observed = {type(value).__name__ for value in series.dropna().head(5_000)}
            if len(observed) > 1:
                mixed_columns.append(str(column))

    blockers: list[str] = []
    warnings: list[str] = []
    if rows == 0:
        blockers.append("The result table is empty.")
    if columns == 0:
        blockers.append("The result has no columns.")
    if duplicate_names:
        blockers.append("Duplicate column names must be resolved before export.")
    if infinite_cells:
        blockers.append(f"{infinite_cells:,} non-finite numeric values were detected in the audited rows.")
    if missing_percent >= 50:
        blockers.append(f"Missingness is {missing_percent:.1f}%; result reliability is blocked.")
    elif missing_percent >= 10:
        warnings.append(f"Missingness is {missing_percent:.1f}%; review imputation or filtering.")
    if duplicate_rows:
        warnings.append(f"{duplicate_rows:,} duplicate rows were detected in the audited rows.")
    if constant_columns:
        warnings.append(f"{len(constant_columns)} constant columns may be uninformative.")
    if mixed_columns:
        warnings.append(f"{len(mixed_columns)} mixed-type columns require schema review.")
    if sampled:
        warnings.append(
            f"Quality audit used {audited_rows:,} evenly-spaced rows from {rows:,} total rows for bounded memory use; "
            "missing-cell count is estimated from that sample."
        )

    penalty = min(100, len(blockers) * 25 + len(warnings) * 6)
    score = max(0, 100 - penalty)
    return FrameAudit(
        rows=rows,
        columns=columns,
        audited_rows=audited_rows,
        missing_cells=missing_cells,
        missing_percent=missing_percent,
        duplicate_rows=duplicate_rows,
        duplicate_columns=duplicate_names,
        infinite_cells=infinite_cells,
        constant_columns=tuple(constant_columns),
        mixed_object_columns=tuple(mixed_columns),
        numeric_columns=int(len(numeric.columns)),
        categorical_columns=int(columns - len(numeric.columns)),
        sampled=sampled,
        score=score,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def _append_atomic_values(value: Any, output: list[Any], *, limit: int) -> bool:
    """Flatten nested Plotly values without allowing huge figures to exhaust memory.

    Returns True when the requested limit was reached.
    """
    if len(output) >= limit:
        return True
    if value is None or isinstance(value, (str, bytes, int, float, complex, bool, np.number)):
        output.append(value)
        return len(output) >= limit
    if isinstance(value, np.ndarray):
        iterator = value.flat
    elif isinstance(value, pd.Series):
        iterator = value.array
    elif isinstance(value, dict):
        iterator = value.values()
    elif isinstance(value, (list, tuple, set)):
        iterator = value
    else:
        try:
            iterator = iter(value)
        except TypeError:
            output.append(value)
            return len(output) >= limit
    for item in iterator:
        if _append_atomic_values(item, output, limit=limit):
            return True
    return False


def _trace_values(trace: Any, *, limit: int) -> tuple[list[Any], bool]:
    values: list[Any] = []
    sampled = False
    fields = (
        "x", "y", "z", "values", "labels", "lat", "lon", "r", "theta",
        "locations", "ids", "parents", "source", "target", "value", "customdata",
        "open", "high", "low", "close", "u", "v", "w", "a", "b", "c", "i", "j", "k",
    )
    for field in fields:
        value = getattr(trace, field, None)
        if value is None:
            continue
        sampled = _append_atomic_values(value, values, limit=limit) or sampled
        if sampled:
            return values, True
    for nested_name in ("node", "link"):
        nested = getattr(trace, nested_name, None)
        if nested is None:
            continue
        for field in ("label", "source", "target", "value", "customdata"):
            value = getattr(nested, field, None)
            if value is None:
                continue
            sampled = _append_atomic_values(value, values, limit=limit) or sampled
            if sampled:
                return values, True
    return values, sampled


def audit_plotly_figure(figure: Any, *, max_values: int = 200_000) -> VisualAudit:
    traces = list(getattr(figure, "data", ()) or ())
    visible = [trace for trace in traces if getattr(trace, "visible", True) not in (False, "legendonly")]
    points: list[Any] = []
    sampled = False
    cap = max(1, int(max_values))
    for trace in visible:
        remaining = cap - len(points)
        if remaining <= 0:
            sampled = True
            break
        trace_points, trace_sampled = _trace_values(trace, limit=remaining)
        points.extend(trace_points)
        sampled = sampled or trace_sampled
        if len(points) >= cap:
            sampled = True
            break

    finite = 0
    for value in points:
        if value is None:
            continue
        if isinstance(value, (float, int, np.number)) and not isinstance(value, bool):
            try:
                if math.isfinite(float(value)):
                    finite += 1
            except (TypeError, ValueError, OverflowError):
                pass
        elif str(value).strip().lower() not in {"", "nan", "none", "nat", "inf", "-inf"}:
            finite += 1

    warnings: list[str] = []
    if not traces:
        warnings.append("The figure contains no traces.")
    elif not visible:
        warnings.append("All figure traces are hidden.")
    elif not points:
        warnings.append("Figure traces contain no drawable values.")
    elif finite == 0:
        warnings.append("Figure values are entirely missing or non-finite.")
    if sampled:
        warnings.append(f"Visual audit inspected a bounded sample of {len(points):,} values.")
    return VisualAudit(
        trace_count=len(traces),
        visible_trace_count=len(visible),
        point_count=len(points),
        finite_point_count=finite,
        sampled=sampled,
        has_data=bool(visible and points and finite),
        warnings=tuple(warnings),
    )


def stable_error_id(exc: BaseException, *, module_key: str = "") -> str:
    source = f"{module_key}|{type(exc).__name__}|{exc}|{traceback.format_exc(limit=8)}"
    return "PEAK-" + hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:12].upper()


def build_manifest(
    *,
    module_key: str,
    title: str,
    domain: str,
    frame_audits: dict[str, FrameAudit] | None = None,
    visual_audits: dict[str, VisualAudit] | None = None,
    run_manifest: dict[str, Any] | None = None,
    evidence_status: str = "research_use",
    software_version: str = "",
) -> dict[str, Any]:
    payload = {
        "schema": "biointel.peak_potential.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "module_key": module_key,
        "module_title": title,
        "domain": domain,
        "evidence_status": evidence_status,
        "software_version": software_version,
        "frame_audits": {key: audit.to_dict() for key, audit in (frame_audits or {}).items()},
        "visual_audits": {key: audit.to_dict() for key, audit in (visual_audits or {}).items()},
        "run_manifest": run_manifest or {},
    }
    canonical = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def refresh_manifest_hash(payload: dict[str, Any]) -> dict[str, Any]:
    """Recompute the manifest digest after additive UI/workflow fields are attached."""
    payload = dict(payload)
    payload.pop("manifest_sha256", None)
    canonical = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload
