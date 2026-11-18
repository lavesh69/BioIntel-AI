from __future__ import annotations

import compileall
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
python_files = [p for p in ROOT.rglob("*.py") if all(part not in {".venv", "__pycache__", ".git"} for part in p.parts)]
compile_ok = compileall.compile_dir(str(ROOT), quiet=1, force=True)
pages = sorted((ROOT / "pages").glob("*.py"))
dbs = sorted(p for p in ROOT.rglob("*.sqlite*") if p.is_file() and not p.name.endswith(("-wal", "-shm")))
healthy = 0; fk_violations = 0; rows = 0; errors = []
for db in dbs:
    try:
        con = sqlite3.connect(db)
        if con.execute("PRAGMA integrity_check").fetchone()[0] == "ok": healthy += 1
        fk_violations += len(con.execute("PRAGMA foreign_key_check").fetchall())
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            try: rows += int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.DatabaseError: pass
        con.close()
    except Exception as exc:
        errors.append(f"{db}:{exc}")
report = {
    "schema": "biointel.step175.static-qualification.v1",
    "status": "passed" if compile_ok and healthy == len(dbs) and fk_violations == 0 and not errors else "failed",
    "version": "14.7.0",
    "python_files": len(python_files),
    "python_compilation_passed": compile_ok,
    "application_pages": len(pages) + 1,
    "sqlite_databases": len(dbs),
    "sqlite_healthy": healthy,
    "database_rows": rows,
    "foreign_key_violations": fk_violations,
    "errors": errors,
}
out = ROOT / "reports" / "step175_static_qualification.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
