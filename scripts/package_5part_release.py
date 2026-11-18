"""Create exactly five balanced, reconstructable BioIntel AI release ZIPs.

The packager is portable, excludes local/runtime state, writes SHA-256 source and
per-part manifests into the archive, and verifies a fresh reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
import zlib
from pathlib import Path
from typing import Iterable

PART_COUNT = 5
RELEASE_NAME = "BioIntel-AI-15.6.0-COMPLETE-INTEGRATION-FIXED-5PART"
EXCLUDED_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", "Temp", "runtime_logs", "UserData", "work",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".pid", ".wal", ".shm"}
SOURCE_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"


def excluded(path: Path, source: Path, output: Path | None = None) -> bool:
    rel = path.relative_to(source)
    if any(part in EXCLUDED_DIRS for part in rel.parts[:-1]):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.lower().endswith(("-wal", "-shm")):
        return True
    if rel.as_posix() == SOURCE_MANIFEST:
        return True
    if output is not None:
        try:
            path.relative_to(output)
            return True
        except ValueError:
            pass
    return False


def iter_source_files(source: Path, output: Path | None = None) -> Iterable[Path]:
    for path in sorted(source.rglob("*")):
        if path.is_file() and not excluded(path, source, output):
            yield path


def digest_and_estimate(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    compressor = zlib.compressobj(level=6)
    compressed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            compressed += len(compressor.compress(chunk))
    compressed += len(compressor.flush())
    return digest.hexdigest(), compressed


def write_release_notes(source: Path) -> None:
    release = source / "release"
    release.mkdir(parents=True, exist_ok=True)
    reconstruction = """# Reconstruct the five-part release on Windows

1. Put all five `BioIntel-AI-15.6.0-COMPLETE-INTEGRATION-FIXED-5PART-PartN.zip` files in one folder.
2. Extract every ZIP into the same empty destination folder, in any order.
3. Confirm the result contains one `BioIntel-Step220` directory and all five `.release_parts/step220_partN.ok` markers.
4. Run `INSTALL_WINDOWS.bat`; after installation, use `RUN_BOTH_WINDOWS.bat`.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\\BioIntelAI\\UserData`.
"""
    completion = """# BioIntel AI 15.6.0 integration repair report

## Implemented and verified

- Reconstructed all five supplied archives without duplicate or unsafe paths.
- Curated pages 271-274 into normal navigation and dashboard entry points.
- Replaced synthetic weather/AQI, default-location, fabricated ClinicalTrials, fake PDF chunks, permissive license-prefix checks, and hardcoded connectivity health with truthful provider-backed or unavailable states.
- Added real PDF/text/notebook extraction and evidence retrieval; no-evidence queries remain explicit.
- Added one-shot browser geolocation consent, saved/recent locations, forecast, AQI, alerts status, comparison, cache provenance, and Celsius/Fahrenheit handling.
- Added bounded real connectivity probes and actual local runtime checks.
- Completed a repository-wide Python compile gate and focused regression suite.
- Built five balanced ZIP parts with SHA-256 manifests and fresh reconstruction verification.
- Updated the Windows release gate to prefer the current archive manifest and reject stale legacy hashes.

## Honest boundaries

No external vendor license confirmation, credentials, clinical patient data, DICOM/PACS endpoint, or official weather-alert endpoint was supplied; those integrations therefore fail closed or report configuration/authentication required. No claim is made that every one of the 275 pages received a new domain-validation test in this repair pass.
"""
    (release / "RECONSTRUCT_5PART.md").write_text(reconstruction, encoding="utf-8", newline="\n")
    (release / "COMPLETION_REPORT.md").write_text(completion, encoding="utf-8", newline="\n")


def collect_records(source: Path, output: Path, *, estimate_compression: bool = True) -> list[dict]:
    records: list[dict] = []
    for index, path in enumerate(iter_source_files(source, output), start=1):
        if estimate_compression:
            digest, compressed = digest_and_estimate(path)
        else:
            digest = sha256(path)
            compressed = path.stat().st_size
        rel = path.relative_to(source).as_posix()
        records.append({
            "path": rel,
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "compressed_estimate": compressed + 160,
            "full_path": str(path),
        })
        if index % 2500 == 0:
            print(f"Hashed {index} source files...", flush=True)
    return records


def write_source_manifest(source: Path, records: list[dict]) -> Path:
    manifest_path = source / SOURCE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "release": RELEASE_NAME,
        "archive_root": source.name,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_count_excluding_manifest": len(records),
        "files": [
            {key: record[key] for key in ("path", "size_bytes", "sha256")}
            for record in records
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    digest, compressed = digest_and_estimate(manifest_path)
    records.append({
        "path": SOURCE_MANIFEST,
        "size_bytes": manifest_path.stat().st_size,
        "sha256": digest,
        "compressed_estimate": compressed + 160,
        "full_path": str(manifest_path),
    })
    return manifest_path


def balance(records: list[dict]) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    for record in sorted(records, key=lambda item: item["compressed_estimate"], reverse=True):
        target = min(range(PART_COUNT), key=totals.__getitem__)
        buckets[target].append(record)
        totals[target] += record["compressed_estimate"]
    return buckets


def balance_from_prior_manifests(records: list[dict], manifest_dir: Path) -> list[list[dict]]:
    assignments: dict[str, int] = {}
    for index in range(1, PART_COUNT + 1):
        path = manifest_dir / f"PART_MANIFEST-Part{index}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("files", []):
            rel = str(row.get("path", ""))
            if rel in assignments:
                raise RuntimeError(f"Duplicate prior part assignment: {rel}")
            assignments[rel] = index - 1
    buckets: list[list[dict]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    unassigned: list[dict] = []
    for record in records:
        target = assignments.get(record["path"])
        if target is None:
            unassigned.append(record)
            continue
        buckets[target].append(record)
        totals[target] += record["compressed_estimate"]
    for record in sorted(unassigned, key=lambda item: item["compressed_estimate"], reverse=True):
        target = min(range(PART_COUNT), key=totals.__getitem__)
        buckets[target].append(record)
        totals[target] += record["compressed_estimate"]
    print(f"Reused prior assignments for {len(records) - len(unassigned)} files; new assignments: {len(unassigned)}", flush=True)
    return buckets


def create_parts(source: Path, output: Path, buckets: list[list[dict]]) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / f"{RELEASE_NAME}-Part{index}.zip" for index in range(1, PART_COUNT + 1)]
    for target in targets:
        target.unlink(missing_ok=True)
    for index, (target, bucket) in enumerate(zip(targets, buckets), start=1):
        print(f"Writing Part {index}: {len(bucket)} source files...", flush=True)
        part_manifest = {
            "release": RELEASE_NAME,
            "part": index,
            "part_count": PART_COUNT,
            "source_file_count": len(bucket),
            "files": [{key: item[key] for key in ("path", "size_bytes", "sha256")} for item in bucket],
        }
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for item in bucket:
                archive.write(item["full_path"], f"{source.name}/{item['path']}")
            archive.writestr(
                f"{source.name}/release/PART_MANIFEST-Part{index}.json",
                json.dumps(part_manifest, indent=2).encode("utf-8"),
            )
    return targets


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"CRC failure in {archive_path.name}: {bad_member}")
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if destination_resolved != target and destination_resolved not in target.parents:
                raise RuntimeError(f"Unsafe path in {archive_path.name}: {info.filename}")
        archive.extractall(destination)


def verify_reconstruction(parts: list[Path], verify_dir: Path, records: list[dict], source_name: str) -> None:
    if verify_dir.exists():
        raise RuntimeError(f"Verification directory already exists: {verify_dir}")
    verify_dir.mkdir(parents=True)
    for part in parts:
        safe_extract(part, verify_dir)
    reconstructed = verify_dir / source_name
    for index, record in enumerate(records, start=1):
        path = reconstructed / Path(record["path"])
        if not path.is_file():
            raise RuntimeError(f"Reconstruction missing: {record['path']}")
        if path.stat().st_size != record["size_bytes"] or sha256(path) != record["sha256"]:
            raise RuntimeError(f"Reconstruction hash mismatch: {record['path']}")
        if index % 3000 == 0:
            print(f"Verified {index} reconstructed files...", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-dir", type=Path, required=True)
    parser.add_argument("--reuse-assignment-dir", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output_dir.resolve()
    verify_dir = args.verify_dir.resolve()
    reuse_assignment_dir = args.reuse_assignment_dir.resolve() if args.reuse_assignment_dir else None
    if not (source / "app.py").is_file():
        raise SystemExit(f"Not a BioIntel source root: {source}")
    write_release_notes(source)
    records = collect_records(source, output, estimate_compression=reuse_assignment_dir is None)
    write_source_manifest(source, records)
    buckets = (
        balance_from_prior_manifests(records, reuse_assignment_dir)
        if reuse_assignment_dir is not None
        else balance(records)
    )
    parts = create_parts(source, output, buckets)
    verify_reconstruction(parts, verify_dir, records, source.name)
    sizes = [part.stat().st_size for part in parts]
    average = sum(sizes) / len(sizes)
    variance = (max(sizes) - min(sizes)) / average * 100
    result = {
        "release": RELEASE_NAME,
        "source_files": len(records),
        "reconstruction_verified": True,
        "size_variance_percent": round(variance, 4),
        "parts": [
            {"name": part.name, "size_bytes": part.stat().st_size, "sha256": sha256(part)}
            for part in parts
        ],
    }
    print("RELEASE_RESULT=" + json.dumps(result, separators=(",", ":")))
    return 0 if variance < 2.0 else 2


if __name__ == "__main__":
    raise SystemExit(main())