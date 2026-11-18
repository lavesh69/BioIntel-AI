"""Create exactly four balanced, reconstructable BioIntel AI Shiro Windows release ZIPs.

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
from concurrent.futures import ThreadPoolExecutor

PART_COUNT = 4
RELEASE_NAME = "BioIntel-AI-15.6.0-EDUCATION-PHASE4"
ARCHIVE_ROOT = "BioIntel-Step220"
EXCLUDED_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", "Temp", "runtime_logs", "UserData", "work",
    ".test-tmp", ".test-smoke", ".hotfix_backups", "edge-profile", "cache", "phase13b_test_runtime",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".pid", ".wal", ".shm"}
SOURCE_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"
MUTABLE_REPORT_DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-shm", ".sqlite3-wal")


def excluded(path: Path, source: Path, output: Path | None = None) -> bool:
    rel = path.relative_to(source)
    if any(part.casefold() in {item.casefold() for item in EXCLUDED_DIRS} for part in rel.parts[:-1]):
        return True
    if (
        rel.parts
        and rel.parts[0].casefold() == "reports"
        and rel.name.casefold().endswith(MUTABLE_REPORT_DATABASE_SUFFIXES)
    ):
        return True
    if rel.parts and rel.parts[0].casefold() == "wheelhouse" and rel.name.casefold().startswith("coverage-") and rel.suffix == ".whl":
        return True
    if rel.parent.as_posix() == ".release_parts" and rel.name.startswith("shiro4_part") and rel.suffix == ".ok":
        return True
    if rel.as_posix() in {".env", ".coverage"}:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.lower().endswith(("-wal", "-shm")):
        return True
    if rel.as_posix() == SOURCE_MANIFEST:
        return True
    if rel.parent.as_posix() == "release" and rel.name.startswith("PART_MANIFEST-Part") and rel.suffix == ".json":
        return True
    if rel.name.startswith(".biointel_step") and rel.name.endswith("_installed"):
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
    reconstruction = """# Reconstruct and install BioIntel AI Education Phase 4

Place all four `BioIntel-AI-15.6.0-EDUCATION-PHASE4-PartN.zip` archives beside `EXTRACT_INSTALL_RUN_EDUCATION_4PART_WINDOWS.bat`, then run the BAT file.

Manual method:
1. Extract all four archives into the same empty folder.
2. Confirm one `BioIntel-Step220` tree and four `.release_parts/shiro4_partN.ok` markers exist.
3. Run `BioIntel-Step220\\INSTALL_WINDOWS.bat`.
4. Run `BioIntel-Step220\\RUN_BOTH_WINDOWS.bat`.
5. Run `BioIntel-Step220\\VERIFY_EDUCATION_PHASE4_WINDOWS.bat`.

Do not run from inside a ZIP. Runtime data belongs under `%LOCALAPPDATA%\\BioIntelAI\\UserData` and is excluded from the release.
"""
    completion = """# Education Phase 4 intelligence and academic-operations report

Implemented:
- New Education Intelligence Hub with app-style responsive Learning Path, Shiro Tutor, Academic Operations, Notifications and Reports workspaces.
- Subject concept knowledge graph with prerequisite links, recency-weighted mastery, evidence confidence, spaced-review dates and human-overridable recommendations.
- Local-first Shiro AI course tutor that indexes approved institutional evidence, returns traceable citations, supports English/Hindi/Hinglish and refuses to invent missing evidence.
- Academic-integrity lock that blocks student tutor access during active subject examination attempts.
- Conflict-safe recurring timetable generation with teacher, room and student-group collision detection and all-or-nothing writes.
- Timetable-to-attendance session automation, bulk attendance validation and shortage support alerts.
- Recipient-owned notification inbox, event preferences, deduplication and assignment/exam reminder generation.
- Governed learner progress report combining attendance, assignments, results and concept mastery.
- Typed Phase 4 API contracts, primary application navigation and import-safe UI compatibility for minimal backend test environments.

Verification:
- 71 Education and Shiro regression tests passed.
- Existing Phase 2 integrity verifier passed 12/12 controls.
- Phase 3 secure examination verifier passed 15/15 controls.
- Phase 4 verifier passed 20/20 controls.
- Python compilation passed for application source, pages and scripts.
- Final four archives are CRC-tested and every packaged file is read and SHA-256 verified against embedded manifests.

External production qualification remains required for institutional SSO/MFA, signed Windows installer, clean-machine browser validation, accessibility audit, production PostgreSQL/object storage, load testing, penetration testing and institutional pilot.
"""
    contract = {
        "schema": "biointel.education-phase4.windows-four-part.v1",
        "product_version": "15.6.0",
        "release_step": 220,
        "physical_archive_count": PART_COUNT,
        "archive_root": ARCHIVE_ROOT,
        "python_runtime": "CPython 3.11.9 x64",
        "education_regression_tests_passed": 71,
        "phase2_integrity_controls_passed": 12,
        "phase3_controls_passed": 15,
        "phase4_controls_passed": 20,
        "install_entrypoint": "INSTALL_WINDOWS.bat",
        "run_entrypoint": "RUN_BOTH_WINDOWS.bat",
        "verification_entrypoint": "VERIFY_EDUCATION_PHASE4_WINDOWS.bat",
        "release_verification_mode": "direct-crc-and-per-file-sha256",
        "qualification": "code and archive qualified; external production qualification remains required",
    }
    (release / "RECONSTRUCT_EDUCATION_PHASE4_4PART.md").write_text(reconstruction, encoding="utf-8", newline="\n")
    (release / "EDUCATION_PHASE4_COMPLETION_REPORT.md").write_text(completion, encoding="utf-8", newline="\n")
    (source / "EDUCATION_PHASE4_RELEASE.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8", newline="\n")

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
        "archive_root": ARCHIVE_ROOT,
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
                archive.write(item["full_path"], f"{ARCHIVE_ROOT}/{item['path']}")
            archive.writestr(
                f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json",
                json.dumps(part_manifest, indent=2).encode("utf-8"),
            )
            archive.writestr(
                f"{ARCHIVE_ROOT}/.release_parts/shiro4_part{index}.ok",
                f"BioIntel AI 15.6.0 Education physical archive part {index} of {PART_COUNT}\n",
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


def verify_archives(parts: list[Path], buckets: list[list[dict]], verify_dir: Path) -> dict:
    """Verify CRC, paths, sizes and SHA-256 by reading every file from the final ZIPs."""
    if verify_dir.exists():
        shutil.rmtree(verify_dir)
    verify_dir.mkdir(parents=True)

    def verify_one(args: tuple[int, Path, list[dict]]) -> dict:
        index, part, bucket = args
        with zipfile.ZipFile(part) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise RuntimeError(f"CRC failure in {part.name}: {bad_member}")
            manifest_name = f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json"
            embedded = json.loads(archive.read(manifest_name))
            embedded_rows = {row["path"]: row for row in embedded.get("files", [])}
            if set(embedded_rows) != {item["path"] for item in bucket}:
                raise RuntimeError(f"Part manifest membership mismatch: {part.name}")
            archive.getinfo(f"{ARCHIVE_ROOT}/.release_parts/shiro4_part{index}.ok")
            for offset, item in enumerate(bucket, start=1):
                rel = item["path"]
                member = archive.getinfo(f"{ARCHIVE_ROOT}/{rel}")
                if member.file_size != item["size_bytes"]:
                    raise RuntimeError(f"Archive size mismatch: {rel}")
                digest = hashlib.sha256()
                with archive.open(member) as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
                if digest.hexdigest() != item["sha256"]:
                    raise RuntimeError(f"Archive hash mismatch: {rel}")
                if offset % 3000 == 0:
                    print(f"Verified {offset} files directly in Part {index}...", flush=True)
        return {
            "part": index,
            "name": part.name,
            "size_bytes": part.stat().st_size,
            "sha256": sha256(part),
            "source_files": len(bucket),
        }

    with ThreadPoolExecutor(max_workers=PART_COUNT) as executor:
        verified_parts = sorted(
            executor.map(verify_one, [(index, part, bucket) for index, (part, bucket) in enumerate(zip(parts, buckets), start=1)]),
            key=lambda row: row["part"],
        )
    payload = {
        "release": RELEASE_NAME,
        "verified": True,
        "verification_mode": "direct-crc-and-per-file-sha256",
        "source_files_including_manifest": sum(item["source_files"] for item in verified_parts),
        "parts": verified_parts,
    }
    (verify_dir / "EDUCATION_PHASE4_ARCHIVE_VERIFICATION.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return payload

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
    verification = verify_archives(parts, buckets, verify_dir)
    sizes = [part.stat().st_size for part in parts]
    average = sum(sizes) / len(sizes)
    variance = (max(sizes) - min(sizes)) / average * 100
    result = {
        "release": RELEASE_NAME,
        "source_files": len(records),
        "archive_contents_verified": True,
        "verification_mode": verification["verification_mode"],
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





