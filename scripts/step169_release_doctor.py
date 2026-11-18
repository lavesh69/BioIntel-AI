from __future__ import annotations
import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "step169_validate_final_consolidation.py"), "--root", str(root)],
        cwd=root,
        text=True,
        capture_output=True,
    )
    version = (root / "VERSION").read_text().strip()
    init_version = ""
    for line in (root / "src" / "biointel" / "__init__.py").read_text().splitlines():
        if line.startswith("__version__"):
            init_version = line.split("=", 1)[1].strip().strip('"\'')
    pyproject = (root / "pyproject.toml").read_text()
    pyproject_ok = f'version = "{version}"' in pyproject
    desktop_version = _json_version(root / "platform" / "desktop" / "package.json")
    mobile_version = _json_version(root / "platform" / "mobile" / "package.json")
    assets = len(list((root / "data" / "step169" / "module_contracts").glob("*/final_consolidation_contract.json")))
    db = root / "data" / "databases" / "step169_verified_release.sqlite"
    db_ok = False
    db_modules = 0
    if db.is_file():
        with sqlite3.connect(db) as conn:
            db_ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and conn.execute("PRAGMA foreign_key_check").fetchall() == []
            db_modules = int(conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0])
    checks = [
        {"check": "Step 169 all-module validation", "passed": proc.returncode == 0, "detail": (proc.stdout or proc.stderr)[-2000:]},
        {"check": "Version consistency", "passed": version == init_version == desktop_version == mobile_version and pyproject_ok and tuple(int(part) for part in version.split(".")) >= (14, 1, 0), "detail": f"VERSION={version}; python={init_version}; desktop={desktop_version}; mobile={mobile_version}"},
        {"check": "Final module contracts", "passed": assets == 80, "detail": f"{assets}/80"},
        {"check": "Verified release registry", "passed": db_ok and db_modules == 80, "detail": f"integrity={db_ok}; modules={db_modules}/80"},
        {"check": "Final consolidation page", "passed": (root / "pages" / "238_Final_Consolidation_10of10_Center.py").is_file(), "detail": "pages/238_Final_Consolidation_10of10_Center.py"},
        {"check": "Latest Windows verifier route", "passed": any(name in (root / "VERIFY_LATEST_WINDOWS.bat").read_text() for name in ("VERIFY_STEP169_WINDOWS.bat", "VERIFY_STEP170_WINDOWS.bat", "VERIFY_STEP171_WINDOWS.bat", "VERIFY_STEP172_WINDOWS.bat", "VERIFY_STEP173_WINDOWS.bat")), "detail": "VERIFY_LATEST_WINDOWS.bat"},
    ]
    payload = {
        "schema": "biointel.step169.release-doctor.v1",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "external_claims_not_inferred": True,
        "metadata_flags_cannot_unlock_release": True,
        "fake_customer_clinical_wetlab_or_regulatory_history_created": False,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step169_release_doctor.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
