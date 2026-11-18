from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def file_signature(path: str | Path) -> tuple[str, int, int, int, str]:
    """Return a robust cache signature for a local file.

    Some filesystems expose coarse timestamp granularity, so same-size rewrites
    can otherwise return stale cached content. Small files are fully hashed; for
    larger files a bounded head/tail fingerprint complements mtime and ctime.
    """

    resolved = Path(path).resolve()
    stat = resolved.stat()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        if stat.st_size <= 1024 * 1024:
            for chunk in iter(lambda: handle.read(256 * 1024), b""):
                digest.update(chunk)
        else:
            digest.update(handle.read(64 * 1024))
            handle.seek(max(0, stat.st_size - 64 * 1024))
            digest.update(handle.read(64 * 1024))
    return (
        str(resolved),
        int(stat.st_mtime_ns),
        int(stat.st_size),
        int(stat.st_ctime_ns),
        digest.hexdigest(),
    )


@lru_cache(maxsize=64)
def _load_json_cached(
    path_string: str,
    modification_ns: int,
    size_bytes: int,
    change_ns: int,
    content_fingerprint: str,
) -> object:
    del modification_ns, size_bytes, change_ns, content_fingerprint
    return json.loads(Path(path_string).read_text(encoding="utf-8"))


def load_json_cached(
    path: str | Path,
    *,
    default: Any | None = None,
) -> Any:
    """Load JSON once per file signature and return a defensive copy."""

    resolved = Path(path).resolve()
    if not resolved.is_file():
        return copy.deepcopy(default)
    payload = _load_json_cached(*file_signature(resolved))
    return copy.deepcopy(payload)


@lru_cache(maxsize=32)
def _read_csv_cached(
    path_string: str,
    modification_ns: int,
    size_bytes: int,
    change_ns: int,
    content_fingerprint: str,
    nrows: int | None,
    usecols: tuple[str, ...] | None,
) -> pd.DataFrame:
    del modification_ns, size_bytes, change_ns, content_fingerprint
    return pd.read_csv(
        path_string,
        nrows=nrows,
        usecols=list(usecols) if usecols else None,
        low_memory=False,
    )


def read_csv_cached(
    path: str | Path,
    *,
    nrows: int | None = None,
    usecols: Iterable[str] | None = None,
    max_cache_bytes: int = 32 * 1024 * 1024,
) -> pd.DataFrame:
    """Read a stable local CSV with automatic mtime/size invalidation.

    This helper is intended for previews and small static libraries. Training
    code should stream or load its working dataset explicitly so large frames
    are released when training finishes.
    """

    resolved = Path(path).resolve()
    columns = tuple(usecols) if usecols is not None else None
    signature = file_signature(resolved)
    if signature[2] > max(0, int(max_cache_bytes)):
        return pd.read_csv(
            resolved,
            nrows=nrows,
            usecols=list(columns) if columns else None,
            low_memory=False,
        )
    frame = _read_csv_cached(
        *signature,
        nrows,
        columns,
    )
    # A defensive copy prevents one page from mutating data shared with another
    # Streamlit session through the process-level cache.
    return frame.copy(deep=True)


@lru_cache(maxsize=32)
def _read_text_cached(
    path_string: str,
    modification_ns: int,
    size_bytes: int,
    change_ns: int,
    content_fingerprint: str,
) -> str:
    del modification_ns, size_bytes, change_ns, content_fingerprint
    return Path(path_string).read_text(encoding="utf-8")


def read_text_cached(path: str | Path) -> str:
    """Read a UTF-8 text file once per file signature."""

    return _read_text_cached(*file_signature(path))


def clear_runtime_caches() -> None:
    """Clear all process-level file caches."""

    _load_json_cached.cache_clear()
    _read_csv_cached.cache_clear()
    _read_text_cached.cache_clear()


def runtime_cache_info() -> dict[str, dict[str, int | None]]:
    """Return cache statistics for diagnostics and the optimization page."""

    return {
        "json": _load_json_cached.cache_info()._asdict(),
        "csv": _read_csv_cached.cache_info()._asdict(),
        "text": _read_text_cached.cache_info()._asdict(),
    }
