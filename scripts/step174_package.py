from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent.parent
BASE = "BioIntel-AI-Step174-PHASE1-TO-9-REAL-WORLD-QUALIFICATION"
ASSIGNMENT = ROOT / "STEP174_PACKAGE_PART_ASSIGNMENT.json"
SOURCE_MANIFEST = ROOT / "STEP174_SOURCE_MANIFEST_SHA256.json"
FIXED_DATE = (2026, 7, 14, 0, 0, 0)
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_files(*, include_assignment: bool = True) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if not include_assignment and path == ASSIGNMENT:
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def prior_mapping() -> dict[str, int]:
    mapping: dict[str, int] = {}
    for part in range(1, 5):
        path = OUT / f"BioIntel-AI-Step173-FINAL-ALL-MODULE-10OF10-Part{part}.zip"
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith("/") or not name.startswith("BioIntel-AI/"):
                    continue
                rel = name[len("BioIntel-AI/"):]
                mapping.setdefault(rel, part)
    return mapping


def prepare() -> dict:
    if ASSIGNMENT.exists():
        ASSIGNMENT.unlink()
    files_before = [path for path in release_files(include_assignment=False) if path != SOURCE_MANIFEST]
    source_entries = [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha_file(path), "size_bytes": path.stat().st_size}
        for path in files_before
    ]
    SOURCE_MANIFEST.write_text(json.dumps({
        "schema": "biointel.step174.source-manifest.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": source_entries,
        "excludes": [SOURCE_MANIFEST.name, ASSIGNMENT.name],
    }, indent=2) + "\n", encoding="utf-8")

    files = release_files(include_assignment=False)
    old = prior_mapping()
    sizes = {1: 0, 2: 0, 3: 0, 4: 0}
    assignments: dict[str, int] = {}
    new_files: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        forced_part = None
        if rel.startswith(".release_parts/step174_part") and rel.endswith(".ok"):
            try:
                forced_part = int(rel.split("step174_part", 1)[1].split(".ok", 1)[0])
            except (ValueError, IndexError):
                forced_part = None
        part = forced_part or old.get(rel)
        if part is None:
            part = min(sizes, key=sizes.get)
            new_files.append(rel)
        assignments[rel] = part
        sizes[part] += path.stat().st_size
    payload = {
        "schema": "biointel.step174.package-assignment.v1",
        "base": BASE,
        "root_prefix": "BioIntel-AI/",
        "file_count_excluding_assignment": len(assignments),
        "new_files": new_files,
        "part_uncompressed_bytes_excluding_assignment": sizes,
        "assignments": assignments,
    }
    ASSIGNMENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("schema", "file_count_excluding_assignment", "part_uncompressed_bytes_excluding_assignment")}, indent=2))
    return payload


def build_part(part: int) -> Path:
    payload = json.loads(ASSIGNMENT.read_text(encoding="utf-8"))
    assignments = payload["assignments"]
    members = [rel for rel, value in assignments.items() if int(value) == part]
    if part == 1:
        members.append(ASSIGNMENT.relative_to(ROOT).as_posix())
    members = sorted(set(members))
    output = OUT / f"{BASE}-Part{part}.zip"
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as zf:
        for rel in members:
            path = ROOT / rel
            if not path.is_file() or path.is_symlink():
                raise FileNotFoundError(path)
            arcname = f"BioIntel-AI/{rel}"
            info = zipfile.ZipInfo(arcname, FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, zf.open(info, "w", force_zip64=True) as target:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    target.write(chunk)
    print(json.dumps({"part": part, "members": len(members), "path": str(output), "size_bytes": output.stat().st_size, "sha256": sha_file(output)}, indent=2))
    return output


def verify() -> dict:
    expected = {path.relative_to(ROOT).as_posix(): sha_file(path) for path in release_files(include_assignment=True)}
    seen: dict[str, int] = {}
    crc_errors: list[str] = []
    unsafe: list[str] = []
    zip_hashes = {}
    for part in range(1, 5):
        path = OUT / f"{BASE}-Part{part}.zip"
        zip_hashes[path.name] = {"sha256": sha_file(path), "size_bytes": path.stat().st_size}
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                crc_errors.append(f"{path.name}:{bad}")
            for info in zf.infolist():
                name = info.filename
                pure = PurePosixPath(name)
                if name.startswith("/") or ".." in pure.parts or not name.startswith("BioIntel-AI/"):
                    unsafe.append(f"{path.name}:{name}")
                    continue
                if name.endswith("/"):
                    continue
                rel = name[len("BioIntel-AI/"):]
                seen[rel] = seen.get(rel, 0) + 1
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    duplicates = sorted(rel for rel, count in seen.items() if count != 1)
    report = {
        "schema": "biointel.step174.package-integrity.v1",
        "status": "passed" if not (missing or extra or duplicates or crc_errors or unsafe) else "failed",
        "source_files": len(expected),
        "packaged_files": len(seen),
        "missing": missing,
        "extra": extra,
        "duplicates": duplicates,
        "crc_errors": crc_errors,
        "unsafe_paths": unsafe,
        "zip_files": zip_hashes,
    }
    (OUT / f"{BASE}-CHECKSUMS.json").write_text(json.dumps({"schema": "biointel.step174.package-checksums.v1", "files": zip_hashes}, indent=2) + "\n", encoding="utf-8")
    (OUT / f"{BASE}-PACKAGE-INTEGRITY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--part", type=int, choices=(1, 2, 3, 4))
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(); return 0
    if args.part:
        build_part(args.part); return 0
    report = verify()
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
