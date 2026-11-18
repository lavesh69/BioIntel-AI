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
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))

    from biointel.scientific_depth import MODULE_PROFILES, native_input_template, native_portfolio_manifest, run_native_workflow
    from biointel.stability_v159.module_health import page_source_health, reliability_summary
    from biointel.stability_v159.resource_guard import assess_dataframe_admission

    checks: list[dict[str, Any]] = []

    def check(key: str, passed: bool, message: str) -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message})

    required = [
        "app.py", "INSTALL_WINDOWS.bat", "RUN_BOTH_WINDOWS.bat", "VERIFY_STEP159_WINDOWS.bat",
        "STEP159_RELEASE.json", "CURRENT_RELEASE.md", "pages/228_Module_Reliability_Command_Center.py",
    ]
    missing = [name for name in required if not (root / name).is_file()]
    check("required_files", not missing, json.dumps(missing))
    markers = [root / ".release_parts" / f"step159_part{part}.ok" for part in range(1, 5)]
    check("release_markers", all(path.is_file() for path in markers), json.dumps([path.name for path in markers if not path.is_file()]))

    pages = page_source_health(root)
    check("page_sources", len(pages) >= 230 and pages["exists"].all() and pages["syntax_ok"].all(), f"{int(pages.syntax_ok.sum())}/{len(pages)}")
    summary = reliability_summary(root)
    check("scientific_contracts", summary["scientific_modules"] == summary["internal_complete"] == 80, json.dumps(summary, default=str))

    manifest = native_portfolio_manifest()
    check("native_portfolio", manifest["workflows"] == 80 and manifest["families"] == 49, f"workflows={manifest['workflows']}; families={manifest['families']}")
    check("step159_controls", all(manifest.get(key) is True for key in (
        "step159_resource_aware_admission", "step159_crash_loop_circuit_breaker", "step159_persistent_redacted_failure_diagnostics"
    )), json.dumps({key: manifest.get(key) for key in manifest if key.startswith("step159_")}))

    modules = sorted(MODULE_PROFILES)
    selected = modules[:3] if args.quick else modules
    statuses: dict[str, str] = {}
    for module_key in selected:
        demo = native_input_template(module_key, demonstration=True)
        admission = assess_dataframe_admission(demo, "auto", root=root)
        result = run_native_workflow(module_key, demo, metadata={"analysis_mode": "auto"})
        statuses[module_key] = result.status
        if not admission.allowed or result.status == "fail":
            break
    check("native_demo_execution", len(statuses) == len(selected) and all(value in {"pass", "review"} for value in statuses.values()), json.dumps(statuses))

    residue = []
    for path in root.rglob("*"):
        if path.name.endswith(("-wal", "-shm")) or path.suffix in {".pyc", ".pyo"} or path.name in {"__pycache__", ".pytest_cache"}:
            residue.append(path.relative_to(root).as_posix())
            if len(residue) >= 100:
                break
    check("release_hygiene", True if args.quick else not residue, "Skipped in quick mode" if args.quick else json.dumps(residue))

    failed = [item for item in checks if not item["passed"]]
    report = {
        "schema": "biointel.step159.installation-validation.v1",
        "step": 159,
        "passed": not failed,
        "checks": checks,
        "failed": len(failed),
        "modules_executed": len(statuses),
        "module_statuses": statuses,
    }
    output = root / "reports" / "step159_installation_validation.json"
    _atomic_json(output, report)
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "failed": len(failed), "report": str(output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
