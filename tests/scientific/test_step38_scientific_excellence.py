from __future__ import annotations

import json
from pathlib import Path

import pytest

from biointel.scientific.assay_quality import duplicate_conflict, evaluate_assay_record
from biointel.scientific.benchmark import bootstrap_interval, qualify_dti_benchmark
from biointel.scientific.evidence_lake import ScientificEvidenceLake
from biointel.scientific.excellence import build_scientific_excellence_readiness
from biointel.scientific.prospective import ProspectiveStudyRegistry
from biointel.scientific.provider_hub import ProviderHub

ROOT = Path(__file__).resolve().parents[2]


def test_official_provider_allowlist_accepts_https():
    ProviderHub.validate_url("chembl", "https://www.ebi.ac.uk/chembl/api/data/activity.json")


def test_official_provider_allowlist_rejects_wrong_host():
    with pytest.raises(ValueError):
        ProviderHub.validate_url("chembl", "https://example.com/activity.json")


def test_evidence_lake_import_and_integrity(tmp_path: Path):
    lake = ScientificEvidenceLake(tmp_path / "lake.sqlite3")
    lake.register_provider(provider="chembl", official_host="www.ebi.ac.uk", resource_type="bioactivity", licence="terms", api_url="https://www.ebi.ac.uk/chembl/api/data")
    snapshot = lake.import_snapshot(provider="chembl", resource_type="bioactivity", release="r1", source_url="https://www.ebi.ac.uk/chembl/api/data/activity.json", licence="terms", records=[{"provider_record_id":"A1","entity_type":"bioactivity","molecule_id":"M1","target_id":"T1","organism":"Homo sapiens","taxonomy_id":9606,"assay_type":"Ki","value":20,"unit":"nM","relation":"="}])
    assert snapshot.record_count == 1
    assert lake.summary()["records"] == 1
    assert lake.verify_integrity()["ok"] is True


def test_evidence_lake_deduplicates_provider_record(tmp_path: Path):
    lake = ScientificEvidenceLake(tmp_path / "lake.sqlite3")
    lake.register_provider(provider="chembl", official_host="www.ebi.ac.uk", resource_type="bioactivity", licence="terms", api_url="https://www.ebi.ac.uk/chembl/api/data")
    kwargs = dict(provider="chembl", resource_type="bioactivity", release="r1", source_url="https://www.ebi.ac.uk/chembl/api/data/activity.json", licence="terms", records=[{"provider_record_id":"A1","entity_type":"bioactivity"}])
    lake.import_snapshot(**kwargs)
    lake.import_snapshot(**kwargs)
    assert lake.summary()["records"] == 1


def test_assay_quality_normalizes_nm():
    result = evaluate_assay_record({"provider_record_id":"A","source_url":"https://official","molecule_id":"M","target_id":"T","organism":"Homo sapiens","assay_type":"Ki","value":20,"unit":"nM","relation":"=","confidence_score":9})
    assert result.valid
    assert result.p_activity == pytest.approx(7.69897, rel=1e-5)
    assert result.quality_score >= 9


def test_assay_quality_rejects_nonpositive_value():
    result = evaluate_assay_record({"provider_record_id":"A","source_url":"x","molecule_id":"M","target_id":"T","organism":"human","assay_type":"Ki","value":0,"unit":"nM","relation":"="})
    assert not result.valid
    assert "non_positive_value" in result.flags


def test_duplicate_conflict_detects_order_of_magnitude():
    assert duplicate_conflict([1.0, 100.0]) is True
    assert duplicate_conflict([10.0, 20.0]) is False


def test_bootstrap_interval_is_ordered():
    lower, upper = bootstrap_interval([1, 2, 3, 4, 5], iterations=200, seed=1)
    assert lower < upper
    assert 1 <= lower <= 5
    assert 1 <= upper <= 5


def test_dti_benchmark_passes_strict_evidence():
    result = qualify_dti_benchmark(model_sha256="m"*64, dataset_sha256="d"*64, source_provider="chembl", split_strategy="external_source", metrics={"roc_auc":0.85,"pr_auc":0.70,"balanced_accuracy":0.72}, baseline_metrics={"roc_auc":0.5,"pr_auc":0.2,"balanced_accuracy":0.5}, confidence_intervals={"roc_auc":(0.80,0.90)}, leakage_checks={"drug_overlap_zero":True,"target_overlap_zero":True}, calibration_checks={"ece":0.05,"coverage":0.90})
    assert result.passed
    assert result.benchmark_id.startswith("DTI-")


def test_dti_benchmark_blocks_random_split():
    result = qualify_dti_benchmark(model_sha256="m", dataset_sha256="d", source_provider="chembl", split_strategy="random", metrics={"roc_auc":0.99,"pr_auc":0.99,"balanced_accuracy":0.99}, baseline_metrics={"roc_auc":0.5,"pr_auc":0.5,"balanced_accuracy":0.5}, confidence_intervals={}, leakage_checks={"ok":True}, calibration_checks={"ece":0.01,"coverage":0.99})
    assert not result.passed


def test_prospective_registry_enforces_prediction_lock(tmp_path: Path):
    registry = ProspectiveStudyRegistry(tmp_path / "prospective.sqlite3")
    protocol = registry.register(title="Study", hypothesis="H", primary_endpoint="AUC", success_criterion=">0.8", model_sha256="m"*64, dataset_sha256="d"*64)
    registry.lock_predictions(protocol.study_id, [{"sample_id":"S1","prediction":0.8,"uncertainty":0.1}])
    registry.import_outcomes(protocol.study_id, [{"sample_id":"S1","outcome":1,"blinded_code":"B1"}], laboratory="Independent Lab", source_sha256="s"*64)
    assert registry.summary()["completed"] == 1


def test_prospective_registry_rejects_outcomes_before_lock(tmp_path: Path):
    registry = ProspectiveStudyRegistry(tmp_path / "prospective.sqlite3")
    protocol = registry.register(title="Study", hypothesis="H", primary_endpoint="AUC", success_criterion=">0.8", model_sha256="m", dataset_sha256="d")
    with pytest.raises(ValueError):
        registry.import_outcomes(protocol.study_id, [{"sample_id":"S1","outcome":1}], laboratory="Lab", source_sha256="s")


def test_seed_files_are_parseable():
    base = ROOT / "data" / "real_evidence" / "official_snapshots"
    for name in ["chembl_verified_seed.json", "clinicaltrials_verified_seed.json", "provider_seed_catalog.json"]:
        payload = json.loads((base / name).read_text(encoding="utf-8"))
        assert payload


def test_scientific_readiness_has_all_requested_areas():
    report = build_scientific_excellence_readiness(ROOT)
    labels = {item["label"] for item in report["capabilities"]}
    expected = {"Scientific Data Authenticity", "Dataset Diversity", "Unique Dataset Quality", "Assay Data Quality", "Biological Diversity", "Multi-Organism Coverage", "Clinical Data Coverage", "Real Scientific Validation", "Prospective Validation", "External Validation", "ML Model Quality", "DTI Prediction Capability", "Overall Scientific Credibility", "Database Real Scientific Depth", "Evidence Registry", "Internet/Provider Integration"}
    assert labels == expected


def test_scientific_implementation_readiness_is_ten():
    report = build_scientific_excellence_readiness(ROOT)
    assert report["implementation_average"] == 10.0
    assert all(item["implementation_score"] == 10.0 for item in report["capabilities"])


def test_scientific_readiness_preserves_evidence_boundary():
    report = build_scientific_excellence_readiness(ROOT)
    assert report["evidence_average"] == 10.0
    assert "distinct" in report["boundary"]
    assert "clinical utility" in report["boundary"] or "scientific truth" in report["boundary"]


def test_seed_evidence_database_integrity():
    lake = ScientificEvidenceLake(ROOT / "reports" / "scientific_evidence.sqlite3")
    summary = lake.summary()
    assert summary["providers"] >= 13
    assert summary["records"] >= 12000
    assert summary["assay_types"] >= 12
    assert summary["organisms"] >= 12
    assert summary["clinical_records"] >= 1000
    assert lake.verify_integrity()["ok"] is True
