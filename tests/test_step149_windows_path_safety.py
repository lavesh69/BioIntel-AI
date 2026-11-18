from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from biointel.utils.path_safety import resolve_path_argument, sanitize_path_text


def test_sanitize_path_text_repairs_windows_trailing_quote() -> None:
    raw = 'C:\\Users\\Lavesh Dobriyal\\Downloads\\PRENIUM THEME\\BioIntel-AI"'
    assert sanitize_path_text(raw) == 'C:\\Users\\Lavesh Dobriyal\\Downloads\\PRENIUM THEME\\BioIntel-AI'


def test_sanitize_path_text_repairs_wrapped_quotes() -> None:
    raw = '  "C:\\BioIntel AI\\BioIntel-AI"  '
    assert sanitize_path_text(raw) == 'C:\\BioIntel AI\\BioIntel-AI'


def test_resolve_path_argument_repairs_malformed_quote(tmp_path: Path) -> None:
    assert resolve_path_argument(str(tmp_path) + '"') == tmp_path.resolve()


def test_main_launcher_uses_path_safe_root_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig")
    assert '--root "."' in launcher
    assert '--root "%~dp0"' not in launcher
    assert 'set "BIOINTEL_PROJECT_ROOT=%CD%"' in launcher
    assert (root / "RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat").is_file()


def test_path_safety_audit_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "step149_path_safety_audit.py"),
            "--root",
            str(root),
            "--output",
            "reports/test_step149_path_safety_audit.json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads((root / "reports" / "test_step149_path_safety_audit.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["findings"] == []


def test_preflight_cli_self_heals_trailing_quote(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "VERSION").write_text("13.2.0", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    process = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "step145_runtime_preflight.py"),
            "--root",
            str(tmp_path) + '"',
            "--no-recover-jobs",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report_path = tmp_path / "reports" / "step145_runtime_preflight.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["path_normalization"]["repaired"] is True
    assert report["root"] == str(tmp_path.resolve())
