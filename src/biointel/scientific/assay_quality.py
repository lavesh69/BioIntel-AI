from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MOLAR_FACTORS = {
    "M": 1.0,
    "mM": 1e-3,
    "uM": 1e-6,
    "µM": 1e-6,
    "nM": 1e-9,
    "pM": 1e-12,
}
SUPPORTED_ACTIVITY_TYPES = {"Ki", "Kd", "IC50", "EC50", "AC50", "GI50", "XC50"}
SUPPORTED_RELATIONS = {"=", "<", ">", "<=", ">="}


@dataclass(frozen=True)
class AssayQualityResult:
    valid: bool
    normalized_molar: float | None
    p_activity: float | None
    quality_score: float
    flags: tuple[str, ...]


def evaluate_assay_record(record: dict[str, Any]) -> AssayQualityResult:
    flags: list[str] = []
    activity_type = str(record.get("assay_type") or record.get("standard_type") or "")
    relation = str(record.get("relation") or record.get("standard_relation") or "=")
    unit = str(record.get("unit") or record.get("standard_units") or "")
    value = record.get("value", record.get("standard_value"))
    if activity_type not in SUPPORTED_ACTIVITY_TYPES:
        flags.append("unsupported_activity_type")
    if relation not in SUPPORTED_RELATIONS:
        flags.append("invalid_relation")
    if unit not in MOLAR_FACTORS:
        flags.append("unsupported_unit")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = float("nan")
        flags.append("invalid_value")
    normalized = None
    p_activity = None
    if not math.isnan(numeric) and numeric > 0 and unit in MOLAR_FACTORS:
        normalized = numeric * MOLAR_FACTORS[unit]
        p_activity = -math.log10(normalized)
        if p_activity < 0 or p_activity > 14:
            flags.append("implausible_activity_range")
    elif not math.isnan(numeric) and numeric <= 0:
        flags.append("non_positive_value")
    if not record.get("organism"):
        flags.append("missing_organism")
    if not record.get("target_id"):
        flags.append("missing_target")
    if not record.get("molecule_id"):
        flags.append("missing_molecule")
    if not record.get("provider_record_id"):
        flags.append("missing_provider_record_id")
    if not record.get("source_url"):
        flags.append("missing_source_url")
    confidence = record.get("confidence_score")
    if confidence is not None:
        try:
            if float(confidence) < 7:
                flags.append("low_target_confidence")
        except (TypeError, ValueError):
            flags.append("invalid_confidence_score")
    critical = {"invalid_value", "non_positive_value", "unsupported_unit", "invalid_relation"}
    score = max(0.0, 10.0 - 0.8 * len(flags) - 2.0 * len(critical.intersection(flags)))
    return AssayQualityResult(not bool(critical.intersection(flags)), normalized, p_activity, round(score, 2), tuple(flags))


def duplicate_conflict(values: list[float], *, tolerance_log10: float = 1.0) -> bool:
    positives = [float(value) for value in values if value is not None and float(value) > 0]
    if len(positives) < 2:
        return False
    logs = [math.log10(value) for value in positives]
    return max(logs) - min(logs) > tolerance_log10
