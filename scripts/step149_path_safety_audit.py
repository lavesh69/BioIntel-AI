from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DANGEROUS_ROOT_ARGUMENT = re.compile(
    r'--(?:root|project-root|app-root)\s+"%~dp0"', re.IGNORECASE
)
WHOLE_DP0_ARGUMENT = re.compile(r'(?<![A-Za-z0-9_])"%~dp0"(?=\s|$)', re.IGNORECASE)


def audit(root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".bat", ".cmd", ".ps1"}:
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError as exc:
            findings.append({"path": str(path), "line": 0, "issue": "read_error", "detail": str(exc)})
            continue
        for number, line in enumerate(lines, start=1):
            lower = line.lower()
            if 'cd /d "%~dp0"' in lower or 'pushd "%~dp0"' in lower:
                continue
            if DANGEROUS_ROOT_ARGUMENT.search(line) or WHOLE_DP0_ARGUMENT.search(line):
                findings.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "line": number,
                        "issue": "trailing_backslash_quote_risk",
                        "detail": line.strip(),
                    }
                )
    run_both = root / "RUN_BOTH_WINDOWS.bat"
    run_text = run_both.read_text(encoding="utf-8-sig", errors="replace") if run_both.is_file() else ""
    contract = {
        "launcher_exists": run_both.is_file(),
        "uses_relative_root_argument": '--root "."' in run_text,
        "sets_normalized_project_root": 'set "BIOINTEL_PROJECT_ROOT=%CD%"' in run_text,
        "legacy_dangerous_argument_absent": '--root "%~dp0"' not in run_text,
        "path_safe_launcher_exists": (root / "RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat").is_file(),
    }
    passed = not findings and all(contract.values())
    return {
        "schema": "biointel.step149.path-safety-audit.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root.resolve()),
        "launchers_scanned": scanned,
        "findings": findings,
        "contract": contract,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="reports/step149_path_safety_audit.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = audit(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
