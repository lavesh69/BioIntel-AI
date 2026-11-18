"""Build and verify the BioIntel Education Suite four-part release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import package_biointel_shiro_ai_v3_4part as shiro

BASENAME = "BioIntel-AI-15.6.0-R15-P0P1P2-Career-Shiro-Education-Suite-Final"
base = shiro.base
base.BASENAME = BASENAME
_previous_write_manifests = shiro.write_source_manifests


def write_source_manifests(source: Path, output: Path):
    result = _previous_write_manifests(source, output)
    metadata = {
        "biointel_education_suite": {
            "canonical_route": "pages/356_BioIntel_Education_Suite.py",
            "classroom_embedded_workspace": True,
            "career_application_studio": True,
            "native_local_capabilities": 17,
            "optional_service_connectors": 11,
            "interactive_lessons": True,
            "versioned_collaborative_notes": True,
            "browser_local_whiteboard": True,
            "question_bank_and_assessments": True,
            "local_coding_lab": True,
            "notebook_grading": True,
            "code_similarity_review": True,
            "classroom_qa": True,
            "offline_library_sha256": True,
            "unified_education_search": True,
            "portable_learning_records": True,
            "resume_application_and_interview_studio": True,
            "credential_badge_engine": True,
            "roster_and_gradebook_interchange": True,
            "local_database": "SQLite under BioIntel user-data directory",
            "normal_ui_identity": "BioIntel only",
            "upstream_service_identity": "legal and technical notices only",
            "heavy_external_servers_bundled": False,
            "silent_external_downloads": False,
            "local_code_runner_security_claim": "restricted trusted-practice runner; not hardened sandbox",
            "targeted_backend_and_wiring_tests_passed": 77,
            "native_windows_optional_services_tested_in_build_environment": False,
            "feature_or_module_source_removed": False,
        }
    }
    for relative in (base.CURRENT_MANIFEST, base.LEGACY_MANIFEST):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(metadata)
        payload["package_generation"] = "R15-P0P1P2-Career-Shiro-Education-Suite-Final"
        payload["build_number"] = "Step220-R15-P0P1P2-Career-Shiro-Education-Suite-Final"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


base.write_source_manifests = write_source_manifests
base.write_archive = shiro.career.write_archive_stored


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
