from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from biointel.database.core import connect, database_health, transaction, utc_now


@dataclass(frozen=True)
class DownloadRecord:
    download_id: int
    provider: str
    resource_id: str | None
    url: str
    filename: str
    relative_path: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    downloaded_at_utc: str
    etag: str | None
    last_modified: str | None
    notes: str


SCHEMA = """
CREATE TABLE IF NOT EXISTS internet_downloads (
    download_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    resource_id TEXT,
    url TEXT NOT NULL,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    downloaded_at_utc TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(url, sha256)
);
CREATE INDEX IF NOT EXISTS idx_internet_downloads_provider
    ON internet_downloads(provider);
CREATE INDEX IF NOT EXISTS idx_internet_downloads_resource
    ON internet_downloads(resource_id);
CREATE INDEX IF NOT EXISTS idx_internet_downloads_time
    ON internet_downloads(downloaded_at_utc);
CREATE INDEX IF NOT EXISTS idx_internet_downloads_status
    ON internet_downloads(status);
CREATE INDEX IF NOT EXISTS idx_internet_downloads_sha
    ON internet_downloads(sha256);
"""


def initialize_download_registry(path: str | Path) -> None:
    with transaction(path) as connection:
        connection.executescript(SCHEMA)


def register_download(
    path: str | Path,
    *,
    provider: str,
    resource_id: str | None,
    url: str,
    filename: str,
    relative_path: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    etag: str | None = None,
    last_modified: str | None = None,
    notes: str = "",
) -> DownloadRecord:
    initialize_download_registry(path)
    with transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO internet_downloads(
                provider, resource_id, url, filename, relative_path,
                content_type, size_bytes, sha256, status,
                downloaded_at_utc, etag, last_modified, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?)
            ON CONFLICT(url, sha256) DO UPDATE SET
                filename = excluded.filename,
                relative_path = excluded.relative_path,
                content_type = excluded.content_type,
                size_bytes = excluded.size_bytes,
                status = 'completed',
                downloaded_at_utc = excluded.downloaded_at_utc,
                etag = excluded.etag,
                last_modified = excluded.last_modified,
                notes = excluded.notes
            """,
            (
                provider,
                resource_id,
                url,
                filename,
                relative_path,
                content_type,
                int(size_bytes),
                sha256,
                utc_now(),
                etag,
                last_modified,
                notes,
            ),
        )
        row = connection.execute(
            """
            SELECT * FROM internet_downloads
            WHERE url = ? AND sha256 = ?
            """,
            (url, sha256),
        ).fetchone()
    if row is None:
        raise RuntimeError("The completed download could not be registered.")
    return DownloadRecord(**dict(row))


def list_downloads(
    path: str | Path,
    *,
    provider: str = "all",
    limit: int = 500,
) -> list[DownloadRecord]:
    initialize_download_registry(path)
    with connect(path, read_only=True) as connection:
        if provider == "all":
            rows = connection.execute(
                """
                SELECT * FROM internet_downloads
                ORDER BY downloaded_at_utc DESC
                LIMIT ?
                """,
                (min(max(int(limit), 1), 5000),),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM internet_downloads
                WHERE provider = ?
                ORDER BY downloaded_at_utc DESC
                LIMIT ?
                """,
                (provider, min(max(int(limit), 1), 5000)),
            ).fetchall()
    return [DownloadRecord(**dict(row)) for row in rows]


def download_summary(path: str | Path) -> dict[str, object]:
    initialize_download_registry(path)
    with connect(path, read_only=True) as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM internet_downloads").fetchone()[0])
        total_bytes = int(
            connection.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM internet_downloads"
            ).fetchone()[0]
        )
        providers = {
            str(row["provider"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT provider, COUNT(*) AS count
                FROM internet_downloads
                GROUP BY provider
                ORDER BY count DESC
                """
            )
        }
    try:
        with connect(path, read_only=True) as connection:
            source_catalog_count = int(connection.execute("SELECT COUNT(*) FROM scientific_source_catalog").fetchone()[0])
    except Exception:
        source_catalog_count = 0
    return {
        "downloads": total,
        "total_bytes": total_bytes,
        "providers": providers,
        "scientific_source_catalog": source_catalog_count,
        "database": asdict(database_health(path, name="Internet Download Registry")),
    }
