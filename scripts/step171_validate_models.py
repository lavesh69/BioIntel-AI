from __future__ import annotations

from pathlib import Path
import json
import sys

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.models_v171 import APPLICABLE_MODULES, Step171Registry, qualification_matrix, sha256_file

checks = []
base = ROOT / "data" / "step171"
manifest = json.loads((base / "build_manifest.json").read_text(encoding="utf-8"))
checks.append({"check": "12 applicable module contracts", "passed": len(list((base / "module_contracts").glob("*/model_qualification_contract.json"))) == 12, "detail": str(len(list((base / "module_contracts").glob("*/model_qualification_contract.json"))))})
checks.append({"check": "8 authentic research packages", "passed": len(list((base / "model_packages").glob("*/model_card.json"))) == 8, "detail": str(len(list((base / "model_packages").glob("*/model_card.json"))))})
checks.append({"check": "4 external acquisition plans", "passed": len(list((base / "acquisition_manifests").glob("*/acquisition_manifest.json"))) == 4, "detail": str(len(list((base / "acquisition_manifests").glob("*/acquisition_manifest.json"))))})

file_failures = []
load_failures = []
for package_dir in sorted((base / "model_packages").iterdir()):
    if not package_dir.is_dir():
        continue
    file_manifest_path = package_dir / "FILE_MANIFEST_SHA256.json"
    payload = json.loads(file_manifest_path.read_text(encoding="utf-8"))
    for item in payload["files"]:
        path = package_dir / item["path"]
        if not path.exists() or sha256_file(path) != item["sha256"]:
            file_failures.append(str(path.relative_to(ROOT)))
    card = json.loads((package_dir / "model_card.json").read_text(encoding="utf-8"))
    artifact = ROOT / card["model_artifact"]
    if not artifact.exists() or sha256_file(artifact) != card["model_sha256"]:
        load_failures.append(f"hash:{card['module_key']}")
    elif artifact.suffix == ".joblib":
        try:
            joblib.load(artifact)
        except Exception as exc:
            load_failures.append(f"load:{card['module_key']}:{type(exc).__name__}")
checks.append({"check": "package file manifests", "passed": not file_failures, "detail": ", ".join(file_failures) or "all package hashes match"})
checks.append({"check": "model artifacts load and hash", "passed": not load_failures, "detail": ", ".join(load_failures) or "all joblib artifacts load"})

registry = Step171Registry(ROOT, rebuild=True)
status = registry.status()
matrix = qualification_matrix(ROOT)
checks.extend([
    {"check": "registry integrity", "passed": status["database_integrity"] == "ok" and status["foreign_key_violations"] == 0, "detail": str(status)},
    {"check": "matrix module coverage", "passed": len(matrix) == len(APPLICABLE_MODULES) == 12, "detail": str(len(matrix))},
    {"check": "authentic research benchmarks", "passed": int(matrix["research_benchmark_qualified"].sum()) == 8, "detail": str(int(matrix["research_benchmark_qualified"].sum()))},
    {"check": "real public or official cohorts", "passed": int(matrix["real_public_or_official_cohort_present"].sum()) == 8, "detail": str(int(matrix["real_public_or_official_cohort_present"].sum()))},
    {"check": "locked benchmark evaluations", "passed": int(matrix["checksum_locked_holdout_complete"].sum()) == 8, "detail": str(int(matrix["checksum_locked_holdout_complete"].sum()))},
    {"check": "synthetic and wrong-domain fail closed", "passed": int(matrix["release_eligible"].sum()) == 0 and status["acquisition_pending"] == 4, "detail": "0 production releases; 4 task cohorts pending"},
])

passed = all(item["passed"] for item in checks)
payload = {
    "schema": "biointel.step171.validation.v2",
    "version": manifest["version"],
    "status": "passed" if passed else "failed",
    "checks": checks,
    "applicable_modules": 12,
    "authentic_research_packages": 8,
    "full_task_specific_research_packages": int(matrix["full_task_specific_domain_model"].sum()),
    "external_acquisition_required": 4,
    "independent_external_site_complete": int(matrix["independent_external_site_complete"].sum()),
    "release_eligible": int(matrix["release_eligible"].sum()),
    "boundary": "Untouched checksum-locked public benchmarks are qualified for research; independent external-site validation and expert approval remain required for controlled release.",
}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "step171_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
raise SystemExit(0 if passed else 1)
