from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[2]
BASE = "BioIntel-AI-Step177-21-MODULE-MODEL-COHORT-RUNTIME-10OF10-INTERNAL"
ASSIGNMENT = ROOT / "STEP177_PACKAGE_PART_ASSIGNMENT.json"
SOURCE_MANIFEST = ROOT / "STEP177_SOURCE_MANIFEST_SHA256.json"
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
        path = OUT / f"BioIntel-AI-Step176-17-MODULE-OPERATIONAL-10OF10-INTERNAL-Part{part}.zip"
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith("/") or not name.startswith("BioIntel-AI/"):
                    continue
                mapping.setdefault(name[len("BioIntel-AI/"):], part)
    return mapping


def prepare() -> dict:
    ASSIGNMENT.unlink(missing_ok=True)
    SOURCE_MANIFEST.unlink(missing_ok=True)
    files_before = release_files(include_assignment=False)
    entries = []
    for path in files_before:
        rel = path.relative_to(ROOT).as_posix()
        entries.append({"path": rel, "sha256": sha_file(path), "size_bytes": path.stat().st_size})
    SOURCE_MANIFEST.write_text(json.dumps({
        "schema": "biointel.step177.source-manifest.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
        "excludes": [ASSIGNMENT.name],
    }, indent=2) + "\n", encoding="utf-8")

    files = release_files(include_assignment=False)
    old = prior_mapping()
    sizes = {1: 0, 2: 0, 3: 0, 4: 0}
    assignments: dict[str, int] = {}
    new_files: list[str] = []
    # First account for files retaining their Step 176 part.
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        part = old.get(rel)
        if part is not None:
            assignments[rel] = part
            sizes[part] += path.stat().st_size
    # Then place new files in the currently smallest part, except explicit markers.
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel in assignments:
            continue
        forced = None
        if rel.startswith(".release_parts/step177_part") and rel.endswith(".ok"):
            forced = int(rel.split("step177_part", 1)[1].split(".ok", 1)[0])
        part = forced or min(sizes, key=sizes.get)
        assignments[rel] = part
        sizes[part] += path.stat().st_size
        new_files.append(rel)
    payload = {
        "schema": "biointel.step177.package-assignment.v1",
        "base": BASE,
        "root_prefix": "BioIntel-AI/",
        "file_count_excluding_assignment": len(assignments),
        "new_files": new_files,
        "part_uncompressed_bytes_excluding_assignment": sizes,
        "assignments": assignments,
    }
    ASSIGNMENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": payload["schema"],
        "file_count": len(assignments),
        "new_files": len(new_files),
        "part_uncompressed_bytes": sizes,
    }, indent=2))
    return payload


def build_part(part: int) -> Path:
    payload = json.loads(ASSIGNMENT.read_text(encoding="utf-8"))
    members = [rel for rel, value in payload["assignments"].items() if int(value) == part]
    if part == 1:
        members.append(ASSIGNMENT.relative_to(ROOT).as_posix())
    output = OUT / f"{BASE}-Part{part}.zip"
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for rel in sorted(set(members)):
            path = ROOT / rel
            if not path.is_file() or path.is_symlink():
                raise FileNotFoundError(path)
            info = zipfile.ZipInfo(f"BioIntel-AI/{rel}", FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, zf.open(info, "w", force_zip64=True) as target:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    target.write(chunk)
    print(json.dumps({"part": part, "path": str(output), "size_bytes": output.stat().st_size, "sha256": sha_file(output)}, indent=2))
    return output


def verify() -> dict:
    expected = {p.relative_to(ROOT).as_posix() for p in release_files(include_assignment=True)}
    seen: dict[str, int] = {}
    crc_errors: list[str] = []
    unsafe: list[str] = []
    zip_hashes: dict[str, dict[str, object]] = {}
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
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    duplicates = sorted(rel for rel, count in seen.items() if count != 1)
    report = {
        "schema": "biointel.step177.package-integrity.v1",
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
    (OUT / f"{BASE}-CHECKSUMS.json").write_text(json.dumps({"schema": "biointel.step177.package-checksums.v1", "files": zip_hashes}, indent=2) + "\n", encoding="utf-8")
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
    return 0 if verify()["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
