from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
sys.dont_write_bytecode = True
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.module_reliability import reliability_summary, runtime_residue
from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_upgrade_v133 import build_module_upgrade_artifacts

LOCKED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def _add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _database_health() -> dict[str, object]:
    paths = sorted(
        {
            path
            for pattern in ("*.db", "*.sqlite", "*.sqlite3")
            for path in ROOT.rglob(pattern)
            if "UserData" not in path.parts and ".venv" not in path.parts
        }
    )
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
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                ]
                for table in tables:
                    try:
                        rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    except sqlite3.DatabaseError:
                        pass
            finally:
                connection.close()
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
    return {
        "passed": not failures and foreign_keys == 0,
        "databases": len(paths),
        "rows": rows,
        "foreign_key_issues": foreign_keys,
        "failures": failures,
    }


def _module_smoke() -> dict[str, object]:
    failures: list[str] = []
    tables = 0
    visuals = 0
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        try:
            data = demo_frame(module, 128)
            result, _summary, secondary, extras = analyse(data, module, 0.7)
            artifacts = build_module_upgrade_artifacts(key, data, result, secondary, extras)
            summary = artifacts.get("summary", {})
            if summary.get("safe_error"):
                failures.append(f"{key}: {summary['safe_error']}")
            tables += int(summary.get("advanced_tables", 0))
            visuals += int(summary.get("advanced_visuals", 0))
        except Exception as exc:
            failures.append(f"{key}: {type(exc).__name__}: {exc}")
    return {
        "passed": not failures,
        "modules": len(NEW_BIOMEDICAL_KEYS),
        "advanced_tables": tables,
        "advanced_visuals": visuals,
        "failures": failures,
    }


def _run_pages() -> dict[str, object]:
    reports = ROOT / "reports" / "step134_page_smoke"
    reports.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, object]] = []
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    for start, end in ((0, 39), (40, 79), (80, 119), (120, 159), (160, 197)):
        output = reports / f"pages_{start:03d}_{end:03d}.json"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "step134_page_smoke_worker.py"),
            "--start",
            str(start),
            "--end",
            str(end),
            "--output",
            str(output),
        ]
        completed = subprocess.run(command, cwd=ROOT, env=env, timeout=420, check=False)
        if output.is_file():
            all_rows.extend(json.loads(output.read_text(encoding="utf-8")))
        if completed.returncode not in (0, 1):
            all_rows.append(
                {
                    "index": start,
                    "page": f"worker:{start}-{end}",
                    "passed": False,
                    "exceptions": [f"worker return code {completed.returncode}"],
                    "ui_errors": [],
                    "seconds": 0,
                }
            )
    aggregate = ROOT / "reports" / "step134_all_pages_verification.json"
    aggregate.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    failures = [row for row in all_rows if not bool(row.get("passed"))]
    return {
        "passed": len(all_rows) == 198 and not failures,
        "entrypoints": len(all_rows),
        "passed_count": sum(bool(row.get("passed")) for row in all_rows),
        "failures": failures,
        "report": aggregate.relative_to(ROOT).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", action="store_true", help="Run all Streamlit entrypoints")
    parser.add_argument("--allow-residue", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    _add(checks, "Product version", version == "13.2.0", version)

    reliability = reliability_summary(ROOT)
    _add(checks, "Page bootstrap and Python compilation", reliability["passed"], reliability)

    module_smoke = _module_smoke()
    _add(checks, "Fifteen module functional smoke tests", module_smoke["passed"], module_smoke)

    locked_failures = [
        relative
        for relative, expected in LOCKED.items()
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected
    ]
    _add(checks, "Protected modules", not locked_failures, locked_failures or "5/5 byte-identical")

    database = _database_health()
    _add(checks, "Database integrity", database["passed"], database)

    release_page = (ROOT / "pages/45_Scientific_Release_Gate.py").read_text(encoding="utf-8")
    button = release_page.find('if st.button("Evaluate release gate"')
    load = release_page.find("artifact = load_model_artifact_cached")
    _add(
        checks,
        "No eager model deserialisation",
        button >= 0 and load > button and "discover_model_artifact_candidates" in release_page,
        {"button_index": button, "load_index": load},
    )

    residue = runtime_residue(ROOT)
    _add(checks, "Runtime residue", args.allow_residue or residue["passed"], residue)

    page_smoke: dict[str, object] | None = None
    if args.pages:
        page_smoke = _run_pages()
        _add(checks, "All Streamlit entrypoints", page_smoke["passed"], page_smoke)

    payload = {
        "schema": "biointel.step134-verification.v1",
        "step": 134,
        "version": version,
        "scope": "full-module-reliability-stability",
        "checks": checks,
        "page_smoke": page_smoke,
        "passed": all(bool(item["passed"]) for item in checks),
    }
    output = ROOT / "reports" / "step134_full_module_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
