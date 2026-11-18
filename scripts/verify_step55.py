from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.repository_audit import run_repository_audit


def database_health(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for database in sorted((root / "reports").glob("*.sqlite3")):
        with sqlite3.connect(database) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            row_count = sum(
                int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in tables
            )
        records.append(
            {
                "path": str(database.relative_to(root)),
                "integrity": integrity,
                "foreign_key_violations": len(foreign_keys),
                "tables": len(tables),
                "rows": row_count,
            }
        )
    return records


def page_scan(root: Path) -> dict[str, int]:
    page_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted((root / "pages").glob("*.py"))
    )
    return {
        "file_uploaders": page_text.count("file_uploader("),
        "single_upload_preflights": page_text.count("render_upload_preflight("),
        "collection_upload_preflights": page_text.count("render_upload_collection_preflight("),
        "direct_pandas_uploaded_csv_reads": page_text.count("pd.read_csv("),
        "analysis_run_contexts": page_text.count("analysis_run("),
        "methodology_disclosures": page_text.count("render_methodology("),
    }


def run(command: list[str], root: Path) -> None:
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 55 comprehensive app upgrade.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json-output", default="reports/step55_local_verification.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    run([sys.executable, "-m", "ruff", "check", "src", "pages", "tests", "app.py"], root)
    run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts"], root)
    if not args.skip_tests:
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_step55_comprehensive_app_improvements.py",
            ],
            root,
        )

    databases = database_health(root)
    audit = run_repository_audit(root)
    scan = page_scan(root)
    upload_coverage = scan["single_upload_preflights"] + scan["collection_upload_preflights"]
    required = [
        root / "src" / "biointel" / "ui" / "workflow.py",
        root / "tests" / "test_step55_comprehensive_app_improvements.py",
        root / "STEP55_COMPREHENSIVE_APP_UPGRADE_REPORT.md",
        root / "VERIFY_STEP55_WINDOWS.bat",
    ]
    result = {
        "release": "BioIntel AI Step 55 Comprehensive App Upgrade",
        "ruff": "passed",
        "python_compilation": "passed",
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "required_files_present": all(path.is_file() for path in required),
        "page_scan": scan,
        "upload_preflight_coverage": f"{upload_coverage}/{scan['file_uploaders']}",
        "all_uploads_preflight_protected": upload_coverage == scan["file_uploaders"],
        "database_count": len(databases),
        "healthy_databases": sum(item["integrity"] == "ok" for item in databases),
        "foreign_key_violations": sum(int(item["foreign_key_violations"]) for item in databases),
        "database_rows": sum(int(item["rows"]) for item in databases),
        "repository_audit": audit,
        "databases": databases,
    }
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    passed = (
        result["required_files_present"]
        and result["all_uploads_preflight_protected"]
        and scan["direct_pandas_uploaded_csv_reads"] == 0
        and result["healthy_databases"] == result["database_count"]
        and result["foreign_key_violations"] == 0
        and bool(audit["passed"])
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
