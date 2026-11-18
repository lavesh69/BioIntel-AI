from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_step170_engine_catalog_has_exactly_53_unique_engines():
    from biointel.runtime_v170 import engine_catalog
    frame = engine_catalog()
    assert len(frame) == 53
    assert frame["engine"].nunique() == 53
    assert frame["package_sha256_required"].all()
    assert frame["license_text_sha256_required"].all()
    assert frame["smoke_test_required"].all()


def test_step170_manual_and_licensed_tools_are_fail_closed():
    from biointel.runtime_v170 import engine_catalog
    frame = engine_catalog()
    manual = frame[frame["manual_distribution"].astype(bool)]
    assert set(["dorado", "netmhcpan", "netmhciipan", "proteinmpnn", "rfdiffusion"]).issubset(set(manual["engine"]))
    assert manual["licence_acceptance_mode"].astype(str).str.len().min() > 0


def test_step170_reference_catalog_has_complete_gates():
    from biointel.runtime_v170 import reference_catalog
    frame = reference_catalog()
    assert len(frame) >= 25
    assert frame["reference_id"].nunique() == len(frame)
    assert frame["release_pin_required"].all()
    assert frame["local_sha256_required"].all()
    assert frame["schema_validation_required"].all()
    assert frame["scientific_review_required"].all()


def test_step170_licence_coverage_is_complete():
    from biointel.runtime_v170 import engine_catalog, licence_catalog, reference_catalog
    licenses = set(licence_catalog()["licence_id"])
    assert set(engine_catalog()["licence_id"]).issubset(licenses)
    assert set(reference_catalog()["licence_id"]).issubset(licenses)


def test_step170_registry_starts_integrity_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "UserData"))
    from biointel.runtime_v170 import Step170Registry
    status = Step170Registry(ROOT).status()
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0
    assert status["engines_qualified"] == 0
    assert status["references_qualified"] == 0


def test_step170_download_is_dry_run_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "UserData"))
    from biointel.runtime_v170 import download_direct
    result = download_direct(ROOT, "hpo-ontology", execute=False)
    assert result["status"] == "dry-run"
    assert not Path(result["target"]).exists()


def test_step170_reference_qualification_requires_licence_and_reviewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "UserData"))
    from biointel.runtime_v170 import Step170Registry
    fake = tmp_path / "hp.obo"
    fake.write_text("format-version: 1.2\n[Term]\nid: HP:0000001\n", encoding="utf-8")
    reg = Step170Registry(ROOT)
    blocked = reg.register_reference("hpo-ontology", fake, release_id="test", scientific_reviewer="")
    assert not blocked["qualified"]
    reg.accept_licence("hpo-terms", accepted_by="Test Reviewer")
    ready = reg.register_reference("hpo-ontology", fake, release_id="test", scientific_reviewer="Domain Reviewer")
    assert ready["qualified"]


def test_step170_assets_exist():
    assert (ROOT / "data" / "step170" / "environment" / "step170-linux-64.yml").is_file()
    assert len(list((ROOT / "data" / "step170" / "engine_manifests").glob("*.json"))) == 53
    assert (ROOT / "pages" / "239_Specialist_Runtime_Reference_Qualification.py").is_file()
