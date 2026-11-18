from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.intelligence import HANDOFF_TARGETS, connect
from biointel.ui.navigation import catalogue_integrity

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: dict[str, object] = {}
    checks["version"] = (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    checks["new_modules"] = len(NEW_BIOMEDICAL_KEYS) == 15
    checks["handoff_profiles"] = set(HANDOFF_TARGETS) == set(NEW_BIOMEDICAL_KEYS)
    checks["central_pages"] = all(list((ROOT / "pages").glob(f"{number}_*.py")) for number in range(189, 195))
    checks["config"] = (ROOT / "config/step130_scientific_intelligence.json").is_file()
    checks["release"] = (ROOT / "STEP130_RELEASE.json").is_file()
    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    checks["module_integration"] = "render_nextgen_intelligence_workspace" in renderer
    workbench = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    checks["persistent_runs"] = "persist_run_snapshot" in workbench
    components = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    checks["linked_selection"] = "publish_linked_selection" in components
    checks["navigation"] = bool(catalogue_integrity(ROOT).get("healthy"))

    syntax_failures: list[str] = []
    python_files = list(ROOT.rglob("*.py"))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_failures.append(f"{path.relative_to(ROOT)}: {exc}")
    checks["python_syntax"] = not syntax_failures

    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "step130.sqlite3"
        with connect(ROOT, path=db_path) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            required = {
                "run_snapshots", "review_decisions", "evidence_board_items", "handoffs",
                "scenario_runs", "validation_cohorts",
            }
            checks["database_schema"] = required.issubset(tables)
            checks["database_integrity"] = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    locked = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    }
    checks["locked_pages"] = all(
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
        for relative, digest in locked.items()
    )

    report = {
        "schema": "biointel.step130.verification.v1",
        "version": "13.2.0",
        "checks": checks,
        "python_files": len(python_files),
        "syntax_failures": syntax_failures,
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
        "healthy": all(bool(value) for value in checks.values()),
    }
    target = ROOT / "reports/step130_scientific_intelligence_verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
