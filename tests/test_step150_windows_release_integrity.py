from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_step150_launcher_contract() -> None:
    root = project_root()
    text = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig")
    assert 'title BioIntel AI Step 150' in text
    assert '--root "."' in text
    assert '--root "%~dp0"' not in text
    assert 'step150_validate_installation.py' in text
    for part in range(1, 5):
        assert f"step150_part%%P.ok" in text or f"step150_part{part}.ok" in text


def test_step150_preflight_is_self_healing() -> None:
    root = project_root()
    text = (root / "scripts" / "step145_runtime_preflight.py").read_text(encoding="utf-8")
    assert "resolve_path_argument" in text
    assert "normalize_path_environment" in text
    assert "biointel.startup-preflight.v150" in text


def test_step150_validator_accepts_clean_source() -> None:
    root = project_root()
    process = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "step150_validate_installation.py"),
            "--root",
            str(root),
            "--allow-uninstalled",
            "--output",
            "reports/test_step150_installation_validation.json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(
        (root / "reports" / "test_step150_installation_validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["passed"] is True
    assert report["failures"] == []


def test_step150_validator_detects_stale_step145_launcher(tmp_path: Path) -> None:
    root = project_root()
    shutil.copytree(root / ".release_parts", tmp_path / ".release_parts")
    shutil.copytree(root / "release", tmp_path / "release")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "biointel" / "utils").mkdir(parents=True, exist_ok=True)

    # Copy all manifest-protected files before corrupting one of them.
    manifest = json.loads(
        (root / "release" / "step150_critical_hashes.json").read_text(encoding="utf-8")
    )
    for relative in manifest["files"]:
        source = root / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    (tmp_path / "RUN_BOTH_WINDOWS.bat").write_text(
        '@echo off\ncd /d "%~dp0"\n'
        'title BioIntel AI Step 145 - Overall Stability Optimized\n'
        'python scripts\\step145_runtime_preflight.py --root "%~dp0"\n',
        encoding="utf-8",
    )

    process = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "step150_validate_installation.py"),
            "--root",
            str(tmp_path),
            "--allow-uninstalled",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 1
    payload = json.loads(process.stdout.split("REPORT_PATH=", 1)[0])
    keys = {item["key"] for item in payload["failures"]}
    assert "critical_file_hash_mismatch" in keys
    assert "legacy_launcher_detected" in keys or "stale_launcher" in keys
