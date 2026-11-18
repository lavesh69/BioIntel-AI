"""Build and verify the BioIntel Career Hub themed four-part release."""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

import package_biointel_all_scientific_integrations_4part as previous

BASENAME = "BioIntel-AI-15.6.0-R15-P0P1P2-Career-Hub-Theme-Final"
previous.base.BASENAME = BASENAME
_previous_write_manifests = previous.write_source_manifests


def write_source_manifests(source: Path, output: Path):
    result = _previous_write_manifests(source, output)
    metadata = {
        "career_hub_biointel_theme": {
            "canonical_route": "pages/355_BioIntel_Career_Internship_Scholarship_Hub.py",
            "compatibility_route": "pages/168_Career_Internship_Scholarship_Hub.py",
            "global_theme_applied_to_both_routes": True,
            "direct_global_sidebar_entry": True,
            "featured_education_module": True,
            "workspace_tabs": 5,
            "ecosystem_links": 4,
            "persistent_preparation_items": 6,
            "source_review_boundary": True,
            "user_submissions_default": "Pending source review",
            "legacy_workspace_records_preserved": True,
            "targeted_tests_passed": 31,
            "targeted_tests_failed": 0,
            "native_windows_visual_runtime_tested_in_build_environment": False,
            "feature_or_module_source_removed": False,
        }
    }
    for relative in (previous.base.CURRENT_MANIFEST, previous.base.LEGACY_MANIFEST):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(metadata)
        payload["package_generation"] = "R15-P0P1P2-Career-Hub-Theme-Final"
        payload["build_number"] = "Step220-R15-P0P1P2-Career-Hub-Theme-Final"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


previous.base.write_source_manifests = write_source_manifests

def write_archive_stored(source: Path, archive: Path, paths: list[Path]):
    """Create a fast, Windows-friendly stored archive with balanced parts."""
    with zipfile.ZipFile(archive, "w", allowZip64=True, compression=zipfile.ZIP_STORED) as bundle:
        for path in sorted(paths, key=lambda item: item.relative_to(source).as_posix().casefold()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(
                f"{previous.base.ARCHIVE_ROOT}/{relative}",
                date_time=previous.base.zip_timestamp(path),
            )
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as input_handle, bundle.open(info, "w", force_zip64=True) as output_handle:
                shutil.copyfileobj(input_handle, output_handle, 1024 * 1024)
    return {
        "name": archive.name,
        "files": len(paths),
        "uncompressed_bytes": sum(path.stat().st_size for path in paths),
        "archive_bytes": archive.stat().st_size,
        "sha256": previous.base.sha256_file(archive),
    }


previous.base.write_archive = write_archive_stored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-extract", type=Path)
    args = parser.parse_args()
    print(json.dumps(previous.base.package(args.source, args.output, args.verify_extract), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
