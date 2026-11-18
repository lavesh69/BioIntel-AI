from __future__ import annotations

from pathlib import Path

from biointel.engine_audit_v196 import audit_catalog, audit_record, audit_summary, write_audit_reports
from biointel.native.engines import ENGINE_REGISTRY


def test_audit_covers_all_76_registered_engines() -> None:
    frame = audit_catalog()
    assert len(ENGINE_REGISTRY) == 76
    assert len(frame) == 76
    assert frame["engine"].nunique() == 76
    assert set(frame["engine"]) == set(ENGINE_REGISTRY)


def test_step212_closes_the_23_engine_catalog_gap() -> None:
    frame = audit_catalog()
    assert int((~frame["legacy_catalog_covered"].astype(bool)).sum()) == 23
    assert frame["official_url"].astype(str).str.startswith("https://").all()


def test_every_engine_has_a_windows_route_and_bundle_policy() -> None:
    frame = audit_catalog()
    for column in (
        "install_route", "windows_mode", "windows_support_level", "offline_install_feasibility",
        "recommended_pack", "priority_tier", "automatic_bundle_policy", "licence_spdx",
    ):
        assert frame[column].astype(str).str.strip().ne("").all(), column


def test_restricted_and_model_engines_fail_closed() -> None:
    for key in ("netmhcpan", "netmhciipan"):
        record = audit_record(key)
        assert record.automatic_bundle_policy == "never-auto-bundle"
        assert record.licence_acceptance_required
    for key in ("proteinmpnn", "rfdiffusion", "colabfold", "llama_cpp", "dorado"):
        record = audit_record(key)
        assert record.automatic_bundle_policy in {"separate-optional-model-pack", "do-not-bundle-until-legal-review"}
        assert record.blockers


def test_reference_engines_include_reference_blocker() -> None:
    for key, spec in ENGINE_REGISTRY.items():
        record = audit_record(key)
        if spec.required_databases:
            assert any("Reference/database" in blocker for blocker in record.blockers)


def test_summary_counts_are_consistent() -> None:
    frame = audit_catalog()
    summary = audit_summary(frame)
    assert summary["registered_engines"] == 76
    assert summary["audited_engines"] == 76
    assert summary["legacy_catalog_covered"] == 53
    assert summary["newly_covered_engines"] == 23
    assert summary["priority_p1"] == 20


def test_reports_are_written(tmp_path: Path) -> None:
    outputs = write_audit_reports(tmp_path)
    assert set(outputs) == {"csv", "json", "summary_json", "summary_md"}
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
