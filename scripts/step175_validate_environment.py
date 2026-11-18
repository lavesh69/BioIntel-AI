from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.environment_v175 import (
    Step175Registry,
    build_step175_assets,
    engine_execution_catalog,
    environment_groups,
    environment_summary,
    execution_matrix,
    reference_execution_catalog,
    target_profiles,
)

checks = []

def check(name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})

assets = build_step175_assets(ROOT)
engines = engine_execution_catalog()
refs = reference_execution_catalog()
groups = environment_groups()
profiles = target_profiles()
matrix = execution_matrix(ROOT)
status = Step175Registry(ROOT).status()
check("version", (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "14.7.0", (ROOT / "VERSION").read_text(encoding="utf-8").strip())
check("engine_catalog", len(engines) == 53 and engines["engine"].nunique() == 53, f"{len(engines)}/53")
check("reference_catalog", len(refs) == 26 and refs["reference_id"].nunique() == 26, f"{len(refs)}/26")
check("environment_groups", len(groups) == 12, str(len(groups)))
check("target_profiles", len(profiles) == 3, str(len(profiles)))
check("qualification_matrix", len(matrix) == 79, str(len(matrix)))
check("software_framework", (matrix["step175_framework_score"] == 10.0).all(), "79/79")
check("fail_closed", (~matrix["final_target_qualification_complete"] | (matrix["artifact_qualified"] & matrix["target_host_qualified"])).all(), "target + artifact required")
check("assets", len(assets) >= 180, str(len(assets)))
check("registry_integrity", status["database_integrity"] == "ok" and status["foreign_key_violations"] == 0 and status["audit_chain_valid"], json.dumps(status, default=str))
for name in (
    "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat", "VERIFY_STEP175_WINDOWS.bat", "RUN_STEP175_RELEASE_DOCTOR_WINDOWS.bat",
    "BUILD_STEP175_ENVIRONMENT_ASSETS_WINDOWS.bat", "scripts/windows/step175_target_environment.ps1", "scripts/linux/step175_execute_wsl.sh",
):
    check(f"file:{name}", (ROOT / name).is_file(), name)

report = {
    "schema": "biointel.step175.validation.v1",
    "status": "passed" if all(item["passed"] for item in checks) else "failed",
    "version": "14.7.0",
    "checks": checks,
    "engines": 53,
    "references": 26,
    "software_framework_score": 10.0,
    "external_installation_fabricated": False,
}
out = ROOT / "reports" / "step175_validation.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
