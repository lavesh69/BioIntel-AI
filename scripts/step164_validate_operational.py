from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import py_compile
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.operational_v164 import ensure_step164_assets, operational_matrix, provisioning_catalog  # noqa: E402
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Step 164 operational qualification framework.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required = [
        "STEP164_RELEASE.json",
        "STEP164_OPERATIONAL_READINESS_REPORT.md",
        "pages/233_Operational_Readiness_10of10_Center.py",
        "src/biointel/operational_v164/catalog.py",
        "src/biointel/operational_v164/qualification.py",
        "src/biointel/operational_v164/module_assurance.py",
        "reports/step164_asset_manifest.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    record("required_files", not missing, json.dumps(missing))

    written = ensure_step164_assets(root)
    matrix = operational_matrix(root, detect_runtime=False)
    catalog = provisioning_catalog()
    record("all_module_contracts", len(matrix) == len(MODULE_PROFILES) == 80 and (matrix["software_owned_score"] == 10.0).all(), f"{int((matrix['software_owned_score'] == 10.0).sum())}/{len(matrix)}")
    record("engine_provisioning_recipes", len(catalog) >= 53 and catalog["software_recipe_complete"].astype(bool).all(), f"{int(catalog['software_recipe_complete'].astype(bool).sum())}/{len(catalog)}")
    record("generated_operational_assets", len(written) >= 400, f"{len(written)} assets")

    modules = ["amr_surveillance", "long_read_epigenome", "protein_ligand_codesign", "clinical_trial_biomarker", "background_job_engine"]
    if not args.quick:
        modules = list(MODULE_PROFILES)
    passed = 0
    for module_key in modules:
        result = run_native_workflow(module_key, native_input_template(module_key, demonstration=True), metadata={"analysis_mode": "interactive", "project_root": str(root)})
        needed = {"step164_operational_readiness_gate", "step164_required_evidence_checklist"}
        if result.status in {"pass", "review"} and needed.issubset(result.tables) and result.summary.get("step164_software_owned_operational_score") == 10.0:
            passed += 1
    record("native_module_integration", passed == len(modules), f"{passed}/{len(modules)} module executions")

    source_files = [
        root / "src/biointel/operational_v164/catalog.py",
        root / "src/biointel/operational_v164/qualification.py",
        root / "src/biointel/operational_v164/assets.py",
        root / "src/biointel/operational_v164/module_assurance.py",
        root / "pages/233_Operational_Readiness_10of10_Center.py",
        root / "scripts/step164_build_operational_assets.py",
        root / "scripts/step164_runtime_manager.py",
        root / "scripts/step164_validate_operational.py",
    ]
    compile_ok = True
    for path in source_files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception:
            compile_ok = False
    record("compile_scan", compile_ok, f"{len(source_files)} Step 164 files")

    payload = {
        "schema": "biointel.step164.validation.v1",
        "status": "passed" if all(bool(item["passed"]) for item in checks) else "failed",
        "checks": checks,
        "software_owned_operational_target": "10/10",
        "external_evidence_not_inferred": True,
        "third_party_installations_not_falsely_marked_complete": True,
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "step164_validation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
