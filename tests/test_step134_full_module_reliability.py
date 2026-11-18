from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_all_pages_have_direct_or_production_bootstrap() -> None:
    from biointel.engineering.module_reliability import audit_page_bootstraps

    rows = audit_page_bootstraps(
        ROOT,
        production_bootstrap_pages={"pages/157_Instrument_Integration_Hub_2.py"},
    )
    assert len(rows) >= 206  # additive releases may introduce further Streamlit pages
    assert all(item.passed for item in rows)
    production = [item for item in rows if item.production_bootstrap_allowed]
    assert [item.page for item in production] == ["pages/157_Instrument_Integration_Hub_2.py"]


def test_reported_direct_page_crashes_are_self_bootstrapped() -> None:
    affected = {
        86,
        154,
        155,
        156,
        158,
        159,
        160,
        161,
        162,
        163,
        164,
        165,
        169,
        170,
        172,
    }
    for number in affected:
        page = next((ROOT / "pages").glob(f"{number}_*.py"))
        text = page.read_text(encoding="utf-8")
        first_import = min(
            index
            for index in (text.find("from biointel"), text.find("import biointel"))
            if index >= 0
        )
        assert "sys.path.insert" in text[:first_import], page.name
        assert 'ROOT / "src"' in text[:first_import], page.name


def test_lightweight_model_discovery_never_deserializes_every_estimator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import biointel.training.model_artifact as module

    model = tmp_path / "candidate.joblib"
    model.write_bytes(b"not-deserialized-during-catalogue-load")
    model.with_suffix(".json").write_text(
        json.dumps(
            {
                "artifact_version": module.ARTIFACT_VERSION,
                "feature_schema": {"feature_hash": "a" * 64},
            }
        ),
        encoding="utf-8",
    )

    def fail_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("catalogue discovery must not deserialize the estimator")

    monkeypatch.setattr(module.joblib, "load", fail_load)
    models, rejected = module.discover_model_artifact_candidates(tmp_path)
    assert models == [model.resolve()]
    assert rejected == {}


def test_lightweight_model_discovery_rejects_missing_or_invalid_sidecar(tmp_path: Path) -> None:
    from biointel.training.model_artifact import discover_model_artifact_candidates

    (tmp_path / "missing.joblib").write_bytes(b"x")
    invalid = tmp_path / "invalid.joblib"
    invalid.write_bytes(b"x")
    invalid.with_suffix(".json").write_text("{}", encoding="utf-8")
    models, rejected = discover_model_artifact_candidates(tmp_path)
    assert not models
    assert set(rejected) == {"missing.joblib", "invalid.joblib"}


def test_visual_intelligence_connection_closes_after_context(tmp_path: Path) -> None:
    from biointel.nextgen.visual_intelligence_v132 import connect

    database = tmp_path / "visual.sqlite3"
    with connect(tmp_path, path=database) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_assurance_snapshot_fast_path_skips_repository_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import biointel.assurance.cache as module

    reports = tmp_path / "reports"
    reports.mkdir()
    expected = {"version": "cached", "checks": []}
    (reports / "final_assurance_cache.json").write_text(
        json.dumps({"fingerprint": "old", "report": expected}), encoding="utf-8"
    )

    def fail_fingerprint(_root: object) -> str:
        raise AssertionError("default page load should use the verified snapshot")

    monkeypatch.setattr(module, "final_assurance_fingerprint", fail_fingerprint)
    assert module.build_final_assurance_cached(
        tmp_path, validate_fingerprint=False
    ) == expected


def test_no_raw_sqlite_connections_outside_managed_core() -> None:
    from biointel.engineering.module_reliability import source_connection_audit

    audit = source_connection_audit(ROOT)
    assert audit["passed"], audit["violations"]


def test_release_gate_does_not_eagerly_load_selected_estimator() -> None:
    text = (ROOT / "pages/45_Scientific_Release_Gate.py").read_text(encoding="utf-8")
    button = text.index('if st.button("Evaluate release gate"')
    load = text.index("artifact = load_model_artifact_cached")
    assert load > button
    assert "discover_model_artifact_candidates" in text


def test_protected_page_hashes_unchanged_from_step133() -> None:
    import hashlib

    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_tenant_store_initialisation_is_idempotent(tmp_path: Path) -> None:
    from biointel.multitenancy.store import TenantStore

    database = tmp_path / "tenants.sqlite3"
    TenantStore(database)
    with sqlite3.connect(database) as connection:
        first = connection.execute(
            "SELECT updated_at_utc FROM tenants WHERE tenant_id='default'"
        ).fetchone()[0]
    TenantStore(database)
    with sqlite3.connect(database) as connection:
        second = connection.execute(
            "SELECT updated_at_utc FROM tenants WHERE tenant_id='default'"
        ).fetchone()[0]
    assert second == first
