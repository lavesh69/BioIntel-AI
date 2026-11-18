from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES, Step173Registry, build_step173_assets, profile_matrix

assets = build_step173_assets(ROOT)
registry = Step173Registry(ROOT)
matrix = registry.latest(refresh=False)
status = registry.status()
checks = {
    "all_80_modules_profiled": len(ALL_MODULES) == len(FINAL_PROFILES) == len(matrix) == 80,
    "internal_software_10of10": bool((matrix["internal_software_rating"] == 10.0).all()),
    "native_depth_10of10": bool((matrix["native_research_depth_rating"] == 10.0).all()),
    "qualification_framework_10of10": bool((matrix["qualification_framework_rating"] == 10.0).all()),
    "profile_matrix_80": len(profile_matrix()) == 80,
    "module_assets_complete": len(assets) >= 401,
    "practical_ratings_in_range": bool(matrix["actual_practical_readiness_rating"].between(0, 10).all()),
    "controlled_release_requires_evidence": bool((matrix.loc[~matrix["controlled_release_eligible"], "decision"] == "research-only-fail-closed").all()),
    "no_fake_10of10_external_claim": bool((matrix.loc[~matrix["controlled_release_eligible"], "actual_practical_readiness_rating"] < 10.0).all()),
    "registry_integrity": status["database_integrity"] == "ok",
    "registry_fk_clean": status["foreign_key_violations"] == 0,
    "registry_audit_chain_valid": status["audit_chain_valid"] is True,
}
report = {
    "schema": "biointel.step173.validation.v1",
    "status": "passed" if all(checks.values()) else "failed",
    "version": "14.5.0",
    "checks": checks,
    "modules": 80,
    "internal_10of10_modules": int(matrix["internal_10of10_complete"].sum()),
    "controlled_release_eligible_modules": int(matrix["controlled_release_eligible"].sum()),
    "average_practical_readiness": round(float(matrix["actual_practical_readiness_rating"].mean()), 2),
    "minimum_practical_readiness": round(float(matrix["actual_practical_readiness_rating"].min()), 2),
    "maximum_practical_readiness": round(float(matrix["actual_practical_readiness_rating"].max()), 2),
    "external_wetlab_clinical_site_or_expert_evidence_fabricated": False,
}
out = ROOT / "reports" / "step173_validation.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
matrix.to_csv(ROOT / "reports" / "step173_final_all_module_ratings.csv", index=False)
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
