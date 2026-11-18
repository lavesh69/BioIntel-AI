from __future__ import annotations

import hashlib
import json
from pathlib import Path

from biointel.utils.large_files import (
    load_registry,
    profile_local_file,
    register_local_file,
    remove_registered_paths,
)

ROOT = Path(__file__).resolve().parents[1]


def test_mypy_targets_supported_python() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.mypy]" in text
    assert 'python_version = "3.11"' in text
    assert 'python_version = "8.9.0"' not in text


def test_streamlit_large_upload_and_local_intake_are_configured() -> None:
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "maxUploadSize = 1024" in config
    assert "maxMessageSize = 1024" in config
    assert (ROOT / "RUN_APP_LOW_MEMORY_WINDOWS.bat").is_file()
    assert (ROOT / "src" / "biointel" / "utils" / "large_files.py").is_file()


def test_offline_wheelhouse_manifest_and_lock_match() -> None:
    wheelhouse = ROOT / "wheelhouse" / "windows-cp311-x64"
    manifest = {}
    for line in (wheelhouse / "MANIFEST_SHA256.txt").read_text(encoding="utf-8").splitlines():
        digest, filename = line.split(None, 1)
        manifest[filename.strip()] = digest
    wheels = sorted(wheelhouse.glob("*.whl"))
    lock_rows = [
        row
        for row in (ROOT / "requirements-windows-cp311-offline.lock")
        .read_text(encoding="utf-8")
        .splitlines()
        if row.strip() and not row.startswith("#")
    ]
    metadata = json.loads((wheelhouse / "WHEELHOUSE_METADATA.json").read_text(encoding="utf-8"))
    assert len(wheels) == len(manifest) == len(lock_rows) == metadata["wheel_count"]
    for wheel in wheels:
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == manifest[wheel.name]
    assert all(" --hash=sha256:" in row for row in lock_rows)


def test_large_file_registry_does_not_copy_source(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    source = tmp_path / "sample.fastq"
    source.write_text("@read\nACGT\n+\n!!!!\n", encoding="utf-8")
    profile = profile_local_file(source, label="test", compute_hash=True)
    assert profile.name == "sample.fastq"
    assert profile.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    registered = register_local_file(root, source, label="test", compute_hash=True)
    assert registered.source_path == str(source.resolve())
    rows = load_registry(root)
    assert len(rows) == 1
    assert not (root / source.name).exists()
    assert remove_registered_paths(root, [str(source.resolve())]) == 1
    assert load_registry(root) == []


def test_windows_installers_prefer_offline_wheels() -> None:
    installer = (ROOT / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")
    assert "scripts\\verify_windows_wheelhouse.py" in installer
    assert "scripts\\bootstrap.py --offline" in installer
    assert "--no-index" in bootstrap
    assert "--require-hashes" in bootstrap
