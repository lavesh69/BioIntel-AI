from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist-release",
}
EXCLUDED_PREFIXES = (
    "reports/runtime_logs/",
    "reports/test-shards/",
    "reports/step87/tmp/",
    "reports/step88/tmp/",
    "reports/ui_profiles/",
)
EXCLUDED_FILENAMES = {"BUILD_PROVENANCE.json", ".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".wal", ".shm", ".bak", ".orig", ".rej"}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _included_files(root: Path) -> list[Path]:
    included: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if path.name in EXCLUDED_FILENAMES:
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if any(relative_text.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        included.append(path)
    return sorted(included, key=lambda item: item.relative_to(root).as_posix())


def build_provenance(root: Path) -> dict[str, Any]:
    epoch = int(os.getenv("SOURCE_DATE_EPOCH", "1577836800"))
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
            "size": path.stat().st_size,
            "executable": bool(path.stat().st_mode & 0o111),
        }
        for path in _included_files(root)
    ]
    return {
        "schema": "biointel.build-provenance.v2",
        "source_date_epoch": epoch,
        "created_utc": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(int(item["size"]) for item in files),
        "files": files,
    }


def _normalized_mode(path: Path) -> int:
    if path.suffix.lower() == ".sh" or bool(path.stat().st_mode & 0o111):
        return 0o755
    return 0o644


def build_reproducible_release(
    root: str | Path,
    output: str | Path,
    *,
    compresslevel: int = 9,
    uncompressed: bool = False,
) -> Path:
    if not 0 <= int(compresslevel) <= 9:
        raise ValueError("compresslevel must be between 0 and 9")
    source = Path(root).resolve()
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    provenance = build_provenance(source)
    provenance_bytes = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    archive_prefix = source.name.strip("/") + "/"
    compression = zipfile.ZIP_STORED if uncompressed else zipfile.ZIP_DEFLATED
    zip_kwargs: dict[str, Any] = {"compression": compression}
    if not uncompressed:
        zip_kwargs["compresslevel"] = compresslevel
    with zipfile.ZipFile(target, "w", **zip_kwargs) as archive:
        for path in _included_files(source):
            if path.resolve() == target:
                continue
            info = zipfile.ZipInfo(
                archive_prefix + path.relative_to(source).as_posix(), FIXED_ZIP_TIMESTAMP
            )
            info.external_attr = _normalized_mode(path) << 16
            write_kwargs: dict[str, Any] = {"compress_type": compression}
            if not uncompressed:
                write_kwargs["compresslevel"] = compresslevel
            archive.writestr(info, path.read_bytes(), **write_kwargs)
        info = zipfile.ZipInfo(archive_prefix + "BUILD_PROVENANCE.json", FIXED_ZIP_TIMESTAMP)
        info.external_attr = 0o644 << 16
        archive.writestr(info, provenance_bytes, **write_kwargs)
    return target


def verify_release_bundle(path: str | Path) -> dict[str, Any]:
    bundle = Path(path).resolve()
    failures: list[str] = []
    verified = 0
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        counts = Counter(names)
        duplicate_names = sorted(name for name, count in counts.items() if count > 1)
        infos = archive.infolist()
        stored_member_count = sum(info.compress_type == zipfile.ZIP_STORED for info in infos)
        compressed_member_count = len(infos) - stored_member_count
        bad = archive.testzip()
        unsafe_names = [
            name
            for name in names
            if name.startswith(("/", "\\")) or ".." in Path(name).parts
        ]
        provenance_members = [
            name
            for name in names
            if name.endswith("/BUILD_PROVENANCE.json") or name == "BUILD_PROVENANCE.json"
        ]
        if len(provenance_members) != 1:
            failures.append("provenance_member_count")
            provenance: dict[str, Any] = {"files": []}
            archive_prefix = ""
        else:
            provenance_member = provenance_members[0]
            provenance = json.loads(archive.read(provenance_member))
            archive_prefix = provenance_member[: -len("BUILD_PROVENANCE.json")]
        name_set = set(names)
        for item in provenance.get("files", []):
            member = archive_prefix + str(item["path"])
            if member not in name_set:
                failures.append(f"missing:{item['path']}")
                continue
            payload = archive.read(member)
            if len(payload) != int(item["size"]):
                failures.append(f"size:{item['path']}")
                continue
            if _sha256_bytes(payload) != str(item["sha256"]):
                failures.append(f"digest:{item['path']}")
                continue
            verified += 1
    valid = (
        bad is None
        and not duplicate_names
        and not unsafe_names
        and not failures
        and verified == len(provenance.get("files", []))
    )
    return {
        "valid": valid,
        "bad_member": bad,
        "duplicate_members": duplicate_names,
        "unsafe_members": unsafe_names,
        "provenance_schema": provenance.get("schema"),
        "provenance_file_count": len(provenance.get("files", [])),
        "verified_file_count": verified,
        "archive_member_count": len(names),
        "stored_member_count": stored_member_count,
        "compressed_member_count": compressed_member_count,
        "all_members_uncompressed": bool(names) and compressed_member_count == 0,
        "failures": failures[:100],
        "sha256": _sha256(bundle),
        "size_bytes": bundle.stat().st_size,
    }
