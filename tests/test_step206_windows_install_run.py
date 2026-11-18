from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")


def test_step206_release_identity_and_five_parts() -> None:
    release = json.loads(read("STEP206_RELEASE.json"))
    assert read("VERSION").strip() == "15.6.0"
    assert release["version"] == "15.6.0"
    assert release["step"] == 206
    assert release["part_count"] == 5
    assert release["package_generation"] == "V19.6"
    assert all((ROOT / ".release_parts" / f"step206_part{part}.ok").is_file() for part in range(1, 6))



def test_current_metadata_and_four_part_runtime_preflight_are_consistent() -> None:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    assert read("VERSION").strip() == project_version == "15.6.0"
    runtime_preflight = read("scripts/step97_runtime_preflight.py")
    assert "use four package markers" in runtime_preflight
    assert "return set(range(1, 5))" in runtime_preflight


def test_same_release_hotfix_replaces_stale_managed_copy() -> None:
    installer = read("scripts/install_windows_step206.py")
    assert "def _target_source_valid(source_root: Path)" in installer
    assert "source_manifest.read_bytes() != target_manifest.read_bytes()" in installer
    assert "if _target_source_valid(source_root):" in installer


def test_release_source_manifest_omits_mutable_report_databases(tmp_path: Path) -> None:
    from scripts.package_shiro_4part_release import excluded

    reports = tmp_path / "reports"
    assert excluded(reports / "analytics.sqlite3", tmp_path)
    assert excluded(reports / "analytics.sqlite3-shm", tmp_path)
    assert excluded(reports / "analytics.sqlite3-wal", tmp_path)
    assert not excluded(reports / "scientific-summary.json", tmp_path)


def test_two_step_windows_workflow_and_supported_python() -> None:
    install = read("INSTALL_WINDOWS.bat")
    run = read("RUN_BOTH_WINDOWS.bat")
    assert "install_windows_step206.py" in install
    assert "run_biointel_step206.py" in run
    assert "for %%P in (1 2 3 4)" in install
    assert "for %%P in (1 2 3 4)" in run
    assert "sys.version_info[:2]==(3,11)" in install.replace(" ", "")
    assert "sys.version_info[:2]==(3,11)" in run.replace(" ", "")
    assert "3.11.9" not in install and "3.11.9" not in run
    assert 'pushd "%~dp0"' in install and 'pushd "%~dp0"' in run
    assert "/no-pause" in install and "/no-pause" in run
    assert "/no-browser" in run and "BIOINTEL_NO_BROWSER" in run
    assert "--deep-hashes" in read("scripts/install_windows_step206.py")
    assert 'if "%MANAGED_MODE%"=="0" goto :ENSURE_AND_DELEGATE' in run


def test_stable_launcher_delegation_avoids_cmd_block_variable_trap() -> None:
    for name, stable in (
        ("RUN_BOTH_WINDOWS.bat", "RUN_BIOINTEL_ACTIVE.bat"),
        ("STOP_BIOINTEL_WINDOWS.bat", "STOP_BIOINTEL_ACTIVE.bat"),
        ("RESTART_BIOINTEL_WINDOWS.bat", "RESTART_BIOINTEL_ACTIVE.bat"),
    ):
        text = read(name)
        assert "BIOINTEL_APP_HOME" in text
        assert rf'%BIOINTEL_APP_HOME%\App\{stable}' in text
        assert 'set "ACTIVE=' not in text


def test_managed_atomic_install_backup_and_rollback_contract() -> None:
    installer = read("scripts/install_windows_step206.py")
    contract = read("scripts/step206_contract.py")
    assert "Releases" in contract and "RELEASE_STEP = 220" in contract
    assert "copytree(source_root, staging" in installer
    assert "staging.replace(TARGET_ROOT)" in installer
    assert 'previous_venv = backup / ".venv"' in installer
    assert "previous_venv.replace(target_venv)" in installer
    assert "invalid-backup" in installer
    assert ".venv.step206-backup" in installer
    main_body = installer[installer.index("def main"):]
    assert main_body.index("_stop_active_runtime_before_activation()") < main_body.index("_backup_databases(previous_root)")
    assert "create_shortcuts_and_active_record" in installer
    assert "_migrate_previous_runtime_databases" in installer
    assert "reports/jobs.sqlite3" in installer
    assert "reports/api_security.sqlite3" in installer


def test_strict_supervisor_and_full_cleanup_contract() -> None:
    supervisor = read("scripts/runtime_supervisor_step206.py")
    assert 'status == 200 and payload.get("status") == "ok"' in supervisor
    assert 'payload.get("version") == PRODUCT_VERSION' in supervisor
    assert "_local_database_ready" in supervisor
    assert "runtime-readiness.sqlite3" in supervisor
    assert 'body.casefold() == "ok"' in supervisor
    assert "worker_service.status().running" in supervisor
    assert "self.cleanup()" in supervisor
    assert "_terminate_process(self.ui)" in supervisor
    assert "_terminate_process(self.api)" in supervisor
    assert "worker_service.stop" in supervisor
    assert "restart loop" in supervisor
    assert "self.api_port = 0" in supervisor and "self.ui_port = 0" in supervisor


def test_optional_services_not_required_by_core_launch() -> None:
    launcher = read("scripts/run_biointel_step206.py")
    installer = read("scripts/install_windows_step206.py")
    assert "setup_free_web_ai_windows.py" not in launcher
    assert "setup_scientific_runtime_windows.py" not in launcher
    assert 'status["optional_services"] = "not-started; offline core remains fully usable"' in installer


def test_historical_entrypoints_delegate_to_step206() -> None:
    assert "from install_windows_step206 import main" in read("scripts/install_windows_step196.py")
    assert "from run_biointel_step206 import main" in read("scripts/run_biointel_step196.py")
    assert "from run_biointel_step206 import main" in read("scripts/run_biointel_step196_runtime.py")


def test_protected_module_hashes_match_step205_baseline() -> None:
    baseline = ROOT.parent / "step206_protected_before.sha256"
    if not baseline.is_file():
        return
    rows = []
    for line in baseline.read_text(encoding="utf-8").splitlines():
        digest, old_path = line.split(None, 1)
        old_root = "BioIntel-AI-15.5.0-Step205-WINDOWS-V18.0/"
        relative = old_path.strip().replace("\\", "/").split(old_root, 1)[-1]
        rows.append((digest, relative))
    assert rows
    for expected, relative in rows:
        path = ROOT / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative


def test_sanitized_support_bundle_is_automatic() -> None:
    launcher = read("scripts/run_biointel_step206.py")
    installer = read("scripts/install_windows_step206.py")
    support = read("scripts/step206_support_bundle.py")
    support_launcher = read("CREATE_STEP206_SUPPORT_BUNDLE_WINDOWS.bat")
    assert "step206_support_bundle.py" in launcher
    assert "step206_support_bundle.py" in installer
    assert "No project datasets" in support
    assert "RELEASE_NAME" in support and 'f"step{RELEASE_STEP}_part{part}"' in support
    assert "15.6.0-Step220" in support_launcher
    assert "workspace" not in support.lower() or "workspace files" in support.lower()


def test_launcher_handles_legacy_process_state_and_duplicate_start() -> None:
    launcher = read("scripts/run_biointel_step206.py")
    assert '("supervisor_pid", "ui_pid", "api_pid", "worker_pid")' in launcher
    assert "BioIntel AI is already starting" in launcher
    assert "deadline = time.monotonic() + 120" in launcher


def test_streamlit_redacted_error_gate_runs_before_activation() -> None:
    installer = read("scripts/install_windows_step206.py")
    check = read("scripts/streamlit_startup_check_step206.py")
    assert "streamlit_startup_check_step206.py" in installer
    assert "AppTest.from_file" in check
    assert "app.exception" in check
    main_body = installer[installer.index("def main"):]
    assert "streamlit_startup_check_step206.py" in installer
    assert main_body.index("run_native_smoke_test(python)") < main_body.index("create_shortcuts_and_active_record()")
