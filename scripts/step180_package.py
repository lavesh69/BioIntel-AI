from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[2]
BASE = "BioIntel-AI-Step180-FINAL-5-SCIENTIFIC-MODULES-80OF80-INTERNAL-10OF10"
ASSIGNMENT = ROOT / "STEP180_PACKAGE_PART_ASSIGNMENT.json"
SOURCE_MANIFEST = ROOT / "STEP180_SOURCE_MANIFEST_SHA256.json"
FIXED_DATE = (2026, 7, 14, 0, 0, 0)
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_files(include_assignment: bool = True) -> list[Path]:
    rows: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts) or path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if not include_assignment and path == ASSIGNMENT:
            continue
        rows.append(path)
    return sorted(rows, key=lambda item: item.relative_to(ROOT).as_posix())


def prior_mapping() -> dict[str, int]:
    result: dict[str, int] = {}
    previous = "BioIntel-AI-Step179-18-PLATFORM-CORE-PRODUCTION-ASSURANCE-10OF10-INTERNAL"
    for part in range(1, 5):
        path = OUT / f"{previous}-Part{part}.zip"
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith("/") or not name.startswith("BioIntel-AI/"):
                    continue
                result.setdefault(name[len("BioIntel-AI/") :], part)
    return result


def prepare() -> dict[str, object]:
    ASSIGNMENT.unlink(missing_ok=True)
    SOURCE_MANIFEST.unlink(missing_ok=True)
    entries = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in release_files(False)
    ]
    SOURCE_MANIFEST.write_text(
        json.dumps(
            {
                "schema": "biointel.step180.source-manifest.v1",
                "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "entries": entries,
                "excludes": [ASSIGNMENT.name],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    files = release_files(False)
    old = prior_mapping()
    sizes = {1: 0, 2: 0, 3: 0, 4: 0}
    assignments: dict[str, int] = {}
    new_files: list[str] = []

    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        part = old.get(relative)
        if part is not None:
            assignments[relative] = part
            sizes[part] += path.stat().st_size

    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative in assignments:
            continue
        forced = None
        if relative.startswith(".release_parts/step180_part") and relative.endswith(".ok"):
            forced = int(relative.split("step180_part", 1)[1].split(".ok", 1)[0])
        part = forced or min(sizes, key=sizes.get)
        assignments[relative] = part
        sizes[part] += path.stat().st_size
        new_files.append(relative)

    payload = {
        "schema": "biointel.step180.package-assignment.v1",
        "base": BASE,
        "root_prefix": "BioIntel-AI/",
        "file_count_excluding_assignment": len(assignments),
        "new_files": new_files,
        "part_uncompressed_bytes_excluding_assignment": sizes,
        "assignments": assignments,
    }
    ASSIGNMENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": len(assignments), "new_files": len(new_files), "sizes": sizes}, indent=2))
    return payload


def build_part(part: int) -> Path:
    payload = json.loads(ASSIGNMENT.read_text(encoding="utf-8"))
    members = [relative for relative, assigned in payload["assignments"].items() if int(assigned) == part]
    if part == 1:
        members.append(ASSIGNMENT.relative_to(ROOT).as_posix())
    output = OUT / f"{BASE}-Part{part}.zip"
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for relative in sorted(set(members)):
            path = ROOT / relative
            if not path.is_file() or path.is_symlink():
                raise FileNotFoundError(path)
            info = zipfile.ZipInfo(f"BioIntel-AI/{relative}", FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    destination.write(chunk)
    print(
        json.dumps(
            {"part": part, "path": str(output), "size_bytes": output.stat().st_size, "sha256": sha_file(output)},
            indent=2,
        )
    )
    return output


def verify() -> dict[str, object]:
    expected = {path.relative_to(ROOT).as_posix() for path in release_files(True)}
    seen: dict[str, int] = {}
    crc_errors: list[str] = []
    unsafe_paths: list[str] = []
    hashes: dict[str, dict[str, object]] = {}

    for part in range(1, 5):
        path = OUT / f"{BASE}-Part{part}.zip"
        hashes[path.name] = {"sha256": sha_file(path), "size_bytes": path.stat().st_size}
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                crc_errors.append(f"{path.name}:{bad}")
            for info in archive.infolist():
                name = info.filename
                pure = PurePosixPath(name)
                if name.startswith("/") or ".." in pure.parts or not name.startswith("BioIntel-AI/"):
                    unsafe_paths.append(f"{path.name}:{name}")
                    continue
                if name.endswith("/"):
                    continue
                relative = name[len("BioIntel-AI/") :]
                seen[relative] = seen.get(relative, 0) + 1

    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    duplicates = sorted(relative for relative, count in seen.items() if count != 1)
    status = "passed" if not (missing or extra or duplicates or crc_errors or unsafe_paths) else "failed"
    report = {
        "schema": "biointel.step180.package-integrity.v1",
        "status": status,
        "source_files": len(expected),
        "packaged_files": len(seen),
        "missing": missing,
        "extra": extra,
        "duplicates": duplicates,
        "crc_errors": crc_errors,
        "unsafe_paths": unsafe_paths,
        "zip_files": hashes,
    }
    (OUT / f"{BASE}-CHECKSUMS.json").write_text(
        json.dumps({"schema": "biointel.step180.package-checksums.v1", "files": hashes}, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / f"{BASE}-PACKAGE-INTEGRITY.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--part", type=int, choices=(1, 2, 3, 4))
    group.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    if arguments.prepare:
        prepare()
        return 0
    if arguments.part:
        build_part(arguments.part)
        return 0
    return 0 if verify()["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
