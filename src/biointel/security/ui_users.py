from __future__ import annotations

import json
from typing import Any


def parse_ui_users(raw: str) -> dict[str, dict[str, str]]:
    """Parse UI-user configuration in mapping or explicit-list format.

    Canonical format is a username-keyed JSON object. The list format is retained
    for compatibility with early store-release templates.
    """

    value = raw.strip()
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    records: list[tuple[str, dict[str, Any]]] = []
    nested = payload.get("users")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                records.append((str(item.get("username", "")), item))
    else:
        records = [(str(username), item) for username, item in payload.items() if isinstance(item, dict)]

    users: dict[str, dict[str, str]] = {}
    for username, item in records:
        password_hash = str(item.get("password_hash", "")).strip()
        key = username.strip().lower()
        if not key or not password_hash:
            continue
        users[key] = {
            "password_hash": password_hash,
            "display_name": str(item.get("display_name") or username).strip(),
            "role": str(item.get("role") or "researcher").strip().lower(),
        }
    return users
