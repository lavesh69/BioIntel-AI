from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

import pandas as pd


REQUIRED_METADATA: tuple[str, ...] = (
    "instrument_id",
    "serial_number",
    "software_version",
    "method_id",
    "method_version",
    "operator",
    "run_date_utc",
    "calibration_date_utc",
    "calibration_due_utc",
    "sop_version",
)


@dataclass(frozen=True)
class InstrumentImportQualification:
    profile: str
    raw_sha256: str
    row_count: int
    column_count: int
    canonical_mapping_count: int
    duplicate_semantic_mappings: tuple[str, ...]
    missing_metadata: tuple[str, ...]
    calibration_current: bool
    raw_file_preserved: bool
    reviewer: str
    reviewed_at_utc: str
    qualification_status: str
    blockers: tuple[str, ...]


def _parse_utc(value: Any) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return None
    return timestamp


def audit_instrument_import(
    frame: pd.DataFrame,
    *,
    raw_bytes: bytes,
    metadata: Mapping[str, Any] | None = None,
    source_map: Mapping[str, str] | None = None,
    profile: str = "Generic table",
    raw_file_preserved: bool = True,
    reviewer: str = "",
    reviewed_at_utc: str = "",
    now_utc: str | None = None,
) -> InstrumentImportQualification:
    metadata = dict(metadata or {})
    mapping = {str(k): str(v) for k, v in dict(source_map or {}).items()}
    blockers: list[str] = []

    reverse: dict[str, list[str]] = {}
    for semantic, source in mapping.items():
        reverse.setdefault(source.strip().lower(), []).append(semantic)
    duplicate_mappings = tuple(
        sorted(source for source, semantics in reverse.items() if source and len(semantics) > 1)
    )
    if duplicate_mappings:
        blockers.append("One source column is assigned to multiple semantic fields.")

    missing = tuple(key for key in REQUIRED_METADATA if not str(metadata.get(key, "")).strip())
    if missing:
        blockers.append("Required instrument/method metadata is incomplete.")

    now = _parse_utc(now_utc) if now_utc else pd.Timestamp(datetime.now(UTC))
    calibration_date = _parse_utc(metadata.get("calibration_date_utc"))
    calibration_due = _parse_utc(metadata.get("calibration_due_utc"))
    calibration_current = bool(
        calibration_date is not None
        and calibration_due is not None
        and calibration_date <= now <= calibration_due
    )
    if not calibration_current:
        blockers.append("Instrument calibration is missing, invalid or expired.")
    if not raw_bytes:
        blockers.append("Raw instrument payload is empty.")
    if not raw_file_preserved:
        blockers.append("Immutable raw-file preservation is not confirmed.")
    if frame.empty:
        blockers.append("Normalized instrument table contains no records.")
    if profile.strip().lower() == "generic table":
        blockers.append("Instrument/vendor profile was not positively identified.")
    if not reviewer.strip() or not reviewed_at_utc.strip():
        blockers.append("Qualified reviewer and review timestamp are required.")

    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return InstrumentImportQualification(
        profile=profile.strip() or "Generic table",
        raw_sha256=raw_sha256,
        row_count=int(len(frame)),
        column_count=int(len(frame.columns)),
        canonical_mapping_count=len(mapping),
        duplicate_semantic_mappings=duplicate_mappings,
        missing_metadata=missing,
        calibration_current=calibration_current,
        raw_file_preserved=bool(raw_file_preserved),
        reviewer=reviewer.strip(),
        reviewed_at_utc=reviewed_at_utc.strip(),
        qualification_status="Qualified" if not blockers else "Blocked",
        blockers=tuple(dict.fromkeys(blockers)),
    )


def qualification_to_dict(result: InstrumentImportQualification) -> dict[str, Any]:
    return asdict(result)


__all__ = [
    "InstrumentImportQualification",
    "REQUIRED_METADATA",
    "audit_instrument_import",
    "qualification_to_dict",
]
