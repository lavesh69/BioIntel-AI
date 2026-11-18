from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


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
            row_count = 0
            for table in tables:
                row_count += int(
                    connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
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


def run(command: list[str], root: Path) -> None:
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the BioIntel AI Step 54 release.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json-output", default="reports/step54_local_verification.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    run([sys.executable, "-m", "ruff", "check", "."], root)
    run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts"], root)
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "tests/test_step54_remaining_fixes.py"], root)

    databases = database_health(root)
    result = {
        "release": "BioIntel AI Step 54 Remaining Functional Fixes",
        "ruff": "passed",
        "python_compilation": "passed",
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "database_count": len(databases),
        "healthy_databases": sum(item["integrity"] == "ok" for item in databases),
        "foreign_key_violations": sum(int(item["foreign_key_violations"]) for item in databases),
        "databases": databases,
    }
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return (
        0
        if (
            result["healthy_databases"] == result["database_count"]
            and result["foreign_key_violations"] == 0
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
