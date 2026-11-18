from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FairCheck:
    principle: str
    label: str
    passed: bool
    evidence: str
    remediation: str


@dataclass(frozen=True)
class FairReport:
    score: float
    passed: int
    total: int
    findable: float
    accessible: float
    interoperable: float
    reusable: float
    checks: tuple[FairCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [asdict(item) for item in self.checks]
        return payload


def _text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key, "")
    return str(value).strip()


def _list(metadata: dict[str, Any], key: str) -> list[Any]:
    value = metadata.get(key, [])
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value] if value else []


def _check(
    principle: str,
    label: str,
    predicate: Callable[[], bool],
    evidence: str,
    remediation: str,
) -> FairCheck:
    try:
        passed = bool(predicate())
    except (TypeError, ValueError, KeyError):
        passed = False
    return FairCheck(principle, label, passed, evidence, remediation)


def evaluate_fair_object(metadata: dict[str, Any]) -> FairReport:
    """Evaluate a digital research object against machine-actionable FAIR controls.

    This is a transparent implementation profile, not an external FAIR certification.
    """

    identifier = _text(metadata, "persistent_identifier")
    identifier_scheme = identifier.split(":", 1)[0].lower() if ":" in identifier else ""
    protocol = _text(metadata, "access_protocol").lower()
    representation = _text(metadata, "representation_language").lower()
    license_value = _text(metadata, "license")
    provenance = metadata.get("provenance")
    checks = (
        _check(
            "F1", "Globally unique persistent identifier",
            lambda: identifier_scheme in {"doi", "ark", "handle", "urn", "https"} and len(identifier) >= 12,
            identifier or "missing",
            "Assign a DOI, ARK, Handle, URN or stable HTTPS identifier.",
        ),
        _check(
            "F2", "Rich metadata",
            lambda: all(_text(metadata, key) for key in ("title", "description"))
            and len(_list(metadata, "creators")) >= 1
            and len(_list(metadata, "keywords")) >= 3,
            "title, description, creators and keywords",
            "Add descriptive metadata, responsible creators and domain keywords.",
        ),
        _check(
            "F3", "Metadata includes data identifier",
            lambda: _text(metadata, "data_identifier") == identifier and bool(identifier),
            _text(metadata, "data_identifier") or "missing",
            "Embed the persistent data identifier in the metadata record.",
        ),
        _check(
            "F4", "Registered or indexed",
            lambda: bool(metadata.get("indexed")) and bool(_text(metadata, "index_name")),
            _text(metadata, "index_name") or "not indexed",
            "Register metadata in a searchable catalog or repository index.",
        ),
        _check(
            "A1", "Retrievable by standard protocol",
            lambda: protocol in {"https", "s3", "oai-pmh", "sparql", "ftp"}
            and bool(_text(metadata, "access_url")),
            f"{protocol or 'missing'} {_text(metadata, 'access_url') or ''}".strip(),
            "Provide a stable access URL over an open, documented protocol.",
        ),
        _check(
            "A1.1", "Open and implementable protocol",
            lambda: protocol in {"https", "oai-pmh", "sparql", "ftp"},
            protocol or "missing",
            "Use an open protocol or document a standards-based gateway.",
        ),
        _check(
            "A1.2", "Authentication and authorization documented",
            lambda: bool(metadata.get("authorization_documented"))
            and _text(metadata, "access_rights") in {"open", "restricted", "embargoed", "controlled"},
            _text(metadata, "access_rights") or "missing",
            "Declare access rights and the authentication/authorization procedure.",
        ),
        _check(
            "A2", "Metadata persists when data is unavailable",
            lambda: bool(metadata.get("metadata_persistence_policy"))
            and bool(_text(metadata, "tombstone_url")),
            _text(metadata, "tombstone_url") or "missing",
            "Maintain persistent metadata and a tombstone record after data withdrawal.",
        ),
        _check(
            "I1", "Formal knowledge representation",
            lambda: representation in {"json-ld", "rdf", "turtle", "xml", "csvw"},
            representation or "missing",
            "Publish metadata using JSON-LD, RDF, Turtle, XML or CSVW.",
        ),
        _check(
            "I2", "FAIR vocabularies",
            lambda: len(_list(metadata, "vocabularies")) >= 1
            and all(str(item).startswith(("http://", "https://", "urn:")) for item in _list(metadata, "vocabularies")),
            ", ".join(map(str, _list(metadata, "vocabularies"))) or "missing",
            "Use resolvable domain ontologies and controlled vocabularies.",
        ),
        _check(
            "I3", "Qualified references",
            lambda: len(_list(metadata, "qualified_references")) >= 1,
            f"{len(_list(metadata, 'qualified_references'))} qualified references",
            "Add typed links to related datasets, protocols, publications, software and models.",
        ),
        _check(
            "R1", "Rich attributes for reuse",
            lambda: all(_text(metadata, key) for key in ("publisher", "version", "resource_type"))
            and len(_list(metadata, "distributions")) >= 1,
            "publisher, version, resource type and distributions",
            "Describe version, publisher, resource type and downloadable distributions.",
        ),
        _check(
            "R1.1", "Clear data usage license",
            lambda: bool(license_value) and license_value.lower() not in {"unknown", "none", "n/a"},
            license_value or "missing",
            "Attach an explicit machine-readable data/software license.",
        ),
        _check(
            "R1.2", "Detailed provenance",
            lambda: isinstance(provenance, dict)
            and all(str(provenance.get(key, "")).strip() for key in ("source", "generated_at", "agent", "activity")),
            "structured provenance" if isinstance(provenance, dict) else "missing",
            "Record source, generation activity, responsible agent and timestamp.",
        ),
        _check(
            "R1.3", "Community standards",
            lambda: len(_list(metadata, "community_standards")) >= 1
            and bool(_text(metadata, "schema_version")),
            ", ".join(map(str, _list(metadata, "community_standards"))) or "missing",
            "Declare applicable community standards and schema version.",
        ),
    )
    buckets = {
        "F": [item for item in checks if item.principle.startswith("F")],
        "A": [item for item in checks if item.principle.startswith("A")],
        "I": [item for item in checks if item.principle.startswith("I")],
        "R": [item for item in checks if item.principle.startswith("R")],
    }

    def bucket_score(items: list[FairCheck]) -> float:
        return round(10.0 * sum(item.passed for item in items) / max(len(items), 1), 1)

    passed = sum(item.passed for item in checks)
    return FairReport(
        score=round(10.0 * passed / len(checks), 1),
        passed=passed,
        total=len(checks),
        findable=bucket_score(buckets["F"]),
        accessible=bucket_score(buckets["A"]),
        interoperable=bucket_score(buckets["I"]),
        reusable=bucket_score(buckets["R"]),
        checks=checks,
    )
