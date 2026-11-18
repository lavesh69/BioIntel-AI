from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "BioIntel-AI-Step192-RELEASE-INTEGRITY-PUBLICATION-INSTALL-REPAIR-80OF80"
MANIFEST_NAME = "STEP192_SOURCE_MANIFEST_SHA256.json"
ASSIGNMENT_NAME = "STEP192_PACKAGE_PART_ASSIGNMENT.json"

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".release_parts"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(relative: str) -> bool:
    path = PurePosixPath(relative)
    return not path.is_absolute() and ".." not in path.parts and not any(part == "" for part in path.parts)


def source_files(*, include_metadata: bool) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if not include_metadata and relative.as_posix() in {MANIFEST_NAME, ASSIGNMENT_NAME}:
            continue
        files.append(path)
    return sorted(files)


def write_source_manifest() -> dict[str, Any]:
    entries = []
    for path in source_files(include_metadata=False):
        entries.append({"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)})
    payload = {"schema": "biointel.step192.source-manifest.v1", "release_step": 192, "release_version": "15.0.0", "entries": entries}
    (ROOT / MANIFEST_NAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def allocate(files: list[Path]) -> tuple[list[list[Path]], list[int]]:
    buckets: list[list[Path]] = [[] for _ in range(4)]
    sizes = [0, 0, 0, 0]
    for path in sorted(files, key=lambda item: item.stat().st_size, reverse=True):
        index = min(range(4), key=lambda item: sizes[item])
        buckets[index].append(path)
        sizes[index] += path.stat().st_size
    return buckets, sizes


def build_atomic_zip(destination: Path, files: list[Path], part: int) -> dict[str, Any]:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
        for source in sorted(files):
            arcname = (Path("BioIntel-AI") / source.relative_to(ROOT)).as_posix()
            archive.write(source, arcname)
        archive.writestr(f"BioIntel-AI/.release_parts/step192_part{part}.ok", "step192\n")
    with zipfile.ZipFile(temporary) as archive:
        corrupt = archive.testzip()
        names = archive.namelist()
        unsafe = [name for name in names if not safe_relative(name)]
        marker = f"BioIntel-AI/.release_parts/step192_part{part}.ok"
        if corrupt or unsafe or marker not in names:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Part {part} validation failed: corrupt={corrupt}, unsafe={unsafe[:3]}, marker={marker in names}")
    os.replace(temporary, destination)
    return {"sha256": sha256(destination), "size_bytes": destination.stat().st_size, "entries": len(files) + 1}


def verify_parts(paths: list[Path], expected_files: list[Path]) -> dict[str, Any]:
    expected = {f"BioIntel-AI/{path.relative_to(ROOT).as_posix()}" for path in expected_files}
    seen: dict[str, int] = {}
    crc_errors: list[str] = []
    unsafe_paths: list[str] = []
    markers: list[str] = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                crc_errors.append(f"{path.name}:{corrupt}")
            for info in archive.infolist():
                name = info.filename
                if not safe_relative(name):
                    unsafe_paths.append(name)
                if "/.release_parts/step192_part" in name:
                    markers.append(name)
                    continue
                seen[name] = seen.get(name, 0) + 1
    actual = set(seen)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    duplicates = sorted(name for name, count in seen.items() if count != 1)
    expected_markers = [f"BioIntel-AI/.release_parts/step192_part{i}.ok" for i in range(1, 5)]
    status = not any((missing, extra, duplicates, crc_errors, unsafe_paths)) and sorted(markers) == expected_markers
    return {
        "schema": "biointel.step192.package-integrity.v1",
        "status": "passed" if status else "failed",
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
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    (ROOT / MANIFEST_NAME).unlink(missing_ok=True)
    (ROOT / ASSIGNMENT_NAME).unlink(missing_ok=True)
    write_source_manifest()
    initial_files = source_files(include_metadata=True)
    buckets, sizes = allocate(initial_files)
    assignment = {
        "schema": "biointel.step192.package-assignment.v1",
        "release_step": 192,
        "release_version": "15.0.0",
        "assignments": {path.relative_to(ROOT).as_posix(): index + 1 for index, bucket in enumerate(buckets) for path in bucket},
        "part_uncompressed_bytes": sizes,
    }
    assignment_part = min(range(4), key=lambda index: sizes[index])
    assignment["assignments"][ASSIGNMENT_NAME] = assignment_part + 1
    (ROOT / ASSIGNMENT_NAME).write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")
    buckets[assignment_part].append(ROOT / ASSIGNMENT_NAME)
    sizes[assignment_part] += (ROOT / ASSIGNMENT_NAME).stat().st_size

    outputs: list[Path] = []
    checksums: dict[str, Any] = {}
    for part, bucket in enumerate(buckets, 1):
        destination = output / f"{args.name}-Part{part}.zip"
        checksums[destination.name] = build_atomic_zip(destination, bucket, part)
        outputs.append(destination)

    final_files = source_files(include_metadata=True)
    integrity = verify_parts(outputs, final_files)
    integrity["checksums"] = {name: {key: value for key, value in payload.items() if key != "entries"} for name, payload in checksums.items()}
    integrity["part_uncompressed_bytes"] = sizes
    checksum_path = output / f"{args.name}-CHECKSUMS.json"
    integrity_path = output / f"{args.name}-PACKAGE-INTEGRITY.json"
    checksum_path.write_text(json.dumps(integrity["checksums"], indent=2) + "\n", encoding="utf-8")
    integrity_path.write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    if integrity["status"] != "passed":
        raise RuntimeError(f"Final package verification failed: {integrity_path}")
    print(json.dumps({"outputs": [str(path) for path in outputs], "checksums": integrity["checksums"], "integrity": integrity}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
