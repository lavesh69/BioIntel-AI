from __future__ import annotations

import json
import os
import shutil
import sqlite3
from biointel.database.core import managed_connect
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from biointel.reference_assets.manager import ReferenceAssetRegistry, sha256_file


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ReleaseRecord:
    asset_id: str
    version: str
    provider: str
    download_url: str = ""
    sha256: str = ""
    license_name: str = ""
    release_date: str = ""
    compatibility: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ReferenceLifecycleManager:
    """Version, verify, index, rollback and clean scientific reference assets."""

    def __init__(self, asset_root: str | Path) -> None:
        self.root = Path(asset_root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = ReferenceAssetRegistry(self.root / "reference_assets.sqlite3")
        self.db_path = self.registry.database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS asset_releases(
                    asset_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    download_url TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL DEFAULT '',
                    license_name TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL DEFAULT '',
                    compatibility_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY(asset_id, version)
                );
                CREATE TABLE IF NOT EXISTS asset_snapshots(
                    snapshot_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS asset_indexes(
                    index_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    index_type TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_path TEXT NOT NULL DEFAULT '',
                    log_path TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS asset_compatibility_checks(
                    check_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    compatible INTEGER NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    checked_at_utc TEXT NOT NULL
                );
                """
            )

    def register_release(self, record: ReleaseRecord) -> None:
        if not record.asset_id.strip() or not record.version.strip():
            raise ValueError("asset_id and version are required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO asset_releases VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id,version) DO UPDATE SET
                    provider=excluded.provider,download_url=excluded.download_url,
                    sha256=excluded.sha256,license_name=excluded.license_name,
                    release_date=excluded.release_date,compatibility_json=excluded.compatibility_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    record.asset_id,
                    record.version,
                    record.provider,
                    record.download_url,
                    record.sha256,
                    record.license_name,
                    record.release_date,
                    json.dumps(record.compatibility or {}, sort_keys=True),
                    json.dumps(record.metadata or {}, sort_keys=True),
                    _now(),
                ),
            )

    def releases(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM asset_releases"
        params: tuple[Any, ...] = ()
        if asset_id:
            query += " WHERE asset_id=?"
            params = (asset_id,)
        query += " ORDER BY asset_id, release_date DESC, version DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def verify_installed(self, asset_id: str) -> dict[str, Any]:
        assets = {str(item["asset_id"]): item for item in self.registry.list_assets()}
        if asset_id not in assets:
            raise KeyError(asset_id)
        item = assets[asset_id]
        path = Path(str(item.get("local_path", ""))).expanduser()
        if not path.exists():
            return {"asset_id": asset_id, "passed": False, "reason": "local path missing"}
        if path.is_file():
            observed = sha256_file(path)
            size = path.stat().st_size
        else:
            digest_parts = []
            size = 0
            for file in sorted(path.rglob("*")):
                if file.is_file():
                    rel = file.relative_to(path).as_posix()
                    digest_parts.append(rel + ":" + sha256_file(file))
                    size += file.stat().st_size
            import hashlib

            observed = hashlib.sha256("\n".join(digest_parts).encode()).hexdigest()
        expected = str(item.get("expected_sha256", "")).lower()
        return {
            "asset_id": asset_id,
            "version": item.get("version"),
            "path": str(path),
            "size_bytes": size,
            "observed_sha256": observed,
            "expected_sha256": expected,
            "passed": not expected or observed.lower() == expected,
            "integrity_level": "provider_verified" if expected else "locally_hashed",
        }

    def snapshot(self, asset_id: str) -> dict[str, Any]:
        assets = {str(item["asset_id"]): item for item in self.registry.list_assets()}
        if asset_id not in assets:
            raise KeyError(asset_id)
        item = assets[asset_id]
        source = Path(str(item["local_path"])).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        snapshot_id = "snapshot-" + uuid4().hex
        destination = self.root / "snapshots" / asset_id / snapshot_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
            digest = self.verify_installed(asset_id)["observed_sha256"]
            size = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
        else:
            destination.mkdir(parents=True, exist_ok=True)
            copied = destination / source.name
            shutil.copy2(source, copied)
            digest = sha256_file(copied)
            size = copied.stat().st_size
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO asset_snapshots VALUES(?,?,?,?,?,?,?,?)",
                (snapshot_id, asset_id, str(item.get("version", "")), str(source), str(destination), digest, size, _now()),
            )
        return {"snapshot_id": snapshot_id, "path": str(destination), "sha256": digest, "size_bytes": size}

    def snapshots(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM asset_snapshots"
        params: tuple[Any, ...] = ()
        if asset_id:
            query += " WHERE asset_id=?"
            params = (asset_id,)
        query += " ORDER BY created_at_utc DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def rollback(self, snapshot_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM asset_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        source = Path(str(row["snapshot_path"]))
        target = Path(str(row["source_path"]))
        if not source.exists():
            raise FileNotFoundError(source)
        backup = target.with_name(target.name + ".rollback-backup")
        if backup.exists():
            shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
        if target.exists():
            os.replace(target, backup)
        try:
            if source.is_dir() and len(list(source.iterdir())) == 1 and next(iter(source.iterdir())).is_file() and target.suffix:
                shutil.copy2(next(iter(source.iterdir())), target)
            elif source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        except Exception:
            if not target.exists() and backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
        return {"snapshot_id": snapshot_id, "restored_path": str(target), "restored": True}

    def compatibility_check(self, asset_id: str, environment: dict[str, str]) -> dict[str, Any]:
        releases = [row for row in self.releases(asset_id) if str(row["version"]) == str(environment.get("asset_version", ""))]
        policy = json.loads(releases[0]["compatibility_json"]) if releases else {}
        failures = []
        for key, expected in policy.items():
            observed = environment.get(key)
            if isinstance(expected, list):
                if observed not in {str(value) for value in expected}:
                    failures.append({"key": key, "expected": expected, "observed": observed})
            elif observed is not None and str(observed) != str(expected):
                failures.append({"key": key, "expected": expected, "observed": observed})
        result = {"asset_id": asset_id, "compatible": not failures, "failures": failures, "policy": policy, "environment": environment}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO asset_compatibility_checks VALUES(?,?,?,?,?,?)",
                ("compat-" + uuid4().hex, asset_id, str(environment.get("asset_version", "")), int(not failures), json.dumps(result, sort_keys=True), _now()),
            )
        return result

    def run_index(self, asset_id: str, version: str, index_type: str, command: list[str], output_path: str | Path, *, timeout_seconds: int = 3600) -> dict[str, Any]:
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ValueError("A command vector is required")
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        log = self.root / "logs" / f"index-{asset_id}-{version}-{index_type}-{uuid4().hex[:8]}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        index_id = "index-" + uuid4().hex
        started = _now()
        with log.open("w", encoding="utf-8", errors="replace") as handle:
            process = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, text=True, timeout=max(10, int(timeout_seconds)), shell=False)
        status = "completed" if process.returncode == 0 else "failed"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO asset_indexes VALUES(?,?,?,?,?,?,?,?,?,?)",
                (index_id, asset_id, version, index_type, json.dumps(command), status, str(output), str(log), started, _now()),
            )
        return {"index_id": index_id, "status": status, "returncode": process.returncode, "output_path": str(output), "log_path": str(log)}

    def storage_summary(self, quota_bytes: int | None = None) -> dict[str, Any]:
        # SQLite WAL/SHM files can disappear between directory enumeration and stat()
        # when a connection checkpoints. Count only files that still exist at the
        # instant they are measured instead of failing the whole storage dashboard.
        used = 0
        file_count = 0
        for path in self.root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                used += path.stat().st_size
                file_count += 1
            except FileNotFoundError:
                continue
        quota = int(quota_bytes) if quota_bytes is not None else None
        return {
            "root": str(self.root),
            "files": file_count,
            "used_bytes": used,
            "quota_bytes": quota,
            "remaining_bytes": max(quota - used, 0) if quota is not None else None,
            "quota_percent": (100.0 * used / quota) if quota else None,
        }

    def cleanup_snapshots(self, *, keep_per_asset: int = 2) -> dict[str, int]:
        removed = 0
        by_asset: dict[str, list[dict[str, Any]]] = {}
        for row in self.snapshots():
            by_asset.setdefault(str(row["asset_id"]), []).append(row)
        with self._connect() as connection:
            for rows in by_asset.values():
                for row in rows[max(0, int(keep_per_asset)):]:
                    path = Path(str(row["snapshot_path"]))
                    shutil.rmtree(path, ignore_errors=True)
                    connection.execute("DELETE FROM asset_snapshots WHERE snapshot_id=?", (row["snapshot_id"],))
                    removed += 1
        return {"removed_snapshots": removed}
