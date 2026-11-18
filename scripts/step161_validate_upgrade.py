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

from biointel.readiness_v161 import (  # noqa: E402
    development_reference_readiness,
    portfolio_upgrade_matrix,
    portfolio_upgrade_summary,
    runtime_recipe_catalog,
    validation_protocol_readiness,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Step 161 all-module upgrade.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required_files = [
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "VERIFY_STEP161_WINDOWS.bat",
        "STEP161_RELEASE.json",
        "CURRENT_RELEASE.md",
        "pages/230_All_Module_10of10_Upgrade_Center.py",
        "src/biointel/readiness_v161/catalog.py",
        "src/biointel/readiness_v161/reference_kits.py",
        "src/biointel/readiness_v161/validation_protocols.py",
        "src/biointel/readiness_v161/assessment.py",
    ]
    missing = [name for name in required_files if not (root / name).is_file()]
    record("required_files", not missing, json.dumps(missing))
    markers = [root / ".release_parts" / f"step161_part{part}.ok" for part in range(1, 5)]
    record("release_markers", all(path.is_file() for path in markers), json.dumps([path.name for path in markers if not path.is_file()]))

    recipes = runtime_recipe_catalog()
    record("runtime_recipes", len(recipes) == 53 and recipes["recipe_complete"].astype(bool).all(), f"{int(recipes['recipe_complete'].astype(bool).sum())}/{len(recipes)} complete")

    references = development_reference_readiness(root)
    record("development_reference_kits", not references.empty and references["development_qualified"].astype(bool).all(), f"{int(references['development_qualified'].astype(bool).sum())}/{len(references)} qualified for development")

    protocols = validation_protocol_readiness(root)
    record("validation_protocols", len(protocols) == len(MODULE_PROFILES) and protocols["protocol_ready"].astype(bool).all(), f"{int(protocols['protocol_ready'].astype(bool).sum())}/{len(protocols)} ready")

    matrix = portfolio_upgrade_matrix(root, detect_runtime=False)
    summary = portfolio_upgrade_summary(matrix)
    record("all_module_upgrade_score", summary["step161_10_of_10"] == len(MODULE_PROFILES), f"{summary['step161_10_of_10']}/{len(MODULE_PROFILES)} at 10/10")

    samples = ["docking_dynamics", "immunoinformatics_vaccine", "single_cell_trajectory", "amr_surveillance"]
    if not args.quick:
        samples = list(MODULE_PROFILES)
    passed_runs = 0
    for module_key in samples:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(root)},
        )
        required_tables = {
            "step161_execution_paths",
            "step161_development_reference_kits",
            "step161_external_validation_protocol",
        }
        if result.status in {"pass", "review"} and required_tables.issubset(result.tables) and result.summary.get("step161_software_upgrade_score") == 10.0:
            passed_runs += 1
    record("native_execution", passed_runs == len(samples), f"{passed_runs}/{len(samples)} module executions passed")

    files = [
        root / "src" / "biointel" / "readiness_v161" / "catalog.py",
        root / "src" / "biointel" / "readiness_v161" / "reference_kits.py",
        root / "src" / "biointel" / "readiness_v161" / "validation_protocols.py",
        root / "src" / "biointel" / "readiness_v161" / "assessment.py",
        root / "pages" / "230_All_Module_10of10_Upgrade_Center.py",
    ]
    compile_ok = True
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception:
            compile_ok = False
    record("compile_scan", compile_ok, f"{len(files)} Step 161 source files compiled")

    payload = {
        "schema": "biointel.step161.validation.v1",
        "status": "passed" if all(bool(item["passed"]) for item in checks) else "failed",
        "checks": checks,
        "external_claims_not_inferred": True,
    }
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "step161_validation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
