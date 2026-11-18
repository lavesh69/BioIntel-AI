from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .final import build_final_assurance


def _update_file(digest: "hashlib._Hash", root: Path, path: Path) -> None:
    if not path.is_file():
        return
    digest.update(path.relative_to(root).as_posix().encode("utf-8"))
    digest.update(str(path.stat().st_size).encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)


def final_assurance_fingerprint(root: str | Path) -> str:
    base = Path(root).resolve()
    digest = hashlib.sha256()
    explicit = [base / "VERSION", base / "config" / "settings.yaml"]
    for folder in (
        base / "src" / "biointel" / "assurance",
        base / "src" / "biointel" / "engineering",
        base / "src" / "biointel" / "clinical",
    ):
        if folder.is_dir():
            explicit.extend(sorted(folder.rglob("*.py")))
    explicit.extend(sorted((base / "reports").glob("*.sqlite3")))
    explicit.extend(sorted((base / "data" / "clinical_pharma").glob("*.sqlite3")))
    for path in explicit:
        _update_file(digest, base, path)
    return digest.hexdigest()


def build_final_assurance_cached(
    root: str | Path,
    *,
    validate_fingerprint: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    base = Path(root).resolve()
    cache_path = base / "reports" / "final_assurance_cache.json"
    fingerprint = ""
    if cache_path.is_file() and not force_refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached.get("report"), dict):
                if not validate_fingerprint:
                    return cached["report"]
                fingerprint = final_assurance_fingerprint(base)
                if cached.get("fingerprint") == fingerprint:
                    return cached["report"]
        except (OSError, json.JSONDecodeError):
            pass
    if not fingerprint:
        fingerprint = final_assurance_fingerprint(base)
    report = build_final_assurance(base)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"fingerprint": fingerprint, "report": report}, indent=2, sort_keys=True, default=str)
    handle, temporary_name = tempfile.mkstemp(prefix="final-assurance-", suffix=".json", dir=cache_path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary_name, cache_path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return report
