from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--include-visual-semantic", action="store_true")
    p.add_argument("--output", default="reports/isolated_test_matrix.json")
    a = p.parse_args()
    files = (
        sorted((ROOT / "tests").glob("test_*.py"))
        + sorted((ROOT / "tests/integration").glob("test_*.py"))
        + sorted((ROOT / "tests/scientific").glob("test_*.py"))
    )
    if a.include_visual_semantic:
        files.append(ROOT / "tests/visual/test_semantic_visual_regression.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    results = []
    for path in files:
        started = time.time()
        try:
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    str(path.relative_to(ROOT)),
                    "--disable-warnings",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=a.timeout,
            )
            results.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "passed": run.returncode == 0,
                    "returncode": run.returncode,
                    "seconds": round(time.time() - started, 2),
                    "output": (run.stdout + run.stderr)[-4000:],
                }
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "passed": False,
                    "returncode": 124,
                    "seconds": round(time.time() - started, 2),
                    "output": f"timeout after {a.timeout}s: {exc}",
                }
            )
    report = {
        "schema": "biointel.isolated-test-matrix.v1",
        "passed": all(x["passed"] for x in results),
        "files": len(results),
        "results": results,
    }
    out = ROOT / a.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in results:
        print(("PASS" if item["passed"] else "FAIL"), item["file"], item["seconds"])
    print("summary", sum(x["passed"] for x in results), "/", len(results))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
