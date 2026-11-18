"""Build and deeply verify the BioIntel Education Phase 17-22 four-part release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

PART_COUNT = 4
RELEASE_NAME = "BioIntel-AI-15.6.0-EDUCATION-PHASE17-TO-22-MEGA-FIXED-R1"
ARCHIVE_ROOT = "BioIntel-Step220"
CURRENT_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"
LEGACY_MANIFEST = "STEP220_SOURCE_MANIFEST_SHA256.json"
EDUCATION_MANIFEST = "release/EDUCATION_PHASE17_TO_22_RELEASE_MANIFEST.json"
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "Temp",
    "runtime_logs",
    "work",
    ".test-tmp",
    ".test-smoke",
    ".hotfix_backups",
    "edge-profile",
    "cache",
    "phase16b_test_runtime",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".pid", ".wal", ".shm"}
MUTABLE_REPORT_DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-shm", ".sqlite3-wal")
BUNDLED_USER_DATA_ROOTS = {
    "databases",
    "data",
    "proof_gates_v10",
    "step183",
    "step184",
    "step185",
    "step186",
    "step187",
    "step188",
    "step189",
    "step190",
    "step192",
    "step193",
}
REPORTS = (
    "PHASE17_TO_PHASE22_IMPLEMENTATION_REPORT.md",
    "EDUCATION_OS_ARCHITECTURE.md",
    "EDUCATION_DATABASE_SCHEMA.md",
    "EDUCATION_API_SPEC.md",
    "EDUCATION_SECURITY_AND_PRIVACY_REPORT.md",
    "EDUCATION_WINDOWS_QUALIFICATION.md",
    "EDUCATION_TEST_REPORT.md",
    "EDUCATION_KNOWN_LIMITATIONS.md",
    "EDUCATION_BACKUP_RESTORE_GUIDE.md",
    "EDUCATION_MIGRATION_AND_ROLLBACK_GUIDE.md",
    "CHANGELOG_EDUCATION_PHASE17_TO_22.md",
    "SOURCE_INVENTORY_PHASE17_TO_22.md",
    "SOURCE_INVENTORY_PHASE17_TO_22.json",
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_archive_name(name: str) -> str:
    clean = name.replace("\\", "/")
    prefix = f"{ARCHIVE_ROOT}/"
    return clean[len(prefix) :] if clean.startswith(prefix) else clean


def excluded(
    path: Path,
    source: Path,
    output: Path | None = None,
    *,
    exclude_manifests: bool = False,
) -> bool:
    rel = path.relative_to(source)
    if any(part.casefold() in {item.casefold() for item in EXCLUDED_DIRS} for part in rel.parts[:-1]):
        return True
    rel_posix = rel.as_posix()
    if rel.parts and rel.parts[0].casefold() == "userdata":
        if len(rel.parts) < 2 or rel.parts[1].casefold() not in {
            item.casefold() for item in BUNDLED_USER_DATA_ROOTS
        }:
            return True
    if rel_posix in {".env", ".coverage"}:
        return True
    if path.suffix.casefold() in EXCLUDED_SUFFIXES or path.name.casefold().endswith(("-wal", "-shm")):
        return True
    if (
        rel.parts
        and rel.parts[0].casefold() == "reports"
        and rel.name.casefold().endswith(MUTABLE_REPORT_DATABASE_SUFFIXES)
    ):
        return True
    if rel.parts and rel.parts[0].casefold() == "wheelhouse":
        if rel.name.casefold().startswith("coverage-") and rel.suffix == ".whl":
            return True
    if rel.parent.as_posix() == "release" and rel.name.startswith("PART_MANIFEST-Part"):
        return True
    if rel.parent.as_posix() == ".release_parts":
        lower = rel.name.casefold()
        if lower.startswith("education_phase") or lower.startswith("shiro4_part"):
            return True
    if rel.name.startswith(".biointel_step") and rel.name.endswith("_installed"):
        return True
    if exclude_manifests and rel_posix in {
        CURRENT_MANIFEST,
        LEGACY_MANIFEST,
        EDUCATION_MANIFEST,
    }:
        return True
    if rel_posix == CURRENT_MANIFEST:
        return True
    if output is not None:
        try:
            path.relative_to(output)
            return True
        except ValueError:
            pass
    return False


def source_paths(
    source: Path,
    output: Path | None = None,
    *,
    exclude_manifests: bool = False,
) -> list[Path]:
    return [
        path
        for path in sorted(source.rglob("*"))
        if path.is_file()
        and not excluded(
            path,
            source,
            output,
            exclude_manifests=exclude_manifests,
        )
    ]


def record_for(path: Path, source: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(source).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "full_path": str(path),
    }


def original_inventory(
    archives: list[Path],
) -> tuple[dict[str, tuple[int, int, int]], dict[str, int], list[dict[str, object]]]:
    original: dict[str, tuple[int, int, int]] = {}
    assignments: dict[str, int] = {}
    evidence = []
    for index, archive_path in enumerate(archives, start=1):
        with zipfile.ZipFile(archive_path) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Canonical archive CRC failure: {archive_path.name}: {bad}")
            files = [item for item in archive.infolist() if not item.is_dir()]
            for item in files:
                relative = clean_archive_name(item.filename)
                original[relative] = (item.file_size, item.CRC, index - 1)
                assignments[relative] = index - 1
        evidence.append(
            {
                "part": index,
                "name": archive_path.name,
                "sha256": sha256_file(archive_path),
                "size_bytes": archive_path.stat().st_size,
                "files": len(files),
            }
        )
    return original, assignments, evidence


def write_legacy_manifest(source: Path, output: Path) -> Path:
    paths = [
        path
        for path in source_paths(source, output, exclude_manifests=True)
        if not path.relative_to(source).as_posix().casefold().startswith("userdata/")
    ]
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        rows = [
            {key: row[key] for key in ("path", "size_bytes", "sha256")}
            for row in executor.map(lambda item: record_for(item, source), paths)
        ]
    payload = {
        "schema": "biointel.step220.windows.source-manifest.v1",
        "release_step": 220,
        "build_number": "Step220-V20.5-Education-Phase17-To-22-R1",
        "base_release_step": 220,
        "release_version": "15.6.0",
        "package_generation": "V20.5",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "excluded_runtime_paths": sorted(EXCLUDED_DIRS),
        "entries": rows,
        "education_phase17_to_22": {
            "release": RELEASE_NAME,
            "migration": "education_phase17_to_22_unified_os_v1",
            "target_regression_tests": 206,
            "phase11_to_16_controls": 189,
            "external_qualification_honesty": True,
        },
    }
    target = source / LEGACY_MANIFEST
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def current_crc(path: Path) -> int:
    import zlib

    value = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value = zlib.crc32(block, value)
    return value & 0xFFFFFFFF


def write_education_manifest(
    source: Path,
    output: Path,
    original: dict[str, tuple[int, int, int]],
    original_archives: list[dict[str, object]],
) -> Path:
    changes = []
    for path in source_paths(source, output):
        relative = path.relative_to(source).as_posix()
        if relative in {CURRENT_MANIFEST, EDUCATION_MANIFEST}:
            continue
        previous = original.get(relative)
        state = "new"
        if previous:
            if path.stat().st_size == previous[0] and current_crc(path) == previous[1]:
                continue
            state = "changed"
        changes.append(
            {
                "path": relative,
                "state": state,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    payload = {
        "schema": "biointel.education.phase17-22.release-manifest.v1",
        "release": RELEASE_NAME,
        "version": "15.6.0",
        "archive_root": ARCHIVE_ROOT,
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "canonical_source_archives": original_archives,
        "changed_files": sorted(changes, key=lambda row: str(row["path"]).casefold()),
        "generated_release_files": [
            CURRENT_MANIFEST,
            EDUCATION_MANIFEST,
            "release/PART_MANIFEST-Part1.json",
            "release/PART_MANIFEST-Part2.json",
            "release/PART_MANIFEST-Part3.json",
            "release/PART_MANIFEST-Part4.json",
        ],
        "database_versions": [
            "education_science_academy_v2_integrity",
            "education_phase3_granular_rbac_v1",
            "education_phase4_intelligence_operations_v1",
            "education_phase3_secure_examination_v1",
            "education_phase5_institution_platform_v1",
            "education_phase6_visual_operations_v1",
            "education_phase7_desktop_workflows_v1",
            "education_phase11_mega_core_v1",
            "education_phase12_final_completion_v1",
            "education_phase13_local_autonomy_v1",
            "education_phase14_academic_intelligence_v1",
            "education_phase15_runtime_intelligence_v1",
            "education_phase16_completion_v1",
            "education_phase17_to_22_unified_os_v1",
        ],
        "tests": {
            "target_education_shiro_connect": {"passed": 206, "failed": 0},
            "phase11_to_16_verifier_controls": {"passed": 189, "failed": 0},
            "phase17_to_22_module": {"passed": 8, "failed": 0},
            "broad_historical_diagnostic": {
                "passed": 1913,
                "failed": 279,
                "skipped": 28,
                "errors": 3,
                "status": "not_green",
            },
        },
        "dependency_changes": [
            {
                "name": "imageio-ffmpeg",
                "version": "0.6.0",
                "purpose": "Bundled Windows local FFmpeg for lecture probing and media jobs.",
                "wheel_sha256": "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a",
            }
        ],
        "completion_matrix": {
            "biointel_connect": "implemented_verified",
            "shiro_ai": "implemented_verified",
            "education_home": "implemented_verified",
            "classroom": "implemented_verified",
            "science_pulse": "implemented_verified",
            "academy_lecture_studio": "implemented_verified",
            "education_universe": "implemented_verified",
            "examination_command_center": "implemented_verified",
            "education_intelligence_hub": "implemented_verified",
            "biointel_studio": "implemented_verified",
            "public_turn_calling": "implemented_external_verification_required",
            "live_external_science_providers": "implemented_external_verification_required",
            "formal_security_accessibility": "implemented_external_verification_required",
            "studio_rendered_formats": "blocked_no_qualified_renderer",
        },
        "known_limitations": [
            "Public calling requires deployed TURN credentials and real relay tests.",
            "Live external providers require network/rate-limit qualification.",
            "Studio PDF/PPTX/image/video rendering is unavailable without a qualified renderer.",
            "Interventions are rule-based indicators, not trained ML.",
            "The broad historical repository test suite is not green; see EDUCATION_TEST_REPORT.md.",
        ],
    }
    target = source / EDUCATION_MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def collect_records(source: Path, output: Path) -> list[dict[str, object]]:
    paths = source_paths(source, output)
    records = []
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        for index, row in enumerate(executor.map(lambda item: record_for(item, source), paths), start=1):
            row["weight"] = int(row["size_bytes"]) + 160
            records.append(row)
            if index % 2500 == 0:
                print(f"Hashed {index} source files...", flush=True)
    return records


def write_current_manifest(source: Path, records: list[dict[str, object]]) -> None:
    payload = {
        "schema": "biointel.release.source-manifest.v1",
        "release_step": 220,
        "build_number": "Step220-V20.5-Education-Phase17-To-22-R1",
        "release_version": "15.6.0",
        "package_generation": "V20.5",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "files": [
            {key: row[key] for key in ("path", "size_bytes", "sha256")}
            for row in records
            if not str(row["path"]).casefold().startswith("userdata/")
        ],
        "education_phase17_to_22": {
            "release": RELEASE_NAME,
            "migration": "education_phase17_to_22_unified_os_v1",
            "api_routes": 17,
            "target_regression_tests": 206,
            "phase11_to_16_controls": 189,
            "wheelhouse_wheels": 122,
        },
    }
    target = source / CURRENT_MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    row = record_for(target, source)
    row["weight"] = int(row["size_bytes"]) + 160
    records.append(row)


def balance(
    records: list[dict[str, object]],
    assignments: dict[str, int],
) -> list[list[dict[str, object]]]:
    buckets: list[list[dict[str, object]]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    unassigned = []
    for row in records:
        target = assignments.get(str(row["path"]))
        if target is None:
            unassigned.append(row)
            continue
        buckets[target].append(row)
        totals[target] += int(row["weight"])
    for row in sorted(unassigned, key=lambda item: int(item["weight"]), reverse=True):
        target = min(range(PART_COUNT), key=totals.__getitem__)
        buckets[target].append(row)
        totals[target] += int(row["weight"])
    print(
        "Part source bytes: "
        + ", ".join(f"{total / 1024**2:.1f} MiB" for total in totals),
        flush=True,
    )
    return buckets


def create_parts(
    source: Path,
    output: Path,
    buckets: list[list[dict[str, object]]],
) -> list[Path]:
    targets = [
        output / f"{RELEASE_NAME}-Part{index}.zip"
        for index in range(1, PART_COUNT + 1)
    ]
    for target in targets:
        target.unlink(missing_ok=True)
    for index, (target, bucket) in enumerate(zip(targets, buckets, strict=True), start=1):
        print(f"Writing Part {index}: {len(bucket)} source files", flush=True)
        part_manifest = {
            "release": RELEASE_NAME,
            "part": index,
            "part_count": PART_COUNT,
            "source_file_count": len(bucket),
            "files": [
                {key: row[key] for key in ("path", "size_bytes", "sha256")}
                for row in bucket
            ],
        }
        with zipfile.ZipFile(
            target,
            "w",
            zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for row in bucket:
                archive.write(
                    str(row["full_path"]),
                    f"{ARCHIVE_ROOT}/{row['path']}",
                )
            archive.writestr(
                f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json",
                json.dumps(part_manifest, indent=2).encode("utf-8"),
            )
            archive.writestr(
                f"{ARCHIVE_ROOT}/.release_parts/education_phase17_22_part{index}.ok",
                f"BioIntel Education Phase 17-22 part {index} of {PART_COUNT}\n",
            )
    return targets


def verify(
    parts: list[Path],
    buckets: list[list[dict[str, object]]],
) -> dict[str, object]:
    seen = set()
    reports = []
    for index, (part, bucket) in enumerate(zip(parts, buckets, strict=True), start=1):
        print(f"Deep-verifying Part {index}...", flush=True)
        with zipfile.ZipFile(part) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"CRC failure in {part.name}: {bad}")
            archive.getinfo(
                f"{ARCHIVE_ROOT}/.release_parts/education_phase17_22_part{index}.ok"
            )
            embedded = json.loads(
                archive.read(f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json")
            )
            embedded_paths = {str(row["path"]) for row in embedded["files"]}
            expected_paths = {str(row["path"]) for row in bucket}
            if embedded_paths != expected_paths:
                raise RuntimeError(f"Part manifest mismatch: {part.name}")
            overlap = seen.intersection(expected_paths)
            if overlap:
                raise RuntimeError(f"Duplicate paths across parts: {sorted(overlap)[:5]}")
            seen.update(expected_paths)
            for row in bucket:
                relative = str(row["path"])
                pure = PurePosixPath(relative)
                if pure.is_absolute() or ".." in pure.parts:
                    raise RuntimeError(f"Unsafe archive path: {relative}")
                member = archive.getinfo(f"{ARCHIVE_ROOT}/{relative}")
                if member.file_size != int(row["size_bytes"]):
                    raise RuntimeError(f"Archive size mismatch: {relative}")
                digest = hashlib.sha256()
                with archive.open(member) as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != row["sha256"]:
                    raise RuntimeError(f"Archive SHA-256 mismatch: {relative}")
        reports.append(
            {
                "part": index,
                "name": part.name,
                "size_bytes": part.stat().st_size,
                "sha256": sha256_file(part),
                "source_files": len(bucket),
                "zip_crc": "passed",
                "deep_sha256": "passed",
            }
        )
    if len(seen) != sum(len(bucket) for bucket in buckets):
        raise RuntimeError("Release part coverage mismatch.")
    return {
        "release": RELEASE_NAME,
        "archive_root": ARCHIVE_ROOT,
        "part_count": PART_COUNT,
        "unique_source_files": len(seen),
        "unsafe_paths": 0,
        "duplicate_paths": 0,
        "parts": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", required=True)
    parser.add_argument("archives", nargs=4)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    if source.name != ARCHIVE_ROOT or not (source / "app.py").is_file():
        raise SystemExit("Source must be the assembled BioIntel-Step220 root.")
    output.mkdir(parents=True, exist_ok=True)
    if source == output or source.is_relative_to(output):
        raise SystemExit("Output must not contain the source tree.")

    archives = [Path(path).resolve() for path in args.archives]
    original, assignments, original_evidence = original_inventory(archives)
    write_legacy_manifest(source, output)
    education_manifest = write_education_manifest(
        source,
        output,
        original,
        original_evidence,
    )
    records = collect_records(source, output)
    write_current_manifest(source, records)
    buckets = balance(records, assignments)
    parts = create_parts(source, output, buckets)
    report = verify(parts, buckets)
    report["generated_at_utc"] = utc_now()
    report_path = output / "EDUCATION_PHASE17_TO_22_PACKAGE_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checksums = output / "SHA256SUMS_EDUCATION_PHASE17_TO_22.txt"
    checksums.write_text(
        "".join(f"{sha256_file(part)}  {part.name}\n" for part in parts),
        encoding="utf-8",
    )
    shutil.copy2(
        education_manifest,
        output / "EDUCATION_PHASE17_TO_22_RELEASE_MANIFEST.json",
    )
    for name in REPORTS:
        shutil.copy2(source / name, output / name)
    print(json.dumps(report, indent=2))
    print(f"Checksums: {checksums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
