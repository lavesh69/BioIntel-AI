from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.bioinformatics_peak_v137.catalog import MODULES, NEW_MODULE_KEYS
from biointel.bioinformatics_peak_v137.scientific import analyse_module, demo_frame, validate_frame
from biointel.bioinformatics_peak_v137.tools import readiness
from biointel.bioinformatics_peak_v137.visuals import build_visuals
from biointel.ui.navigation import catalogue_integrity


PROTECTED_BASE_HASHES = {
    "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def database_checks() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            continue
        relative = path.relative_to(ROOT).as_posix()
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                quick = connection.execute("PRAGMA quick_check").fetchone()[0]
                foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                count = 0
                for (table,) in tables:
                    try:
                        count += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    except sqlite3.Error:
                        pass
            rows.append({"path": relative, "quick_check": quick, "foreign_key_issues": len(foreign), "rows": count, "passed": quick == "ok" and not foreign})
        except sqlite3.Error as exc:
            rows.append({"path": relative, "quick_check": "error", "foreign_key_issues": None, "rows": None, "passed": False, "error": str(exc)})
    return rows


def python_compile_checks() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    targets = [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py")), *sorted((ROOT / "src").rglob("*.py")), *sorted((ROOT / "scripts").glob("*.py"))]
    for path in targets:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
            rows.append({"path": path.relative_to(ROOT).as_posix(), "passed": True})
        except Exception as exc:
            rows.append({"path": path.relative_to(ROOT).as_posix(), "passed": False, "error": f"{type(exc).__name__}: {exc}"})
    return rows


def module_checks() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in MODULES:
        try:
            frame = demo_frame(module, 120)
            audit = validate_frame(frame, module)
            bundle = analyse_module(frame, module)
            visuals = build_visuals(module.key, bundle)
            numeric = bundle.result.select_dtypes(include=[np.number]).to_numpy()
            finite = not np.isinf(numeric).any()
            tool_rows = readiness(module.key)
            rows.append({
                "key": module.key,
                "title": module.title,
                "existing_page_upgraded": bool(module.existing_page),
                "new_module": module.key in NEW_MODULE_KEYS,
                "input_rows": len(frame),
                "result_rows": len(bundle.result),
                "visuals": len(visuals),
                "quality_valid": bool(audit["valid"]),
                "finite_numeric_output": finite,
                "tool_checks": len(tool_rows),
                "passed": bool(audit["valid"] and len(bundle.result) and len(visuals) == 8 and finite),
            })
        except Exception as exc:
            rows.append({"key": module.key, "title": module.title, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
    return rows


def build_report() -> dict[str, object]:
    modules = module_checks()
    databases = database_checks()
    compiled = python_compile_checks()
    navigation = catalogue_integrity(ROOT)
    protected = {relative: {"expected": expected, "actual": sha(ROOT / relative), "passed": sha(ROOT / relative) == expected} for relative, expected in PROTECTED_BASE_HASHES.items()}
    report = {
        "schema": "biointel.step137.bioinformatics-peak-qualification.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "scope": {
            "specialist_modules": len(MODULES),
            "existing_modules_upgraded": sum(bool(module.existing_page) for module in MODULES),
            "new_modules_added": len(NEW_MODULE_KEYS),
            "visuals_per_module": 8,
            "total_signature_visual_assignments": len(MODULES) * 8,
        },
        "modules": modules,
        "navigation": navigation,
        "databases": databases,
        "python_compile": {
            "files": len(compiled),
            "passed": sum(bool(row["passed"]) for row in compiled),
            "failures": [row for row in compiled if not row["passed"]],
        },
        "protected_base_files": protected,
    }
    report["summary"] = {
        "modules_passed": sum(bool(row["passed"]) for row in modules),
        "modules_total": len(modules),
        "visuals_built": sum(int(row.get("visuals", 0)) for row in modules),
        "databases_passed": sum(bool(row["passed"]) for row in databases),
        "databases_total": len(databases),
        "database_rows": sum(int(row.get("rows") or 0) for row in databases),
        "foreign_key_issues": sum(int(row.get("foreign_key_issues") or 0) for row in databases),
        "compile_failures": len(report["python_compile"]["failures"]),
        "navigation_healthy": bool(navigation["healthy"]),
        "protected_files_unchanged": all(bool(row["passed"]) for row in protected.values()),
    }
    summary = report["summary"]
    report["qualified"] = bool(
        summary["modules_passed"] == summary["modules_total"]
        and summary["databases_passed"] == summary["databases_total"]
        and summary["compile_failures"] == 0
        and summary["navigation_healthy"]
        and summary["protected_files_unchanged"]
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/generated/step137_bioinformatics_peak_qualification.json")
    args = parser.parse_args()
    report = build_report()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"qualified": report["qualified"], **report["summary"]}, indent=2))
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
