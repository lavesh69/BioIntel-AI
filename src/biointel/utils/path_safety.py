from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def sanitize_path_text(value: str | os.PathLike[str] | None) -> str:
    """Return a command-line/environment path without accidental quote residue.

    Windows batch expansion such as ``--root \"%~dp0\"`` can pass an unmatched
    trailing quote when ``%~dp0`` ends in a backslash. A double quote is not a
    valid Windows filename character, so removing quote characters at the outer
    boundary is safe and prevents paths such as ``BioIntel-AI\"\\reports``.

    Internal characters are preserved. Only whitespace and quote characters at
    the beginning/end of the value are removed.
    """

    if value is None:
        return ""
    text = os.fspath(value).strip()
    # More than one layer can be introduced by nested BAT/PowerShell launchers.
    for _ in range(4):
        previous = text
        text = text.strip().lstrip('"').rstrip('"').strip()
        if text == previous:
            break
    return text


def resolve_path_argument(
    value: str | os.PathLike[str] | None,
    *,
    default: str | os.PathLike[str] | None = None,
    base: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve a user/launcher supplied path after quote-safe normalization."""

    cleaned = sanitize_path_text(value)
    if not cleaned:
        cleaned = sanitize_path_text(default)
    if not cleaned:
        raise ValueError("A non-empty path is required")
    candidate = Path(cleaned).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = Path(base).expanduser() / candidate
    return candidate.resolve()


def normalize_path_environment(keys: tuple[str, ...]) -> dict[str, str]:
    """Repair accidental surrounding quotes in path-like environment values."""

    repaired: dict[str, str] = {}
    for key in keys:
        original = os.environ.get(key)
        if original is None:
            continue
        cleaned = sanitize_path_text(original)
        if cleaned and cleaned != original:
            os.environ[key] = cleaned
            repaired[key] = cleaned
    return repaired


def path_debug_payload(raw: Any, normalized: Path) -> dict[str, Any]:
    raw_text = "" if raw is None else os.fspath(raw)
    cleaned = sanitize_path_text(raw_text)
    return {
        "raw": raw_text,
        "cleaned": cleaned,
        "normalized": str(normalized),
        "repaired": cleaned != raw_text.strip(),
    }
