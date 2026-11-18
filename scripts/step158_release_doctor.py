from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_STEP = 158
PRODUCT_VERSION = "13.2.0"
CURRENT_FILES = {
    "README.md",
    "CURRENT_RELEASE.md",
    "STEP158_RELEASE.json",
    "VERIFY_LATEST_WINDOWS.bat",
    "VERIFY_STEP158_WINDOWS.bat",
    "RUN_RELEASE_DOCTOR_WINDOWS.bat",
    "INSTALL_WINDOWS.bat",
    "RUN_BOTH_WINDOWS.bat",
}
RUNTIME_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUNTIME_SUFFIXES = ("-wal", "-shm", ".pyc", ".pyo")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the canonical BioIntel AI Step 158 release surface.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    def check(key: str, passed: bool, message: str = "", advisory: bool = False) -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message, "advisory": advisory})

    check("root_exists", root.is_dir(), str(root))
    missing = sorted(name for name in CURRENT_FILES if not (root / name).is_file())
    check("canonical_entry_points_present", not missing, json.dumps(missing))

    release_path = root / "STEP158_RELEASE.json"
    release: dict[str, Any] = {}
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except Exception as exc:
        check("release_metadata_parse", False, repr(exc))
    else:
        check("release_metadata_parse", True)
        check("release_step_current", release.get("step") == CURRENT_STEP, str(release.get("step")))
        check("release_product_version", release.get("product_version") == PRODUCT_VERSION, str(release.get("product_version")))
        check("release_boundary_present", bool(release.get("validation_boundary")), "validation_boundary")

    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else ""
    check("version_file_matches", version == PRODUCT_VERSION, version)

    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace") if (root / "README.md").is_file() else ""
    check("readme_current_step", "Step 158" in readme, "README must identify Step 158")
    check("readme_current_version", PRODUCT_VERSION in readme, "README must identify product version")
    stale_header = bool(re.search(r"^#\s+BioIntel AI\s+(?!13\.2\.0)", readme, flags=re.MULTILINE))
    check("readme_no_stale_product_header", not stale_header, "stale BioIntel AI version header")
    check("readme_external_boundary", "cannot manufacture" in readme.lower() or "does not claim" in readme.lower(), "external boundary")

    residue = []
    for path in root.rglob("*"):
        if path.name in RUNTIME_NAMES or path.name.endswith(RUNTIME_SUFFIXES):
            residue.append(path.relative_to(root).as_posix())
    newer_release_present = (root / "STEP159_RELEASE.json").is_file()
    check(
        "release_runtime_residue_absent",
        not residue,
        json.dumps(residue[:100]),
        advisory=newer_release_present,
    )

    sqlite_reports = []
    for db in sorted(root.rglob("*.sqlite3")):
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            con.close()
            sqlite_reports.append({"path": db.relative_to(root).as_posix(), "integrity": integrity, "foreign_key_violations": len(fk)})
        except Exception as exc:
            sqlite_reports.append({"path": db.relative_to(root).as_posix(), "error": repr(exc)})
    sqlite_ok = all(item.get("integrity") == "ok" and item.get("foreign_key_violations") == 0 for item in sqlite_reports)
    check("sqlite_release_integrity", sqlite_ok, f"databases={len(sqlite_reports)}")

    old_verifiers = sorted(p.name for p in root.glob("VERIFY_STEP*_WINDOWS.bat") if p.name != "VERIFY_STEP158_WINDOWS.bat")
    check("historical_verifiers_retained_as_traceability", True, f"historical={len(old_verifiers)}", advisory=True)
    check("latest_verifier_alias_present", (root / "VERIFY_LATEST_WINDOWS.bat").is_file(), "VERIFY_LATEST_WINDOWS.bat")

    blocking = [item for item in checks if not item["passed"] and not item["advisory"]]
    payload = {
        "schema": "biointel.step158.release-doctor.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "step": CURRENT_STEP,
        "product_version": PRODUCT_VERSION,
        "passed": not blocking,
        "checks": checks,
        "blocking_failures": blocking,
        "sqlite_databases": sqlite_reports,
        "historical_verifiers": old_verifiers,
    }
    report = root / "reports" / "step158_release_doctor.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "checks": len(checks), "blocking": len(blocking), "report": str(report)}, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
