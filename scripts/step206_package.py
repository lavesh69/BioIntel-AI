from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from step206_contract import (
    ARCHIVE_ROOT,
    ASSIGNMENT_NAME,
    MANIFEST_NAME,
    PACKAGE_GENERATION,
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_STEP,
)

ROOT = Path(__file__).resolve().parents[1]
METADATA = {MANIFEST_NAME, ASSIGNMENT_NAME}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv.step196-backup",
    ".venv.step206-backup",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".release_parts",
    ".hotfix_backups",
}
MANIFEST_EXCLUDED_DIRS = EXCLUDED_DIRS | {"reports"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
RUNTIME_EXCLUDES = {
    ".biointel_step196_installed",
    ".biointel_step206_installed",
    "reports/step196/validation.json",
    "reports/step196_release_metadata_repair.json",
    "reports/step196/v16-preinstall.json",
    "reports/step196/v16-validation-prebuild.json",
    "reports/step203-preflight.json",
    "reports/step203-preflight-runtime.json",
    "reports/step205-release-gate-runtime.json",
    "reports/step206-release-gate-runtime.json",
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


def source_files(include_metadata: bool, *, manifest_only: bool = False) -> list[Path]:
    output: list[Path] = []
    excluded_dirs = MANIFEST_EXCLUDED_DIRS if manifest_only else EXCLUDED_DIRS
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        text = relative.as_posix()
        if any(part in excluded_dirs for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith(("-wal", "-shm")):
            continue
        if relative.parts[:2] == ("UserData", "proof_gates_v10"):
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
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": digest,
        }
        for path, digest in zip(files, hashes, strict=True)
    ]


def write_manifest() -> None:
    for name in (MANIFEST_NAME, ASSIGNMENT_NAME):
        (ROOT / name).unlink(missing_ok=True)
    files = source_files(False, manifest_only=True)
    rows = entries(files)
    payload = {
        "schema": "biointel.step206.windows-install-run-fix.source-manifest.v1",
        "release_step": RELEASE_STEP,
        "base_release_step": 205,
        "release_version": PRODUCT_VERSION,
        "package_generation": PACKAGE_GENERATION,
        "part_count": PART_COUNT,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "hash_algorithm": "sha256",
        "excluded_runtime_paths": sorted(RUNTIME_EXCLUDES),
        "entries": rows,
    }
    (ROOT / MANIFEST_NAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
            archive.write(
                path,
                f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}",
                compress_type=zipfile.ZIP_STORED,
            )
        archive.writestr(
            f"{ARCHIVE_ROOT}/.release_parts/step206_part{part}.ok",
            f"BioIntel AI {PRODUCT_VERSION} Step206 {PACKAGE_GENERATION} physical package part {part} of {PART_COUNT}\n",
        )
        if part == 1:
            for legacy_part in range(1, 5):
                archive.writestr(
                    f"{ARCHIVE_ROOT}/.release_parts/step159_part{legacy_part}.ok",
                    f"Legacy compatibility marker Step159 Part {legacy_part}; current package is Step206 five-part.\n",
                )
            for step in (196, 200, 201, 202, 203):
                for legacy_part in range(1, 6):
                    archive.writestr(
                        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{legacy_part}.ok",
                        f"Legacy compatibility marker Step{step} Part {legacy_part}; current package is Step206 five-part.\n",
                    )
            for step in (204, 205):
                for legacy_part in range(1, 5):
                    archive.writestr(
                        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{legacy_part}.ok",
                        f"Legacy compatibility marker Step{step} Part {legacy_part}; current package is Step206 five-part.\n",
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
            for info in archive.infolist():
                name = info.filename
                if not safe(name):
                    unsafe_paths.append(name)
                if "/.release_parts/step206_part" in name:
                    current_markers.append(name)
                elif "/.release_parts/step" in name:
                    legacy_markers.append(name)
                else:
                    seen[name] = seen.get(name, 0) + 1

    def crc_result(part: Path) -> tuple[str, str | None]:
        with zipfile.ZipFile(part) as archive:
            return part.name, archive.testzip()

    with ThreadPoolExecutor(max_workers=PART_COUNT) as executor:
        for part_name, bad in executor.map(crc_result, parts):
            if bad:
                crc_errors.append(f"{part_name}:{bad}")

    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    duplicates = sorted(name for name, count in seen.items() if count != 1)
    expected_current = [
        f"{ARCHIVE_ROOT}/.release_parts/step206_part{part}.ok" for part in range(1, PART_COUNT + 1)
    ]
    expected_legacy = [
        f"{ARCHIVE_ROOT}/.release_parts/step159_part{part}.ok" for part in range(1, 5)
    ] + [
        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{part}.ok"
        for step in (196, 200, 201, 202, 203)
        for part in range(1, 6)
    ] + [
        f"{ARCHIVE_ROOT}/.release_parts/step{step}_part{part}.ok"
        for step in (204, 205)
        for part in range(1, 5)
    ]
    markers_ok = sorted(current_markers) == expected_current and sorted(legacy_markers) == expected_legacy
    passed = not any((missing, extra, duplicates, crc_errors, unsafe_paths)) and markers_ok
    return {
        "schema": "biointel.step206.package-integrity.v1",
        "status": "passed" if passed else "failed",
        "part_count": PART_COUNT,
        "source_files": len(expected),
        "packaged_source_files": len(seen),
        "missing_files": missing,
        "extra_files": extra,
        "duplicate_files": duplicates,
        "crc_errors": crc_errors,
        "unsafe_paths": unsafe_paths,
        "current_markers": current_markers,
        "legacy_markers": legacy_markers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--name",
        default="BioIntel-AI-15.6.0-Step206-ENGINE-PLATFORM-INTEGRATION-WINDOWS-V19.6-5PART",
    )
    args = parser.parse_args()
    output = args.output_dir.resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        parser.error("--output-dir must be outside the BioIntel source tree to avoid packaging generated archives.")
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob(f"{args.name}-Part*.zip"):
        old.unlink()

    write_manifest()
    # The assignment is generated below and appended exactly once to the
    # smallest part.  Filtering an existing copy prevents a regenerated
    # package from accidentally carrying a stale self-entry twice.
    initial = [path for path in source_files(True) if path.name != ASSIGNMENT_NAME]
    buckets, sizes = allocate(initial)
    assignment_rows = [
        {"path": path.relative_to(ROOT).as_posix(), "part": index, "size_bytes": path.stat().st_size}
        for index, bucket in enumerate(buckets, 1)
        for path in bucket
    ]
    assignment = {
        "schema": "biointel.step206.package-assignment.v1",
        "step": RELEASE_STEP,
        "part_count": PART_COUNT,
        "archive_root": ARCHIVE_ROOT,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "estimated_uncompressed_part_bytes_before_assignment": sizes,
        "entries": assignment_rows,
        "note": "This assignment manifest excludes itself; package verification includes it.",
    }
    (ROOT / ASSIGNMENT_NAME).write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")
    index = min(range(PART_COUNT), key=lambda item: sizes[item])
    buckets[index].append(ROOT / ASSIGNMENT_NAME)
    sizes[index] += (ROOT / ASSIGNMENT_NAME).stat().st_size

    parts = [output / f"{args.name}-Part{part}.zip" for part in range(1, PART_COUNT + 1)]
    results = [build_part(parts[index], buckets[index], index + 1) for index in range(PART_COUNT)]
    integrity = verify(parts, source_files(True))
    with ThreadPoolExecutor(max_workers=PART_COUNT) as executor:
        hashes = list(executor.map(sha256, parts))
    for row, digest in zip(results, hashes, strict=True):
        row["sha256"] = digest
    integrity["parts"] = sorted(results, key=lambda row: str(row["file"]))
    integrity["part_uncompressed_bytes"] = sizes
    (output / "STEP206_PACKAGE_INTEGRITY.json").write_text(
        json.dumps(integrity, indent=2) + "\n", encoding="utf-8"
    )
    (output / "SHA256SUMS.txt").write_text(
        "".join(
            f"{row['sha256']}  {row['file']}\n"
            for row in sorted(results, key=lambda row: str(row["file"]))
        ),
        encoding="utf-8",
    )
    print(json.dumps(integrity, indent=2))
    return 0 if integrity["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
