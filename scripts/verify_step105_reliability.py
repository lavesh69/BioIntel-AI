from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 105 reliability fixes")
    parser.add_argument("--output", default="reports/step105_verification.json")
    args = parser.parse_args()
    command = [sys.executable, "-m", "pytest", "-q", "tests/test_step105_reliability_optimization.py", "tests/test_step104_optimized_expansion.py", "tests/test_step103_advanced_scientific_depth.py", "tests/test_step102_scientific_expansion.py"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    report = {
        "schema": "biointel.step105.verification.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "command": command,
        "return_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
