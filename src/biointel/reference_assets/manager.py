from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from biointel.database.core import managed_connect
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


DEFAULT_MAX_ARCHIVE_FILES = 250_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 750 * 1024**3


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    provider: str
    version: str
    status: str
    source_url: str
    local_path: str
    expected_sha256: str
    observed_sha256: str
    size_bytes: int
    license_name: str
    license_accepted: bool
    installed_at_utc: str
    metadata_json: str = "{}"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        try:
            payload["metadata"] = json.loads(payload.pop("metadata_json"))
        except json.JSONDecodeError:
            payload["metadata"] = {}
        return payload


class ReferenceAssetRegistry:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    local_path TEXT NOT NULL DEFAULT '',
                    expected_sha256 TEXT NOT NULL DEFAULT '',
                    observed_sha256 TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0 CHECK(size_bytes >= 0),
                    license_name TEXT NOT NULL DEFAULT '',
                    license_accepted INTEGER NOT NULL DEFAULT 0 CHECK(license_accepted IN (0,1)),
                    installed_at_utc TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS asset_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_asset_events_asset_created
                    ON asset_events(asset_id, created_at_utc DESC);
                """
            )

    def upsert(self, record: AssetRecord, *, event_type: str = "upsert") -> None:
        if not record.asset_id.strip():
            raise ValueError("asset_id is required")
        if not record.license_accepted:
            raise ValueError("Licence acknowledgement is required before registry installation.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assets(asset_id,provider,version,status,source_url,local_path,expected_sha256,
                                   observed_sha256,size_bytes,license_name,license_accepted,installed_at_utc,metadata_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    provider=excluded.provider, version=excluded.version, status=excluded.status,
                    source_url=excluded.source_url, local_path=excluded.local_path,
                    expected_sha256=excluded.expected_sha256, observed_sha256=excluded.observed_sha256,
                    size_bytes=excluded.size_bytes, license_name=excluded.license_name,
                    license_accepted=excluded.license_accepted, installed_at_utc=excluded.installed_at_utc,
                    metadata_json=excluded.metadata_json
                """,
                (
                    record.asset_id, record.provider, record.version, record.status, record.source_url,
                    record.local_path, record.expected_sha256, record.observed_sha256, record.size_bytes,
                    record.license_name, int(record.license_accepted), record.installed_at_utc, record.metadata_json,
                ),
            )
            connection.execute(
                "INSERT INTO asset_events(asset_id,event_type,created_at_utc,payload_json) VALUES(?,?,?,?)",
                (record.asset_id, event_type, datetime.now(timezone.utc).isoformat(), json.dumps(record.to_dict(), sort_keys=True)),
            )

    def list_assets(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM assets ORDER BY provider, asset_id").fetchall()
        return [AssetRecord(**{**dict(row), "license_accepted": bool(row["license_accepted"])}).to_dict() for row in rows]

    def events(self, asset_id: str | None = None, *, limit: int = 250) -> list[dict[str, object]]:
        query = "SELECT * FROM asset_events"
        parameters: tuple[object, ...] = ()
        if asset_id:
            query += " WHERE asset_id=?"
            parameters = (asset_id,)
        query += " ORDER BY event_id DESC LIMIT ?"
        parameters += (max(1, min(int(limit), 5000)),)
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def _validate_checksum(path: Path, expected_sha256: str) -> str:
    observed = sha256_file(path)
    expected = expected_sha256.strip().lower()
    if expected and observed.lower() != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}: expected {expected}, observed {observed}")
    return observed


def _validate_download_url(url: str, *, allow_insecure_http: bool = False) -> None:
    parsed = urlparse(url)
    allowed = {"https"}
    if allow_insecure_http:
        allowed.add("http")
    if parsed.scheme.lower() not in allowed or not parsed.hostname:
        expected = "HTTPS" if not allow_insecure_http else "HTTP(S)"
        raise ValueError(f"A valid {expected} download URL is required.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in the download URL.")


def download_asset(
    url: str,
    destination: str | Path,
    *,
    expected_sha256: str = "",
    resume: bool = True,
    timeout_seconds: int = 60,
    progress: Callable[[int, int | None], None] | None = None,
    allow_insecure_http: bool = False,
) -> dict[str, object]:
    _validate_download_url(url, allow_insecure_http=allow_insecure_http)
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    existing = partial.stat().st_size if resume and partial.exists() else 0
    headers = {"User-Agent": "BioIntel-AI/9.6", "Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=max(5, int(timeout_seconds)))
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and partial.exists():
            observed = _validate_checksum(partial, expected_sha256)
            os.replace(partial, target)
            return {"path": str(target), "sha256": observed, "size_bytes": target.stat().st_size, "resumed": True}
        raise
    status = int(getattr(response, "status", 200))
    if existing and status != 206:
        existing = 0
        partial.unlink(missing_ok=True)
    mode = "ab" if existing else "wb"
    content_length = response.headers.get("Content-Length")
    total = existing + int(content_length) if content_length and content_length.isdigit() else None
    downloaded = existing
    with response, partial.open(mode) as handle:
        while True:
            chunk = response.read(4 * 1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if progress:
                progress(downloaded, total)
        handle.flush()
        os.fsync(handle.fileno())
    observed = _validate_checksum(partial, expected_sha256)
    os.replace(partial, target)
    return {"path": str(target), "sha256": observed, "size_bytes": target.stat().st_size, "resumed": bool(existing)}


def import_local_asset(source: str | Path, destination: str | Path, *, expected_sha256: str = "") -> dict[str, object]:
    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    dst = Path(destination).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_suffix(dst.suffix + ".importing")
    shutil.copy2(src, temp)
    observed = _validate_checksum(temp, expected_sha256)
    os.replace(temp, dst)
    return {"path": str(dst), "sha256": observed, "size_bytes": dst.stat().st_size, "resumed": False}


def _safe_member(destination: Path, name: str) -> Path:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise ValueError(f"Unsafe archive member: {name}")
    target = (destination / normalized).resolve()
    try:
        target.relative_to(destination.resolve())
    except ValueError as exc:
        raise ValueError(f"Archive path traversal blocked: {name}") from exc
    return target


def _activate_directory(staging: Path, final: Path) -> None:
    previous = final.with_name(final.name + ".previous")
    if previous.exists():
        shutil.rmtree(previous)
    try:
        if final.exists():
            os.replace(final, previous)
        os.replace(staging, final)
    except Exception:
        if not final.exists() and previous.exists():
            os.replace(previous, final)
        raise
    else:
        shutil.rmtree(previous, ignore_errors=True)


def safe_extract_archive(
    archive: str | Path,
    destination: str | Path,
    *,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, object]:
    source = Path(archive).expanduser().resolve()
    final = Path(destination).expanduser().resolve()
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".biointel-reference-", dir=final.parent))
    count = 0
    total = 0
    try:
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as handle:
                members = handle.infolist()
                if len(members) > max_files:
                    raise ValueError(f"Archive contains too many members ({len(members):,} > {max_files:,}).")
                for member in members:
                    _safe_member(staging, member.filename)
                    if member.is_dir():
                        continue
                    mode = (member.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        raise ValueError(f"Symbolic links are not accepted: {member.filename}")
                    total += int(member.file_size)
                    if total > max_uncompressed_bytes:
                        raise ValueError("Archive exceeds the configured uncompressed-size limit.")
                    handle.extract(member, staging)
                    count += 1
        elif tarfile.is_tarfile(source):
            with tarfile.open(source, "r:*") as handle:
                members = handle.getmembers()
                if len(members) > max_files:
                    raise ValueError(f"Archive contains too many members ({len(members):,} > {max_files:,}).")
                for member in members:
                    _safe_member(staging, member.name)
                    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                        raise ValueError(f"Unsafe tar member type: {member.name}")
                    if member.isfile():
                        total += int(member.size)
                        if total > max_uncompressed_bytes:
                            raise ValueError("Archive exceeds the configured uncompressed-size limit.")
                    handle.extract(member, staging, filter="data")
                    if member.isfile():
                        count += 1
        else:
            raise ValueError(f"Unsupported reference archive: {source.name}")
        _activate_directory(staging, final)
        return {"path": str(final), "files_extracted": count, "uncompressed_bytes": total}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
