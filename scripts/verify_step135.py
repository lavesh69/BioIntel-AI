from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_scientific_v135 import PROFILES, build_module_scientific_artifacts

LOCKED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def syntax_health() -> dict[str, object]:
    failures: list[str] = []
    count = 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".venv", "venv", "site-packages"} for part in path.parts):
            continue
        count += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
    return {"passed": not failures, "files": count, "failures": failures}


def database_health() -> dict[str, object]:
    paths = sorted({path for pattern in ("*.db", "*.sqlite", "*.sqlite3") for path in ROOT.rglob(pattern) if ".venv" not in path.parts and "UserData" not in path.parts})
    failures: list[str] = []
    rows = 0
    foreign_keys = 0
    for path in paths:
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    failures.append(f"{path.relative_to(ROOT)}: {integrity}")
                foreign_keys += len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for table in tables:
                    try:
                        rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    except sqlite3.DatabaseError:
                        pass
            finally:
                connection.close()
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
    return {"passed": not failures and foreign_keys == 0, "databases": len(paths), "rows": rows, "foreign_key_issues": foreign_keys, "failures": failures}


def module_smoke() -> dict[str, object]:
    failures: list[str] = []
    tables = 0
    figures = 0
    modules: list[dict[str, object]] = []
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        try:
            module = MODULE_BY_KEY[key]
            data = demo_frame(module, 180)
            result, _summary, secondary, extras = analyse(data, module, 0.7)
            artifacts = build_module_scientific_artifacts(key, data, result, secondary, extras)
            summary = artifacts["summary"]
            if summary.get("safe_error"):
                failures.append(f"{key}: {summary['safe_error']}")
            table_count = len(artifacts["tables"])
            figure_count = len(artifacts["figures"])
            if table_count < 2 or figure_count < 3:
                failures.append(f"{key}: expected >=2 tables and >=3 figures, got {table_count}/{figure_count}")
            for name, figure in artifacts["figures"].items():
                payload = figure.to_json()
                if not payload or '"data"' not in payload:
                    failures.append(f"{key}/{name}: invalid figure serialisation")
            tables += table_count
            figures += figure_count
            modules.append({"module": key, "tables": table_count, "figures": figure_count, "quality_checks": len(artifacts["quality"])})
        except Exception as exc:
            failures.append(f"{key}: {type(exc).__name__}: {exc}")
    return {"passed": not failures and len(modules) == 15 and tables >= 39 and figures >= 49, "modules": modules, "module_count": len(modules), "scientific_tables": tables, "specialist_figures": figures, "failures": failures}


def runtime_residue() -> dict[str, object]:
    residue = []
    for path in ROOT.rglob("*"):
        if path.is_dir() and path.name in {"__pycache__", ".pytest_cache"}:
            residue.append(path.relative_to(ROOT).as_posix())
        elif path.is_file() and (path.suffix in {".pyc", ".pyo"} or path.name.endswith(("-wal", "-shm"))):
            residue.append(path.relative_to(ROOT).as_posix())
    return {"passed": not residue, "count": len(residue), "paths": residue[:100]}


def main() -> int:
    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add(checks, "Product version preserved", version == "13.2.0", version)
    add(checks, "Exactly fifteen module profiles", set(PROFILES) == set(NEW_BIOMEDICAL_KEYS) and len(PROFILES) == 15, sorted(PROFILES))

    smoke = module_smoke()
    add(checks, "Module scientific and visual smoke", smoke["passed"], smoke)

    syntax = syntax_health()
    add(checks, "Python syntax", syntax["passed"], syntax)

    database = database_health()
    add(checks, "Database integrity", database["passed"], database)

    locked_failures = [relative for relative, expected in LOCKED.items() if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected]
    add(checks, "Protected pages", not locked_failures, locked_failures or "5/5 byte-identical")

    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    page_names = {path.name for path in (ROOT / "pages").glob("*.py")}
    integration = "render_module_scientific_v135_panel" in renderer and not any("Step135" in name or "Module_Scientific_Depth_135" in name for name in page_names)
    add(checks, "Module-only renderer integration", integration, {"renderer_hook": "render_module_scientific_v135_panel" in renderer, "new_central_pages": [name for name in page_names if "Step135" in name]})

    required = [ROOT / "STEP135_MODULE_SCIENTIFIC_VISUALS_RELEASE.json", ROOT / "config/step135_module_scientific_visuals.json", ROOT / "STEP135_MODULE_SCIENTIFIC_DEPTH_VISUALS_REPORT.md", ROOT / "VERIFY_STEP135_MODULES_WINDOWS.bat"]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    add(checks, "Release artifacts", not missing, missing or "Complete")

    residue = runtime_residue()
    add(checks, "Runtime residue", residue["passed"], residue)

    payload = {
        "schema": "biointel.step135-module-scientific-verification.v1",
        "step": 135,
        "version": version,
        "scope": "module-scientific-depth-specialist-visuals",
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks),
    }
    output = ROOT / "reports" / "step135_module_scientific_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
