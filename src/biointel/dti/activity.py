from __future__ import annotations

import math
from dataclasses import dataclass

SUPPORTED_ACTIVITY_TYPES = {"KD", "KI", "IC50", "EC50"}
UNIT_TO_MOLAR = {
    "M": 1.0,
    "MM": 1e-3,
    "UM": 1e-6,
    "ΜM": 1e-6,
    "NM": 1e-9,
    "PM": 1e-12,
}


@dataclass(frozen=True)
class StandardizedActivity:
    activity_type: str
    original_value: float
    original_unit: str
    molar_value: float
    p_activity: float


def standardize_activity(activity_type: str, value: float, unit: str) -> StandardizedActivity:
    """Convert a supported positive concentration to molar and pActivity."""

    normalized_type = activity_type.strip().upper()
    normalized_unit = unit.strip().upper()

    if normalized_type not in SUPPORTED_ACTIVITY_TYPES:
        raise ValueError(
            "Unsupported activity type. Supported values: "
            + ", ".join(sorted(SUPPORTED_ACTIVITY_TYPES))
        )
    if normalized_unit not in UNIT_TO_MOLAR:
        raise ValueError("Unsupported activity unit. Use M, mM, uM/µM, nM or pM.")

    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError("Activity value must be a finite positive number.")

    molar = numeric * UNIT_TO_MOLAR[normalized_unit]
    return StandardizedActivity(
        activity_type=normalized_type,
        original_value=numeric,
        original_unit=unit,
        molar_value=molar,
        p_activity=-math.log10(molar),
    )
