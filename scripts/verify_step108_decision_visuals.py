from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 108 decision visual intelligence")
    parser.add_argument("--output", default="reports/step108_verification.json")
    args = parser.parse_args()
    tests = [
        "tests/test_step108_decision_visuals.py",
        "tests/test_step107_scientific_visual_excellence.py",
        "tests/test_step106_scientific_workbench_ui.py",
        "tests/test_step105_reliability_optimization.py",
    ]
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    report = {
        "schema": "biointel.step108.verification.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "modules": 14,
        "visual_views": 70,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    print(f"Verification report: {output}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
