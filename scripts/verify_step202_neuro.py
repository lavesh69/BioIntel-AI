from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run(command: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if "pytest" in command:
        env["BIOINTEL_PROJECT_LOCAL_RUNTIME"] = "1"
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"command": command, "passed": completed.returncode == 0, "returncode": completed.returncode, "output_tail": (completed.stdout + completed.stderr)[-4000:]}


def main() -> int:
    preflight = [sys.executable, "scripts/step202_preflight.py", "--root", "."]
    if sys.version_info[:2] != (3, 11) or os.name != "nt":
        preflight.append("--allow-non-cp311")
    commands = [
        preflight,
        [sys.executable, "-m", "compileall", "-q", "src/biointel/neuro_cns", "pages/263_Neuro_CNS_Intelligence_Studio.py", "scripts/run_step202_neuro_demo.py", "scripts/step202_runtime_self_test.py"],
        [sys.executable, "scripts/step202_runtime_self_test.py"],
        [sys.executable, "scripts/run_step202_neuro_demo.py", "--output-dir", str(ROOT / "reports" / "generated" / "step202-demo-verification")],
    ]
    try:
        import pytest  # noqa: F401
    except ImportError:
        pytest_available = False
    else:
        pytest_available = True
        commands.insert(3, [sys.executable, "-m", "pytest", "-q", "tests/test_neuro_cns_studio.py", "tests/test_neuro_cns_step198_hardening.py", "tests/test_neuro_cns_step199_advanced.py", "tests/test_neuro_cns_step200_max_potential.py", "tests/test_neuro_cns_step201_completion.py", "tests/test_neuro_cns_step202_production.py"])
    checks = [run(command) for command in commands]
    report = {"schema": "biointel.step202.neuro-verification.v1", "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"), "passed": all(row["passed"] for row in checks), "pytest_available": pytest_available, "checks": checks}
    output = ROOT / "reports" / "step202-neuro-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
