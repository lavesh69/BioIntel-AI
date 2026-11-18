from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssayClassification:
    activity_type: str
    endpoint_family: str
    assay_category: str

def classify_assay(activity_type: object, assay_type: object = "", description: object = "") -> AssayClassification:
    activity = str(activity_type or "unspecified").strip().upper()
    text = f"{assay_type or ''} {description or ''}".lower()
    endpoint = {"KI":"binding_affinity","KD":"binding_affinity","IC50":"inhibition","EC50":"activation_or_response"}.get(activity, "other")
    if any(token in text for token in ("cell","cellular","phenotyp")):
        category = "cellular_or_phenotypic"
    elif any(token in text for token in ("functional","response","signal")):
        category = "functional"
    elif any(token in text for token in ("binding","affinity","biochemical")):
        category = "binding_or_biochemical"
    else:
        category = "unspecified"
    return AssayClassification(activity, endpoint, category)
