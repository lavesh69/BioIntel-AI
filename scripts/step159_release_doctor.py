from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sqlite_check(path: Path) -> tuple[bool, str]:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
        finally:
            connection.close()
        return integrity.lower() == "ok" and not foreign_keys, f"integrity={integrity}; foreign_keys={len(foreign_keys)}"
    except sqlite3.Error as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))

    from biointel.stability_v159.module_health import reliability_summary
    from biointel.stability_v159.resource_guard import resource_manifest

    checks: list[dict[str, Any]] = []

    def check(key: str, passed: bool, message: str, *, advisory: bool = False) -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message, "advisory": advisory})

    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else ""
    release_path = root / "STEP159_RELEASE.json"
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        release = {}
    check("release_metadata", release.get("step") == 159, str(release_path))
    check("product_version", release.get("product_version") == version == "13.2.0", version)
    required = [
        "VERIFY_LATEST_WINDOWS.bat",
        "VERIFY_STEP159_WINDOWS.bat",
        "RUN_RELEASE_DOCTOR_WINDOWS.bat",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "CURRENT_RELEASE.md",
        "pages/228_Module_Reliability_Command_Center.py",
        "src/biointel/stability_v159/resource_guard.py",
        "src/biointel/stability_v159/circuit_breaker.py",
    ]
    missing = [name for name in required if not (root / name).is_file()]
    check("current_entry_points", not missing, json.dumps(missing))

    markers = [root / ".release_parts" / f"step159_part{part}.ok" for part in range(1, 5)]
    check("four_part_markers", all(path.is_file() for path in markers), json.dumps([path.name for path in markers if not path.is_file()]))

    summary = reliability_summary(root)
    check("scientific_contracts", summary["internal_complete"] == summary["scientific_modules"] == 80, json.dumps(summary, default=str))
    check("registered_screens", summary["pages_present"] == summary["pages_syntax_clean"] == summary["pages"] >= 230, json.dumps(summary, default=str))
    resource = resource_manifest(root)
    check("resource_guard", resource["snapshot"]["available_memory_bytes"] >= 0, json.dumps(resource["snapshot"]))

    residue_names = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    residue = []
    for path in root.rglob("*"):
        if path.name in residue_names or path.suffix in {".pyc", ".pyo"} or path.name.endswith(("-wal", "-shm")):
            residue.append(path.relative_to(root).as_posix())
            if len(residue) >= 100:
                break
    check("release_runtime_residue_absent", not residue, json.dumps(residue))

    database_results: list[dict[str, Any]] = []
    if not args.quick:
        for path in sorted(root.rglob("*.sqlite3")):
            if "UserData" in path.parts:
                continue
            passed, detail = _sqlite_check(path)
            database_results.append({"path": path.relative_to(root).as_posix(), "passed": passed, "detail": detail})
        check("sqlite_integrity", bool(database_results) and all(item["passed"] for item in database_results), f"{sum(item['passed'] for item in database_results)}/{len(database_results)}")
    else:
        check("sqlite_integrity", True, "Skipped in quick mode", advisory=True)

    blocking = [item for item in checks if not item["passed"] and not item["advisory"]]
    report = {
        "schema": "biointel.step159.release-doctor.v1",
        "step": 159,
        "product_version": version,
        "passed": not blocking,
        "checks": checks,
        "blocking": len(blocking),
        "reliability_summary": summary,
        "database_results": database_results,
        "boundary": "Internal software and package reliability only; external scientific, clinical, regulatory and wet-lab evidence is not manufactured.",
    }
    output = root / "reports" / "step159_release_doctor.json"
    _atomic_json(output, report)
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "blocking": len(blocking), "report": str(output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
