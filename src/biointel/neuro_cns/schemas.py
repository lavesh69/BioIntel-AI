from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


_CONCENTRATION_TO_NM = {
    "m": 1e9,
    "mm": 1e6,
    "um": 1e3,
    "µm": 1e3,
    "μm": 1e3,
    "nm": 1.0,
    "pm": 1e-3,
}
_TIME_TO_HOURS = {
    "s": 1.0 / 3600.0,
    "sec": 1.0 / 3600.0,
    "second": 1.0 / 3600.0,
    "seconds": 1.0 / 3600.0,
    "min": 1.0 / 60.0,
    "minute": 1.0 / 60.0,
    "minutes": 1.0 / 60.0,
    "h": 1.0,
    "hr": 1.0,
    "hour": 1.0,
    "hours": 1.0,
    "d": 24.0,
    "day": 24.0,
    "days": 24.0,
}


@dataclass(frozen=True)
class TableQualityReport:
    rows: int
    columns: int
    missing_cells: int
    missing_fraction: float
    duplicate_rows: int
    duplicate_identifiers: int
    numeric_columns: int
    constant_numeric_columns: int
    warnings: tuple[str, ...]
    fingerprint_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unit_token(unit: str) -> str:
    return re.sub(r"\s+", "", str(unit or "").strip().lower())


def concentration_to_nm(value: float, unit: str = "nM") -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("Concentration must be a finite non-negative number.")
    token = _unit_token(unit)
    if token not in _CONCENTRATION_TO_NM:
        raise ValueError(f"Unsupported concentration unit {unit!r}. Use M, mM, uM/µM, nM or pM.")
    return numeric * _CONCENTRATION_TO_NM[token]


def time_to_hours(value: float, unit: str = "hours") -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("Time must be a finite non-negative number.")
    token = _unit_token(unit)
    if token not in _TIME_TO_HOURS:
        raise ValueError(f"Unsupported time unit {unit!r}. Use seconds, minutes, hours or days.")
    return numeric * _TIME_TO_HOURS[token]


def require_columns(frame: pd.DataFrame, required: Iterable[str], *, context: str = "table") -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{context} is missing required column(s): {', '.join(missing)}")


def frame_fingerprint(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    canonical.columns = [str(column) for column in canonical.columns]
    payload = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def table_quality_report(frame: pd.DataFrame, identifier_column: str | None = None) -> TableQualityReport:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("A pandas DataFrame is required.")
    rows, columns = frame.shape
    missing_cells = int(frame.isna().sum().sum())
    total_cells = max(rows * columns, 1)
    duplicate_rows = int(frame.duplicated().sum()) if rows else 0
    duplicate_identifiers = 0
    warnings: list[str] = []
    if identifier_column:
        if identifier_column in frame.columns:
            identifiers = frame[identifier_column].astype("string")
            duplicate_identifiers = int(identifiers[identifiers.notna()].duplicated().sum())
            if duplicate_identifiers:
                warnings.append(f"{duplicate_identifiers} duplicate identifier value(s)")
        else:
            warnings.append(f"Identifier column {identifier_column!r} is absent")
    numeric = frame.select_dtypes(include=[np.number])
    constant_numeric = int(sum(numeric[column].nunique(dropna=True) <= 1 for column in numeric.columns))
    missing_fraction = float(missing_cells / total_cells)
    if missing_fraction > 0.20:
        warnings.append(f"High missingness ({missing_fraction:.1%})")
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} duplicate row(s)")
    if constant_numeric:
        warnings.append(f"{constant_numeric} constant numeric feature(s)")
    if rows < 5:
        warnings.append("Very small table; statistical outputs will be unstable")
    if columns > 5000:
        warnings.append("Very wide table; memory and multiple-testing burden may be high")
    return TableQualityReport(
        rows=int(rows),
        columns=int(columns),
        missing_cells=missing_cells,
        missing_fraction=round(missing_fraction, 6),
        duplicate_rows=duplicate_rows,
        duplicate_identifiers=duplicate_identifiers,
        numeric_columns=int(numeric.shape[1]),
        constant_numeric_columns=constant_numeric,
        warnings=tuple(warnings),
        fingerprint_sha256=frame_fingerprint(frame),
    )


def normalize_affinity_rows(
    rows: Iterable[dict[str, Any]],
    *,
    default_unit: str = "nM",
    target_keys: tuple[str, ...] = ("target", "target_id", "gene"),
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        target = next((str(row.get(key)).strip() for key in target_keys if row.get(key) not in (None, "")), "")
        raw = row.get("kd", row.get("ki", row.get("affinity", row.get("affinity_value"))))
        unit = str(row.get("unit") or row.get("affinity_unit") or default_unit)
        record: dict[str, Any] = {"source_row": index + 1, "target": target, "input_unit": unit}
        if not target:
            record.update({"affinity_nm": np.nan, "error": "missing target"})
            normalized.append(record)
            continue
        try:
            record.update({"affinity_nm": concentration_to_nm(float(raw), unit), "error": None})
        except (TypeError, ValueError) as exc:
            record.update({"affinity_nm": np.nan, "error": str(exc)})
        normalized.append(record)
    return normalized


def validate_probability(value: float, *, name: str = "probability") -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be a finite value between 0 and 1.")
    return numeric
