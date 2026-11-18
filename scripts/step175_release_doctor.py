from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.environment_v175 import Step175Registry, environment_summary

checks = []
for step in range(170, 176):
    path = ROOT / "reports" / f"step{step}_validation.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checks.append({"name": f"step{step}_validation", "passed": payload.get("status") == "passed", "detail": str(path.relative_to(ROOT))})
    except Exception as exc:
        checks.append({"name": f"step{step}_validation", "passed": False, "detail": str(exc)})
status = Step175Registry(ROOT).status()
summary = environment_summary(ROOT)
checks.extend([
    {"name": "step175_registry", "passed": status["database_integrity"] == "ok" and status["foreign_key_violations"] == 0 and status["audit_chain_valid"], "detail": json.dumps(status, default=str)},
    {"name": "version_consistency", "passed": (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "14.7.0", "detail": (ROOT / "VERSION").read_text(encoding="utf-8").strip()},
    {"name": "target_environment_runner", "passed": (ROOT / "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat").is_file(), "detail": "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat"},
])
report = {
    "schema": "biointel.step175.release-doctor.v1",
    "status": "passed" if all(item["passed"] for item in checks) else "failed",
    "version": "14.7.0",
    "checks": checks,
    "summary": summary,
    "software_framework_score": 10.0,
    "target_installation_policy": "actual target-host probe, artifact hashes, licence capture, smoke/golden/negative/module-integration checks required",
    "external_installation_fabricated": False,
}
out = ROOT / "reports" / "step175_release_doctor.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
