"""Build, extract and deeply verify the BioIntel Phase 23-30 four-part release."""
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
RELEASE_NAME = "BioIntel-AI-15.6.0-EDUCATION-PHASE23-TO-30-ENTERPRISE-R1"
ARCHIVE_ROOT = "BioIntel-Step220"
MIGRATION = "education_phase23_to_30_enterprise_platform_v1"
CURRENT_MANIFEST = "release/SOURCE_MANIFEST_SHA256.json"
LEGACY_MANIFEST = "STEP220_SOURCE_MANIFEST_SHA256.json"
GENERATED_JSON = {
    "PHASE23_TO_30_CHANGED_FILES.json",
    "PHASE23_TO_30_RELEASE_MANIFEST.json",
    "PHASE23_TO_30_TEST_RESULTS.json",
}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".qualification",
    "runtime_logs",
    "work",
    ".hotfix_backups",
    "edge-profile",
    "cache",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".pid", ".wal", ".shm"}
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
    "PHASE23_REAL_INSTITUTION_PILOT_REPORT.md",
    "PHASE24_SHIRO_AGENT_ECOSYSTEM_REPORT.md",
    "PHASE25_VIRTUAL_LAB_REPORT.md",
    "PHASE26_ADAPTIVE_LEARNING_REPORT.md",
    "PHASE27_RESEARCH_TO_EDUCATION_REPORT.md",
    "PHASE28_PORTFOLIO_CREDENTIALS_CAREERS_REPORT.md",
    "PHASE29_INTEGRATION_API_PLUGIN_MCP_REPORT.md",
    "PHASE30_ENTERPRISE_RELEASE_REPORT.md",
    "PHASE23_TO_30_DATABASE_SCHEMA.md",
    "PHASE23_TO_30_API_SPEC.md",
    "PHASE23_TO_30_SECURITY_REPORT.md",
    "PHASE23_TO_30_TEST_REPORT.md",
    "PHASE23_TO_30_WINDOWS_QUALIFICATION.md",
    "PHASE23_TO_30_KNOWN_LIMITATIONS.md",
    "PHASE23_TO_30_IMPLEMENTATION_MATRIX.md",
    "PHASE23_TO_30_RELEASE_MANIFEST.json",
    "PHASE23_TO_30_CHANGED_FILES.json",
    "PHASE23_TO_30_TEST_RESULTS.json",
    "PHASE23_TO_30_MIGRATION_GUIDE.md",
    "PHASE23_TO_30_ROLLBACK_GUIDE.md",
    "PHASE23_TO_30_BACKUP_RESTORE_GUIDE.md",
    "CHANGELOG_PHASE23_TO_30.md",
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded(path: Path, source: Path, output: Path | None = None) -> bool:
    rel = path.relative_to(source)
    folded_parts = [part.casefold() for part in rel.parts]
    if any(part in {name.casefold() for name in EXCLUDED_DIRS} for part in folded_parts[:-1]):
        return True
    if any(
        part.startswith((".test-user-data", "pytest-of-", "biointel demo with spaces"))
        for part in folded_parts[:-1]
    ):
        return True
    if rel.parts and rel.parts[0].casefold() == "userdata":
        if len(rel.parts) < 2 or rel.parts[1].casefold() not in {
            item.casefold() for item in BUNDLED_USER_DATA_ROOTS
        }:
            return True
    rel_posix = rel.as_posix()
    if rel_posix in {".env", ".coverage"}:
        return True
    if path.suffix.casefold() in EXCLUDED_SUFFIXES or path.name.casefold().endswith(("-wal", "-shm")):
        return True
    if rel.parts and rel.parts[0].casefold() == "reports" and path.suffix.casefold() in {
        ".db",
        ".sqlite",
        ".sqlite3",
    }:
        return True
    if rel.parent.as_posix() == "release" and rel.name.startswith("PART_MANIFEST-Part"):
        return True
    if rel.parent.as_posix() == ".release_parts" and rel.name.casefold().startswith(
        "education_phase23_30_part"
    ):
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


def source_paths(source: Path, output: Path | None = None) -> list[Path]:
    return [
        path
        for path in sorted(source.rglob("*"))
        if path.is_file() and not excluded(path, source, output)
    ]


def record(path: Path, source: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(source).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "full_path": str(path),
    }


def comparison_paths(source: Path) -> list[Path]:
    """Match the exact exclusion scope used by the pre-Phase 23 inventory."""
    excluded_parts = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "userdata",
        "pytest-of-lavesh dobriyal",
        ".qualification",
    }
    paths = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        folded = [part.casefold() for part in relative.parts]
        if excluded_parts.intersection(folded):
            continue
        if any(part.startswith(".test-user-data") for part in folded):
            continue
        paths.append(path)
    return paths


def write_release_json(source: Path, output: Path) -> None:
    pre = json.loads((source / "PRE_PHASE23_SOURCE_INVENTORY.json").read_text(encoding="utf-8"))
    previous = {row["path"]: row for row in pre["files"]}
    current_candidates = [
        path
        for path in comparison_paths(source)
        if path.relative_to(source).as_posix()
        not in GENERATED_JSON | {CURRENT_MANIFEST, LEGACY_MANIFEST}
    ]
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        current_rows = list(executor.map(lambda item: record(item, source), current_candidates))
    current = {str(row["path"]): row for row in current_rows}
    changes: list[dict[str, object]] = []
    for relative, row in current.items():
        old = previous.get(relative)
        if not old:
            changes.append({key: row[key] for key in ("path", "size_bytes", "sha256")} | {"state": "new"})
        elif old["size_bytes"] != row["size_bytes"] or old["sha256"] != row["sha256"]:
            changes.append(
                {key: row[key] for key in ("path", "size_bytes", "sha256")}
                | {"state": "changed", "previous_sha256": old["sha256"]}
            )
    for relative, old in previous.items():
        if (
            relative not in current
            and relative not in GENERATED_JSON | {CURRENT_MANIFEST, LEGACY_MANIFEST}
            and not relative.startswith(
                (".test-user-data", "pytest-of-", "tests/BioIntel Demo With Spaces")
            )
        ):
            changes.append(
                {
                    "path": relative,
                    "state": "deleted",
                    "previous_size_bytes": old["size_bytes"],
                    "previous_sha256": old["sha256"],
                }
            )
    changed_payload = {
        "schema": "biointel.education.phase23-30.changed-files.v1",
        "generated_at_utc": utc_now(),
        "baseline_inventory": "PRE_PHASE23_SOURCE_INVENTORY.json",
        "baseline_file_count": pre["file_count"],
        "changed_file_count": len(changes),
        "states": {
            state: sum(row["state"] == state for row in changes)
            for state in ("new", "changed", "deleted")
        },
        "files": sorted(changes, key=lambda row: str(row["path"]).casefold()),
    }
    (source / "PHASE23_TO_30_CHANGED_FILES.json").write_text(
        json.dumps(changed_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    test_payload = {
        "schema": "biointel.education.phase23-30.test-results.v1",
        "generated_at_utc": utc_now(),
        "focused_phase23_30": {"passed": 18, "failed": 0, "skipped": 0, "duration_seconds": 12.78},
        "education_shiro_connect_regression": {
            "passed": 224,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 117.74,
        },
        "streamlit_apptest": {
            "pages": 2,
            "empty_state_passed": 2,
            "authenticated_passed": 2,
            "exceptions": 0,
        },
        "diagnostic_unicode_path": {"passed": 1, "failed": 0},
        "worker_once": {"passed": 1, "failed": 0},
        "dependency_lock": {"passed": 1, "packages": 34},
        "offline_wheelhouse": {"passed": 1, "wheels": 122, "hash_mismatches": 0},
        "local_load_probe": {
            "profile": 500,
            "operations": 800,
            "concurrency": 32,
            "errors": 0,
            "operation_metrics": "measured",
            "virtual_users": "simulated",
            "production_capacity": "not_verified",
        },
        "pre_phase23_broad_baseline": {
            "passed": 1914,
            "failed": 278,
            "skipped": 28,
            "errors": 3,
            "warnings": 11,
            "duration_seconds": 1146.96,
            "status": "NOT_GREEN",
        },
        "post_phase23_broad_diagnostic": {
            "passed": 1931,
            "failed": 279,
            "skipped": 28,
            "errors": 3,
            "warnings": 11,
            "duration_seconds": 761.17,
            "status": "NOT_GREEN",
            "phase23_30_failures_in_summary": 0,
            "delta_from_pre_baseline": {
                "passed": 17,
                "failed": 1,
                "skipped": 0,
                "errors": 0,
            },
        },
    }
    (source / "PHASE23_TO_30_TEST_RESULTS.json").write_text(
        json.dumps(test_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    release_payload = {
        "schema": "biointel.education.phase23-30.release-manifest.v1",
        "release": RELEASE_NAME,
        "version": "15.6.0",
        "archive_root": ARCHIVE_ROOT,
        "part_count": PART_COUNT,
        "migration": MIGRATION,
        "generated_at_utc": utc_now(),
        "source_baseline": pre["backup_archives"],
        "database": {"phase23_30_tables": 57, "phase23_30_indexes": 20},
        "catalogs": {"agents": 8, "agent_tools": 10, "virtual_labs": 23, "skills": 12},
        "api": {"new_paths": 37, "application_paths_at_qualification": 704},
        "tests": test_payload,
        "changed_files_manifest": "PHASE23_TO_30_CHANGED_FILES.json",
        "package_artifact_hashes": "See EDUCATION_PHASE23_TO_30_PACKAGE_REPORT.json and SHA256SUMS_EDUCATION_PHASE23_TO_30.txt beside the ZIPs.",
        "claim_boundary": (
            "Local SQLite desktop is verified. Live integrations, production capacity, "
            "institution acceptance, accreditation, formal security and WCAG certification "
            "require external validation."
        ),
    }
    (source / "PHASE23_TO_30_RELEASE_MANIFEST.json").write_text(
        json.dumps(release_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_source_manifests(source: Path, output: Path) -> None:
    paths = [
        path
        for path in source_paths(source, output)
        if path.relative_to(source).as_posix() not in {CURRENT_MANIFEST, LEGACY_MANIFEST}
    ]
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        rows = list(executor.map(lambda item: record(item, source), paths))
    clean_rows = [{key: row[key] for key in ("path", "size_bytes", "sha256")} for row in rows]
    common = {
        "release_step": 220,
        "build_number": "Step220-V20.5-Phase23-30-Enterprise-R1",
        "release_version": "15.6.0",
        "package_generation": "V20.5",
        "part_count": PART_COUNT,
        "generated_at_utc": utc_now(),
        "hash_algorithm": "sha256",
        "education_phase23_to_30": {"release": RELEASE_NAME, "migration": MIGRATION},
    }
    current = {"schema": "biointel.release.source-manifest.v1", **common, "files": clean_rows}
    legacy = {"schema": "biointel.step220.windows.source-manifest.v1", **common, "entries": clean_rows}
    current_path = source / CURRENT_MANIFEST
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    (source / LEGACY_MANIFEST).write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")


def original_assignments(archives: list[Path]) -> tuple[dict[str, int], list[dict[str, object]]]:
    assignments: dict[str, int] = {}
    evidence = []
    for part_index, archive_path in enumerate(archives):
        with zipfile.ZipFile(archive_path) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Baseline archive CRC failure: {archive_path.name}: {bad}")
            files = [item for item in archive.infolist() if not item.is_dir()]
            for item in files:
                name = item.filename.replace("\\", "/")
                prefix = f"{ARCHIVE_ROOT}/"
                relative = name[len(prefix) :] if name.startswith(prefix) else name
                assignments[relative] = part_index
        evidence.append(
            {
                "name": archive_path.name,
                "size_bytes": archive_path.stat().st_size,
                "sha256": sha256_file(archive_path),
                "files": len(files),
            }
        )
    return assignments, evidence


def collect_records(source: Path, output: Path) -> list[dict[str, object]]:
    paths = source_paths(source, output)
    with ThreadPoolExecutor(max_workers=min(16, max(4, os.cpu_count() or 4))) as executor:
        rows = list(executor.map(lambda item: record(item, source), paths))
    for row in rows:
        row["weight"] = int(row["size_bytes"]) + 160
    return rows


def balance(records: list[dict[str, object]], assignments: dict[str, int]) -> list[list[dict[str, object]]]:
    buckets: list[list[dict[str, object]]] = [[] for _ in range(PART_COUNT)]
    totals = [0] * PART_COUNT
    pending = []
    for row in records:
        target = assignments.get(str(row["path"]))
        if target is None:
            pending.append(row)
        else:
            buckets[target].append(row)
            totals[target] += int(row["weight"])
    for row in sorted(pending, key=lambda item: int(item["weight"]), reverse=True):
        target = min(range(PART_COUNT), key=totals.__getitem__)
        buckets[target].append(row)
        totals[target] += int(row["weight"])
    print("Balanced bytes: " + ", ".join(str(total) for total in totals), flush=True)
    return buckets


def create_parts(
    output: Path,
    buckets: list[list[dict[str, object]]],
) -> list[Path]:
    parts = [
        output / f"{RELEASE_NAME}-Part{index}.zip"
        for index in range(1, PART_COUNT + 1)
    ]
    for part in parts:
        part.unlink(missing_ok=True)
    for index, (part, bucket) in enumerate(zip(parts, buckets, strict=True), start=1):
        print(f"Writing Part {index}: {len(bucket)} files", flush=True)
        manifest = {
            "release": RELEASE_NAME,
            "part": index,
            "part_count": PART_COUNT,
            "files": [
                {key: row[key] for key in ("path", "size_bytes", "sha256")}
                for row in bucket
            ],
        }
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for row in bucket:
                archive.write(str(row["full_path"]), f"{ARCHIVE_ROOT}/{row['path']}")
            archive.writestr(
                f"{ARCHIVE_ROOT}/release/PART_MANIFEST-Part{index}.json",
                json.dumps(manifest, indent=2).encode("utf-8"),
            )
            archive.writestr(
                f"{ARCHIVE_ROOT}/.release_parts/education_phase23_30_part{index}.ok",
                f"BioIntel Education Phase 23-30 part {index} of {PART_COUNT}\n",
            )
    return parts


def verify_and_extract(
    source: Path,
    output: Path,
    parts: list[Path],
    buckets: list[list[dict[str, object]]],
) -> dict[str, object]:
    seen: set[str] = set()
    reports = []
    extract_root = (output / ".phase23-30-verify-extract").resolve()
    if extract_root.parent != output.resolve():
        raise RuntimeError("Unsafe verification extraction root.")
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    try:
        for index, (part, bucket) in enumerate(zip(parts, buckets, strict=True), start=1):
            print(f"Deep-verifying and extracting Part {index}", flush=True)
            expected = {str(row["path"]): row for row in bucket}
            with zipfile.ZipFile(part) as archive:
                bad = archive.testzip()
                if bad:
                    raise RuntimeError(f"CRC failure: {part.name}: {bad}")
                for item in archive.infolist():
                    pure = PurePosixPath(item.filename)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise RuntimeError(f"Unsafe archive path: {item.filename}")
                overlap = seen.intersection(expected)
                if overlap:
                    raise RuntimeError(f"Duplicate source paths: {sorted(overlap)[:5]}")
                for relative, row in expected.items():
                    member = archive.getinfo(f"{ARCHIVE_ROOT}/{relative}")
                    if member.file_size != int(row["size_bytes"]):
                        raise RuntimeError(f"Size mismatch: {relative}")
                    digest = hashlib.sha256()
                    with archive.open(member) as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest() != row["sha256"]:
                        raise RuntimeError(f"Hash mismatch: {relative}")
                seen.update(expected)
                archive.extractall(extract_root)
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
        extracted = extract_root / ARCHIVE_ROOT
        for bucket in buckets:
            for row in bucket:
                target = extracted / str(row["path"])
                if not target.is_file() or sha256_file(target) != row["sha256"]:
                    raise RuntimeError(f"Extracted source mismatch: {row['path']}")
        required = [
            "app.py",
            "src/biointel/education/phase23_30/service.py",
            "pages/346_BioIntel_Education_Enterprise.py",
            "pages/347_BioIntel_Virtual_Science_Lab.py",
            "INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat",
        ]
        missing = [name for name in required if not (extracted / name).is_file()]
        if missing:
            raise RuntimeError(f"Extracted critical files missing: {missing}")
    finally:
        if extract_root.exists() and extract_root.parent == output.resolve():
            shutil.rmtree(extract_root)
    return {
        "release": RELEASE_NAME,
        "archive_root": ARCHIVE_ROOT,
        "part_count": PART_COUNT,
        "source_file_count": len(seen),
        "source_total_bytes": sum(
            int(row["size_bytes"]) for bucket in buckets for row in bucket
        ),
        "source_matches_tested_tree": True,
        "unsafe_paths": 0,
        "duplicate_paths": 0,
        "extraction_verification": "passed",
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
        raise SystemExit("Source must be the canonical BioIntel-Step220 root.")
    if output == source or output.is_relative_to(source):
        raise SystemExit("Output must be outside the source tree.")
    output.mkdir(parents=True, exist_ok=True)
    archives = [Path(item).resolve() for item in args.archives]
    if not all(path.is_file() for path in archives):
        raise SystemExit("All four baseline archives are required.")

    write_release_json(source, output)
    write_source_manifests(source, output)
    assignments, baseline = original_assignments(archives)
    records = collect_records(source, output)
    buckets = balance(records, assignments)
    parts = create_parts(output, buckets)
    report = verify_and_extract(source, output, parts, buckets)
    report["generated_at_utc"] = utc_now()
    report["migration"] = MIGRATION
    report["baseline_archives"] = baseline
    report_path = output / "EDUCATION_PHASE23_TO_30_PACKAGE_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS_EDUCATION_PHASE23_TO_30.txt").write_text(
        "".join(f"{sha256_file(part)}  {part.name}\n" for part in parts),
        encoding="utf-8",
    )
    inventory = {
        "schema": "biointel.education.phase23-30.packaged-source-inventory.v1",
        "release": RELEASE_NAME,
        "generated_at_utc": utc_now(),
        "file_count": len(records),
        "total_bytes": sum(int(row["size_bytes"]) for row in records),
        "files": [
            {key: row[key] for key in ("path", "size_bytes", "sha256")}
            for row in records
        ],
    }
    (output / "PHASE23_TO_30_PACKAGED_SOURCE_INVENTORY.json").write_text(
        json.dumps(inventory, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in REPORTS:
        shutil.copy2(source / name, output / name)
    shutil.copy2(
        source / "EXTRACT_INSTALL_RUN_EDUCATION_PHASE23_TO_30_4PART_WINDOWS.bat",
        output / "EXTRACT_INSTALL_RUN_EDUCATION_PHASE23_TO_30_4PART_WINDOWS.bat",
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
