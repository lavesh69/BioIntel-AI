from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .evidence import AREA_LABELS, build_step41_realworld_readiness


@dataclass(frozen=True)
class VerifiableCapability:
    key: str
    label: str
    implementation_score: float
    verifiable_score: float
    authentic_external_score: float
    maximum_current_score: float
    ceiling_without_external_evidence: float
    evidence_level: str
    passed_measurements: tuple[str, ...]
    missing_external_proof: tuple[str, ...]
    boundary: str


INTERNAL_SCORE_CAPS: dict[str, float] = {
    "pharma_rnd_deployment": 6.5,
    "clinical_deployment": 5.5,
    "publication_grade_dti": 8.0,
    "peer_reviewed_validation": 4.0,
    "regulatory_approval": 3.0,
    "gxp_operating_history": 7.0,
    "regulatory_inspection": 4.5,
    "production_sla_history": 7.5,
    "multitenant_production": 8.0,
    "kubernetes_production": 7.5,
    "cloud_scale": 6.5,
    "sustained_high_load": 7.5,
    "disaster_recovery_drill": 9.0,
    "high_availability": 7.0,
    "commercial_saas_history": 5.5,
    "enterprise_customer_validation": 4.0,
    "pharma_customer_validation": 4.0,
    "overall_platform_maturity": 7.0,
}

MEASUREMENT_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "pharma_rnd_deployment": (
        ("scientific_validation", "Scientific benchmark and validation package verified"),
        ("publication_bundle", "Decision-use publication/reproducibility bundle verified"),
        ("gxp_controls", "Controlled R&D operating controls verified"),
    ),
    "clinical_deployment": (
        ("clinical_reference", "Clinical-reference data and safety-control package verified"),
        ("gxp_controls", "Audit trail, controlled records and validation controls verified"),
    ),
    "publication_grade_dti": (
        ("publication_bundle", "Complete checksum-bound publication package verified"),
        ("scientific_validation", "Deterministic scientific validation report verified"),
        ("release_provenance", "Release provenance and source manifest verified"),
    ),
    "peer_reviewed_validation": (
        ("publication_bundle", "Review-ready manuscript, methods, data and code package verified"),
        ("scientific_validation", "Independent-reproduction instructions and golden results verified"),
    ),
    "regulatory_approval": (
        ("regulatory_dossier", "Regulator-ready dossier completeness verified"),
        ("gxp_controls", "Electronic-record, audit-trail and signature controls verified"),
    ),
    "gxp_operating_history": (
        ("gxp_controls", "GxP control execution and audit-chain integrity verified"),
        ("database_drill", "Controlled backup/restore and record integrity verified"),
        ("release_provenance", "Immutable release provenance verified"),
    ),
    "regulatory_inspection": (
        ("regulatory_dossier", "Inspection-ready evidence index and CAPA workflow verified"),
        ("gxp_controls", "Inspection reconstruction controls verified"),
    ),
    "production_sla_history": (
        ("api_load", "Measured API availability, latency and error-rate qualification passed"),
        ("ha_rehearsal", "Application failover rehearsal passed"),
        ("database_drill", "Restore integrity qualification passed"),
    ),
    "multitenant_production": (
        ("multitenant_isolation", "High-volume tenant isolation qualification passed"),
        ("api_load", "Tenant-capable API load qualification passed"),
    ),
    "kubernetes_production": (
        ("kubernetes_static", "Helm/Kubernetes production-control validation passed"),
        ("ha_rehearsal", "Service redundancy/failover rehearsal passed"),
        ("release_provenance", "Deployable artifact provenance verified"),
    ),
    "cloud_scale": (
        ("cloud_iac", "Cloud-neutral infrastructure-as-code qualification passed"),
        ("api_load", "Measured scale/load qualification passed"),
        ("kubernetes_static", "Autoscaling and multi-zone controls verified"),
    ),
    "sustained_high_load": (
        ("api_load", "Measured concurrent load run passed"),
        ("ha_rehearsal", "Failover under request traffic passed"),
    ),
    "disaster_recovery_drill": (
        ("database_drill", "All active databases restored with matching checksums and integrity"),
        ("release_provenance", "Restore evidence is checksum-bound to release provenance"),
    ),
    "high_availability": (
        ("ha_rehearsal", "Primary-to-secondary failover rehearsal passed"),
        ("kubernetes_static", "PDB, HPA, topology spread and multi-replica controls verified"),
        ("api_load", "Post-failover API traffic qualification passed"),
    ),
    "commercial_saas_history": (
        ("multitenant_isolation", "Tenant isolation and resource ownership verified"),
        ("saas_controls", "Entitlement, quota, billing-event and support controls verified"),
    ),
    "enterprise_customer_validation": (
        ("customer_acceptance_kit", "Enterprise UAT and acceptance package verified"),
        ("security_controls", "Enterprise security and audit controls verified"),
    ),
    "pharma_customer_validation": (
        ("customer_acceptance_kit", "Pharmaceutical UAT/scientific decision-use package verified"),
        ("gxp_controls", "GxP and scientific governance controls verified"),
        ("scientific_validation", "Scientific validation evidence package verified"),
    ),
}

EXTERNAL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "pharma_rnd_deployment": ("Sponsor-signed deployment dossier", "90+ days authentic pharmaceutical operating history"),
    "clinical_deployment": ("Approved protocol and ethics decision", "Real clinical production history"),
    "publication_grade_dti": ("Persistent DOI and public archival record",),
    "peer_reviewed_validation": ("Journal acceptance and independent peer-review record",),
    "regulatory_approval": ("Regulatory authority decision letter and approval identifier",),
    "gxp_operating_history": ("180+ days controlled operation with approved SOP execution",),
    "regulatory_inspection": ("Authority inspection report and finding closure",),
    "production_sla_history": ("90+ days signed production telemetry and incident history",),
    "multitenant_production": ("90+ days with independent external tenants",),
    "kubernetes_production": ("90+ days on a real multi-zone Kubernetes cluster",),
    "cloud_scale": ("Cloud telemetry, billing and regional production evidence",),
    "sustained_high_load": ("24-hour production-like independent load qualification",),
    "disaster_recovery_drill": ("Independently witnessed production restore drill",),
    "high_availability": ("90+ days availability and real multi-zone failover",),
    "commercial_saas_history": ("Paying customers and completed billing/support history",),
    "enterprise_customer_validation": ("External enterprise acceptance signature",),
    "pharma_customer_validation": ("External pharmaceutical customer acceptance signature",),
    "overall_platform_maturity": ("Qualifying external evidence across all operating-history areas",),
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_step42_artifacts(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    evidence_dir = base / "reports" / "step42"
    index = _load_json(evidence_dir / "evidence_index.json")
    failures: list[str] = []
    verified: dict[str, bool] = {}
    for key, item in dict(index.get("artifacts") or {}).items():
        relative = str(dict(item).get("path", ""))
        expected = str(dict(item).get("sha256", ""))
        path = base / relative
        ok = path.is_file() and len(expected) == 64 and _sha256(path) == expected
        verified[str(key)] = ok
        if not ok:
            failures.append(str(key))
    return {
        "ok": bool(verified) and not failures,
        "verified": verified,
        "verified_count": sum(verified.values()),
        "artifact_count": len(verified),
        "failures": failures,
    }


def _measurement_passes(root: Path) -> dict[str, bool]:
    verification = verify_step42_artifacts(root)
    if not verification["ok"]:
        return {key: False for rules in MEASUREMENT_RULES.values() for key, _ in rules}
    results = _load_json(Path(root).resolve() / "reports" / "step42" / "verification_results.json")
    checks = dict(results.get("checks") or {})
    return {str(key): bool(dict(value).get("passed")) for key, value in checks.items()}


def build_step42_maximum_evidence(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    step41 = build_step41_realworld_readiness(base)
    external_by_key = {item["key"]: float(item["evidence_score"]) for item in step41["capabilities"]}
    measurements = _measurement_passes(base)
    artifact_integrity = verify_step42_artifacts(base)
    capabilities: list[VerifiableCapability] = []

    for key, label in AREA_LABELS.items():
        external_score = external_by_key.get(key, 0.0)
        cap = INTERNAL_SCORE_CAPS[key]
        if key == "overall_platform_maturity":
            non_aggregate = [item for item in capabilities if item.key != "overall_platform_maturity"]
            verifiable_score = round(sum(item.verifiable_score for item in non_aggregate) / len(non_aggregate), 1) if non_aggregate else 0.0
            passed = tuple(f"{item.label}: {item.verifiable_score:.1f}/10" for item in non_aggregate if item.verifiable_score > 0)
        else:
            rules = MEASUREMENT_RULES[key]
            passed_rules = [(measurement, label_text) for measurement, label_text in rules if measurements.get(measurement, False)]
            passed = tuple(label_text for _, label_text in passed_rules)
            ratio = len(passed_rules) / len(rules)
            verifiable_score = round(cap * ratio, 1)
        maximum = max(verifiable_score, external_score)
        if external_score == 10.0:
            level = "authentic_external_qualified"
        elif verifiable_score >= 7.0:
            level = "strong_verifiable_internal_evidence"
        elif verifiable_score >= 4.0:
            level = "moderate_verifiable_internal_evidence"
        elif verifiable_score > 0:
            level = "foundational_verifiable_evidence"
        else:
            level = "implementation_only"
        capabilities.append(
            VerifiableCapability(
                key=key,
                label=label,
                implementation_score=10.0,
                verifiable_score=verifiable_score,
                authentic_external_score=external_score,
                maximum_current_score=maximum,
                ceiling_without_external_evidence=cap,
                evidence_level=level,
                passed_measurements=passed,
                missing_external_proof=EXTERNAL_REQUIREMENTS[key] if external_score < 10.0 else (),
                boundary="Measured repository qualification can raise the verifiable score only to the published cap; customers, regulators, journals and production history require genuine third-party evidence.",
            )
        )

    non_aggregate = [item for item in capabilities if item.key != "overall_platform_maturity"]
    return {
        "schema": "biointel.step42.maximum-verifiable-evidence.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "capabilities": [asdict(item) for item in capabilities],
        "capability_count": len(capabilities),
        "implementation_average": 10.0,
        "verifiable_average": round(sum(item.verifiable_score for item in non_aggregate) / len(non_aggregate), 1),
        "authentic_external_average": round(sum(item.authentic_external_score for item in non_aggregate) / len(non_aggregate), 1),
        "maximum_current_average": round(sum(item.maximum_current_score for item in non_aggregate) / len(non_aggregate), 1),
        "strong_verifiable_areas": sum(item.verifiable_score >= 7.0 for item in non_aggregate),
        "artifact_integrity": artifact_integrity,
        "measurement_status": measurements,
        "external_registry_integrity": step41["integrity"],
        "score_policy": {
            "implementation": "Repository controls, schemas, APIs and tests.",
            "verifiable": "Measured, checksum-bound repository or controlled-environment qualification evidence.",
            "authentic_external": "Independent customers, regulators, journals, laboratories or real production operating history.",
        },
    }
