from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "BioIntel-AI-Step196-WINDOWS-RELEASE-V16-5PART"
ARCHIVE_ROOT = "BioIntel-AI-Step196-WINDOWS-RELEASE-V16"
MANIFEST_NAME = "STEP196_SOURCE_MANIFEST_SHA256.json"
ASSIGNMENT_NAME = "STEP196_PACKAGE_PART_ASSIGNMENT.json"
FLAT_MANIFEST_NAME = "FILE_MANIFEST_SHA256.txt"
PART_COUNT = 5
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".release_parts",
    ".hotfix_backups",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_RELATIVE = {
    MANIFEST_NAME,
    ASSIGNMENT_NAME,
    ".biointel_step196_installed",
    "reports/step196/validation.json",
    "reports/step196_release_metadata_repair.json",
    "reports/step196/v16-preinstall.json",
    "reports/step196/v16-validation-prebuild.json",
    # The supported V16 flow is deliberately two-step.  Legacy one-click
    # launchers are excluded so they cannot create a second, confusing path.
    "AUTO_INSTALL_AND_RUN_WINDOWS.bat",
    "START_STEP91_AUTO_INSTALL_WINDOWS.bat",
}
EXCLUDED_RUNTIME_PREFIXES = {
    ("UserData", "proof_gates_v10"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and bool(path.parts)


def source_files(*, include_metadata: bool) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        relative_text = relative.as_posix()
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if any(relative.parts[:len(prefix)] == prefix for prefix in EXCLUDED_RUNTIME_PREFIXES):
            # Locally staged P0/P1 evidence is user data, not a release input.
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if path.name.endswith(("-wal", "-shm")):
            # SQLite sidecars are runtime residue, not immutable release inputs.
            continue
        if relative_text in EXCLUDED_RELATIVE and not (
            include_metadata and relative_text in {MANIFEST_NAME, ASSIGNMENT_NAME}
        ):
            continue
        files.append(path)
    return sorted(files)


def write_source_manifest() -> dict[str, Any]:
    files = source_files(include_metadata=False)
    workers = min(16, max(4, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        hashes = list(executor.map(sha256, files))
    entries = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": digest,
        }
        for path, digest in zip(files, hashes, strict=True)
    ]
    payload = {
        "schema": "biointel.step196.source-manifest.v1",
        "release_step": 196,
        "release_version": "15.4.0",
        "hash_algorithm": "sha256",
        "excluded_runtime_paths": sorted(EXCLUDED_RELATIVE - {MANIFEST_NAME, ASSIGNMENT_NAME}),
        "entries": entries,
    }
    (ROOT / MANIFEST_NAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def write_flat_manifest() -> int:
    """Write the user-readable SHA-256 manifest without self-referential rows."""
    files = [path for path in source_files(include_metadata=False) if path.name != FLAT_MANIFEST_NAME]
    workers = min(16, max(4, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        hashes = list(executor.map(sha256, files))
    body = "".join(
        f"{digest}  {path.relative_to(ROOT).as_posix()}\n"
        for path, digest in zip(files, hashes, strict=True)
    )
    (ROOT / FLAT_MANIFEST_NAME).write_text(body, encoding="utf-8")
    return len(files)


def allocate(files: list[Path]) -> tuple[list[list[Path]], list[int]]:
    buckets: list[list[Path]] = [[] for _ in range(PART_COUNT)]
    sizes = [0 for _ in range(PART_COUNT)]
    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True):
        index = min(range(PART_COUNT), key=lambda item: sizes[item])
        buckets[index].append(path)
        sizes[index] += path.stat().st_size
    return buckets, sizes


def compression_for(path: Path) -> int:
    # Store release members without recompression. The package already contains many
    # compressed wheels/models and atomic stored ZIPs build much faster and more reliably.
    return zipfile.ZIP_STORED


def build_zip(destination: Path, files: list[Path], part: int) -> dict[str, Any]:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    marker = f"{ARCHIVE_ROOT}/.release_parts/step196_part{part}.ok"
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for source in sorted(files):
            member = (Path(ARCHIVE_ROOT) / source.relative_to(ROOT)).as_posix()
            archive.write(source, member, compress_type=compression_for(source), compresslevel=6)
        archive.writestr(marker, "BioIntel AI Step 196 verified release part\n")
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        names = archive.namelist()
        unsafe = [name for name in names if not safe_relative(name)]
        if bad or unsafe or marker not in names:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"Part {part} invalid: bad={bad!r}, unsafe={unsafe[:3]}, marker={marker in names}"
            )
    os.replace(temporary, destination)
    return {
        "sha256": sha256(destination),
        "size_bytes": destination.stat().st_size,
        "entries": len(files) + 1,
    }


def verify(parts: list[Path], expected_files: list[Path]) -> dict[str, Any]:
    expected = {
        f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}" for path in expected_files
    }
    seen: dict[str, int] = {}
    markers: list[str] = []
    crc_errors: list[str] = []
    unsafe_paths: list[str] = []
    for part in parts:
        with zipfile.ZipFile(part) as archive:
            bad = archive.testzip()
            if bad:
                crc_errors.append(f"{part.name}:{bad}")
            for info in archive.infolist():
                name = info.filename
                if not safe_relative(name):
                    unsafe_paths.append(name)
                if "/.release_parts/step196_part" in name:
                    markers.append(name)
                    continue
                seen[name] = seen.get(name, 0) + 1
    actual = set(seen)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    duplicates = sorted(name for name, count in seen.items() if count != 1)
    expected_markers = [
        f"{ARCHIVE_ROOT}/.release_parts/step196_part{part}.ok" for part in range(1, PART_COUNT + 1)
    ]
    passed = not any((missing, extra, duplicates, crc_errors, unsafe_paths)) and sorted(markers) == expected_markers
    return {
        "schema": "biointel.step196.package-integrity.v1",
        "status": "passed" if passed else "failed",
        "source_files": len(expected),
        "packaged_source_files": len(actual),
        "package_entries_including_markers": sum(seen.values()) + len(markers),
        "release_markers": sorted(markers),
        "missing_files": missing,
        "extra_files": extra,
        "duplicate_files": duplicates,
        "crc_errors": crc_errors,
        "unsafe_paths": unsafe_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    parser.add_argument("--name", default=DEFAULT_NAME)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    (ROOT / MANIFEST_NAME).unlink(missing_ok=True)
    (ROOT / ASSIGNMENT_NAME).unlink(missing_ok=True)
    (ROOT / FLAT_MANIFEST_NAME).unlink(missing_ok=True)
    flat_manifest_entries = write_flat_manifest()
    write_source_manifest()

    # The assignment is generated below and deliberately appended to exactly one
    # bucket.  Filter it here as well so a stale/recreated metadata file can
    # never be included twice on a rebuild.
    initial = [
        path
        for path in source_files(include_metadata=True)
        if path.relative_to(ROOT).as_posix() != ASSIGNMENT_NAME
    ]
    buckets, sizes = allocate(initial)
    assignments = {
        path.relative_to(ROOT).as_posix(): index + 1
        for index, bucket in enumerate(buckets)
        for path in bucket
    }
    assignment = {
        "schema": "biointel.step196.package-assignment.v1",
        "release_step": 196,
        "release_version": "15.4.0",
        "package_revision": "V16-5PART",
        "part_count": PART_COUNT,
        "assignments": assignments,
        "part_uncompressed_bytes": sizes,
    }
    smallest = min(range(PART_COUNT), key=lambda index: sizes[index])
    assignment["assignments"][ASSIGNMENT_NAME] = smallest + 1
    (ROOT / ASSIGNMENT_NAME).write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")
    buckets[smallest].append(ROOT / ASSIGNMENT_NAME)
    sizes[smallest] += (ROOT / ASSIGNMENT_NAME).stat().st_size

    parts: list[Path] = []
    checksums: dict[str, Any] = {}
    for part, bucket in enumerate(buckets, 1):
        destination = output_dir / f"{args.name}-Part{part}.zip"
        checksums[destination.name] = build_zip(destination, bucket, part)
        parts.append(destination)

    integrity = verify(parts, source_files(include_metadata=True))
    integrity["checksums"] = {
        name: {"sha256": row["sha256"], "size_bytes": row["size_bytes"]}
        for name, row in checksums.items()
    }
    integrity["part_uncompressed_bytes"] = sizes
    integrity["part_count"] = PART_COUNT
    integrity["flat_manifest_entries"] = flat_manifest_entries
    (output_dir / f"{args.name}-CHECKSUMS.json").write_text(
        json.dumps(integrity["checksums"], indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / f"{args.name}-PACKAGE-INTEGRITY.json").write_text(
        json.dumps(integrity, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"outputs": [str(path) for path in parts], "integrity": integrity}, indent=2))
    return 0 if integrity["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
