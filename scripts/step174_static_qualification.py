from __future__ import annotations

import ast
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
python_files = [p for p in ROOT.rglob("*.py") if not any(x in p.parts for x in (".venv", "node_modules", "__pycache__"))]
compile_failures = []
for path in python_files:
    try:
        ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except Exception as exc:
        compile_failures.append({"path": str(path.relative_to(ROOT)), "error": str(exc)})
pages = sorted((ROOT / "pages").glob("*.py"))
databases = sorted({p.resolve() for p in ROOT.rglob("*.sqlite*") if p.is_file() and p.suffix in {".sqlite", ".sqlite3", ".db"}})
db_results = []
for path in databases:
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        rows = 0
        for table in tables:
            try: rows += int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.Error: pass
        con.close()
        db_results.append({"path": str(path.relative_to(ROOT)), "integrity": integrity, "foreign_key_violations": len(fk), "tables": len(tables), "rows": rows})
    except Exception as exc:
        db_results.append({"path": str(path.relative_to(ROOT)), "integrity": "error", "foreign_key_violations": -1, "error": str(exc)})
report = {
    "schema": "biointel.step174.static-qualification.v1",
    "status": "passed" if not compile_failures and all(r["integrity"] == "ok" and r["foreign_key_violations"] == 0 for r in db_results) else "failed",
    "version": "14.6.0",
    "python_files": len(python_files),
    "python_failures": compile_failures,
    "application_pages": len(pages),
    "databases": len(db_results),
    "database_rows": sum(max(0, int(r.get("rows", 0))) for r in db_results),
    "foreign_key_violations": sum(max(0, int(r.get("foreign_key_violations", 0))) for r in db_results),
    "database_results": db_results,
}
(ROOT / "reports" / "step174_static_qualification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: report[k] for k in ("status", "version", "python_files", "application_pages", "databases", "database_rows", "foreign_key_violations")}, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
