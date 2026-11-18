from __future__ import annotations

import json
from pathlib import Path
import py_compile
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
python_files = []
for path in ROOT.rglob("*.py"):
    if any(part in EXCLUDED_PARTS for part in path.parts):
        continue
    python_files.append(path)
compile_failures = []
for path in python_files:
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        compile_failures.append({"path": path.relative_to(ROOT).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
page_files = sorted((ROOT / "pages").glob("*.py"))
page_compile_failures = [item for item in compile_failures if item["path"].startswith("pages/")]

db_extensions = {".db", ".sqlite", ".sqlite3"}
databases = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in db_extensions:
        continue
    if any(part in EXCLUDED_PARTS for part in path.parts):
        continue
    entry = {"path": path.relative_to(ROOT).as_posix(), "integrity": "error", "foreign_key_violations": -1, "tables": 0, "rows": 0, "error": ""}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=20)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        rows = 0
        for table in tables:
            try:
                rows += int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.Error:
                pass
        con.close()
        entry.update({"integrity": integrity, "foreign_key_violations": len(fk), "tables": len(tables), "rows": rows})
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"
    databases.append(entry)

db_ok = all(item["integrity"] == "ok" and item["foreign_key_violations"] == 0 and not item["error"] for item in databases)
compilation = {
    "schema": "biointel.step173.compilation.v1",
    "version": "14.5.0",
    "status": "passed" if not compile_failures else "failed",
    "python_files": len(python_files),
    "compiled": len(python_files) - len(compile_failures),
    "failures": compile_failures,
    "application_pages": len(page_files),
    "application_pages_clean": len(page_files) - len(page_compile_failures),
}
db_report = {
    "schema": "biointel.step173.database-integrity.v1",
    "version": "14.5.0",
    "status": "passed" if db_ok else "failed",
    "databases": len(databases),
    "healthy": sum(item["integrity"] == "ok" and item["foreign_key_violations"] == 0 and not item["error"] for item in databases),
    "rows_inspected": sum(max(0, item["rows"]) for item in databases),
    "foreign_key_violations": sum(max(0, item["foreign_key_violations"]) for item in databases),
    "details": databases,
}
(ROOT / "reports" / "step173_compilation.json").write_text(json.dumps(compilation, indent=2) + "\n", encoding="utf-8")
(ROOT / "reports" / "step173_database_integrity.json").write_text(json.dumps(db_report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"compilation": compilation, "database_summary": {k: db_report[k] for k in ("status", "databases", "healthy", "rows_inspected", "foreign_key_violations")}}, indent=2))
raise SystemExit(0 if compilation["status"] == "passed" and db_report["status"] == "passed" else 1)
