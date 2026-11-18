"""Package and deeply verify the four-part BioIntel Selective Education Mega R9 release."""
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
from typing import Any

ARCHIVE_ROOT = "BioIntel-Step220"
PART_COUNT = 4
BASENAME = "BioIntel-AI-15.6.0-Selective-Education-Mega-R9"
CURRENT_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"
LEGACY_MANIFEST = "STEP220_SOURCE_MANIFEST_SHA256.json"
SOURCE_EXTENSIONS = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".css", ".html"}
RUNTIME_NAMES = {".git", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".qualification"}
RUNTIME_SUFFIXES = {".log", ".tmp", ".pid"}
STORE_SUFFIXES = {".zip", ".whl", ".gz", ".bz2", ".xz", ".7z", ".png", ".jpg", ".jpeg", ".mp4", ".webm", ".onnx"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_relative(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and not (path.parts and ":" in path.parts[0])


def source_paths(source: Path, output: Path | None = None, *, include_manifests: bool = True) -> list[Path]:
    result = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in RUNTIME_NAMES for part in relative.parts):
            continue
        if path.suffix.casefold() in RUNTIME_SUFFIXES or path.name.casefold().endswith(("-wal", "-shm")):
            continue
        if path.name.startswith(".codex_"):
            continue
        if not include_manifests and relative.as_posix() in {CURRENT_MANIFEST, LEGACY_MANIFEST}:
            continue
        if output:
            try:
                path.relative_to(output)
                continue
            except ValueError:
                pass
        result.append(path)
    return result


def record(path: Path, source: Path) -> dict[str, Any]:
    return {"path": path.relative_to(source).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def write_source_manifests(source: Path, output: Path) -> dict[str, Any]:
    paths = source_paths(source, output, include_manifests=False)
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as pool:
        rows = list(pool.map(lambda item: record(item, source), paths))
    common = {
        "release_step": 220,
        "build_number": "Step220-Selective-Education-Mega-R9",
        "release_version": "15.6.0",
        "package_generation": "R9",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "selective_education_mega": {
            "migration": "education_selective_mega_r9_v1",
            "scope": ["Education Hub", "Classroom", "Examination Command Center"],
            "zero_removal": True,
        },
    }
    current = {"schema": "biointel.release.source-manifest.v1", **common, "files": rows}
    legacy = {"schema": "biointel.step220.windows.source-manifest.v1", **common, "entries": rows}
    current_path, legacy_path = source / CURRENT_MANIFEST, source / LEGACY_MANIFEST
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    legacy_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": len(rows), "current": str(current_path), "legacy": str(legacy_path)}


def assign_parts(paths: list[Path]) -> list[list[Path]]:
    parts: list[list[Path]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    for path in sorted(paths, key=lambda item: (-item.stat().st_size, item.as_posix().casefold())):
        index = min(range(PART_COUNT), key=lambda part: (totals[part], part))
        parts[index].append(path)
        totals[index] += path.stat().st_size
    return parts


def zip_timestamp(path: Path) -> tuple[int, int, int, int, int, int]:
    value = time.localtime(path.stat().st_mtime)
    year = min(max(value.tm_year, 1980), 2107)
    return year, value.tm_mon, value.tm_mday, value.tm_hour, value.tm_min, value.tm_sec - value.tm_sec % 2


def write_archive(source: Path, archive: Path, paths: list[Path]) -> dict[str, Any]:
    with zipfile.ZipFile(archive, "w", allowZip64=True) as bundle:
        for path in sorted(paths, key=lambda item: item.relative_to(source).as_posix().casefold()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{relative}", date_time=zip_timestamp(path))
            info.compress_type = zipfile.ZIP_STORED if path.suffix.casefold() in STORE_SUFFIXES else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as input_handle, bundle.open(info, "w", force_zip64=True) as output_handle:
                shutil.copyfileobj(input_handle, output_handle, 1024 * 1024)
    return {
        "name": archive.name,
        "files": len(paths),
        "uncompressed_bytes": sum(path.stat().st_size for path in paths),
        "archive_bytes": archive.stat().st_size,
        "sha256": sha256_file(archive),
    }


def verify_archives(source: Path, archives: list[Path], expected: list[Path], extract_to: Path | None) -> dict[str, Any]:
    expected_names = {f"{ARCHIVE_ROOT}/{path.relative_to(source).as_posix()}" for path in expected}
    seen: set[str] = set()
    crc_failures = []
    roots = set()
    for archive in archives:
        with zipfile.ZipFile(archive) as bundle:
            bad = bundle.testzip()
            if bad:
                crc_failures.append({"archive": archive.name, "member": bad})
            for item in bundle.infolist():
                if item.is_dir():
                    continue
                if not safe_relative(item.filename):
                    raise RuntimeError(f"Unsafe ZIP member: {item.filename}")
                roots.add(PurePosixPath(item.filename).parts[0])
                if item.filename in seen:
                    raise RuntimeError(f"Duplicate member across parts: {item.filename}")
                seen.add(item.filename)
    if crc_failures:
        raise RuntimeError(f"ZIP CRC failure: {crc_failures}")
    if roots != {ARCHIVE_ROOT}:
        raise RuntimeError(f"Unexpected archive roots: {roots}")
    missing, extra = expected_names - seen, seen - expected_names
    if missing or extra:
        raise RuntimeError(f"Combined archive mismatch: missing={len(missing)} extra={len(extra)}")
    extraction = {"performed": False}
    if extract_to:
        extract_to = extract_to.resolve()
        if extract_to.exists():
            raise RuntimeError(f"Verification extraction target must not exist: {extract_to}")
        extract_to.mkdir(parents=True)
        for archive in archives:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extract_to)
        extracted_root = extract_to / ARCHIVE_ROOT
        extracted_files = [path for path in extracted_root.rglob("*") if path.is_file()]
        if len(extracted_files) != len(expected):
            raise RuntimeError(f"Extracted file count mismatch: {len(extracted_files)} != {len(expected)}")
        manifest = json.loads((extracted_root / CURRENT_MANIFEST).read_text(encoding="utf-8"))
        failures = []
        for row in manifest["files"]:
            path = extracted_root / row["path"]
            if not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
                failures.append(row["path"])
        if failures:
            raise RuntimeError(f"Extracted source-manifest failures: {failures[:10]}")
        extraction = {"performed": True, "path": str(extract_to), "files": len(extracted_files), "manifest_failures": 0}
    return {"crc_failures": 0, "combined_files": len(seen), "root": ARCHIVE_ROOT, "missing": 0, "extra": 0, "extraction": extraction}


def package(source: Path, output: Path, extract_to: Path | None = None) -> dict[str, Any]:
    source, output = source.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_source_manifests(source, output)
    paths = source_paths(source, output)
    zero_sources = [path.relative_to(source).as_posix() for path in paths if path.suffix.casefold() in SOURCE_EXTENSIONS and path.stat().st_size == 0]
    if zero_sources:
        raise RuntimeError(f"Zero-byte source files: {zero_sources}")
    parts = assign_parts(paths)
    archives = [output / f"{BASENAME}-Part{index}.zip" for index in range(1, PART_COUNT + 1)]
    for archive in archives:
        if archive.exists():
            raise RuntimeError(f"Refusing to overwrite existing package: {archive}")
    records = [write_archive(source, archive, assigned) for archive, assigned in zip(archives, parts)]
    verification = verify_archives(source, archives, paths, extract_to)
    sums = output / f"{BASENAME}-SHA256SUMS.txt"
    sums.write_text("".join(f"{row['sha256']}  {row['name']}\n" for row in records), encoding="ascii")
    assignment = output / f"{BASENAME}-PACKAGE-ASSIGNMENT.json"
    assignment.write_text(json.dumps({
        "schema": "biointel.selective-education-mega-r9.package.v1",
        "generated_at_utc": utc_now(), "source": str(source), "parts": records,
        "combined": {"files": len(paths), "uncompressed_bytes": sum(path.stat().st_size for path in paths)},
        "verification": verification,
    }, indent=2) + "\n", encoding="utf-8")
    return {"parts": records, "sha256sums": str(sums), "assignment": str(assignment), "verification": verification}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-extract", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(package(arguments.source, arguments.output, arguments.verify_extract), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
