from __future__ import annotations

import hashlib
import json
import math
import time
import traceback
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None


MAX_INTERACTIVE_ROWS = 100_000
MAX_INTERACTIVE_COLUMNS = 2_000
MAX_TEXT_CHARS = 5_000_000
MAX_PAYLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class ExecutionError:
    error_type: str
    message: str
    stage: str
    recovery_code: str
    safe_traceback: str | None = None


@dataclass(frozen=True)
class ExecutionEnvelope:
    schema: str
    module_key: str
    status: str
    started_at_utc: str
    elapsed_ms: float
    peak_memory_mb: float
    input_fingerprint_sha256: str
    warnings: tuple[str, ...]
    result: Any = None
    error: ExecutionError | None = None
    controlled_release_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {"columns": [str(c) for c in value.columns], "records": value.to_dict(orient="records")}
    if isinstance(value, pd.Series):
        return value.to_list()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def approximate_payload_size(value: Any) -> int:
    """Conservative payload-size estimate without recursively materialising huge arrays."""
    if value is None:
        return 0
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="replace"))
    if isinstance(value, pd.DataFrame):
        return int(value.memory_usage(index=True, deep=True).sum())
    if isinstance(value, pd.Series):
        return int(value.memory_usage(index=True, deep=True))
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, Mapping):
        return sum(approximate_payload_size(k) + approximate_payload_size(v) for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return sum(approximate_payload_size(v) for v in value)
    return 64


def validate_payload(value: Any, *, interactive: bool = True) -> tuple[str, ...]:
    size = approximate_payload_size(value)
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Input payload is approximately {size / 1024 / 1024:.1f} MB; the safe limit is "
            f"{MAX_PAYLOAD_BYTES / 1024 / 1024:.0f} MB. Use the background queue or split the input."
        )
    warnings: list[str] = []

    def inspect(item: Any, path: str = "input") -> None:
        if isinstance(item, pd.DataFrame):
            if item.shape[1] > MAX_INTERACTIVE_COLUMNS:
                raise ValueError(f"{path} has {item.shape[1]} columns; maximum supported is {MAX_INTERACTIVE_COLUMNS}.")
            if interactive and len(item) > MAX_INTERACTIVE_ROWS:
                warnings.append(f"{path} has {len(item):,} rows; background execution is recommended.")
            duplicate_columns = item.columns[item.columns.duplicated()].astype(str).tolist()
            if duplicate_columns:
                raise ValueError(f"{path} contains duplicate columns: {', '.join(duplicate_columns[:10])}")
        elif isinstance(item, str) and len(item) > MAX_TEXT_CHARS:
            raise ValueError(f"{path} text exceeds the {MAX_TEXT_CHARS:,}-character safety limit.")
        elif isinstance(item, Mapping):
            for key, child in item.items():
                inspect(child, f"{path}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item[:100_001]):
                inspect(child, f"{path}[{index}]")
            if len(item) > 100_000:
                warnings.append(f"{path} contains more than 100,000 items; background execution is recommended.")

    inspect(value)
    return tuple(dict.fromkeys(warnings))


def _recovery_code(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return "INPUT_VALIDATION"
    if isinstance(exc, MemoryError) or "memory" in message:
        return "RESOURCE_EXHAUSTION"
    if isinstance(exc, FileNotFoundError) or "not installed" in message or "optional" in message:
        return "MISSING_RESOURCE"
    if "column" in message or "schema" in message:
        return "SCHEMA_MISMATCH"
    if "unit" in message:
        return "UNIT_MISMATCH"
    return "ENGINE_FAILURE"


def safe_execute(
    module_key: str,
    runner: Callable[[], Any],
    *,
    inputs: Any = None,
    parameters: Mapping[str, Any] | None = None,
    interactive: bool = True,
    include_safe_traceback: bool = False,
) -> ExecutionEnvelope:
    started = datetime.now(UTC).isoformat(timespec="seconds")
    fingerprint = stable_fingerprint({"inputs": inputs, "parameters": dict(parameters or {})})
    warnings: tuple[str, ...] = ()
    begin = time.perf_counter()
    tracemalloc.start()
    try:
        warnings = validate_payload(inputs, interactive=interactive)
        result = runner()
        _current, peak = tracemalloc.get_traced_memory()
        return ExecutionEnvelope(
            schema="biointel.neuro-cns.execution-envelope.v1",
            module_key=module_key,
            status="completed",
            started_at_utc=started,
            elapsed_ms=round((time.perf_counter() - begin) * 1000.0, 3),
            peak_memory_mb=round(peak / 1024 / 1024, 3),
            input_fingerprint_sha256=fingerprint,
            warnings=warnings,
            result=result,
        )
    except Exception as exc:
        _current, peak = tracemalloc.get_traced_memory()
        safe_tb = None
        if include_safe_traceback:
            safe_tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return ExecutionEnvelope(
            schema="biointel.neuro-cns.execution-envelope.v1",
            module_key=module_key,
            status="failed",
            started_at_utc=started,
            elapsed_ms=round((time.perf_counter() - begin) * 1000.0, 3),
            peak_memory_mb=round(peak / 1024 / 1024, 3),
            input_fingerprint_sha256=fingerprint,
            warnings=warnings,
            error=ExecutionError(
                error_type=type(exc).__name__,
                message=str(exc),
                stage="validation_or_execution",
                recovery_code=_recovery_code(exc),
                safe_traceback=safe_tb,
            ),
        )
    finally:
        tracemalloc.stop()


def numeric_frame_health(frame: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    numeric = frame.select_dtypes(include=[np.number])
    finite_count = int(np.isfinite(numeric.to_numpy(float)).sum()) if not numeric.empty else 0
    total_numeric = int(numeric.size)
    duplicate_rows = int(frame.duplicated().sum()) if len(frame) else 0
    missing_cells = int(frame.isna().sum().sum())
    constant_columns = [str(column) for column in numeric.columns if numeric[column].nunique(dropna=True) <= 1]
    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "numeric_columns": int(numeric.shape[1]),
        "missing_cells": missing_cells,
        "missing_fraction": round(missing_cells / max(frame.size, 1), 6),
        "duplicate_rows": duplicate_rows,
        "finite_numeric_fraction": round(finite_count / max(total_numeric, 1), 6),
        "constant_numeric_columns": constant_columns,
        "quality_grade": (
            "poor" if missing_cells / max(frame.size, 1) > 0.30 or duplicate_rows / max(len(frame), 1) > 0.20
            else "review" if missing_cells or constant_columns
            else "good"
        ),
    }


def finite_number(value: Any, *, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be at most {maximum}.")
    return number
