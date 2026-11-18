from __future__ import annotations

import json
import tomllib
from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_step97_version_is_synchronized() -> None:
    base = root()
    assert (base / "VERSION").read_text().strip() == "13.2.0"
    assert tomllib.loads((base / "pyproject.toml").read_text())["project"]["version"] == "13.2.0"
    assert json.loads((base / "platform/desktop/package.json").read_text())["version"] == "13.2.0"
    assert json.loads((base / "store/release-manifest.json").read_text())["release_version"] == "13.2.0"
    assert json.loads((base / "store/model-manifest.json").read_text())["version"] == "13.2.0"


def test_reliability_center_is_registered() -> None:
    base = root()
    page = base / "pages/110_Reliability_Optimization_Center.py"
    navigation = (base / "src/biointel/ui/navigation.py").read_text()
    assert page.is_file()
    assert "reliability_optimization" in navigation
    assert page.name in navigation


def test_packaged_streamlit_runtime_avoids_development_watcher() -> None:
    config = tomllib.loads((root() / ".streamlit/config.toml").read_text())
    assert config["server"]["fileWatcherType"] == "none"
    assert config["server"]["runOnSave"] is False
    assert config["server"]["maxUploadSize"] == 1024
    assert config["runner"]["magicEnabled"] is False


def test_transactional_step97_installer_has_rollback_and_self_test() -> None:
    base = root()
    transaction = (base / "scripts/install_step97_transaction.ps1").read_text()
    rollback = (base / "scripts/rollback_step97.ps1").read_text()
    install = (base / "INSTALL_WINDOWS.bat").read_text()
    assert 'if($Version -ne "9.7.0")' in transaction
    assert "BIOINTEL_BACKUP_MANIFEST.json" in transaction
    assert "Get-FileHash -Algorithm SHA256" in transaction
    assert "Restore-UserDataMirror" in transaction
    assert '"runtime_logs","cache"' in transaction
    assert "FailedActivation" in rollback
    assert "step97_self_test.py" in install
    assert "verify_windows_wheelhouse.py" in install


def test_startup_preflight_and_runtime_guard_are_persistent() -> None:
    base = root()
    preflight = (base / "scripts/step97_runtime_preflight.py").read_text()
    guard = (base / "src/biointel/ui/runtime_guard.py").read_text()
    launcher = (base / "RUN_APP_WINDOWS.bat").read_text()
    assert "_free_port" in preflight
    assert "BIOINTEL_USER_DATA_DIR" in preflight
    assert "_SECRET_PATTERN" in guard
    assert "_rotate_runtime_reports" in guard
    assert "step97_runtime_preflight.py" in launcher
