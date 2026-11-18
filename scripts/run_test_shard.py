from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def discover() -> list[Path]:
    return sorted(ROOT.glob("tests/test_*.py"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic isolated pytest file shards.")
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--junit-dir", default="reports/test-shards")
    args = parser.parse_args()
    if args.total < 1 or not 0 <= args.index < args.total:
        parser.error("Shard index must satisfy 0 <= index < total.")
    files = [path for offset, path in enumerate(discover()) if offset % args.total == args.index]
    output = ROOT / args.junit_dir
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("PYTHONPATH", str(ROOT / "src"))
    environment.setdefault("OMP_NUM_THREADS", "1")
    environment.setdefault("OPENBLAS_NUM_THREADS", "1")
    environment.setdefault("MKL_NUM_THREADS", "1")
    failed: list[str] = []
    for path in files:
        relative = path.relative_to(ROOT)
        junit = output / f"shard-{args.index}-{path.stem}.xml"
        print(f"[shard {args.index}/{args.total}] {relative}", flush=True)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    str(relative),
                    "--disable-warnings",
                    f"--junitxml={junit}",
                ],
                cwd=ROOT,
                env=environment,
                timeout=args.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            failed.append(f"{relative}:timeout")
            continue
        if result.returncode:
            failed.append(f"{relative}:exit-{result.returncode}")
    if failed:
        print("Failed test files:")
        for item in failed:
            print(f"- {item}")
        return 1
    print(f"Shard {args.index} passed: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
