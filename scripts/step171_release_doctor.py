from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.models_v171 import Step171Registry, qualification_matrix

checks = []
validation = subprocess.run([sys.executable, str(ROOT / "scripts" / "step171_validate_models.py")], cwd=ROOT, capture_output=True, text=True)
checks.append({"check": "Step 171 model validator", "passed": validation.returncode == 0, "detail": validation.stdout[-1000:] if validation.stdout else validation.stderr[-1000:]})
step170 = subprocess.run([sys.executable, str(ROOT / "scripts" / "step170_validate_runtime_reference.py")], cwd=ROOT, capture_output=True, text=True)
checks.append({"check": "Step 170 runtime/reference compatibility", "passed": step170.returncode == 0, "detail": step170.stdout[-500:] if step170.stdout else step170.stderr[-500:]})
version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
checks.append({"check": "Version 14.3.0", "passed": version == "14.3.0", "detail": version})
latest = (ROOT / "VERIFY_LATEST_WINDOWS.bat").read_text(encoding="utf-8", errors="ignore")
checks.append({"check": "Latest verifier routes Step 171", "passed": "VERIFY_STEP171_WINDOWS.bat" in latest, "detail": "VERIFY_STEP171_WINDOWS.bat"})
status = Step171Registry(ROOT).status()
matrix = qualification_matrix(ROOT)
checks.append({"check": "80-module native assurance integration", "passed": "apply_step171_model_benchmark_assurance" in (ROOT / "src" / "biointel" / "scientific_depth" / "native_workflows.py").read_text(encoding="utf-8"), "detail": "Step 171 assurance hook present"})
passed = all(item["passed"] for item in checks)
payload = {
    "schema": "biointel.step171.release-doctor.v2",
    "version": version,
    "status": "passed" if passed else "failed",
    "checks": checks,
    "applicable_modules": len(matrix),
    "software_framework_10of10": int((matrix["software_framework_score"] == 10.0).sum()),
    "authentic_research_packages": int(matrix["research_benchmark_qualified"].sum()),
    "real_public_or_official_cohorts": int(matrix["real_public_or_official_cohort_present"].sum()),
    "locked_benchmarks": int(matrix["checksum_locked_holdout_complete"].sum()),
    "external_acquisition_required": status["acquisition_pending"],
    "independent_external_sites_complete": status["independent_external_sites"],
    "release_eligible": status["release_eligible_models"],
    "boundary": "Research benchmark qualification is not clinical, wet-lab, regulatory or independent-site approval.",
}
(ROOT / "reports" / "step171_release_doctor.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
raise SystemExit(0 if passed else 1)
