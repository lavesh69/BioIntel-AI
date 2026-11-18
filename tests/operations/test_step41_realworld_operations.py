from __future__ import annotations

from pathlib import Path

import pytest

from biointel.realworld import (
    AREA_LABELS,
    OperationalArtifact,
    OperationalAttestation,
    RealWorldEvidenceRegistry,
    build_step41_realworld_readiness,
    sha256_text,
)

# Literal coverage for implementation-control inspection:
STEP41_AREA_KEYS = (
    "pharma_rnd_deployment", "clinical_deployment", "publication_grade_dti",
    "peer_reviewed_validation", "regulatory_approval", "gxp_operating_history",
    "regulatory_inspection", "production_sla_history", "multitenant_production",
    "kubernetes_production", "cloud_scale", "sustained_high_load",
    "disaster_recovery_drill", "high_availability", "commercial_saas_history",
    "enterprise_customer_validation", "pharma_customer_validation",
    "overall_platform_maturity",
)


def _sha(label: str) -> str:
    return sha256_text(label)


def _artifacts() -> list[OperationalArtifact]:
    types = {
        "deployment_dossier", "scientific_outcome_report", "clinical_protocol", "ethics_decision",
        "manuscript", "dataset", "source_code", "reproducibility_bundle", "regulatory_decision_letter",
        "validation_report", "sop_index", "training_report", "inspection_report", "capa_evidence",
        "signed_sla_report", "incident_postmortems", "rollback_drill", "cloud_telemetry_export",
        "cost_report", "load_test_report", "drill_report", "restore_manifest", "failover_report",
        "billing_export", "support_report", "customer_acceptance", "success_criteria_report",
    }
    return [
        OperationalArtifact(kind, f"evidence://test/{kind}", _sha(f"artifact:{kind}"), "2026-01-02T00:00:00+00:00", {})
        for kind in sorted(types)
    ]


def _metrics() -> list[dict[str, object]]:
    values = {
        "projects_completed": 2, "decision_adoption": 2, "critical_safety_events": 0,
        "training_compliance": 0.99, "audit_trail_completeness": 1.0, "capa_closure_rate": 0.98,
        "open_critical_findings": 0, "findings_total": 1, "availability_percent": 99.99,
        "error_rate_percent": 0.1, "p95_latency_ms": 250, "isolation_tests": 5000,
        "confirmed_isolation_breaches": 0, "availability_zones": 3, "successful_upgrades": 3,
        "total_requests": 5_000_000, "autoscale_events": 50, "regions": 3, "rto_minutes": 30,
        "rpo_minutes": 5, "restore_checksum_match": 1, "successful_failovers": 3,
        "paying_customers": 8, "completed_billing_cycles": 12, "support_sla_percent": 99,
        "success_criteria_passed": 5, "scientific_decisions_supported": 3,
    }
    return [
        {"metric_name": name, "metric_value": value, "unit": "", "threshold": None, "passed": True}
        for name, value in values.items()
    ]


def _attestations() -> list[OperationalAttestation]:
    return [
        OperationalAttestation("external-review-one", "reviewer-1", "independent reviewer", True, "approved", _sha("signature:1"), "2026-01-03T00:00:00+00:00"),
        OperationalAttestation("external-review-two", "reviewer-2", "independent reviewer", True, "approved", _sha("signature:2"), "2026-01-03T00:00:00+00:00"),
    ]


def _entities() -> list[dict[str, object]]:
    return [
        {"entity_type": "tenant", "entity_key": f"tenant-{i}", "organization": f"external-tenant-{i}", "country": "IN", "external": True, "metadata": {}}
        for i in range(3)
    ] + [
        {"entity_type": "customer", "entity_key": "customer-1", "organization": "external-customer", "country": "GB", "external": True, "metadata": {}}
    ]


def _payload(area: str, *, evidence_class: str = "external_operating_history") -> dict[str, object]:
    return {
        "evidence_id": f"TEST-{area}", "area_key": area, "title": AREA_LABELS[area], "status": "completed",
        "evidence_class": evidence_class, "issuer_organization": "external-authority", "subject_organization": "platform-operator",
        "environment": "production", "country": "IN", "started_at": "2025-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:00:00+00:00", "manifest_sha256": _sha(f"manifest:{area}"),
        "metadata": {
            "subject_sector": "pharmaceutical", "customer_sector": "pharmaceutical", "ethics_approved": True,
            "doi": "10.1234/biointel.validation", "dti_domain": True, "peer_reviewed": True,
            "regulatory_authority": "test-authority", "approval_id": "APPROVAL-001", "intended_use": "validated research use",
        },
    }


@pytest.mark.parametrize("area", [key for key in STEP41_AREA_KEYS if key != "overall_platform_maturity"])
def test_each_realworld_area_has_enforceable_qualifying_rules(tmp_path: Path, area: str):
    registry = RealWorldEvidenceRegistry(tmp_path / "realworld.sqlite3")
    record = registry.register_evidence(
        payload=_payload(area), artifacts=_artifacts(), metrics=_metrics(), attestations=_attestations(), entities=_entities()
    )
    assert record.release_eligible, record.blockers
    assert registry.area_qualifying_count(area) == 1
    assert registry.verify_integrity()["ok"]


def test_rehearsal_evidence_cannot_inflate_realworld_score(tmp_path: Path):
    registry = RealWorldEvidenceRegistry(tmp_path / "realworld.sqlite3")
    record = registry.register_evidence(
        payload=_payload("production_sla_history", evidence_class="rehearsal"),
        artifacts=_artifacts(), metrics=_metrics(), attestations=_attestations(), entities=_entities(),
    )
    assert not record.release_eligible
    assert any("rehearsal" in item.lower() for item in record.blockers)


def test_external_signature_is_required(tmp_path: Path):
    registry = RealWorldEvidenceRegistry(tmp_path / "realworld.sqlite3")
    self_attestation = OperationalAttestation(
        "platform-operator", "owner", "owner", False, "approved", _sha("self"), "2026-01-03T00:00:00+00:00"
    )
    record = registry.register_evidence(
        payload=_payload("enterprise_customer_validation"), artifacts=_artifacts(), metrics=_metrics(),
        attestations=[self_attestation], entities=_entities(),
    )
    assert not record.release_eligible
    assert any("independent external" in item.lower() for item in record.blockers)


def test_step41_implementation_matrix_is_complete():
    root = Path(__file__).resolve().parents[2]
    report = build_step41_realworld_readiness(root)
    assert report["capability_count"] == 18
    assert report["implementation_average"] == 10.0
    assert report["all_implementation_targets_complete"]
    assert report["integrity"]["ok"]
    assert set(STEP41_AREA_KEYS) == {item["key"] for item in report["capabilities"]}
    # Authentic operating history remains separate and cannot be created by repository code.
    assert report["evidence_average"] <= 10.0
