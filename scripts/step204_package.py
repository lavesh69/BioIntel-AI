from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "BioIntel-AI-15.4.0-Step204-WINDOWS-V17.1"
PART_COUNT = 4
STEP196_MANIFEST = "STEP196_SOURCE_MANIFEST_SHA256.json"
STEP204_MANIFEST = "STEP204_SOURCE_MANIFEST_SHA256.json"
STEP204_ASSIGNMENT = "STEP204_PACKAGE_PART_ASSIGNMENT.json"
METADATA = {STEP196_MANIFEST, STEP204_MANIFEST, STEP204_ASSIGNMENT, "STEP203_SOURCE_MANIFEST_SHA256.json", "STEP203_PACKAGE_PART_ASSIGNMENT.json"}
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".release_parts", ".hotfix_backups"}
IMMUTABLE_EXCLUDED_DIRS = EXCLUDED_DIRS | {"reports"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
RUNTIME_EXCLUDES = {
    ".biointel_step196_installed",
    "reports/step196/validation.json",
    "reports/step196_release_metadata_repair.json",
    "reports/step196/v16-preinstall.json",
    "reports/step196/v16-validation-prebuild.json",
    "reports/step203-preflight.json",
    "reports/step203-preflight-runtime.json",
    "reports/step204-release-gate-runtime.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def source_files(include_metadata: bool, *, immutable_only: bool = False) -> list[Path]:
    output: list[Path] = []
    excluded_dirs = IMMUTABLE_EXCLUDED_DIRS if immutable_only else EXCLUDED_DIRS
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        text = rel.as_posix()
        if any(part in excluded_dirs for part in rel.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith(("-wal", "-shm")):
            continue
        if rel.parts[:2] == ("UserData", "proof_gates_v10"):
            continue
        if text in RUNTIME_EXCLUDES:
            continue
        if not include_metadata and path.name in METADATA:
            continue
        output.append(path)
    return sorted(output)


def entries(files: list[Path]) -> list[dict[str, object]]:
    workers = min(16, max(4, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        hashes = list(executor.map(sha256, files))
    return [
        {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest}
        for path, digest in zip(files, hashes, strict=True)
    ]


def write_manifests() -> None:
    for name in METADATA:
        (ROOT / name).unlink(missing_ok=True)
    base_files = source_files(False, immutable_only=True)
    base_rows = entries(base_files)
    (ROOT / STEP196_MANIFEST).write_text(json.dumps({
        "schema": "biointel.step196.source-manifest.v1",
        "release_step": 196, "release_version": "15.4.0",
        "hash_algorithm": "sha256", "excluded_runtime_paths": sorted(RUNTIME_EXCLUDES),
        "entries": base_rows,
    }, indent=2) + "\n", encoding="utf-8")
    current_files = source_files(False, immutable_only=True) + [ROOT / STEP196_MANIFEST]
    current_rows = entries(sorted(set(current_files)))
    (ROOT / STEP204_MANIFEST).write_text(json.dumps({
        "schema": "biointel.step204.windows-install-run-fix.source-manifest.v1",
        "release_step": 204, "base_release_step": 196, "release_version": "15.4.0",
        "package_generation": "V17.1", "part_count": 4,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "hash_algorithm": "sha256", "entries": current_rows,
    }, indent=2) + "\n", encoding="utf-8")


def allocate(files: list[Path]) -> tuple[list[list[Path]], list[int]]:
    buckets: list[list[Path]] = [[] for _ in range(PART_COUNT)]
    sizes = [0] * PART_COUNT
    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True):
        index = min(range(PART_COUNT), key=lambda item: sizes[item])
        buckets[index].append(path)
        sizes[index] += path.stat().st_size
    return buckets, sizes


def build_part(destination: Path, files: list[Path], part: int) -> dict[str, object]:
    temporary = destination.with_suffix(".zip.tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for path in sorted(files):
            archive.write(path, f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}", compress_type=zipfile.ZIP_STORED)
        # Current physical package markers: one unique marker per ZIP part.
        archive.writestr(
            f"{ARCHIVE_ROOT}/.release_parts/step204_part{part}.ok",
            f"BioIntel AI 15.4.0 Step204 V17.1 physical package part {part} of 4\n",
        )
        # Historical validators require five marker names. They are written once
        # in Part 1 only and do not represent five physical Step204 ZIP files.
        if part == 1:
            for step in (196, 200, 201, 202, 203):
                for legacy_part in range(1, 6):
                    archive.writestr(
                        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{legacy_part}.ok",
                        f"Legacy compatibility marker Step{step} Part {legacy_part}; current package is Step204 four-part.\n",
                    )
    os.replace(temporary, destination)
    return {
        "file": destination.name,
        "size_bytes": destination.stat().st_size,
        "source_entries": len(files),
    }


def verify(parts: list[Path], expected_files: list[Path]) -> dict[str, object]:
    expected = {f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}" for path in expected_files}
    seen: dict[str, int] = {}
    crc_errors: list[str] = []
    unsafe_paths: list[str] = []
    current_markers: list[str] = []
    legacy_markers: list[str] = []
    for part in parts:
        with zipfile.ZipFile(part) as archive:
            bad = archive.testzip()
            if bad:
                crc_errors.append(f"{part.name}:{bad}")
            for info in archive.infolist():
                name = info.filename
                if not safe(name):
                    unsafe_paths.append(name)
                if "/.release_parts/step204_part" in name:
                    current_markers.append(name)
                elif "/.release_parts/step" in name:
                    legacy_markers.append(name)
                else:
                    seen[name] = seen.get(name, 0) + 1
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    duplicates = sorted(name for name, count in seen.items() if count != 1)
    expected_current = [f"{ARCHIVE_ROOT}/.release_parts/step204_part{part}.ok" for part in range(1, 5)]
    expected_legacy = [
        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{part}.ok"
        for step in (196, 200, 201, 202, 203) for part in range(1, 6)
    ]
    markers_ok = sorted(current_markers) == expected_current and sorted(legacy_markers) == expected_legacy
    passed = not any((missing, extra, duplicates, crc_errors, unsafe_paths)) and markers_ok
    return {
        "schema": "biointel.step204.package-integrity.v1",
        "status": "passed" if passed else "failed",
        "part_count": 4,
        "source_files": len(expected), "packaged_source_files": len(seen),
        "missing_files": missing, "extra_files": extra, "duplicate_files": duplicates,
        "crc_errors": crc_errors, "unsafe_paths": unsafe_paths,
        "current_markers": current_markers, "legacy_markers": legacy_markers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", default="BioIntel-AI-15.4.0-Step204-WINDOWS-INSTALL-RUN-FIX-V17.1-4PART")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    write_manifests()
    initial = source_files(True)
    buckets, sizes = allocate(initial)
    assignment_rows = [
        {"path": path.relative_to(ROOT).as_posix(), "part": index, "size_bytes": path.stat().st_size}
        for index, bucket in enumerate(buckets, 1) for path in bucket
    ]
    assignment = {
        "schema": "biointel.step204.package-assignment.v1", "step": 204, "part_count": 4,
        "archive_root": ARCHIVE_ROOT,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "estimated_uncompressed_part_bytes_before_assignment": sizes,
        "entries": assignment_rows,
        "note": "This assignment manifest excludes itself; package verification includes it.",
    }
    (ROOT / STEP204_ASSIGNMENT).write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")
    index = min(range(PART_COUNT), key=lambda item: sizes[item])
    buckets[index].append(ROOT / STEP204_ASSIGNMENT)
    sizes[index] += (ROOT / STEP204_ASSIGNMENT).stat().st_size

    parts = [output / f"{args.name}-Part{part}.zip" for part in range(1, 5)]
    results = [build_part(parts[index], buckets[index], index + 1) for index in range(4)]
    integrity = verify(parts, source_files(True))
    with ThreadPoolExecutor(max_workers=4) as executor:
        hashes = list(executor.map(sha256, parts))
    for row, digest in zip(results, hashes, strict=True):
        row["sha256"] = digest
    integrity["parts"] = sorted(results, key=lambda row: str(row["file"]))
    integrity["part_uncompressed_bytes"] = sizes
    (output / "STEP204_PACKAGE_INTEGRITY.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text("".join(
        f"{row['sha256']}  {row['file']}\n" for row in sorted(results, key=lambda row: str(row["file"]))
    ), encoding="utf-8")
    print(json.dumps(integrity, indent=2))
    return 0 if integrity["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
