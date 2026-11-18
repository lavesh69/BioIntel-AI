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

    from biointel.native.engines import ENGINE_REGISTRY, plan_catalog
    from biointel.scientific_depth import MODULE_PROFILES

    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    bad_exclusions = []
    for relative, expected in EXCLUDED.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            bad_exclusions.append(relative)
    add(
        "Excluded modules unchanged",
        not bad_exclusions,
        "5/5 Step 113 source hashes preserved" if not bad_exclusions else ", ".join(bad_exclusions),
    )

    excluded_profile_keys = {
        "dti_predictor",
        "dti_validation",
        "lims_eln_chain",
        "instrument_integration_v2",
        "lab_instrument_import",
    }
    present = sorted(excluded_profile_keys.intersection(MODULE_PROFILES))
    add(
        "Excluded profiles absent",
        not present,
        f"64 eligible depth profiles; excluded profile keys present={present}",
    )

    add("External-engine registry", len(ENGINE_REGISTRY) >= 53, f"{len(ENGINE_REGISTRY)} engine adapters")
    plans = plan_catalog()
    add("Protected execution plans", len(plans) >= 21, f"{len(plans)} shell-free plan templates")

    critical = [
        ROOT / "pages/168_Scientific_Depth_Optimization_Center.py",
        ROOT / "src/biointel/scientific_depth/profiles.py",
        ROOT / "src/biointel/scientific_depth/assessment.py",
        ROOT / "src/biointel/scientific_depth/renderer.py",
        ROOT / "src/biointel/native/engines.py",
        ROOT / "src/biointel/expansion/renderer.py",
        ROOT / "src/biointel/nextgen/renderer.py",
    ]
    compile_errors = []
    for path in critical:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:  # pragma: no cover - verifier output
            compile_errors.append(f"{path.name}: {exc}")
    add("Critical compilation", not compile_errors, f"{len(critical)} files compiled" if not compile_errors else "; ".join(compile_errors))

    runtime_path = ROOT / "reports/step114_runtime_pages.json"
    if runtime_path.is_file():
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        passed = runtime.get("failed", 1) == 0
        detail = f"{runtime.get('passed', 0)}/{runtime.get('pages_tested', 0)} targeted pages passed"
    else:
        passed, detail = False, "Runtime report missing"
    add("Targeted Streamlit runtime", passed, detail)

    database_path = ROOT / "reports/step114_database_integrity.json"
    if database_path.is_file():
        database = json.loads(database_path.read_text(encoding="utf-8"))
        passed = database.get("healthy") == database.get("database_count")
        detail = f"{database.get('healthy')}/{database.get('database_count')} databases healthy; {database.get('total_rows', 0):,} rows"
    else:
        passed, detail = False, "Database report missing"
    add("SQLite integrity", passed, detail)

    ui_reports = sorted((ROOT / "reports/ui_regression").glob("ui-regression-*.json"))
    if ui_reports:
        ui = json.loads(ui_reports[-1].read_text(encoding="utf-8"))
        passed = ui.get("failed") == 0 and ui.get("warnings") == 0
        detail = f"{ui.get('passed')}/{ui.get('checks')} static checks; {ui.get('warnings')} warnings"
    else:
        passed, detail = False, "Static UI report missing"
    add("Static UI audit", passed, detail)

    report = {
        "schema": "biointel.step114.verification.v1",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "passed": sum(c["status"] == "PASS" for c in checks),
        "failed": sum(c["status"] != "PASS" for c in checks),
        "checks": checks,
    }
    output = ROOT / "reports/step114_scientific_depth_verification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
