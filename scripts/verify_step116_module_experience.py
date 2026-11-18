from __future__ import annotations

import hashlib
import json
import py_compile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    import sys

    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from biointel.ui.module_experience_2_9 import MODULE_EXPERIENCE_CATALOG

    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")
    groups = Counter(spec.group for spec in MODULE_EXPERIENCE_CATALOG.values())
    add("Module workspace catalogue", len(MODULE_EXPERIENCE_CATALOG) == 78, f"{len(MODULE_EXPERIENCE_CATALOG)}/78")
    add("Scientific groups", len(groups) == 8, f"{len(groups)}/8: {dict(groups)}")
    affected = [p for p in (ROOT / "pages").glob("*.py") if "STEP116_MODULE_EXPERIENCE_2_TO_9" in p.read_text(encoding="utf-8", errors="ignore")]
    add("Embedded pages", len(affected) == 77, f"{len(affected)}/77")
    add("Hub page", (ROOT / "pages/170_Module_Experience_Canvases_2_to_9.py").is_file(), "page 170 present")

    mismatches = [relative for relative, expected in EXCLUDED.items() if sha256(ROOT / relative) != expected]
    add("Excluded modules unchanged", not mismatches, "5/5 source hashes preserved" if not mismatches else ", ".join(mismatches))

    critical = [
        ROOT / "src/biointel/ui/module_experience_2_9.py",
        ROOT / "src/biointel/ui/runtime_guard.py",
        ROOT / "pages/170_Module_Experience_Canvases_2_to_9.py",
        ROOT / "src/biointel/ui/navigation.py",
    ]
    errors = []
    for path in critical:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    add("Critical compilation", not errors, f"{len(critical)} files compiled" if not errors else "; ".join(errors))

    report_checks = [
        ("step116_runtime_pages.json", lambda d: d.get("failed") == 0 and d.get("passed") == 77, "77/77 affected pages"),
        ("step116_renderer_states.json", lambda d: d.get("failed") == 0 and d.get("passed") == 40, "40/40 renderer states"),
        ("step116_static_audit.json", lambda d: d.get("failed") == 0, "static compilation audit"),
        ("step116_database_integrity.json", lambda d: d.get("healthy") == d.get("database_count"), "all SQLite databases"),
        ("step116_self_test.json", lambda d: d.get("failed") == 0 and d.get("passed") == 7, "7/7 self-tests"),
    ]
    for report_name, predicate, description in report_checks:
        path = ROOT / "reports" / report_name
        if not path.is_file():
            add(description, False, f"{report_name} missing")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        add(description, bool(predicate(data)), report_name)

    report = {
        "schema": "biointel.step116.verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "passed": sum(item["status"] == "PASS" for item in checks),
        "failed": sum(item["status"] != "PASS" for item in checks),
        "checks": checks,
    }
    (ROOT / "reports/step116_verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
