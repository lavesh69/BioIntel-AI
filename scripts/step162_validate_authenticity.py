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

from biointel.authenticity_v162 import (  # noqa: E402
    legacy_model_authenticity,
    portfolio_authenticity_matrix,
    portfolio_authenticity_summary,
    provider_contract_matrix,
    verify_public_benchmark_suite,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Step 162 model authenticity controls.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required = [
        "STEP162_RELEASE.json",
        "STEP162_MODEL_AUTHENTICITY_REPORT.md",
        "pages/231_Model_Authenticity_10of10_Center.py",
        "src/biointel/authenticity_v162/benchmark_suite.py",
        "src/biointel/authenticity_v162/model_registry.py",
        "src/biointel/authenticity_v162/provider_contracts.py",
        "src/biointel/authenticity_v162/module_assurance.py",
        "models/authenticity_registry.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    record("required_files", not missing, json.dumps(missing))

    benchmarks = verify_public_benchmark_suite(root)
    record(
        "public_benchmark_models",
        len(benchmarks) == 5 and benchmarks["passed"].astype(bool).all(),
        f"{int(benchmarks['passed'].astype(bool).sum())}/{len(benchmarks)} verified",
    )
    legacy = legacy_model_authenticity(root)
    synthetic = int(legacy["synthetic_demo"].astype(bool).sum()) if not legacy.empty else 0
    unsafe_defaults = int(
        (legacy["synthetic_demo"].astype(bool) & legacy["default_scientific_inference_allowed"].astype(bool)).sum()
    ) if not legacy.empty else 0
    record("synthetic_model_quarantine", synthetic >= 23 and unsafe_defaults == 0, f"{synthetic} synthetic models quarantined; unsafe defaults={unsafe_defaults}")

    providers = provider_contract_matrix(root)
    record(
        "provider_source_contracts",
        len(providers) == 14 and providers["source_descriptor_verified"].astype(bool).all(),
        f"{int(providers['source_descriptor_verified'].astype(bool).sum())}/{len(providers)} descriptors verified; {int(providers['local_snapshot_checksum_verified'].astype(bool).sum())} have local checksummed assets",
    )

    matrix = portfolio_authenticity_matrix(root)
    summary = portfolio_authenticity_summary(matrix)
    record(
        "module_authenticity_contracts",
        len(matrix) == len(MODULE_PROFILES) and summary["software_authenticity_10_of_10"] == len(MODULE_PROFILES),
        f"{summary['software_authenticity_10_of_10']}/{len(MODULE_PROFILES)} software authenticity contracts at 10/10",
    )

    modules = ["benchmark_validation_v2", "docking_dynamics", "cancer_genomics_core", "amr_surveillance"]
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
            "step162_model_authenticity_contract",
            "step162_production_reference_requirements",
        }
        if (
            result.status in {"pass", "review"}
            and required_tables.issubset(result.tables)
            and result.summary.get("step162_software_authenticity_score") == 10.0
        ):
            passed_runs += 1
    record("native_module_integration", passed_runs == len(modules), f"{passed_runs}/{len(modules)} module executions passed")

    source_files = [
        root / "src" / "biointel" / "authenticity_v162" / "benchmark_suite.py",
        root / "src" / "biointel" / "authenticity_v162" / "model_registry.py",
        root / "src" / "biointel" / "authenticity_v162" / "provider_contracts.py",
        root / "src" / "biointel" / "authenticity_v162" / "module_assurance.py",
        root / "src" / "biointel" / "authenticity_v162" / "assessment.py",
        root / "pages" / "231_Model_Authenticity_10of10_Center.py",
    ]
    compile_ok = True
    for path in source_files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception:
            compile_ok = False
    record("compile_scan", compile_ok, f"{len(source_files)} Step 162 source files compiled")

    payload = {
        "schema": "biointel.step162.validation.v1",
        "status": "passed" if all(bool(item["passed"]) for item in checks) else "failed",
        "checks": checks,
        "external_claims_not_inferred": True,
        "public_benchmark_is_not_domain_validation": True,
    }
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "step162_validation.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
