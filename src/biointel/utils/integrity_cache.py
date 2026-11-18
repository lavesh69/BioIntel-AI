from __future__ import annotations

from biointel.runtime_paths import runtime_reports_directory

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

CACHE_VERSION = "1.0"


def _load_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": CACHE_VERSION, "files": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "files": {}}
    if payload.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "files": {}}
    if not isinstance(payload.get("files"), dict):
        payload["files"] = {}
    return payload


def _atomic_write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_cache_name(cache_name: str) -> str:
    name = Path(str(cache_name)).name
    if not name or name != str(cache_name) or name in {".", ".."}:
        raise ValueError("Integrity cache name must be a plain filename.")
    return name


def verify_manifest_files(
    root: str | Path,
    items: Iterable[Mapping[str, object]],
    *,
    cache_name: str = ".file_integrity_cache.json",
) -> dict[str, object]:
    """Verify manifest files while re-hashing only changed file signatures."""

    project_root = Path(root).resolve()
    cache_name = _safe_cache_name(cache_name)
    cache_path = runtime_reports_directory(project_root) / cache_name
    cache = _load_cache(cache_path)
    files_cache = cache.setdefault("files", {})
    assert isinstance(files_cache, dict)

    errors: list[str] = []
    checked_files = 0
    reused_hashes = 0
    computed_hashes = 0
    changed = False
    seen: set[str] = set()

    for item in items:
        filename = str(item.get("filename", "")).strip()
        expected = str(item.get("sha256", "")).strip()
        if not filename or not expected:
            errors.append("Manifest entry is missing filename or SHA-256.")
            continue

        path = project_root / filename
        seen.add(filename)
        if not path.is_file():
            errors.append(f"Missing file: {filename}")
            continue

        stat = path.stat()
        signature = {
            "mtime_ns": int(stat.st_mtime_ns),
            "size": int(stat.st_size),
            "expected": expected,
        }
        previous = files_cache.get(filename)
        if (
            isinstance(previous, dict)
            and previous.get("mtime_ns") == signature["mtime_ns"]
            and previous.get("size") == signature["size"]
            and previous.get("expected") == expected
            and previous.get("actual") == expected
        ):
            actual = expected
            reused_hashes += 1
        else:
            actual = _sha256(path)
            computed_hashes += 1
            files_cache[filename] = {
                **signature,
                "actual": actual,
            }
            changed = True

        if actual != expected:
            errors.append(f"Checksum mismatch: {filename}")
            continue
        checked_files += 1

    stale = [name for name in files_cache if name not in seen]
    for name in stale:
        del files_cache[name]
        changed = True

    if changed or not cache_path.is_file():
        _atomic_write(cache_path, cache)

    return {
        "valid": not errors,
        "checked_files": checked_files,
        "errors": errors,
        "reused_hashes": reused_hashes,
        "computed_hashes": computed_hashes,
        "cache_path": f"reports/{cache_path.name}",
    }


def clear_integrity_cache(
    root: str | Path,
    *,
    cache_name: str = ".file_integrity_cache.json",
) -> bool:
    """Remove the persistent integrity cache."""

    cache_name = _safe_cache_name(cache_name)
    path = runtime_reports_directory(Path(root).resolve()) / cache_name
    if not path.exists():
        return False
    path.unlink()
    return True
