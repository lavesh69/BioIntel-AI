from __future__ import annotations

import hashlib
import json
import py_compile
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_upgrade_v133 import MODULE_ONLY_KEYS, PROFILES, build_module_upgrade_artifacts

checks: list[dict[str, object]] = []

def add(name: str, passed: bool, detail: object) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})

version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
add("Product version preserved", version == "13.2.0", version)
add("Module-only scope", MODULE_ONLY_KEYS == NEW_BIOMEDICAL_KEYS and len(MODULE_ONLY_KEYS) == 15, len(MODULE_ONLY_KEYS))
add("Module profiles", set(PROFILES) == set(MODULE_ONLY_KEYS), len(PROFILES))
add("No Step 133 central page", not any("Step133" in p.name or "Module_Upgrade_Center" in p.name for p in (ROOT / "pages").glob("*.py")), "no new central page")

runtime_failures: list[str] = []
table_count = 0
visual_count = 0
for key in sorted(MODULE_ONLY_KEYS):
    module = MODULE_BY_KEY[key]
    try:
        data = demo_frame(module, 120)
        result, _summary, secondary, extras = analyse(data, module, 0.7)
        artifacts = build_module_upgrade_artifacts(key, data, result, secondary, extras)
        if artifacts["summary"].get("safe_error"):
            runtime_failures.append(f"{key}: {artifacts['summary']['safe_error']}")
        if artifacts["summary"].get("advanced_tables", 0) < 1:
            runtime_failures.append(f"{key}: no advanced table")
        if artifacts["summary"].get("advanced_visuals", 0) < 1:
            runtime_failures.append(f"{key}: no advanced visual")
        table_count += int(artifacts["summary"].get("advanced_tables", 0))
        visual_count += int(artifacts["summary"].get("advanced_visuals", 0))
    except Exception as exc:
        runtime_failures.append(f"{key}: {type(exc).__name__}: {exc}")
add("All module analyses", not runtime_failures, runtime_failures or "15/15")
add("Advanced tables", table_count >= 15, table_count)
add("Advanced visuals", visual_count >= 15, visual_count)

renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
add("Renderer integration", "Module upgrade" in renderer and "render_module_upgrade_panel" in renderer, "module tab")

config = json.loads((ROOT / "config/step133_module_only_upgrade.json").read_text(encoding="utf-8"))
locked_failures: list[str] = []
for relative, expected in config["locked_page_sha256"].items():
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    if actual != expected:
        locked_failures.append(relative)
add("Locked pages", not locked_failures, locked_failures or "5/5")

compile_failures: list[str] = []
python_files = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "site-packages" not in p.parts]
for path in python_files:
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        compile_failures.append(f"{path.relative_to(ROOT)}: {exc}")
add("Python syntax", not compile_failures, {"files": len(python_files), "failures": compile_failures[:10]})

db_files = sorted({p for pattern in ("*.db", "*.sqlite", "*.sqlite3") for p in ROOT.rglob(pattern) if "UserData" not in p.parts})
db_failures: list[str] = []
rows = 0
foreign_keys = 0
for path in db_files:
    try:
        connection = sqlite3.connect(path)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                db_failures.append(f"{path.relative_to(ROOT)}: {integrity}")
            foreign_keys += len(connection.execute("PRAGMA foreign_key_check").fetchall())
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                try:
                    rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                except sqlite3.DatabaseError:
                    pass
        finally:
            connection.close()
    except Exception as exc:
        db_failures.append(f"{path.relative_to(ROOT)}: {exc}")
add("Database integrity", not db_failures and foreign_keys == 0, {"databases": len(db_files), "rows": rows, "foreign_key_issues": foreign_keys, "failures": db_failures})

payload = {
    "step": 133,
    "version": version,
    "scope": "module-only",
    "checks": checks,
    "passed": all(bool(item["passed"]) for item in checks),
}
output = ROOT / "reports/step133_module_only_verification.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2))
raise SystemExit(0 if payload["passed"] else 1)
