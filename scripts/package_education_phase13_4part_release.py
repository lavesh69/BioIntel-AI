"""Build and deeply verify the BioIntel Education Phase 13 four-part release."""
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
RELEASE_NAME = "BioIntel-AI-15.6.0-EDUCATION-PHASE13"
ARCHIVE_ROOT = "BioIntel-Step220"
CURRENT_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"
LEGACY_MANIFEST = "STEP220_SOURCE_MANIFEST_SHA256.json"
EXCLUDED_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", "Temp", "runtime_logs", "UserData", "work",
    ".test-tmp", ".test-smoke", ".hotfix_backups", "edge-profile", "cache",
    "phase13b_test_runtime",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".pid", ".wal", ".shm"}
MUTABLE_REPORT_DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-shm", ".sqlite3-wal")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excluded(path: Path, source: Path, output: Path | None = None, *, exclude_manifests: bool = False) -> bool:
    rel = path.relative_to(source)
    folded_dirs = {item.casefold() for item in EXCLUDED_DIRS}
    if any(part.casefold() in folded_dirs for part in rel.parts[:-1]):
        return True
    rel_posix = rel.as_posix()
    if rel_posix in {".env", ".coverage"}:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.lower().endswith(("-wal", "-shm")):
        return True
    if rel.parts and rel.parts[0].casefold() == "reports" and rel.name.casefold().endswith(MUTABLE_REPORT_DATABASE_SUFFIXES):
        return True
    if rel.parts and rel.parts[0].casefold() == "wheelhouse" and rel.name.casefold().startswith("coverage-") and rel.suffix == ".whl":
        return True
    if rel.parent.as_posix() == "release" and rel.name.startswith("PART_MANIFEST-Part") and rel.suffix == ".json":
        return True
    if rel.parent.as_posix() == ".release_parts":
        lower = rel.name.lower()
        if lower.startswith("education_phase") or lower.startswith("shiro4_part"):
            return True
    if rel.name.startswith(".biointel_step") and rel.name.endswith("_installed"):
        return True
    if exclude_manifests and rel_posix in {CURRENT_MANIFEST, LEGACY_MANIFEST}:
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


def source_paths(source: Path, output: Path | None = None, *, exclude_manifests: bool = False) -> list[Path]:
    return [
        path for path in sorted(source.rglob("*"))
        if path.is_file() and not excluded(path, source, output, exclude_manifests=exclude_manifests)
    ]


def record_for(path: Path, source: Path) -> dict:
    return {
        "path": path.relative_to(source).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "full_path": str(path),
    }


def write_legacy_manifest(source: Path, output: Path) -> Path:
    rows = []
    paths = source_paths(source, output, exclude_manifests=True)
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        for row in executor.map(lambda p: record_for(p, source), paths):
            rows.append({key: row[key] for key in ("path", "size_bytes", "sha256")})
    payload = {
        "schema": "biointel.step220.windows.source-manifest.v1",
        "release_step": 220,
        "build_number": "Step220-V20.3-Phase13",
        "base_release_step": 219,
        "release_version": "15.6.0",
        "package_generation": "V20.3",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "excluded_runtime_paths": sorted(EXCLUDED_DIRS),
        "entries": rows,
        "phase13": {
            "release": RELEASE_NAME,
            "controls": 27,
            "combined_controls": 363,
            "regression_tests": 110,
            "multiformat_rag": True,
            "automatic_timetable": True,
            "notification_policy_and_dead_letter": True,
            "retention_and_support_diagnostics": True,
            "external_qualification_honesty": True,
        },
    }
    path = source / LEGACY_MANIFEST
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def collect_records(source: Path, output: Path) -> list[dict]:
    paths = source_paths(source, output)
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        for index, row in enumerate(executor.map(lambda p: record_for(p, source), paths), start=1):
            row["weight"] = row["size_bytes"] + 160
            records.append(row)
            if index % 2500 == 0:
                print(f"Hashed {index} package files...", flush=True)
    return records


def write_current_manifest(source: Path, records: list[dict]) -> dict:
    path = source / CURRENT_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "biointel.release.source-manifest.v1",
        "release_step": 220,
        "build_number": "Step220-V20.3-Phase13",
        "release_version": "15.6.0",
        "package_generation": "V20.3",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "files": [{key: row[key] for key in ("path", "size_bytes", "sha256")} for row in records],
        "phase13": {
            "release": RELEASE_NAME,
            "controls": 27,
            "combined_controls": 363,
            "regression_tests": 110,
            "api_routes": 199,
            "phase13_api_routes": 12,
            "multiformat_rag": True,
            "automatic_timetable": True,
            "notification_policy_and_dead_letter": True,
            "retention_and_support_diagnostics": True,
            "external_qualification_honesty": True,
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    row = record_for(path, source)
    row["weight"] = row["size_bytes"] + 160
    records.append(row)
    return payload


def prior_assignments(prior_dir: Path | None) -> dict[str, int]:
    assignments: dict[str, int] = {}
    if prior_dir is None:
        return assignments
    for index in range(1, PART_COUNT + 1):
        path = prior_dir / f"PART_MANIFEST-Part{index}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("files", []):
            rel = str(row.get("path", ""))
            if rel and rel not in assignments:
                assignments[rel] = index - 1
    return assignments


def balance(records: list[dict], assignments: dict[str, int]) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    unassigned: list[dict] = []
    for row in records:
        target = assignments.get(row["path"])
        if target is None:
            unassigned.append(row)
        else:
            buckets[target].append(row)
            totals[target] += row["weight"]
    for row in sorted(unassigned, key=lambda item: item["weight"], reverse=True):
        target = min(range(PART_COUNT), key=totals.__getitem__)
        buckets[target].append(row)
        totals[target] += row["weight"]
    print(f"Reused assignments: {len(records)-len(unassigned)}; new: {len(unassigned)}", flush=True)
    return buckets


def create_parts(source: Path, output: Path, buckets: list[list[dict]]) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / f"{RELEASE_NAME}-Part{i}.zip" for i in range(1, PART_COUNT + 1)]
    for target in targets:
        target.unlink(missing_ok=True)
    for index, (target, bucket) in enumerate(zip(targets, buckets, strict=True), start=1):
        print(f"Writing Part {index}: {len(bucket)} source files", flush=True)
        part_manifest = {
            "release": RELEASE_NAME,
            "part": index,
            "part_count": PART_COUNT,
            "source_file_count": len(bucket),
            "files": [{key: row[key] for key in ("path", "size_bytes", "sha256")} for row in bucket],
        }
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for row in bucket:
                archive.write(row["full_path"], f"{ARCHIVE_ROOT}/{row['path']}")
            archive.writestr(
                f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json",
                json.dumps(part_manifest, indent=2).encode("utf-8"),
            )
            archive.writestr(
                f"{ARCHIVE_ROOT}/.release_parts/education_phase13_part{index}.ok",
                f"BioIntel AI Education Phase 13 archive part {index} of {PART_COUNT}\n",
            )
            archive.writestr(
                f"{ARCHIVE_ROOT}/.release_parts/shiro4_part{index}.ok",
                f"BioIntel AI Education compatibility archive part {index} of {PART_COUNT}\n",
            )
    return targets


def verify(parts: list[Path], buckets: list[list[dict]]) -> dict:
    seen: set[str] = set()
    part_rows: list[dict] = []
    for index, (part, bucket) in enumerate(zip(parts, buckets, strict=True), start=1):
        with zipfile.ZipFile(part) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"CRC failure in {part.name}: {bad}")
            archive.getinfo(f"{ARCHIVE_ROOT}/.release_parts/education_phase13_part{index}.ok")
            archive.getinfo(f"{ARCHIVE_ROOT}/.release_parts/shiro4_part{index}.ok")
            embedded = json.loads(archive.read(f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json"))
            embedded_paths = {str(row["path"]) for row in embedded.get("files", [])}
            expected_paths = {row["path"] for row in bucket}
            if embedded_paths != expected_paths:
                raise RuntimeError(f"Part manifest mismatch: {part.name}")
            overlap = seen.intersection(expected_paths)
            if overlap:
                raise RuntimeError(f"Duplicate source paths across parts: {sorted(overlap)[:10]}")
            seen.update(expected_paths)
            for offset, row in enumerate(bucket, start=1):
                rel = row["path"]
                if PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts:
                    raise RuntimeError(f"Unsafe source path: {rel}")
                member = archive.getinfo(f"{ARCHIVE_ROOT}/{rel}")
                if member.file_size != row["size_bytes"]:
                    raise RuntimeError(f"Size mismatch in archive: {rel}")
                digest = hashlib.sha256()
                with archive.open(member) as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != row["sha256"]:
                    raise RuntimeError(f"SHA-256 mismatch in archive: {rel}")
                if offset % 3000 == 0:
                    print(f"Verified {offset} files in Part {index}", flush=True)
        part_rows.append({
            "part": index,
            "name": part.name,
            "size_bytes": part.stat().st_size,
            "sha256": sha256_file(part),
            "source_files": len(bucket),
        })
    expected = {row["path"] for bucket in buckets for row in bucket}
    if seen != expected:
        raise RuntimeError("Archive source union mismatch")
    sizes = [row["size_bytes"] for row in part_rows]
    average = sum(sizes) / len(sizes)
    variance = (max(sizes) - min(sizes)) / average * 100 if average else 0.0
    return {
        "schema": "biointel.education-phase13.archive-verification.v1",
        "release": RELEASE_NAME,
        "verified": True,
        "verification_mode": "crc-exact-path-union-and-direct-per-file-sha256",
        "source_files_including_current_manifest": len(expected),
        "missing_paths": 0,
        "duplicate_source_paths": 0,
        "size_variance_percent": round(variance, 4),
        "parts": part_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prior-manifest-dir", type=Path)
    parser.add_argument("--verification-output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_legacy_manifest(source, output)
    records = collect_records(source, output)
    current_payload = write_current_manifest(source, records)
    assignments = prior_assignments(args.prior_manifest_dir.resolve() if args.prior_manifest_dir else None)
    buckets = balance(records, assignments)
    parts = create_parts(source, output, buckets)
    verification = verify(parts, buckets)
    args.verification_output.parent.mkdir(parents=True, exist_ok=True)
    args.verification_output.write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("RELEASE_RESULT=" + json.dumps({
        "release": RELEASE_NAME,
        "tracked_files": len(current_payload["files"]),
        "packaged_source_files": verification["source_files_including_current_manifest"],
        "size_variance_percent": verification["size_variance_percent"],
        "parts": verification["parts"],
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
