from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_self_test_module():
    path = ROOT / "scripts" / "step193_self_test.py"
    spec = importlib.util.spec_from_file_location("step193_self_test_contract_fix", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_step206_installer_contract_passes() -> None:
    installer = (ROOT / "scripts" / "install_windows_step206.py").read_text(encoding="utf-8")
    gate = (ROOT / "scripts" / "step206_release_gate.py").read_text(encoding="utf-8")
    assert "step206_release_gate.py" in installer
    assert "--deep-hashes" in installer
    assert "verify_dependency_lock.py" in installer
    assert "verify_windows_wheelhouse.py" in installer
    assert "Step206" in gate


def test_current_version_is_compatible_with_step193_mandatory_baseline() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "15.6.0"
    release = (ROOT / "STEP206_RELEASE.json").read_text(encoding="utf-8")
    assert '"step": 206' in release
    assert '"version": "15.6.0"' in release


def test_no_active_step193_marker_dependency_remains() -> None:
    self_test = (ROOT / "scripts" / "step193_self_test.py").read_text(encoding="utf-8")
    path_safe = (ROOT / "RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat").read_text(encoding="utf-8")
    repair = (ROOT / "REPAIR_BIOINTEL_WINDOWS.bat").read_text(encoding="utf-8")
    assert "step193_part%%P.ok" not in self_test
    assert "step196_part%%P.ok" in path_safe
    assert "REPAIR_WINDOWS.bat" in repair
    current_repair = (ROOT / "REPAIR_WINDOWS.bat").read_text(encoding="utf-8")
    assert "step206_release_gate.py" in current_repair
    assert "install_windows_step206.py" in current_repair
    assert "step196_validate_release.py" not in current_repair


def test_installer_runs_contract_check_before_environment_changes() -> None:
    installer = (ROOT / "scripts" / "install_windows_step206.py").read_text(encoding="utf-8")
    verify_block = installer.split("def verify_source_before_copy", 1)[1].split("def _copy_ignore", 1)[0]
    assert "step206_release_gate.py" in verify_block
    assert "--deep-hashes" in verify_block
    assert "verify_dependency_lock.py" in verify_block
    assert "verify_windows_wheelhouse.py" in verify_block
    assert verify_block.index("step206_release_gate.py") < verify_block.index("verify_dependency_lock.py")
    assert verify_block.index("verify_dependency_lock.py") < verify_block.index("verify_windows_wheelhouse.py")
