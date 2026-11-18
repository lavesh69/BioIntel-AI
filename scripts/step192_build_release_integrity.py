from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.release_integrity_v192 import build_step192


def main() -> int:
    report = ROOT / "reports" / "step192" / "wheelhouse_verification.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_windows_wheelhouse.py"), "--root", str(ROOT), "--output", str(report)],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        print("Step 192 wheelhouse verification failed.", file=sys.stderr)
        return completed.returncode
    summary = build_step192(ROOT)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("release_audit_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
