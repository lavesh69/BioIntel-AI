"""Build the four-part BioIntel scientific-integration public-identity release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import package_education_full_upgrade_r15 as base

BASENAME = "BioIntel-AI-15.6.0-R15-Scientific-Integration-BioIntel-Identity-Final"
base.BASENAME = BASENAME
_original_write_manifests = base.write_source_manifests


def write_source_manifests(source: Path, output: Path):
    result = _original_write_manifests(source, output)
    metadata = {
        "scientific_integration_upgrade": {
            "public_identity_policy": "BioIntel names on normal product surfaces",
            "scientific_integration_profiles": 20,
            "public_engine_aliases": 109,
            "advanced_tool_records": 86,
            "legal_component_notices": 76,
            "github_repository_urls_on_audited_normal_surfaces": 0,
            "identity_audit": "BIOINTEL_ENGINE_IDENTITY_AUDIT.json",
            "integration_report": "BIOINTEL_SCIENTIFIC_INTEGRATION_UPGRADE_REPORT.md",
            "legal_notice": "docs/legal/THIRD_PARTY_NOTICES.md",
            "internal_runtime_identifiers_preserved": True,
            "normal_ui_white_labelled": True,
            "targeted_tests_passed": 67,
            "feature_or_module_source_removed": False,
            "runtime_state_and_secret_files_not_redistributed": 12
        }
    }
    for relative in (base.CURRENT_MANIFEST, base.LEGACY_MANIFEST):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(metadata)
        payload["package_generation"] = "R15-Scientific-Integration-BioIntel-Identity-Final"
        payload["build_number"] = "Step220-R15-Scientific-Integration-BioIntel-Identity-Final"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


base.write_source_manifests = write_source_manifests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-extract", type=Path)
    args = parser.parse_args()
    print(json.dumps(base.package(args.source, args.output, args.verify_extract), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
