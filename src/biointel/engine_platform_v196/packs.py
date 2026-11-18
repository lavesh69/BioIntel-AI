from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import contained_path

MANIFEST_NAME = "BIOINTEL_ENGINE_PACK.json"
MAX_FILES = 200_000
MAX_UNCOMPRESSED_BYTES = 250 * 1024**3
MAX_FILE_BYTES = 100 * 1024**3


class EnginePackError(ValueError):
    pass


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy.pop("manifest_sha256", None)
    return hashlib.sha256(json.dumps(copy, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts and not any(":" in part for part in path.parts)


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = archive.read(MANIFEST_NAME)
    except KeyError as exc:
        raise EnginePackError(f"{MANIFEST_NAME} is missing.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise EnginePackError("Engine-pack manifest is not valid UTF-8 JSON.") from exc
    if payload.get("schema") != "biointel.engine-pack.v1":
        raise EnginePackError("Unsupported engine-pack schema.")
    if payload.get("manifest_sha256") != canonical_sha256(payload):
        raise EnginePackError("Engine-pack manifest SHA-256 is invalid.")
    return payload


def inspect_pack(path: str | Path, *, verify_payloads: bool = True) -> dict[str, Any]:
    pack_path = Path(path).expanduser().resolve()
    if not pack_path.is_file():
        raise EnginePackError("Engine pack does not exist.")
    with zipfile.ZipFile(pack_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            raise EnginePackError("Engine pack contains too many files.")
        unsafe = [item.filename for item in infos if not _safe_member(item.filename)]
        if unsafe:
            raise EnginePackError("Unsafe archive path detected: " + unsafe[0])
        counts = Counter(item.filename for item in infos)
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        if duplicates:
            raise EnginePackError("Duplicate archive member detected: " + duplicates[0])
        total = sum(item.file_size for item in infos)
        if total > MAX_UNCOMPRESSED_BYTES or any(item.file_size > MAX_FILE_BYTES for item in infos):
            raise EnginePackError("Engine pack exceeds configured extraction limits.")
        bad_crc = archive.testzip()
        if bad_crc:
            raise EnginePackError(f"CRC failure: {bad_crc}")
        manifest = _read_manifest(archive)
        declared = {str(row["path"]): row for row in manifest.get("files", [])}
        actual = {item.filename for item in infos if not item.is_dir() and item.filename != MANIFEST_NAME}
        if set(declared) != actual:
            missing = sorted(set(declared) - actual)
            extra = sorted(actual - set(declared))
            raise EnginePackError(f"Pack file inventory mismatch. missing={missing[:3]} extra={extra[:3]}")
        if verify_payloads:
            for name, row in declared.items():
                digest = hashlib.sha256(archive.read(name)).hexdigest()
                if digest != str(row.get("sha256", "")):
                    raise EnginePackError(f"SHA-256 mismatch: {name}")
                if int(row.get("size_bytes", -1)) != len(archive.read(name)):
                    raise EnginePackError(f"Size mismatch: {name}")
    return {
        "path": str(pack_path),
        "archive_sha256": sha256_file(pack_path),
        "pack_id": str(manifest.get("pack_id", "")),
        "pack_version": str(manifest.get("pack_version", "")),
        "platform": str(manifest.get("platform", "")),
        "engines": list(manifest.get("engines", [])),
        "files": len(manifest.get("files", [])),
        "uncompressed_bytes": total,
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest": manifest,
        "status": "verified",
    }


def extract_pack(path: str | Path, destination: str | Path) -> dict[str, Any]:
    inspection = inspect_pack(path, verify_payloads=True)
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        with zipfile.ZipFile(Path(path).resolve()) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                output = contained_path(temporary, item.filename)
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, output.open("wb") as sink:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
        backup = target.with_name(target.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            os.replace(target, backup)
        os.replace(temporary, target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    inspection["extracted_to"] = str(target)
    return inspection


def build_pack(source: str | Path, destination: str | Path, *, pack_id: str, pack_version: str, platform: str, engines: list[dict[str, Any]], licence_records: list[dict[str, Any]] | None = None) -> Path:
    source_root = Path(source).expanduser().resolve()
    output = Path(destination).expanduser().resolve()
    if not source_root.is_dir():
        raise EnginePackError("Pack source folder does not exist.")
    files = [path for path in source_root.rglob("*") if path.is_file() and path.name != MANIFEST_NAME]
    rows = [{"path": path.relative_to(source_root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted(files)]
    payload: dict[str, Any] = {
        "schema": "biointel.engine-pack.v1",
        "pack_id": pack_id,
        "pack_version": pack_version,
        "platform": platform,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "engines": engines,
        "licence_records": licence_records or [],
        "files": rows,
        "claim_boundary": "A verified pack is not scientifically qualified until executable/version, positive fixture and negative control evidence pass on the target machine.",
    }
    payload["manifest_sha256"] = canonical_sha256(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(source_root).as_posix())
        archive.writestr(MANIFEST_NAME, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    inspect_pack(output)
    return output
