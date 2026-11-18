from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from biointel.scientific.validation_depth import (
    SiteAttestation,
    ValidationEvidenceRegistry,
    build_step40_validation_readiness,
    sha256_text,
)


def _hash(label: str) -> str:
    return sha256_text(label)


def _site(site_id: str, org: str, country: str, independent: bool = True) -> SiteAttestation:
    return SiteAttestation(site_id, f"{org} laboratory", country, org, "ISO/IEC 17025 or declared GLP system", independent, _hash(f"attestation:{site_id}"))


def _times():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return start.isoformat(), (start + timedelta(days=1)).isoformat(), (start + timedelta(days=2)).isoformat()


def _outcomes(site_id: str, count: int = 100):
    return [
        {
            "sample_id": f"S{i:04d}", "prediction": (i % 10) / 10, "uncertainty": 0.08,
            "outcome": 1.0 if i % 2 else 0.0, "blinded_code": f"BL-{i:04d}",
            "site_id": site_id, "measured_at": "2026-01-03T00:00:00+00:00",
        }
        for i in range(count)
    ]




def _dti_metrics(multisite: bool = False):
    rows = [
        {"split_name":"independent_external","metric_name":"roc_auc","metric_value":0.82,"ci_lower":0.78,"ci_upper":0.86,"threshold":0.75,"passed":True},
        {"split_name":"independent_external","metric_name":"balanced_accuracy","metric_value":0.74,"ci_lower":0.69,"ci_upper":0.79,"threshold":0.65,"passed":True},
        {"split_name":"independent_external","metric_name":"ece","metric_value":0.06,"ci_lower":0.04,"ci_upper":0.08,"threshold":0.10,"passed":True},
        {"split_name":"independent_external","metric_name":"interval_coverage","metric_value":0.91,"ci_lower":0.87,"ci_upper":0.94,"threshold":0.85,"passed":True},
    ]
    if multisite:
        rows.extend([
            {"split_name":"multisite","metric_name":"site_effect","metric_value":0.03,"ci_lower":0.01,"ci_upper":0.06,"threshold":0.10,"passed":True},
            {"split_name":"multisite","metric_name":"heterogeneity_i2","metric_value":0.18,"ci_lower":0.08,"ci_upper":0.31,"threshold":0.50,"passed":True},
        ])
    return rows

def _review(org: str = "review-org"):
    return [{
        "reviewer_organization": org, "reviewer_identity": "reviewer-001", "independent": True,
        "decision": "approved", "signature_sha256": _hash(f"review:{org}"),
        "reviewed_at": "2026-01-04T00:00:00+00:00", "notes": "Independent protocol and result review.",
    }]


def _payload(evidence_class: str, *, sponsor: str = "sponsor-org", analytical_only: bool = True):
    prereg, locked, completed = _times()
    return {
        "study_id": f"TEST-{evidence_class}", "title": evidence_class, "domain": "dti",
        "study_type": "validation", "evidence_class": evidence_class, "status": "completed",
        "sponsor_organization": sponsor, "coordinator_organization": "coord-org",
        "source_provider": "bindingdb", "training_provider": "chembl",
        "dataset_sha256": _hash("dataset"), "model_sha256": _hash("model"),
        "protocol_sha256": _hash("protocol"), "manifest_sha256": _hash("manifest"),
        "preregistered_at": prereg, "locked_at": locked, "completed_at": completed,
        "blinded": True, "analytical_only": analytical_only,
    }


def test_placeholder_hashes_are_never_release_eligible(tmp_path: Path):
    registry = ValidationEvidenceRegistry(tmp_path / "validation.sqlite3")
    payload = _payload("independent_external_analytical")
    payload["dataset_sha256"] = "step39-dataset-sha256-placeholder"
    site = _site("site-a", "external-org", "IN")
    study = registry.register_study(payload=payload, sites=[site], outcomes=_outcomes(site.site_id), metrics=_dti_metrics(), reviews=_review())
    assert not study.release_eligible
    assert any("placeholder" in blocker for blocker in study.blockers)


def test_valid_independent_external_analytical_study_passes(tmp_path: Path):
    registry = ValidationEvidenceRegistry(tmp_path / "validation.sqlite3")
    site = _site("site-a", "external-org", "IN")
    study = registry.register_study(
        payload=_payload("independent_external_analytical"), sites=[site],
        outcomes=_outcomes(site.site_id), reviews=_review(),
        metrics=_dti_metrics(),
    )
    assert study.release_eligible
    assert not study.blockers
    assert registry.summary()["completed_external_dti"] == 1
    assert registry.verify_integrity()["ok"]


def test_multisite_wetlab_requires_three_independent_orgs_and_two_countries(tmp_path: Path):
    registry = ValidationEvidenceRegistry(tmp_path / "validation.sqlite3")
    sites = [_site("site-a", "lab-a", "IN"), _site("site-b", "lab-b", "GB"), _site("site-c", "lab-c", "IN")]
    outcomes = []
    for i in range(102):
        site = sites[i % len(sites)]
        outcomes.append({
            "sample_id": f"M{i:04d}", "prediction": 0.8 if i % 2 else 0.2, "uncertainty": 0.05,
            "outcome": 1.0 if i % 2 else 0.0, "blinded_code": f"MB-{i:04d}",
            "site_id": site.site_id, "measured_at": "2026-01-03T00:00:00+00:00",
        })
    study = registry.register_study(
        payload=_payload("wet_lab_multisite", analytical_only=False), sites=sites, outcomes=outcomes,
        metrics=_dti_metrics(multisite=True), reviews=_review("independent-review-board")
    )
    assert study.release_eligible
    assert registry.summary()["completed_multisite"] == 1


def test_wetlab_self_attestation_is_blocked(tmp_path: Path):
    registry = ValidationEvidenceRegistry(tmp_path / "validation.sqlite3")
    sponsor_site = _site("site-s", "sponsor-org", "IN", independent=False)
    study = registry.register_study(
        payload=_payload("wet_lab_independent", analytical_only=False), sites=[sponsor_site],
        outcomes=_outcomes(sponsor_site.site_id), metrics=_dti_metrics(), reviews=_review("sponsor-org"),
    )
    assert not study.release_eligible
    assert any("sponsor-independent" in item or "Independent approved review" in item for item in study.blockers)


def test_step40_implementation_matrix_is_complete():
    root = Path(__file__).resolve().parents[2]
    report = build_step40_validation_readiness(root)
    assert report["implementation_average"] == 10.0
    assert report["capability_count"] == 22
    assert report["integrity"]["ok"]
    # Evidence scores are allowed to remain below ten until external/lab evidence exists.
    assert report["evidence_average"] < 10.0
