from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalSearchStatus:
    available: bool
    enabled: bool
    detail: str


def redact_external_query(query: str) -> tuple[str, tuple[str, ...]]:
    """Remove common private record identifiers before an explicitly approved search."""
    patterns = {
        "patient_identifier": r"\b(?:patient|subject|sample)[-_: ]?[A-Z0-9]{3,}\b",
        "project_identifier": r"\bPROJECT[-_:][A-Z0-9_-]+\b",
        "email": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    }
    value = query
    found: list[str] = []
    for label, pattern in patterns.items():
        value, count = re.subn(pattern, f"[{label.upper()} REDACTED]", value, flags=re.IGNORECASE)
        if count:
            found.append(label)
    return value, tuple(found)


def external_search_status(enabled: bool) -> ExternalSearchStatus:
    return ExternalSearchStatus(
        available=False,
        enabled=enabled,
        detail="No literature/web adapter is configured; Shiro will not fabricate external references.",
    )