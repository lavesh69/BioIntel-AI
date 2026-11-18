from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha512
import base64
import json
import re
from typing import Any, Iterable, Mapping

import pandas as pd


_HPO_RE = re.compile(r"^HP:\d{7}$")
_CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*:[^\s]+$")


def _sha512t24u(payload: bytes) -> str:
    digest = sha512(payload).digest()[:24]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sequence_identifier(sequence: str | bytes) -> str:
    payload = sequence.encode("ascii") if isinstance(sequence, str) else bytes(sequence)
    normalized = b"".join(payload.upper().split())
    if not normalized:
        raise ValueError("Cannot create a sequence identifier for an empty sequence.")
    return f"ga4gh:SQ.{_sha512t24u(normalized)}"


def _clean_allele(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def vrs_allele(record: Mapping[str, Any], *, reference_id: str | None = None) -> dict[str, Any]:
    chrom = str(record.get("chrom") or record.get("#CHROM") or record.get("chromosome") or "").strip()
    pos = record.get("position", record.get("pos", record.get("start")))
    ref = _clean_allele(record.get("ref") or record.get("reference") or record.get("reference_allele"))
    alt = _clean_allele(record.get("alt") or record.get("alternate") or record.get("alternate_allele"))
    if not chrom or pos in (None, ""):
        raise ValueError("Variant requires chromosome and position/start.")
    try:
        start = max(0, int(float(pos)) - (1 if record.get("position") is not None or record.get("pos") is not None else 0))
    except Exception as exc:
        raise ValueError(f"Invalid variant position: {pos}") from exc
    end = start + max(1, len(ref))
    location = {
        "type": "SequenceLocation",
        "sequenceReference": {"refgetAccession": reference_id or f"biointel:{chrom}"},
        "start": start,
        "end": end,
    }
    state = {"type": "LiteralSequenceExpression", "sequence": alt or ref or "N"}
    core = {"type": "Allele", "location": location, "state": state}
    core["id"] = f"ga4gh:VA.{_sha512t24u(canonical_json(core))}"
    return core


def categorical_variant(alleles: Iterable[Mapping[str, Any]], *, label: str = "") -> dict[str, Any]:
    members = [dict(item) for item in alleles]
    if not members:
        raise ValueError("Categorical variant requires at least one member allele.")
    payload = {"type": "CanonicalVariation", "name": label or "BioIntel categorical variant", "members": members}
    payload["id"] = f"ga4gh:CX.{_sha512t24u(canonical_json(payload))}"
    return payload


def variation_statement(variation: Mapping[str, Any], *, proposition: str, evidence_level: str = "research") -> dict[str, Any]:
    statement = {
        "type": "VariationDescriptor",
        "variation": dict(variation),
        "label": proposition.strip() or "Research variation statement",
        "extensions": [{"name": "evidence_level", "value": evidence_level}],
    }
    statement["id"] = f"ga4gh:VD.{_sha512t24u(canonical_json(statement))}"
    return statement


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


def validate_phenopacket(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(document, Mapping):
        return [ValidationIssue("Block", "$", "Phenopacket document must be an object.")]
    if not document.get("id"):
        issues.append(ValidationIssue("Block", "$.id", "Phenopacket id is required."))
    subject = document.get("subject")
    if not isinstance(subject, Mapping) or not subject.get("id"):
        issues.append(ValidationIssue("Review", "$.subject.id", "Subject id is missing."))
    features = document.get("phenotypicFeatures") or document.get("phenotypic_features") or []
    if not isinstance(features, list):
        issues.append(ValidationIssue("Block", "$.phenotypicFeatures", "Phenotypic features must be an array."))
    else:
        for index, feature in enumerate(features):
            if not isinstance(feature, Mapping):
                issues.append(ValidationIssue("Block", f"$.phenotypicFeatures[{index}]", "Feature must be an object."))
                continue
            term = feature.get("type") or feature.get("term") or {}
            term_id = term.get("id") if isinstance(term, Mapping) else str(term)
            if not term_id:
                issues.append(ValidationIssue("Review", f"$.phenotypicFeatures[{index}].type.id", "Ontology term id is missing."))
            elif not _HPO_RE.match(str(term_id)):
                issues.append(ValidationIssue("Review", f"$.phenotypicFeatures[{index}].type.id", f"Expected an HPO CURIE such as HP:0000001, received {term_id}."))
    diseases = document.get("diseases") or []
    if diseases and not isinstance(diseases, list):
        issues.append(ValidationIssue("Block", "$.diseases", "Diseases must be an array."))
    meta = document.get("metaData") or document.get("meta_data")
    if not isinstance(meta, Mapping):
        issues.append(ValidationIssue("Review", "$.metaData", "Metadata/schema information is missing."))
    return issues


def normalize_curie(value: Any, *, default_prefix: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _CURIE_RE.match(text):
        prefix, suffix = text.split(":", 1)
        return f"{prefix.upper()}:{suffix}"
    return f"{default_prefix.upper()}:{text}" if default_prefix else text


def canonicalize_variants(frame: pd.DataFrame, *, reference_id: str | None = None, limit: int = 25_000) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["row_index", "vrs_id", "status", "message"])
    rows: list[dict[str, Any]] = []
    for index, row in frame.head(limit).iterrows():
        try:
            allele = vrs_allele(row.to_dict(), reference_id=reference_id)
            rows.append({"row_index": int(index), "vrs_id": allele["id"], "status": "Canonicalized", "message": "", "vrs_json": json.dumps(allele, sort_keys=True)})
        except Exception as exc:
            rows.append({"row_index": int(index), "vrs_id": "", "status": "Review", "message": str(exc), "vrs_json": ""})
    return pd.DataFrame(rows)


def drs_object(*, object_id: str, name: str, size: int, sha256: str, access_uri: str | None = None) -> dict[str, Any]:
    access_methods = []
    if access_uri:
        access_methods.append({"type": "https" if access_uri.startswith("https://") else "file", "access_url": {"url": access_uri}})
    return {
        "id": object_id,
        "name": name,
        "size": int(size),
        "checksums": [{"type": "sha-256", "checksum": sha256}],
        "access_methods": access_methods,
        "self_uri": f"drs://biointel.local/{object_id}",
    }


def htsget_request(*, data_id: str, reference_name: str, start: int, end: int, data_format: str) -> dict[str, Any]:
    if start < 0 or end <= start:
        raise ValueError("htsget interval must satisfy 0 <= start < end.")
    return {
        "format": data_format.upper(),
        "class": "body",
        "id": data_id,
        "referenceName": reference_name,
        "start": int(start),
        "end": int(end),
    }


def standards_bundle(module_key: str, frame: pd.DataFrame, *, reference_id: str | None = None) -> dict[str, Any]:
    variant_columns = {"chrom", "position", "start"}.intersection(frame.columns)
    canonical = canonicalize_variants(frame, reference_id=reference_id) if variant_columns else pd.DataFrame()
    return {
        "schema": "biointel.interoperability_bundle.v140",
        "module_key": module_key,
        "standards": {
            "VRS": "compatibility subset with sha512t24u identifiers",
            "Cat-VRS": "canonical variation export helper",
            "VA-Spec": "variation descriptor export helper",
            "Phenopackets": "local structural and ontology validation",
            "refget": "sequence digest/collection manifest helper",
            "DRS": "portable object manifest",
            "htsget": "regional request manifest",
        },
        "variant_records": canonical.to_dict("records"),
        "variant_summary": canonical["status"].value_counts().to_dict() if not canonical.empty else {},
    }


__all__ = [
    "ValidationIssue", "canonical_json", "sequence_identifier", "vrs_allele", "categorical_variant",
    "variation_statement", "validate_phenopacket", "normalize_curie", "canonicalize_variants",
    "drs_object", "htsget_request", "standards_bundle",
]
