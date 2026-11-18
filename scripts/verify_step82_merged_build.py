from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_compile_check() -> dict[str, object]:
    files = sorted(ROOT.rglob("*.py"))
    failures: list[dict[str, str]] = []
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:  # noqa: BLE001
            failures.append({"path": path.relative_to(ROOT).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
    return {"python_files": len(files), "failures": failures, "passed": not failures}


def database_check() -> dict[str, object]:
    paths = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.db")})
    records: list[dict[str, object]] = []
    for path in paths:
        record: dict[str, object] = {"path": path.relative_to(ROOT).as_posix()}
        try:
            connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=5)
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            total_rows = 0
            for table in tables:
                try:
                    total_rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                except sqlite3.DatabaseError:
                    continue
            connection.close()
            record.update(
                healthy=quick == "ok" and not foreign_keys,
                quick_check=quick,
                foreign_key_violations=len(foreign_keys),
                tables=len(tables),
                rows=total_rows,
            )
        except Exception as exc:  # noqa: BLE001
            record.update(healthy=False, error=f"{type(exc).__name__}: {exc}")
        records.append(record)
    return {
        "database_count": len(records),
        "healthy": sum(bool(item.get("healthy")) for item in records),
        "total_rows": sum(int(item.get("rows", 0)) for item in records),
        "databases": records,
        "passed": all(bool(item.get("healthy")) for item in records),
    }


def desktop_check() -> dict[str, object]:
    files = ["platform/desktop/src/main.cjs", "platform/desktop/src/preload.cjs"]
    results = []
    for relative in files:
        completed = subprocess.run(
            ["node", "--check", str(ROOT / relative)],
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "path": relative,
                "passed": completed.returncode == 0,
                "message": (completed.stderr or completed.stdout).strip(),
            }
        )
    return {"files": results, "passed": all(bool(item["passed"]) for item in results)}


def required_feature_check() -> dict[str, object]:
    required = [
        "src/biointel/ui/onboarding.py",
        "src/biointel/automation/workflow_automation.py",
        "src/biointel/ui/runtime_guard.py",
        "pages/19_System_Diagnostics.py",
        "pages/20_Workflow_Dashboard.py",
        "platform/desktop/src/main.cjs",
        "tests/test_step82_merged_reliability.py",
    ]
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    return {"required": required, "missing": missing, "passed": not missing}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/step82_merged_qualification.json")
    args = parser.parse_args()
    checks = {
        "required_features": required_feature_check(),
        "python_compilation": python_compile_check(),
        "databases": database_check(),
        "desktop_syntax": desktop_check(),
    }
    streamlit_report = ROOT / "reports" / "step82_streamlit_sweep.json"
    if streamlit_report.is_file():
        payload = json.loads(streamlit_report.read_text(encoding="utf-8"))
        checks["streamlit_entry_points"] = {
            "total": int(payload.get("total", 0)),
            "passed": int(payload.get("passed", 0)),
            "failed": int(payload.get("failed", 0)),
            "qualified": int(payload.get("total", 0)) == int(payload.get("passed", -1)) and not int(payload.get("failed", 1)),
        }
    passed = all(
        bool(value.get("passed", value.get("qualified", False)))
        for value in checks.values()
    )
    report = {
        "release": "BioIntel AI Step 70→82 reconstructed merged build",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
        "source_boundary": "Reconstructed from documented Step 70–82 requirements on the available Step 68 stability-hardened source; not a byte-for-byte merge of unavailable archives.",
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
