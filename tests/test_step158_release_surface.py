from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_step158_release_metadata_and_current_docs() -> None:
    release = json.loads((ROOT / "STEP158_RELEASE.json").read_text(encoding="utf-8"))
    assert release["step"] == 158
    assert release["product_version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Step 158" in readme
    assert "VERIFY_LATEST_WINDOWS.bat" in readme
    assert "Step 126" not in readme


def test_step158_canonical_entry_points_exist() -> None:
    for name in (
        "VERIFY_LATEST_WINDOWS.bat",
        "VERIFY_STEP158_WINDOWS.bat",
        "RUN_RELEASE_DOCTOR_WINDOWS.bat",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "CURRENT_RELEASE.md",
    ):
        assert (ROOT / name).is_file(), name


def test_step158_release_doctor_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "step158_release_doctor.py"), "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((ROOT / "reports" / "step158_release_doctor.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
