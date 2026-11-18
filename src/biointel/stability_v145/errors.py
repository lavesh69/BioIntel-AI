from __future__ import annotations

import hashlib
import json
import re
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.utils.atomic_io import atomic_write_json

_SECRET_KEY = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|session|private[_-]?key)")
_INLINE_SECRET = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|bearer)(\s*[:=]\s*)([^\s,;]+)"
)
_PATH_TOKEN = re.compile(r"(?i)([?&](?:token|key|secret|signature)=)[^&\s]+")
_LOCK = threading.RLock()


def redact_sensitive(value: Any) -> Any:
    """Recursively redact common credentials without mutating the source object."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    text = str(value)
    text = _INLINE_SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
    return _PATH_TOKEN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)


def recovery_id(context: str, exc: BaseException, *, occurred_at: datetime | None = None) -> str:
    timestamp = occurred_at or datetime.now(UTC)
    material = f"{context}|{type(exc).__name__}|{exc}|{timestamp.isoformat()}".encode("utf-8", errors="replace")
    return "ERR-" + timestamp.strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(material).hexdigest()[:12].upper()


class ErrorStore:
    def __init__(
        self,
        directory: str | Path,
        *,
        max_files: int = 200,
        max_total_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.directory = Path(directory).resolve()
        self.max_files = max(1, int(max_files))
        self.max_total_bytes = max(1024, int(max_total_bytes))

    def record(self, context: str, exc: BaseException, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        timestamp = datetime.now(UTC)
        error_id = recovery_id(context, exc, occurred_at=timestamp)
        payload = {
            "schema": "biointel.error.v145",
            "error_id": error_id,
            "timestamp_utc": timestamp.isoformat(),
            "context": redact_sensitive(context),
            "exception_type": type(exc).__name__,
            "message": redact_sensitive(str(exc)),
            "metadata": redact_sensitive(metadata or {}),
            "traceback": redact_sensitive("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            atomic_write_json(self.directory / f"{error_id}.json", payload, indent=2, sort_keys=False)
            self.rotate()
        return payload

    def rotate(self) -> dict[str, int]:
        try:
            files = sorted(self.directory.glob("ERR-*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        except OSError:
            return {"removed_files": 0, "removed_bytes": 0, "retained_files": 0}
        retained = 0
        retained_bytes = 0
        removed = 0
        removed_bytes = 0
        for path in files:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            if retained >= self.max_files or retained_bytes + size > self.max_total_bytes:
                try:
                    path.unlink()
                except OSError:
                    continue
                removed += 1
                removed_bytes += size
            else:
                retained += 1
                retained_bytes += size
        return {"removed_files": removed, "removed_bytes": removed_bytes, "retained_files": retained}

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("ERR-*.json"), reverse=True)[: max(1, min(int(limit), 500))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows
