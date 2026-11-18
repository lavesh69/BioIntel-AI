from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit BioIntel public scientific-engine identity surfaces.")
    parser.add_argument("--output", type=Path, default=ROOT / "BIOINTEL_ENGINE_IDENTITY_AUDIT.json")
    args = parser.parse_args()

    aliases = load_json(ROOT / "config" / "public_engine_aliases.json")["records"]
    advanced = load_json(ROOT / "config" / "advanced_tools_manifest.json")["tools"]
    legal = load_json(ROOT / "docs" / "legal" / "THIRD_PARTY_NOTICES.json")["components"]
    integrations = load_json(ROOT / "config" / "biointel_scientific_integrations.json")["integrations"]

    normal_surface_files = [
        ROOT / "pages" / "277_BioIntel_Engine_Status.py",
        ROOT / "pages" / "93_Advanced_Bioinformatics_Tools.py",
        ROOT / "pages" / "108_BioIntel_Model_Qualification.py",
        ROOT / "BIOINTEL_ENGINE_SETUP.bat",
        ROOT / "BIOINTEL_ENGINE_STATUS.md",
        ROOT / "pages" / "356_BioIntel_Scientific_Integration_Center.py",
    ]
    forbidden_urls = []
    for path in normal_surface_files:
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        for token in ("github.com", "raw.githubusercontent.com", "bioconda.github.io"):
            if token in text:
                forbidden_urls.append({"path": str(path.relative_to(ROOT)), "token": token})

    checks = {
        "alias_count_at_least_100": len(aliases) >= 100,
        "unique_public_keys": len({row["public_key"] for row in aliases}) == len(aliases),
        "unique_public_names": len({row["public_name"] for row in aliases}) == len(aliases),
        "all_alias_names_biointel": all(row["public_name"].startswith("BioIntel ") for row in aliases),
        "advanced_tool_count_at_least_80": len(advanced) >= 80,
        "twenty_scientific_integration_profiles": len(integrations) == 20,
        "integration_names_biointel": all(row["public_name"].startswith("BioIntel ") for row in integrations),
        "advanced_labels_biointel": all(row["label"].startswith("BioIntel ") for row in advanced),
        "required_legal_notices_present": len(legal) >= 70 and all(row.get("licence") for row in legal),
        "normal_surfaces_have_no_repository_urls": not forbidden_urls,
        "biointel_engine_status_route_exists": (ROOT / "pages" / "277_BioIntel_Engine_Status.py").is_file(),
        "legacy_engine_status_route_removed": not (ROOT / "pages" / "277_External_Engines_Status.py").exists(),
        "biointel_model_qualification_route_exists": (ROOT / "pages" / "108_BioIntel_Model_Qualification.py").is_file(),
        "legacy_model_qualification_route_removed": not (ROOT / "pages" / "108_External_Model_Qualification.py").exists(),
        "biointel_setup_entrypoint_exists": (ROOT / "BIOINTEL_ENGINE_SETUP.bat").is_file(),
    }

    report = {
        "schema": "biointel.engine-public-identity-audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "counts": {
            "public_alias_records": len(aliases),
            "advanced_tool_records": len(advanced),
            "legal_component_notices": len(legal),
            "scientific_integration_profiles": len(integrations),
            "normal_surface_files_checked": len(normal_surface_files),
        },
        "checks": checks,
        "forbidden_url_findings": forbidden_urls,
        "policy": {
            "normal_product_surfaces": "BioIntel public identities only",
            "internal_runtime_identifiers": "Preserved for execution compatibility",
            "legal_notices": "Required upstream names, sources and licences retained",
            "technical_logs": "May retain internal component identifiers for diagnostics",
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
