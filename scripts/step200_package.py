from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "BioIntel-AI-Step196-WINDOWS-RELEASE-V16"
PART_COUNT = 5
STEP196_MANIFEST = "STEP196_SOURCE_MANIFEST_SHA256.json"
STEP196_ASSIGNMENT = "STEP196_PACKAGE_PART_ASSIGNMENT.json"
STEP200_MANIFEST = "STEP200_SOURCE_MANIFEST_SHA256.json"
STEP200_ASSIGNMENT = "STEP200_PACKAGE_PART_ASSIGNMENT.json"
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".release_parts", ".hotfix_backups"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
RUNTIME_EXCLUDES = {
    ".biointel_step196_installed",
    "reports/step196/validation.json",
    "reports/step196_release_metadata_repair.json",
    "reports/step196/v16-preinstall.json",
    "reports/step196/v16-validation-prebuild.json",
    "AUTO_INSTALL_AND_RUN_WINDOWS.bat",
    "START_STEP91_AUTO_INSTALL_WINDOWS.bat",
}
METADATA_NAMES = {STEP196_MANIFEST, STEP196_ASSIGNMENT, STEP200_MANIFEST, STEP200_ASSIGNMENT}
PRECOMPRESSED_SUFFIXES = {
    ".whl", ".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".pdf", ".mp4", ".avi", ".npy", ".npz", ".parquet", ".sqlite", ".sqlite3", ".db"
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
        text = relative.as_posix()
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith(("-wal", "-shm")):
            continue
        if relative.parts[:2] == ("UserData", "proof_gates_v10"):
            continue
        if text in RUNTIME_EXCLUDES:
            continue
        if not include_metadata and text in METADATA_NAMES:
            continue
        files.append(path)
    return sorted(files)


def hash_entries(files: list[Path]) -> list[dict[str, Any]]:
    workers = min(16, max(4, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        hashes = list(executor.map(sha256, files))
    return [
        {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest}
        for path, digest in zip(files, hashes, strict=True)
    ]


def write_manifests() -> None:
    base_files = source_files(include_metadata=False)
    entries = hash_entries(base_files)
    step196 = {
        "schema": "biointel.step196.source-manifest.v1",
        "release_step": 196,
        "release_version": "15.4.0",
        "hash_algorithm": "sha256",
        "excluded_runtime_paths": sorted(RUNTIME_EXCLUDES),
        "entries": entries,
    }
    (ROOT / STEP196_MANIFEST).write_text(json.dumps(step196, indent=2) + "\n", encoding="utf-8")

    step200_files = [path for path in source_files(include_metadata=False) if path.name != STEP200_MANIFEST]
    step200_entries = hash_entries(step200_files + [ROOT / STEP196_MANIFEST])
    # Deduplicate in case the Step196 manifest entered the normal file list after creation.
    dedup: dict[str, dict[str, Any]] = {row["path"]: row for row in step200_entries}
    step200 = {
        "schema": "biointel.step200.neuro-cns.source-manifest.v1",
        "release_step": 200,
        "base_release_step": 196,
        "hash_algorithm": "sha256",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "entries": [dedup[key] for key in sorted(dedup)],
    }
    (ROOT / STEP200_MANIFEST).write_text(json.dumps(step200, indent=2) + "\n", encoding="utf-8")


def allocate(files: list[Path]) -> tuple[list[list[Path]], list[int]]:
    buckets: list[list[Path]] = [[] for _ in range(PART_COUNT)]
    sizes = [0] * PART_COUNT
    for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True):
        index = min(range(PART_COUNT), key=lambda i: sizes[i])
        buckets[index].append(path)
        sizes[index] += path.stat().st_size
    return buckets, sizes


def write_assignments(buckets: list[list[Path]], sizes: list[int]) -> None:
    rows = []
    for index, bucket in enumerate(buckets, start=1):
        for path in bucket:
            rows.append({"path": path.relative_to(ROOT).as_posix(), "part": index, "size_bytes": path.stat().st_size})
    payload = {
        "schema": "biointel.step200.neuro-cns.package-assignment.v1",
        "step": 200,
        "part_count": PART_COUNT,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "estimated_uncompressed_part_bytes": sizes,
        "entries": rows,
    }
    text = json.dumps(payload, indent=2) + "\n"
    (ROOT / STEP200_ASSIGNMENT).write_text(text, encoding="utf-8")
    (ROOT / STEP196_ASSIGNMENT).write_text(text.replace("step200.neuro-cns", "step196.compatible-step200"), encoding="utf-8")


def compression_for(path: Path) -> int:
    if path.suffix.lower() in PRECOMPRESSED_SUFFIXES or path.stat().st_size > 25 * 1024 * 1024:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def build_part(destination: Path, files: list[Path], part: int) -> dict[str, Any]:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    marker196 = f"{ARCHIVE_ROOT}/.release_parts/step196_part{part}.ok"
    marker200 = f"{ARCHIVE_ROOT}/.release_parts/step200_part{part}.ok"
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for source in sorted(files):
            member = f"{ARCHIVE_ROOT}/{source.relative_to(ROOT).as_posix()}"
            archive.write(source, member, compress_type=compression_for(source), compresslevel=6)
        archive.writestr(marker196, f"BioIntel AI Step196 base marker for Step200 part {part}\n")
        archive.writestr(marker200, f"BioIntel AI Step200 Neuro/CNS verified release part {part}\n")
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        names = archive.namelist()
        unsafe = [name for name in names if not safe_relative(name)]
        if bad or unsafe or marker196 not in names or marker200 not in names:
            raise RuntimeError(f"Invalid part {part}: bad={bad}, unsafe={unsafe[:3]}")
    os.replace(temporary, destination)
    return {"part": part, "file": destination.name, "size_bytes": destination.stat().st_size, "sha256": sha256(destination), "entries": len(files) + 2}


def verify(parts: list[Path], expected_files: list[Path]) -> dict[str, Any]:
    expected = {f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}" for path in expected_files}
    seen: dict[str, int] = {}
    markers196: list[str] = []
    markers200: list[str] = []
    crc_errors: list[str] = []
    unsafe: list[str] = []
    for part in parts:
        with zipfile.ZipFile(part) as archive:
            bad = archive.testzip()
            if bad:
                crc_errors.append(f"{part.name}:{bad}")
            for info in archive.infolist():
                name = info.filename
                if not safe_relative(name):
                    unsafe.append(name)
                if "/.release_parts/step196_part" in name:
                    markers196.append(name)
                elif "/.release_parts/step200_part" in name:
                    markers200.append(name)
                else:
                    seen[name] = seen.get(name, 0) + 1
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    duplicates = sorted(name for name, count in seen.items() if count != 1)
    expected196 = [f"{ARCHIVE_ROOT}/.release_parts/step196_part{i}.ok" for i in range(1, 6)]
    expected200 = [f"{ARCHIVE_ROOT}/.release_parts/step200_part{i}.ok" for i in range(1, 6)]
    passed = not any((missing, extra, duplicates, crc_errors, unsafe)) and sorted(markers196) == expected196 and sorted(markers200) == expected200
    return {
        "schema": "biointel.step200.neuro-cns.package-integrity.v1",
        "status": "passed" if passed else "failed",
        "source_files": len(expected),
        "packaged_source_files": len(seen),
        "missing_files": missing,
        "extra_files": extra,
        "duplicate_files": duplicates,
        "crc_errors": crc_errors,
        "unsafe_paths": unsafe,
        "step196_markers": sorted(markers196),
        "step200_markers": sorted(markers200),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", default="BioIntel-AI-Step200-NEURO-CNS-MAX-POTENTIAL-WINDOWS-V16-5PART")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    for name in METADATA_NAMES:
        (ROOT / name).unlink(missing_ok=True)
    write_manifests()

    initial_files = [path for path in source_files(include_metadata=True) if path.name not in {STEP196_ASSIGNMENT, STEP200_ASSIGNMENT}]
    buckets, sizes = allocate(initial_files)
    write_assignments(buckets, sizes)
    # Put both assignment files in the currently smallest buckets.
    for assignment in (ROOT / STEP196_ASSIGNMENT, ROOT / STEP200_ASSIGNMENT):
        index = min(range(PART_COUNT), key=lambda i: sizes[i])
        buckets[index].append(assignment)
        sizes[index] += assignment.stat().st_size

    parts = [output / f"{args.name}-Part{i}.zip" for i in range(1, 6)]
    for part in parts:
        part.unlink(missing_ok=True)
    reports: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=PART_COUNT) as executor:
        futures = {executor.submit(build_part, parts[i], buckets[i], i + 1): i for i in range(PART_COUNT)}
        for future in as_completed(futures):
            reports.append(future.result())
    reports.sort(key=lambda row: row["part"])

    expected_files = source_files(include_metadata=True)
    integrity = verify(parts, expected_files)
    if integrity["status"] != "passed":
        raise RuntimeError(json.dumps(integrity, indent=2)[:10000])
    integrity["parts"] = reports
    integrity["generated_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    (output / "STEP200_PACKAGE_INTEGRITY.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text("".join(f"{row['sha256']}  {row['file']}\n" for row in reports), encoding="utf-8")

    for name in (
        "INSTALL_INSTRUCTIONS.txt",
        "CHANGELOG_STEP200_NEURO_CNS.md",
        "NEURO_CNS_STEP200_MAX_POTENTIAL_REPORT.md",
        "STEP200_23_MODULE_MAX_POTENTIAL_MATRIX.csv",
        "STEP200_23_MODULE_MAX_POTENTIAL_MATRIX.md",
        "STEP200_NEURO_TEST_STATUS.json",
    ):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, output / source.name)
    print(json.dumps({"integrity": integrity, "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
