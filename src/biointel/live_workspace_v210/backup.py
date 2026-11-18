from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_replace(source: Path, target: Path, *, attempts: int = 5) -> None:
    """Publish a completed backup despite short-lived Windows file locks."""
    for attempt in range(max(int(attempts), 1)):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(0.05 * (2**attempt))


def _remove_temporary(path: Path, *, attempts: int = 5) -> None:
    """Best-effort cleanup for files briefly held by Windows scanners."""
    for attempt in range(max(int(attempts), 1)):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                return
            time.sleep(0.05 * (2**attempt))


def create_live_workspace_snapshot(
    database_path: Path,
    backup_dir: Path,
    *,
    retention: int = 20,
) -> dict[str, Any] | None:
    """Create an atomic SQLite snapshot plus checksum manifest.

    Returns None when the collaboration database has not been created yet.
    """
    database_path = Path(database_path).expanduser().resolve()
    if not database_path.is_file():
        return None
    backup_dir = Path(backup_dir).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    stamp = created_at.strftime("%Y%m%d-%H%M%S-%f")
    operation_id = f"{os.getpid()}-{secrets.token_hex(4)}"
    snapshot = backup_dir / f".live-workspace-{stamp}-{operation_id}.sqlite3.tmp"
    archive = backup_dir / f"BioIntel-Live-Workspace-AutoBackup-{stamp}-{operation_id}.zip"
    temporary_archive = backup_dir / f".{archive.name}.tmp"
    try:
        with closing(sqlite3.connect(database_path, timeout=30)) as source, closing(sqlite3.connect(snapshot, timeout=30)) as target:
            source.backup(target, pages=256)
            target.commit()
            integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError("Live Workspace automatic backup failed its SQLite integrity check.")
        digest = _sha256(snapshot)
        manifest = {
            "schema": "biointel.live-workspace.sqlite-snapshot.v1",
            "created_at_utc": created_at.isoformat(timespec="seconds"),
            "source_database": database_path.name,
            "snapshot_file": "live_workspace.sqlite3",
            "snapshot_sha256": digest,
            "snapshot_size_bytes": snapshot.stat().st_size,
            "sqlite_integrity": integrity,
        }
        with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            output.write(snapshot, "live_workspace.sqlite3")
            output.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        _atomic_replace(temporary_archive, archive)
    finally:
        _remove_temporary(snapshot)
        _remove_temporary(temporary_archive)
    backups = sorted(backup_dir.glob("BioIntel-Live-Workspace-AutoBackup-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[min(max(int(retention), 1), 200) :]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            # A running verifier or antivirus may briefly hold an old archive.
            continue
    return {**manifest, "archive_file": str(archive), "archive_size_bytes": archive.stat().st_size}


def inspect_live_workspace_snapshot(archive_path: Path) -> dict[str, Any]:
    archive_path = Path(archive_path).expanduser().resolve()
    with zipfile.ZipFile(archive_path, "r") as archive:
        if set(archive.namelist()) != {"live_workspace.sqlite3", "manifest.json"}:
            raise ValueError("Unexpected files are present in the automatic backup.")
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("live_workspace.sqlite3")
    if hashlib.sha256(payload).hexdigest() != manifest.get("snapshot_sha256"):
        raise ValueError("Automatic backup checksum verification failed.")
    return {**manifest, "archive_file": str(archive_path), "verified": True}


__all__ = ["create_live_workspace_snapshot", "inspect_live_workspace_snapshot"]
