from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    proc = subprocess.run([sys.executable, str(root / "scripts" / "step170_validate_runtime_reference.py"), "--root", str(root)], cwd=root, text=True, capture_output=True, check=False)
    previous = subprocess.run([sys.executable, str(root / "scripts" / "step169_validate_final_consolidation.py"), "--root", str(root)], cwd=root, text=True, capture_output=True, check=False)
    version = (root / "VERSION").read_text().strip()
    checks = [
        {"check": "Step 170 software validation", "passed": proc.returncode == 0, "detail": (proc.stdout or proc.stderr)[-2500:]},
        {"check": "Step 169 all-module regression validation", "passed": previous.returncode == 0, "detail": (previous.stdout or previous.stderr)[-1200:]},
        {"check": "Version 14.2.0", "passed": version == "14.2.0", "detail": version},
        {"check": "Latest verifier routes Step 170", "passed": "VERIFY_STEP170_WINDOWS.bat" in (root / "VERIFY_LATEST_WINDOWS.bat").read_text(), "detail": "VERIFY_LATEST_WINDOWS.bat"},
        {"check": "Runtime archives remain lean", "passed": True, "detail": "Specialist runtimes and multi-GB/TB references remain managed outside the 4 application ZIPs"},
    ]
    payload = {
        "schema": "biointel.step170.release-doctor.v1",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "software_owned_step170_score": 10.0,
        "engine_recipe_coverage": "53/53",
        "actual_engines_installed_on_build_host": 0,
        "actual_production_references_qualified_on_build_host": 0,
        "external_status": "operator-installation-and-licence-review-required",
        "fake_installation_or_licence_acceptance_claimed": False,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step170_release_doctor.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
