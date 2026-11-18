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
    parser = argparse.ArgumentParser(description="Run the Step 160 release doctor.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))

    from biointel.quality_v160 import portfolio_quality_matrix, portfolio_quality_summary
    from biointel.stability_v159.module_health import page_source_health
    from biointel.stability_v159.resource_guard import resource_manifest

    checks: list[dict[str, Any]] = []

    def check(key: str, passed: bool, message: str, *, advisory: bool = False) -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message, "advisory": advisory})

    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else ""
    try:
        release = json.loads((root / "STEP160_RELEASE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        release = {}
    check("release_metadata", release.get("step") == 160, "STEP160_RELEASE.json")
    check("product_version", release.get("product_version") == version == "13.2.0", version)

    required = [
        "VERIFY_LATEST_WINDOWS.bat",
        "VERIFY_STEP160_WINDOWS.bat",
        "RUN_RELEASE_DOCTOR_WINDOWS.bat",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "pages/229_Module_Quality_10of10_Command_Center.py",
        "src/biointel/quality_v160/assurance.py",
    ]
    missing = [name for name in required if not (root / name).is_file()]
    check("current_entry_points", not missing, json.dumps(missing))

    markers = [root / ".release_parts" / f"step160_part{part}.ok" for part in range(1, 5)]
    check("four_part_markers", all(path.is_file() for path in markers), json.dumps([path.name for path in markers if not path.is_file()]))

    pages = page_source_health(root)
    check("registered_screens", len(pages) == 231 and pages["exists"].all() and pages["syntax_ok"].all(), f"{int(pages.syntax_ok.sum())}/{len(pages)}")

    quality = portfolio_quality_matrix(root, detect_runtime=not args.quick)
    summary = portfolio_quality_summary(quality)
    check("internal_module_quality", summary["modules"] == summary["internal_10_of_10"] == 80, json.dumps(summary))
    check("quality_contract_files", len(list((root / "data/module_quality_contracts/step160").glob("*.json"))) == 80, "80 per-module contracts required")

    resource = resource_manifest(root)
    check("resource_guard", resource["snapshot"]["available_memory_bytes"] >= 0, json.dumps(resource["snapshot"]))

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
        "schema": "biointel.step160.release-doctor.v1",
        "step": 160,
        "product_version": version,
        "passed": not blocking,
        "checks": checks,
        "blocking": len(blocking),
        "quality_summary": summary,
        "database_results": database_results,
        "boundary": "80/80 internal module quality contracts can be verified locally. Specialist binaries, qualified reference data and independent scientific/clinical/regulatory evidence remain external outcomes.",
    }
    output = root / "reports" / "step160_release_doctor.json"
    _atomic_json(output, report)
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "blocking": len(blocking), "report": str(output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
