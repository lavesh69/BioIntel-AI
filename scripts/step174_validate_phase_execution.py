from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.final_v173 import ALL_MODULES
from biointel.realworld_v174 import PHASES, Step174ExecutionRegistry, build_step174_assets, phase_catalog

assets = build_step174_assets(ROOT)
registry = Step174ExecutionRegistry(ROOT)
matrix = registry.latest(refresh=False)
status = registry.status()
checks = {
    "exactly_nine_phases": len(PHASES) == len(phase_catalog()) == 9,
    "all_80_modules_covered": len(ALL_MODULES) == len(matrix) == 80,
    "software_automation_10of10": bool((matrix["software_phase_automation_rating"] == 10.0).all()),
    "all_phase_automation_available": bool(matrix["all_phase_software_automation_available"].all()),
    "phase_counts_valid": bool((matrix["completed_phases"] <= matrix["required_phases"]).all()),
    "no_fake_external_completion": bool((matrix.loc[~matrix["controlled_release_eligible"], "decision"] == "research-only-fail-closed").all()),
    "external_evidence_fabricated_false": bool((matrix["external_evidence_fabricated"] == False).all()),
    "module_assets_complete": len(assets) >= 960,
    "registry_integrity": status["database_integrity"] == "ok",
    "registry_fk_clean": status["foreign_key_violations"] == 0,
    "registry_audit_chain_valid": status["audit_chain_valid"] is True,
}
report = {
    "schema": "biointel.step174.validation.v1",
    "status": "passed" if all(checks.values()) else "failed",
    "version": "14.6.0",
    "checks": checks,
    "phases": 9,
    "modules": 80,
    "assets": len(assets),
    "controlled_release_eligible_modules": int(matrix["controlled_release_eligible"].sum()),
    "average_completed_external_phases": round(float(matrix["completed_phases"].mean()), 2),
    "external_evidence_fabricated": False,
}
out = ROOT / "reports" / "step174_validation.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
matrix.to_csv(ROOT / "reports" / "step174_phase1_to_9_execution_matrix.csv", index=False)
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
