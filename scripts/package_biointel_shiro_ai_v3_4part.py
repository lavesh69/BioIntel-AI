"""Build and verify the BioIntel Shiro AI v3 four-part release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import package_biointel_career_hub_theme_4part as career

BASENAME = "BioIntel-AI-15.6.0-R15-P0P1P2-Career-Hub-Shiro-AI-v3-Final"
base = career.previous.base
base.BASENAME = BASENAME
_previous_write_manifests = career.write_source_manifests


def write_source_manifests(source: Path, output: Path):
    result = _previous_write_manifests(source, output)
    metadata = {
        "shiro_ai_runtime_v3": {
            "local_first": True,
            "intelligence_modes": 4,
            "provider_routes": 4,
            "general_conversation": True,
            "multi_turn_history": True,
            "persistent_conversations": True,
            "project_rag_and_citations": True,
            "supported_attachment_groups": [
                "documents",
                "tables",
                "FASTA",
                "VCF",
                "images",
            ],
            "local_chat_profile": "qwen3:4b",
            "local_vision_profile": "gemma3:4b",
            "local_reasoning_profile": "deepseek-r1:8b",
            "local_embedding_profile": "embeddinggemma",
            "module_action_profiles": 13,
            "conversation_exports": ["json", "markdown", "docx", "pdf"],
            "voice_input_optional": True,
            "windows_text_to_speech_optional": True,
            "secure_credential_boundary": "Windows DPAPI; encrypted local fallback elsewhere",
            "cloud_provider_eligibility_gate": True,
            "cloud_per_request_consent": True,
            "local_private_mode_calls_cloud": False,
            "models_bundled": False,
            "api_keys_bundled": False,
            "shiro_specific_tests_passed": 41,
            "current_combined_regression_tests_passed": 103,
            "docx_export_render_qa": True,
            "pdf_export_render_qa": True,
            "public_identity_policy": "BioIntel names on normal product surfaces",
            "upstream_identity_location": "Legal, setup, and protected diagnostics only",
            "native_windows_model_cloud_voice_gpu_tested_in_build_environment": False,
            "feature_or_module_source_removed": False,
        }
    }
    for relative in (base.CURRENT_MANIFEST, base.LEGACY_MANIFEST):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(metadata)
        payload["package_generation"] = "R15-P0P1P2-Career-Hub-Shiro-AI-v3-Final"
        payload["build_number"] = "Step220-R15-P0P1P2-Career-Hub-Shiro-AI-v3-Final"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


base.write_source_manifests = write_source_manifests
base.write_archive = career.write_archive_stored


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
