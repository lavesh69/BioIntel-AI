from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a merged BioIntel AI Step 158 folder.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--allow-uninstalled", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True

    checks = []
    def check(key: str, passed: bool, message: str = "") -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message})

    check("root_exists", root.is_dir(), str(root))
    for part in range(1, 5):
        marker = root / ".release_parts" / f"step158_part{part}.ok"
        check(f"step158_part_{part}", marker.is_file(), marker.as_posix())

    for name in (
        "STEP158_RELEASE.json",
        "README.md",
        "CURRENT_RELEASE.md",
        "VERIFY_LATEST_WINDOWS.bat",
        "VERIFY_STEP158_WINDOWS.bat",
        "RUN_RELEASE_DOCTOR_WINDOWS.bat",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
    ):
        check(f"current_file_{name}", (root / name).is_file(), name)

    inherited_report = load_json(root / "reports" / "step157_target_qualification.json")
    if not inherited_report:
        inherited_report = load_json(root / "release" / "STEP157_TARGET_QUALIFICATION.json")
    inherited_package = load_json(root / "reports" / "step157_package_verification.json")
    if not inherited_package:
        inherited_package = load_json(root / "BioIntel-AI-Step157-PACKAGE-VERIFICATION.json")
    # The distributed package may retain reports under different names; the release metadata is canonical.
    release157 = load_json(root / "STEP157_RELEASE.json")
    check("step157_release_metadata_present", release157.get("step") == 157, str(release157.get("step")))
    tests = release157.get("tests", {})
    check("step157_zero_failures", tests.get("failed") == 0, str(tests))
    check("step157_all_screens", release157.get("screen_qualification", {}).get("passed") == 229, str(release157.get("screen_qualification")))

    doctor = root / "scripts" / "step158_release_doctor.py"
    check("release_doctor_present", doctor.is_file(), str(doctor))
    if doctor.is_file():
        completed = subprocess.run(
            [sys.executable, str(doctor), "--root", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=90,
        )
        check("release_doctor_passed", completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:])

    if not args.allow_uninstalled:
        check("installation_marker_or_runtime", (root / ".venv").exists() or (root / "runtime").exists(), "Run INSTALL_WINDOWS.bat first")

    failures = [item for item in checks if not item["passed"]]
    payload = {"schema": "biointel.step158.installation-validation.v1", "passed": not failures, "checks": checks, "failures": failures}
    report = root / "reports" / "step158_installation_validation.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "checks": len(checks), "failures": len(failures), "report": str(report)}, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
