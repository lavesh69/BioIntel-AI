from __future__ import annotations

from pathlib import Path

from biointel.product_registry import MODULE_REGISTRY, registry_integrity
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")


def test_authoritative_registry_covers_every_page_exactly_once() -> None:
    integrity = registry_integrity(ROOT)
    assert integrity["healthy"], integrity
    assert len(MODULE_REGISTRY) == len(PAGE_CATALOG)
    assert {record.id for record in MODULE_REGISTRY} == {page.key for page in PAGE_CATALOG}
    assert {record.path for record in MODULE_REGISTRY} == {page.path for page in PAGE_CATALOG}
    assert all(record.validation_status and record.limitations for record in MODULE_REGISTRY)


def test_external_requirements_are_not_claimed_as_bundled() -> None:
    external = [record for record in MODULE_REGISTRY if record.external_engines]
    assert external
    assert all(record.full_analysis_requires_external_assets for record in external)
    assert all("External dependency required" in record.capability_labels for record in external)
    assert all(record.offline_core_available for record in external)


def test_canonical_windows_recovery_controls_follow_current_contract() -> None:
    repair = read("REPAIR_WINDOWS.bat")
    legacy_repair = read("REPAIR_BIOINTEL_WINDOWS.bat")
    diagnostic = read("DIAGNOSE_WINDOWS.bat")
    safe_mode = read("SAFE_MODE_WINDOWS.bat")
    uninstall = read("UNINSTALL_BIOINTEL_WINDOWS.bat")
    assert "step206_release_gate.py" in repair
    assert "install_windows_step206.py" in repair
    assert "step196_validate_release.py" not in repair
    assert "REPAIR_WINDOWS.bat" in legacy_repair
    assert "diagnose_windows_step206.py" in diagnostic
    assert "Step220 - Diagnostics" in diagnostic
    diagnostic_runner = read("scripts/diagnose_windows_step206.py")
    assert "MANIFEST_NAME" in diagnostic_runner and "RELEASE_NAME" in diagnostic_runner
    assert 'f"step{RELEASE_STEP}_part{part}.ok"' in diagnostic_runner
    assert "BIOINTEL_SAFE_MODE=1" in safe_mode
    assert "BIOINTEL_INTERNET_ENABLED=0" in safe_mode
    assert "BIOINTELAI\\UserData" not in uninstall.upper() or "preserved" in uninstall.casefold()
    assert "Type UNINSTALL" in uninstall


def test_installer_creates_stable_controls_and_shortcuts() -> None:
    installer = read("scripts/install_windows_step206.py")
    contract = read("scripts/step206_contract.py")
    for token in (
        "stable_repair_path",
        "stable_diagnose_path",
        "stable_safe_mode_path",
        "stable_uninstall_path",
    ):
        assert token in installer
        assert token in contract
    for title in ("Repair BioIntel AI", "Diagnose BioIntel AI", "BioIntel AI Safe Mode", "Uninstall BioIntel AI"):
        assert title in installer


def test_safe_mode_is_enforced_by_runtime_supervisor() -> None:
    supervisor = read("scripts/runtime_supervisor_step206.py")
    assert 'os.environ.get("BIOINTEL_SAFE_MODE"' in supervisor
    assert "not self.safe_mode" in supervisor
    assert '"safe_mode": self.safe_mode' in supervisor
    assert '"--server.maxUploadSize", "100"' in supervisor


def test_registry_export_and_final_packaging_contracts() -> None:
    exporter = read("scripts/export_ultimate_registries.py")
    packager = read("scripts/step206_package_professional.py")
    for name in ("MODULE_REGISTRY", "ENGINE_REGISTRY", "MODEL_REGISTRY", "REFERENCE_DATABASE_REGISTRY"):
        assert name in exporter
    assert "export_ultimate_registries.py" in packager
    assert "BIOINTEL_FINAL_RELEASE_MANIFEST.json" in packager
    assert "SHA256SUMS.txt" in packager


def test_required_professional_documentation_is_present() -> None:
    required = (
        "docs/INSTALLATION_GUIDE.md",
        "docs/TROUBLESHOOTING_GUIDE.md",
        "docs/USER_GUIDE.md",
        "docs/DEVELOPER_GUIDE.md",
        "docs/PROJECT_ARCHITECTURE.md",
        "docs/WEBSITE_INTEGRATION_SPECIFICATION.md",
        "docs/BACKUP_AND_ROLLBACK.md",
        "release/ultimate/TEST_REPORT.md",
        "release/ultimate/PERFORMANCE_BENCHMARK_REPORT.md",
        "release/ultimate/SECURITY_AUDIT_SUMMARY.md",
        "release/ultimate/SCIENTIFIC_VALIDATION_STATUS.md",
        "release/ultimate/FINAL_RELEASE_READINESS_REPORT.md",
    )
    assert all((ROOT / path).is_file() and (ROOT / path).stat().st_size > 100 for path in required)


def test_remaining_acceptance_gaps_have_fail_closed_target_runner() -> None:
    batch = read("RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat")
    runner = read("scripts/ultimate_acceptance_step206.py")
    assert "--require-native-windows" in batch
    assert "15.6.0-Step220" in batch
    assert "step220-ultimate-acceptance.json" in batch
    assert "RELEASE_STEP" in runner
    assert "step206_release_gate.py" in runner and "--deep-hashes" in runner
    assert "verify_dependency_lock.py" in runner
    assert "verify_windows_wheelhouse.py" in runner
    assert "registry_integrity" in runner
    assert "windows_smoke_test_step206.py" in runner
    assert "external_evidence_gates" in runner


def test_current_user_and_release_docs_match_supported_five_part_workflow() -> None:
    readme = read("README.md")
    user_guide = read("docs/USER_GUIDE.md")
    release = read("STEP220_RELEASE.json")
    assert "all five parts" in readme
    assert "V20.3" in readme and "V20.3" in release
    assert "RUN_BOTH_WINDOWS.bat" in user_guide
    assert "RUN_APP_WINDOWS.bat" not in user_guide
    assert "all four parts" not in readme


def test_registry_contains_master_governance_fields() -> None:
    required = (
        "subcategory",
        "route",
        "maturity_status",
        "required_ai_models",
        "optional_online_providers",
        "estimated_resource_requirement",
    )
    assert all(all(getattr(record, field) is not None for field in required) for record in MODULE_REGISTRY)
