from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Step 160 module-quality release.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))

    from biointel.quality_v160 import portfolio_quality_matrix, portfolio_quality_summary
    from biointel.scientific_depth import MODULE_PROFILES, native_input_template, native_portfolio_manifest, run_native_workflow
    from biointel.stability_v159.module_health import page_source_health
    from biointel.ui.navigation import PAGE_BY_KEY

    checks: list[dict[str, Any]] = []

    def check(key: str, passed: bool, message: str) -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message})

    required = [
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "VERIFY_STEP160_WINDOWS.bat",
        "STEP160_RELEASE.json",
        "CURRENT_RELEASE.md",
        "pages/229_Module_Quality_10of10_Command_Center.py",
        "src/biointel/quality_v160/contracts.py",
        "src/biointel/quality_v160/assurance.py",
        "src/biointel/quality_v160/native_assurance.py",
    ]
    missing = [name for name in required if not (root / name).is_file()]
    check("required_files", not missing, json.dumps(missing))

    markers = [root / ".release_parts" / f"step160_part{part}.ok" for part in range(1, 5)]
    check("release_markers", all(path.is_file() for path in markers), json.dumps([path.name for path in markers if not path.is_file()]))

    contracts = sorted((root / "data" / "module_quality_contracts" / "step160").glob("*.json"))
    check("per_module_contracts", len(contracts) == 80, f"{len(contracts)}/80")

    pages = page_source_health(root)
    check("page_sources", len(pages) >= 231 and pages["exists"].all() and pages["syntax_ok"].all(), f"{int(pages.syntax_ok.sum())}/{len(pages)}")
    check("quality_command_center", "module_quality_10of10_command_center" in PAGE_BY_KEY, str(PAGE_BY_KEY.get("module_quality_10of10_command_center")))

    quality = portfolio_quality_matrix(root, detect_runtime=not args.quick)
    summary = portfolio_quality_summary(quality)
    check("scientific_modules", len(MODULE_PROFILES) == 80 and len(quality) == 80, f"profiles={len(MODULE_PROFILES)}; matrix={len(quality)}")
    check("internal_quality_10of10", summary["internal_10_of_10"] == 80, json.dumps(summary))
    check("quality_dimensions", bool((quality["dimensions_passed"] == 10).all() and (quality["dimensions_total"] == 10).all()), "Every module must pass 10/10 software-owned dimensions")

    native_manifest = native_portfolio_manifest()
    check("step160_native_controls", all(native_manifest.get(key) is True for key in (
        "step160_internal_quality_contracts",
        "step160_full_input_integrity_audit",
        "step160_output_table_integrity_audit",
        "step160_reproducibility_signature",
    )), json.dumps({key: native_manifest.get(key) for key in native_manifest if key.startswith("step160_")}))

    modules = sorted(MODULE_PROFILES)
    selected = modules[:4] if args.quick else modules
    statuses: dict[str, str] = {}
    assurance_tables: dict[str, list[str]] = {}
    for module_key in selected:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "auto", "project_root": str(root)},
        )
        statuses[module_key] = result.status
        assurance_tables[module_key] = sorted(name for name in result.tables if name.startswith("step160_"))
        if result.status == "fail" or result.summary.get("step160_internal_quality_score") != 10.0:
            break
    check("native_demo_execution", len(statuses) == len(selected) and all(value in {"pass", "review"} for value in statuses.values()), json.dumps(statuses))
    check("native_assurance_outputs", len(assurance_tables) == len(selected) and all(len(names) >= 3 for names in assurance_tables.values()), json.dumps(assurance_tables))

    failed = [item for item in checks if not item["passed"]]
    report = {
        "schema": "biointel.step160.installation-validation.v1",
        "step": 160,
        "passed": not failed,
        "checks": checks,
        "failed": len(failed),
        "modules_executed": len(statuses),
        "module_statuses": statuses,
        "quality_summary": summary,
    }
    output = root / "reports" / "step160_installation_validation.json"
    _atomic_json(output, report)
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "failed": len(failed), "report": str(output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
