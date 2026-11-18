from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.runtime_v170 import Step170Registry, engine_catalog, licence_catalog, reference_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    engines = engine_catalog()
    references = reference_catalog()
    licences = licence_catalog()
    checks = [
        {"check": "53 unique specialist engines", "passed": len(engines) == engines["engine"].nunique() == 53, "detail": f"{len(engines)}/53"},
        {"check": "Engine manifests", "passed": len(list((root / "data" / "step170" / "engine_manifests").glob("*.json"))) == 53, "detail": "data/step170/engine_manifests"},
        {"check": "Reference catalog", "passed": len(references) >= 25 and references["reference_id"].nunique() == len(references), "detail": f"{len(references)} production reference groups"},
        {"check": "Licence policy coverage", "passed": set(engines["licence_id"]).issubset(set(licences["licence_id"])) and set(references["licence_id"]).issubset(set(licences["licence_id"])), "detail": f"{len(licences)} licence policies"},
        {"check": "Provider/manual installs fail closed", "passed": int(engines["manual_distribution"].astype(bool).sum()) >= 5 and all(engines.loc[engines["manual_distribution"].astype(bool), "licence_acceptance_mode"].astype(str).str.len() > 0), "detail": f"manual={int(engines['manual_distribution'].astype(bool).sum())}"},
        {"check": "Every engine has checksum and smoke-test policy", "passed": bool(engines["package_sha256_required"].all() and engines["license_text_sha256_required"].all() and engines["smoke_test_required"].all()), "detail": "all 53"},
        {"check": "Every reference has release/hash/licence/schema gates", "passed": bool(references["release_pin_required"].all() and references["local_sha256_required"].all() and references["schema_validation_required"].all() and references["scientific_review_required"].all()), "detail": f"all {len(references)}"},
        {"check": "WSL/micromamba environment plan", "passed": (root / "data" / "step170" / "environment" / "step170-linux-64.yml").is_file(), "detail": "step170-linux-64.yml"},
        {"check": "Registry integrity", "passed": Step170Registry(root).status()["database_integrity"] == "ok" and Step170Registry(root).status()["foreign_key_violations"] == 0, "detail": json.dumps(Step170Registry(root).status())},
        {"check": "Step 170 UI page", "passed": (root / "pages" / "239_Specialist_Runtime_Reference_Qualification.py").is_file(), "detail": "pages/239_Specialist_Runtime_Reference_Qualification.py"},
        {"check": "Windows provisioning launchers", "passed": all((root / name).is_file() for name in ("PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat", "DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat", "VERIFY_STEP170_WINDOWS.bat", "RUN_STEP170_RELEASE_DOCTOR_WINDOWS.bat")), "detail": "4 launchers"},
    ]
    payload = {
        "schema": "biointel.step170.validation.v1",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "software_qualification_complete": all(row["passed"] for row in checks),
        "external_runtime_installation_complete": False,
        "production_reference_downloads_complete": False,
        "licences_not_auto_accepted": True,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step170_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
