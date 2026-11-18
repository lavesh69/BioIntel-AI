from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheEntry:
    url: str
    key: str
    created_at_epoch: float
    content_type: str
    size_bytes: int
    body_path: Path
    metadata_path: Path

    def age_seconds(self, now: float | None = None) -> float:
        current = time.time() if now is None else float(now)
        return max(0.0, current - self.created_at_epoch)

    def is_fresh(
        self,
        ttl_seconds: float,
        now: float | None = None,
    ) -> bool:
        return self.age_seconds(now) <= float(ttl_seconds)


class ExternalResponseCache:
    """Small file cache for official scientific-database responses."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key_for_url(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _paths(self, key: str) -> tuple[Path, Path]:
        return (
            self.directory / f"{key}.bin",
            self.directory / f"{key}.json",
        )

    def put(
        self,
        url: str,
        body: bytes,
        content_type: str,
        created_at_epoch: float | None = None,
    ) -> CacheEntry:
        key = self.key_for_url(url)
        body_path, metadata_path = self._paths(key)
        created = time.time() if created_at_epoch is None else float(created_at_epoch)

        body_path.write_bytes(body)
        metadata = {
            "url": url,
            "key": key,
            "created_at_epoch": created,
            "content_type": content_type,
            "size_bytes": len(body),
        }
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return CacheEntry(
            url=url,
            key=key,
            created_at_epoch=created,
            content_type=content_type,
            size_bytes=len(body),
            body_path=body_path,
            metadata_path=metadata_path,
        )

    def get(self, url: str) -> CacheEntry | None:
        key = self.key_for_url(url)
        body_path, metadata_path = self._paths(key)
        if not body_path.is_file() or not metadata_path.is_file():
            return None

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            entry = CacheEntry(
                url=str(metadata["url"]),
                key=str(metadata["key"]),
                created_at_epoch=float(metadata["created_at_epoch"]),
                content_type=str(
                    metadata.get(
                        "content_type",
                        "application/octet-stream",
                    )
                ),
                size_bytes=int(metadata["size_bytes"]),
                body_path=body_path,
                metadata_path=metadata_path,
            )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

        if entry.url != url:
            return None
        if body_path.stat().st_size != entry.size_bytes:
            return None
        return entry

    def read_bytes(self, entry: CacheEntry) -> bytes:
        return entry.body_path.read_bytes()

    def list_entries(self) -> list[CacheEntry]:
        entries: list[CacheEntry] = []
        for metadata_path in sorted(self.directory.glob("*.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                url = str(metadata["url"])
            except (
                OSError,
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                continue
            entry = self.get(url)
            if entry is not None:
                entries.append(entry)
        return sorted(
            entries,
            key=lambda item: item.created_at_epoch,
            reverse=True,
        )

    def clear(self) -> int:
        removed = 0
        for path in self.directory.glob("*"):
            if path.is_file() and path.suffix in {".bin", ".json"}:
                path.unlink()
                removed += 1
        return removed

    def remove_expired(
        self,
        ttl_seconds: float,
        now: float | None = None,
    ) -> int:
        removed_entries = 0
        for entry in self.list_entries():
            if entry.is_fresh(ttl_seconds, now):
                continue
            entry.body_path.unlink(missing_ok=True)
            entry.metadata_path.unlink(missing_ok=True)
            removed_entries += 1
        return removed_entries

    def total_size_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.directory.glob("*") if path.is_file())
