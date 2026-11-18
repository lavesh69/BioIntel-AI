from __future__ import annotations

"""Public BioIntel identity layer for specialist scientific components.

Internal executable/package identifiers remain unchanged for runtime reliability.
Normal product surfaces use BioIntel names. Upstream names and licence sources are
available only in the dedicated Legal & Component Notices workspace.
"""

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALIAS_PATH = PROJECT_ROOT / "config" / "public_engine_aliases.json"

# Components that can be imported directly by Python modules and may not be in
# the native executable registry.
_BUILTIN_RECORDS: tuple[dict[str, Any], ...] = (
    {"public_key": "BI-LIB-001", "public_name": "BioIntel Sequence Intelligence Engine", "upstream_name": "Biopython", "aliases": ["Biopython", "Bio.Python"]},
    {"public_key": "BI-LIB-002", "public_name": "BioIntel Molecular Intelligence Engine", "upstream_name": "RDKit", "aliases": ["RDKit"]},
    {"public_key": "BI-LIB-003", "public_name": "BioIntel Single-Cell Data Engine", "upstream_name": "AnnData", "aliases": ["AnnData", "anndata"]},
    {"public_key": "BI-LIB-004", "public_name": "BioIntel Molecular AI Engine", "upstream_name": "DeepChem", "aliases": ["DeepChem"]},
    {"public_key": "BI-LIB-005", "public_name": "BioIntel Pathway Intelligence Engine", "upstream_name": "GSEApy", "aliases": ["GSEApy"]},
    {"public_key": "BI-LIB-006", "public_name": "BioIntel Biological Statistics Engine", "upstream_name": "scikit-bio", "aliases": ["scikit-bio", "scikit bio", "skbio"]},
    {"public_key": "BI-LIB-007", "public_name": "BioIntel Bioimaging Workspace", "upstream_name": "napari", "aliases": ["napari"]},
    {"public_key": "BI-LIB-008", "public_name": "BioIntel Molecular Trajectory Engine", "upstream_name": "MDAnalysis", "aliases": ["MDAnalysis"]},
    {"public_key": "BI-LIB-009", "public_name": "BioIntel Medical Imaging AI Engine", "upstream_name": "MONAI", "aliases": ["MONAI"]},
    {"public_key": "BI-LIB-010", "public_name": "BioIntel Single-Cell AI Engine", "upstream_name": "scvi-tools", "aliases": ["scvi-tools", "scvi tools", "scvi"]},
    {"public_key": "BI-LIB-011", "public_name": "BioIntel Multi-Omics Integration Engine", "upstream_name": "Muon", "aliases": ["Muon", "MuON"]},
    {"public_key": "BI-LIB-012", "public_name": "BioIntel Spatial Omics Engine", "upstream_name": "Squidpy", "aliases": ["Squidpy"]},
    {"public_key": "BI-LIB-013", "public_name": "BioIntel Curated Pipeline Library", "upstream_name": "nf-core", "aliases": ["nf-core", "nf core"]},
    {"public_key": "BI-LIB-014", "public_name": "BioIntel Protein Language Engine", "upstream_name": "ESM", "aliases": ["ESMFold", "ESM-2", "facebookresearch/esm"]},
    {"public_key": "BI-LIB-015", "public_name": "BioIntel Variant File Engine", "upstream_name": "pysam", "aliases": ["pysam"]},
    {"public_key": "BI-LIB-016", "public_name": "BioIntel Local AI Runtime", "upstream_name": "Ollama", "aliases": ["Ollama", "ollama"]},
    {"public_key": "BI-LIB-017", "public_name": "BioIntel Document Recognition Engine", "upstream_name": "Tesseract OCR", "aliases": ["Tesseract OCR", "Tesseract"]},
)

_GENERIC_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bexternal scientific engines?\b", re.I), "BioIntel scientific engines"),
    (re.compile(r"\bexternal engines?\b", re.I), "BioIntel engines"),
    (re.compile(r"\bexternal model qualification\b", re.I), "BioIntel model qualification"),
    (re.compile(r"\bthird[- ]party scientific engines?\b", re.I), "licensed BioIntel scientific engines"),
    (re.compile(r"\bthird[- ]party engines?\b", re.I), "licensed BioIntel engines"),
    (re.compile(r"\bupstream engine\b", re.I), "BioIntel engine component"),
)

_URL_PATTERN = re.compile(
    r"(?:git\s+clone\s+)?https?://(?:www\.)?(?:github\.com|bioconda\.github\.io|raw\.githubusercontent\.com)/[^\s)`\]}>]+",
    re.I,
)


_PUBLIC_FIELD_LABELS = {
    "artifact_url": "BioIntel managed asset",
    "binary_path": "BioIntel runtime location",
    "command": "BioIntel managed operation",
    "conda_packages": "BioIntel environment packages",
    "executable": "BioIntel runtime location",
    "executable_candidates": "BioIntel runtime candidates",
    "install_command": "BioIntel setup operation",
    "licence_url": "BioIntel licence record",
    "official_url": "BioIntel official source",
    "package_specs": "BioIntel package specification",
    "path_or_command": "BioIntel runtime operation",
    "pip_packages": "BioIntel Python packages",
    "repository": "BioIntel managed repository",
    "repository_url": "BioIntel repository reference",
    "source_repository": "BioIntel source repository",
    "source_url": "BioIntel source reference",
    "upstream_component": "BioIntel licensed component",
    "upstream_label": "BioIntel component label",
    "upstream_name": "BioIntel component name",
    "upstream_url": "BioIntel component reference",
    "version_probe": "BioIntel version check",
}

_SENSITIVE_KEYS = {
    "artifact_url",
    "binary_path",
    "command",
    "conda_packages",
    "executable",
    "executable_candidates",
    "install_command",
    "licence_url",
    "official_url",
    "package_specs",
    "path_or_command",
    "pip_packages",
    "repository",
    "repository_url",
    "source_repository",
    "source_url",
    "upstream_component",
    "upstream_label",
    "upstream_name",
    "upstream_url",
    "version_probe",
}


def _read_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if ALIAS_PATH.is_file():
        try:
            payload = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
            raw = payload.get("records", []) if isinstance(payload, dict) else []
            if isinstance(raw, list):
                records.extend(item for item in raw if isinstance(item, dict))
        except (OSError, json.JSONDecodeError):
            pass
    records.extend(_BUILTIN_RECORDS)
    return records


@lru_cache(maxsize=1)
def _maps() -> tuple[dict[str, str], re.Pattern[str] | None, dict[str, str]]:
    exact: dict[str, str] = {}
    strong: dict[str, str] = {}
    for record in _read_records():
        public_name = str(record.get("public_name", "")).strip()
        if not public_name:
            continue
        aliases = [
            str(record.get("upstream_name", "")).strip(),
            str(record.get("internal_id", "")).strip(),
            *[str(value).strip() for value in record.get("aliases", []) if str(value).strip()],
        ]
        for alias in aliases:
            if not alias:
                continue
            exact.setdefault(alias.casefold(), public_name)
            # Distinctive names can be safely replaced inside prose. Short/common
            # identifiers remain exact-cell replacements only.
            if len(alias) >= 5 or any(char in alias for char in ".+-/0123456789"):
                strong.setdefault(alias.casefold(), public_name)
    if strong:
        alternatives = "|".join(
            re.escape(alias) for alias in sorted(strong, key=lambda item: (-len(item), item))
        )
        combined = re.compile(
            rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])",
            re.I,
        )
    else:
        combined = None
    return exact, combined, strong


@lru_cache(maxsize=1)
def _public_key_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for record in _read_records():
        public_key = str(record.get("public_key", "")).strip()
        if not public_key:
            continue
        aliases = [
            str(record.get("upstream_name", "")).strip(),
            str(record.get("internal_id", "")).strip(),
            *[str(value).strip() for value in record.get("aliases", []) if str(value).strip()],
        ]
        for alias in aliases:
            if alias:
                result.setdefault(alias.casefold(), public_key)
    return result


def public_engine_name(value: object, fallback: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback or "BioIntel Scientific Engine"
    exact, _pattern, _strong = _maps()
    return exact.get(text.casefold(), fallback or text)


def public_engine_key(value: object, fallback: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback or "BI-ENG"
    return _public_key_map().get(text.casefold(), fallback or text)


def brand_public_text(value: object, *, allow_legal: bool = False) -> object:
    if allow_legal or not isinstance(value, str) or not value:
        return value
    exact, combined, strong = _maps()
    stripped = value.strip()
    mapped = exact.get(stripped.casefold())
    if mapped is not None:
        prefix = value[: len(value) - len(value.lstrip())]
        suffix = value[len(value.rstrip()) :]
        return f"{prefix}{mapped}{suffix}"

    result = _URL_PATTERN.sub("BioIntel managed component source", value)
    if combined is not None:
        result = combined.sub(lambda match: strong.get(match.group(0).casefold(), match.group(0)), result)
    for pattern, replacement in _GENERIC_PHRASES:
        result = pattern.sub(replacement, result)
    # Do not expose raw repository commands in normal product surfaces.
    result = re.sub(r"\bgit\s+clone\b[^\n]*", "Run BIOINTEL_ENGINE_SETUP.bat", result, flags=re.I)
    return result


def _public_field_label(key: object, *, allow_legal: bool = False) -> object:
    if allow_legal:
        return key
    key_text = str(key)
    return _PUBLIC_FIELD_LABELS.get(key_text.casefold(), brand_public_text(key_text))


def _brand_mapping(value: dict[Any, Any], *, allow_legal: bool) -> dict[Any, Any]:
    branded: dict[Any, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        public_key = _public_field_label(key_text, allow_legal=allow_legal)
        if not allow_legal and key_text.casefold() in _SENSITIVE_KEYS and item not in (None, "", [], (), {}):
            branded[public_key] = "Managed internally by BioIntel"
        else:
            branded[public_key] = brand_public_value(item, allow_legal=allow_legal)
    return branded


def brand_public_value(value: Any, *, allow_legal: bool = False) -> Any:
    if allow_legal:
        return value
    if isinstance(value, str):
        return brand_public_text(value, allow_legal=False)
    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8")
        except UnicodeDecodeError:
            return value
        return str(brand_public_text(decoded)).encode("utf-8")
    if isinstance(value, dict):
        return _brand_mapping(value, allow_legal=False)
    if isinstance(value, list):
        return [brand_public_value(item, allow_legal=False) for item in value]
    if isinstance(value, tuple):
        return tuple(brand_public_value(item, allow_legal=False) for item in value)
    if isinstance(value, set):
        return {brand_public_value(item, allow_legal=False) for item in value}

    # Pandas is optional at import time; handle it lazily.
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            frame = value.copy()
            original_columns = list(frame.columns)
            renamed = [_public_field_label(column, allow_legal=False) for column in original_columns]
            frame.columns = renamed
            for original_column, public_column in zip(original_columns, renamed):
                original_name = str(original_column).casefold()
                if original_name in _SENSITIVE_KEYS:
                    frame[public_column] = frame[public_column].map(
                        lambda item: "Managed internally by BioIntel" if item not in (None, "") else item
                    )
                elif frame[public_column].dtype == object:
                    frame[public_column] = frame[public_column].map(
                        lambda item: brand_public_value(item, allow_legal=False)
                    )
            return frame
        if isinstance(value, pd.Series):
            return value.map(lambda item: brand_public_value(item, allow_legal=False))
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return value


def brand_download_payload(data: Any, *, mime: str | None = None, allow_legal: bool = False) -> Any:
    if allow_legal:
        return data
    mime_text = str(mime or "").casefold()
    if isinstance(data, str):
        return brand_public_text(data)
    if isinstance(data, bytes) and (
        not mime_text
        or mime_text.startswith("text/")
        or any(token in mime_text for token in ("json", "csv", "xml", "yaml"))
    ):
        return brand_public_value(data)
    return data


def clear_branding_cache() -> None:
    _maps.cache_clear()
    _public_key_map.cache_clear()
