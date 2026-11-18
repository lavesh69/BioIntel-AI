from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "wheelhouse" / "windows-cp311-x64"
SETUPTOOLS_WHEEL = WHEELHOUSE / "setuptools-80.9.0-py3-none-any.whl"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")


def test_legacy_pkg_resources_consumer_has_compatible_setuptools() -> None:
    assert SETUPTOOLS_WHEEL.is_file()
    assert not (WHEELHOUSE / "setuptools-83.0.0-py3-none-any.whl").exists()
    with zipfile.ZipFile(SETUPTOOLS_WHEEL) as archive:
        assert "pkg_resources/__init__.py" in archive.namelist()


def test_offline_lock_and_metadata_match_compatible_wheel() -> None:
    digest = hashlib.sha256(SETUPTOOLS_WHEEL.read_bytes()).hexdigest()
    lock = read("requirements-windows-cp311-offline.lock")
    assert f"setuptools==80.9.0 --hash=sha256:{digest}" in lock
    metadata = json.loads(read("wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json"))
    row = next(item for item in metadata["packages"] if item["canonical_name"] == "setuptools")
    assert row["version"] == "80.9.0"
    assert row["filename"] == SETUPTOOLS_WHEEL.name
    assert row["sha256"] == digest
    assert row["size_bytes"] == SETUPTOOLS_WHEEL.stat().st_size


def test_install_and_run_both_execute_complete_runtime_verifier() -> None:
    bootstrap = read("scripts/bootstrap.py")
    installer = read("scripts/install_windows_step206.py")
    run_both = read("RUN_BOTH_WINDOWS.bat")
    verifier = read("scripts/verify_windows_runtime_compatibility_step206.py")
    online_fallback = read("INSTALL_WINDOWS_ONLINE_FALLBACK.bat")

    assert "setuptools==80.9.0" in bootstrap
    assert "setuptools==83.0.0" not in bootstrap
    assert 'requires = ["setuptools==80.9.0", "wheel==0.47.0"]' in read("pyproject.toml")
    assert "requirements-windows-cp311-offline.lock" in bootstrap
    assert "verify_windows_runtime_compatibility_step206.py" in installer
    assert "verify_windows_runtime_compatibility_step206.py" in run_both
    assert "pkg_resources" in verifier
    assert "ont_fast5_api" in verifier
    assert "FAST5 VBZ plugin registration" in verifier
    assert "install_windows_step206.py" in online_fallback
    assert "--force-repair --online" in online_fallback
    assert 'parser.add_argument("--online"' in installer


def test_wheelhouse_gate_prevents_pkg_resources_regression() -> None:
    gate = read("scripts/verify_windows_wheelhouse.py")
    assert "setuptools-80.9.0-py3-none-any.whl" in gate
    assert "pkg_resources/__init__.py" in gate
    assert "setuptools 83.x removes pkg_resources" in gate
    assert "ont_fast5_api-4.1.3-py3-none-any.whl" in gate
