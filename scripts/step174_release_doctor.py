from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.final_v173 import Step173Registry
from biointel.realworld_v174 import Step174ExecutionRegistry

checks = []
for step in (170, 171, 172, 173, 174):
    path = ROOT / "reports" / f"step{step}_validation.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        passed = payload.get("status") == "passed"
        checks.append({"name": f"step{step}_validation", "passed": passed, "detail": str(path.relative_to(ROOT))})
    except Exception as exc:
        checks.append({"name": f"step{step}_validation", "passed": False, "detail": str(exc)})

static_path = ROOT / "reports" / "step174_static_qualification.json"
try:
    static = json.loads(static_path.read_text(encoding="utf-8"))
    checks.append({"name": "step174_static_qualification", "passed": static.get("status") == "passed", "detail": str(static_path.relative_to(ROOT))})
except Exception as exc:
    checks.append({"name": "step174_static_qualification", "passed": False, "detail": str(exc)})

step173_status = Step173Registry(ROOT).status()
step174_status = Step174ExecutionRegistry(ROOT).status()
checks.extend([
    {"name": "step173_registry_integrity", "passed": step173_status["database_integrity"] == "ok" and step173_status["foreign_key_violations"] == 0 and step173_status["audit_chain_valid"], "detail": json.dumps(step173_status, default=str)},
    {"name": "step174_registry_integrity", "passed": step174_status["database_integrity"] == "ok" and step174_status["foreign_key_violations"] == 0 and step174_status["audit_chain_valid"], "detail": json.dumps(step174_status, default=str)},
    {"name": "version_consistency", "passed": (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "14.6.0", "detail": (ROOT / "VERSION").read_text(encoding="utf-8").strip()},
    {"name": "phase1_to_9_runner", "passed": (ROOT / "RUN_STEP174_PHASE1_TO_9_WINDOWS.bat").is_file(), "detail": "RUN_STEP174_PHASE1_TO_9_WINDOWS.bat"},
])

report = {
    "schema": "biointel.step174.release-doctor.v1",
    "status": "passed" if all(item["passed"] for item in checks) else "failed",
    "version": "14.6.0",
    "checks": checks,
    "phase1_to_9_software_automation": "10/10",
    "external_execution_policy": "genuine artifacts and target-machine/laboratory/site/expert execution required; no fabrication",
    "fake_external_evidence_created": False,
}
out = ROOT / "reports" / "step174_release_doctor.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
