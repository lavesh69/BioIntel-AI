from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.release_integrity_v192.audit import run_release_audit

PART_MARKERS = tuple(f".release_parts/step192_part{i}.ok" for i in range(1, 5))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an extracted BioIntel AI Step 192 release.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--allow-uninstalled", action="store_true")
    parser.add_argument("--deep-hashes", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    audit = run_release_audit(root, deep_hashes=args.deep_hashes)
    missing_markers = [marker for marker in PART_MARKERS if not (root / marker).is_file()]
    assignment_path = root / "STEP192_PACKAGE_PART_ASSIGNMENT.json"
    assignment_ok = False
    assignment_missing: list[str] = []
    if assignment_path.is_file():
        try:
            assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
            entries = assignment.get("assignments", {})
            if isinstance(entries, dict):
                assignment_missing = [relative for relative in entries if not (root / relative).is_file()]
                assignment_ok = not assignment_missing and len(entries) > 10000
        except (OSError, json.JSONDecodeError):
            assignment_ok = False

    installed_ok = args.allow_uninstalled or (root / ".venv" / "Scripts" / "python.exe").is_file()
    extra_checks = [
        {"name": "four Step 192 part markers", "passed": not missing_markers, "detail": ", ".join(missing_markers) or "all markers present", "severity": "critical"},
        {"name": "package assignment completeness", "passed": assignment_ok, "detail": f"missing={len(assignment_missing)}", "severity": "critical"},
        {"name": "installed virtual environment", "passed": installed_ok, "detail": "allowed before install" if args.allow_uninstalled else ".venv/Scripts/python.exe", "severity": "critical"},
    ]
    audit["checks"].extend(extra_checks)
    critical_failures = [item for item in audit["checks"] if not item.get("passed") and item.get("severity") == "critical"]
    audit["critical_failures"] = critical_failures
    audit["passed"] = not critical_failures
    audit["validation_generated_at_utc"] = datetime.now(UTC).isoformat()
    audit["missing_part_markers"] = missing_markers
    audit["assignment_missing"] = assignment_missing[:100]

    output = Path(args.output) if args.output else root / "reports" / "step192" / "extracted_release_validation.json"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, default=str))
    print(f"REPORT_PATH={output.resolve()}")
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
