from __future__ import annotations

import hashlib
import json
import py_compile
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

    from biointel.ui.non_chart_scientific_visuals import MODULE_NON_CHART_CONTEXTS, NON_CHART_VISUAL_CATALOG

    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")
    add("Advanced non-chart catalogue", len(NON_CHART_VISUAL_CATALOG) == 15, f"{len(NON_CHART_VISUAL_CATALOG)}/15")
    add("Module-specific workspaces", len(MODULE_NON_CHART_CONTEXTS) == 13, f"{len(MODULE_NON_CHART_CONTEXTS)}/13")

    mismatches = [relative for relative, expected in EXCLUDED.items() if sha256(ROOT / relative) != expected]
    add("Excluded modules unchanged", not mismatches, "5/5 source hashes preserved" if not mismatches else ", ".join(mismatches))

    critical = [
        ROOT / "src/biointel/ui/non_chart_scientific_visuals.py",
        ROOT / "pages/169_Non_Chart_Scientific_Visuals.py",
        ROOT / "src/biointel/ui/navigation.py",
    ]
    errors = []
    for path in critical:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    add("Critical compilation", not errors, f"{len(critical)} files compiled" if not errors else "; ".join(errors))

    for report_name, label, count_key, expected in [
        ("step115_runtime_non_chart.json", "Runtime pages and renderer states", "failed", 0),
        ("step115_static_audit.json", "Static page and Python audit", "failed", 0),
        ("step115_database_integrity.json", "SQLite integrity", "healthy", None),
        ("step115_self_test.json", "Application self-test", "failed", 0),
    ]:
        path = ROOT / "reports" / report_name
        if not path.is_file():
            add(label, False, "Report missing")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if report_name == "step115_database_integrity.json":
            passed = data.get("healthy") == data.get("database_count")
            detail = f"{data.get('healthy')}/{data.get('database_count')} databases healthy"
        else:
            passed = data.get(count_key) == expected
            detail = f"{count_key}={data.get(count_key)}"
        add(label, passed, detail)

    report = {
        "schema": "biointel.step115.verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "passed": sum(item["status"] == "PASS" for item in checks),
        "failed": sum(item["status"] != "PASS" for item in checks),
        "checks": checks,
    }
    output = ROOT / "reports" / "step115_verification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
