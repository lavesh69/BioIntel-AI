from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Step 162 model-authenticity release doctor.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(root / "src")}
    commands = [
        [sys.executable, str(root / "scripts" / "step162_build_authenticity_assets.py"), "--root", str(root)],
        [sys.executable, str(root / "scripts" / "step162_validate_authenticity.py"), "--root", str(root), "--quick"],
        [sys.executable, str(root / "scripts" / "step161_validate_upgrade.py"), "--root", str(root), "--quick"],
    ]
    results: list[dict[str, object]] = []
    for command in commands:
        completed = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
        results.append(
            {
                "command": command,
                "return_code": completed.returncode,
                "passed": completed.returncode == 0,
                "stdout_tail": completed.stdout[-5000:],
                "stderr_tail": completed.stderr[-5000:],
            }
        )
    payload = {
        "schema": "biointel.step162.release-doctor.v1",
        "status": "passed" if all(bool(item["passed"]) for item in results) else "failed",
        "checks": results,
        "external_release_not_inferred": True,
    }
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "step162_release_doctor.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
