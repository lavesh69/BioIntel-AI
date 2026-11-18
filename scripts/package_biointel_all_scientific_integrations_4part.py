"""Build and verify the four-part BioIntel P0/P1/P2 scientific integration release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import package_education_full_upgrade_r15 as base

BASENAME = "BioIntel-AI-15.6.0-R15-P0-P1-P2-Scientific-Integration-Runtime-v2-Final"
base.BASENAME = BASENAME
_original_write_manifests = base.write_source_manifests


def write_source_manifests(source: Path, output: Path):
    result = _original_write_manifests(source, output)
    metadata = {
        "scientific_integration_runtime_v2": {
            "priority_counts": {"P0": 7, "P1": 10, "P2": 3},
            "integration_adapters": 20,
            "registered_operations": 61,
            "non_diagnostic_operations": 41,
            "scientifically_relevant_page_wiring": 29,
            "runtime_isolation": "core + isolated Python + native CLI + WSL workers",
            "audited_operation_console": True,
            "timeout_and_provenance_contract": True,
            "public_identity_policy": "BioIntel names on normal product surfaces",
            "upstream_identity_location": "Legal & Component Notices and protected diagnostics only",
            "heavy_assets_bundled": False,
            "model_and_database_qualification_gate": True,
            "focused_setup_instead_of_legacy_full_suite": True,
            "targeted_tests_passed": 73,
            "native_windows_wsl_gpu_runtime_tested_in_build_environment": False,
            "feature_or_module_source_removed": False,
        }
    }
    for relative in (base.CURRENT_MANIFEST, base.LEGACY_MANIFEST):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(metadata)
        payload["package_generation"] = "R15-P0-P1-P2-Scientific-Integration-Runtime-v2-Final"
        payload["build_number"] = "Step220-R15-P0-P1-P2-Scientific-Integration-Runtime-v2-Final"
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
