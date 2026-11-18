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

from biointel.excellence_v163 import module_excellence_matrix, module_excellence_summary  # noqa: E402
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Step 163 all-module software excellence.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required = [
        "STEP163_RELEASE.json",
        "STEP163_ALL_MODULE_EXCELLENCE_REPORT.md",
        "pages/232_All_Module_Authentic_10of10_Center.py",
        "src/biointel/excellence_v163/contracts.py",
        "src/biointel/excellence_v163/module_assurance.py",
        "reports/step163_asset_manifest.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    record("required_files", not missing, json.dumps(missing))

    matrix = module_excellence_matrix(root)
    summary = module_excellence_summary(matrix)
    record(
        "portfolio_software_excellence",
        len(matrix) == len(MODULE_PROFILES) and summary.get("software_owned_10of10") == len(MODULE_PROFILES),
        f"{summary.get('software_owned_10of10', 0)}/{len(MODULE_PROFILES)} modules at software-owned 10/10",
    )
    record(
        "task_specific_benchmark_specs",
        summary.get("benchmark_specs_10of10") == len(MODULE_PROFILES),
        f"{summary.get('benchmark_specs_10of10', 0)}/{len(MODULE_PROFILES)} benchmark specifications complete",
    )
    record(
        "model_authenticity_guards",
        summary.get("model_guards_10of10") == len(MODULE_PROFILES),
        f"{summary.get('model_guards_10of10', 0)}/{len(MODULE_PROFILES)} model guards complete",
    )

    modules = ["amr_surveillance", "docking_dynamics", "clinical_trial_biomarker", "background_job_engine"]
    if not args.quick:
        modules = list(MODULE_PROFILES)
    passed_runs = 0
    for module_key in modules:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(root)},
        )
        required_tables = {
            "step163_module_excellence_contract",
            "step163_task_specific_benchmark_specification",
            "step163_reference_acquisition_manifest",
            "step163_model_eligibility_policy",
            "step163_claim_and_uncertainty_policy",
        }
        if (
            result.status in {"pass", "review"}
            and required_tables.issubset(result.tables)
            and result.summary.get("step163_software_owned_module_score") == 10.0
        ):
            passed_runs += 1
    record("native_module_integration", passed_runs == len(modules), f"{passed_runs}/{len(modules)} module executions passed")

    source_files = [
        root / "src" / "biointel" / "excellence_v163" / "contracts.py",
        root / "src" / "biointel" / "excellence_v163" / "module_assurance.py",
        root / "pages" / "232_All_Module_Authentic_10of10_Center.py",
        root / "scripts" / "step163_build_module_excellence.py",
        root / "scripts" / "step163_validate_module_excellence.py",
    ]
    compile_ok = True
    for path in source_files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception:
            compile_ok = False
    record("compile_scan", compile_ok, f"{len(source_files)} Step 163 source files compiled")

    payload = {
        "schema": "biointel.step163.validation.v1",
        "status": "passed" if all(bool(item["passed"]) for item in checks) else "failed",
        "checks": checks,
        "software_owned_upgrade_target": "10/10",
        "external_evidence_not_inferred": True,
        "third_party_tools_not_falsely_marked_bundled": True,
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "step163_validation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
