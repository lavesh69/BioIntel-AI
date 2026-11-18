from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

SENSITIVE_KEYS = {
    "sequence", "protein_sequence", "canonical_smiles", "smiles", "raw_text",
    "dataset", "dataframe", "password", "secret", "token", "api_key",
    "authorization", "credential",
}
AUDIT_CHAIN_VERSION = "1.1"
_AUDIT_LOCK = Lock()


def hash_sensitive_value(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:16]


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return (
        lowered in SENSITIVE_KEYS
        or lowered.endswith("_sequence")
        or "smiles" in lowered
        or "token" in lowered
        or "secret" in lowered
        or "password" in lowered
        or "credential" in lowered
        or lowered in {"api-key", "apikey"}
    )


def _sanitize_value(key: str, value: Any, *, depth: int = 0) -> Any:
    if _is_sensitive_key(key):
        return {"sha256_prefix": hash_sensitive_value(value), "length": len(str(value))}
    if depth >= 6:
        return str(value)[:500]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, dict):
        return {str(k)[:128]: _sanitize_value(str(k), v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(key, item, depth=depth + 1) for item in list(value)[:200]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def sanitize_audit_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        if _is_sensitive_key(key):
            sanitized[f"{key}_sha256_prefix"] = hash_sensitive_value(value)
            sanitized[f"{key}_length"] = len(str(value))
        else:
            sanitized[key] = _sanitize_value(key, value)
    return sanitized


def _canonical_hash(payload: dict[str, Any]) -> str:
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _last_event_hash(path: Path) -> str:
    events = read_audit_events(path, limit=1)
    return str(events[-1].get("event_hash", "")) if events else ""


def append_audit_event(path: str | Path, event: str, status: str, fields: dict[str, Any] | None = None) -> None:
    """Append a privacy-safe hash-chained event with in-process serialization."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with _AUDIT_LOCK:
        payload: dict[str, Any] = {
            "audit_chain_version": AUDIT_CHAIN_VERSION,
            "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": event,
            "status": status,
            "fields": sanitize_audit_fields(fields or {}),
            "prev_hash": _last_event_hash(output),
        }
        payload["event_hash"] = _canonical_hash(payload)
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            handle.flush()


def read_audit_events(path: str | Path, limit: int = 1000) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    bounded_limit = max(1, min(int(limit), 10000))
    # Stream only the requested tail instead of loading unbounded audit files.
    with source.open("r", encoding="utf-8", errors="replace") as handle:
        lines = deque(handle, maxlen=bounded_limit)
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        except json.JSONDecodeError:
            continue
    return events


def verify_audit_chain(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if not source.exists():
        return {"valid": True, "total_events": 0, "chained_events": 0, "legacy_events": 0, "errors": [], "latest_hash": ""}
    errors: list[str] = []
    chained = 0
    legacy = 0
    expected_previous = ""
    events = read_audit_events(source, limit=10000)
    for index, event in enumerate(events, start=1):
        event_hash = event.get("event_hash")
        if not event_hash:
            legacy += 1
            expected_previous = ""
            continue
        chained += 1
        payload = dict(event)
        payload.pop("event_hash", None)
        if _canonical_hash(payload) != event_hash:
            errors.append(f"Event {index} content hash mismatch.")
        previous = str(event.get("prev_hash", ""))
        if previous != expected_previous:
            errors.append(f"Event {index} previous hash mismatch.")
        expected_previous = str(event_hash)
    return {
        "valid": not errors, "total_events": len(events), "chained_events": chained,
        "legacy_events": legacy, "errors": errors, "latest_hash": expected_previous,
    }
