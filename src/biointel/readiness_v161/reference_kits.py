from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

import pandas as pd

from biointel.scientific_depth.profiles import MODULE_PROFILES


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:80] or "reference"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_development_reference_kits(root: str | Path) -> list[Path]:
    root_path = Path(root).expanduser().resolve()
    base = root_path / "data" / "step161" / "development_reference_kits"
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for module_key, profile in sorted(MODULE_PROFILES.items()):
        module_dir = base / module_key
        module_dir.mkdir(parents=True, exist_ok=True)
        for index, reference in enumerate(profile.references, start=1):
            stem = f"{index:02d}-{_slug(reference)}"
            payload_path = module_dir / f"{stem}.fixture.json"
            fixture = {
                "schema": "biointel.step161.development-reference-fixture.v1",
                "module_key": module_key,
                "module_title": profile.title,
                "reference_name": reference,
                "scope": "development-and-regression-only",
                "synthetic": True,
                "records": [
                    {
                        "record_id": f"{module_key}:{index}:demo",
                        "reference_label": reference,
                        "status": "test-fixture",
                        "value": 1.0,
                    }
                ],
                "production_use_allowed": False,
                "external_scientific_evidence": False,
            }
            payload_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            checksum = _sha256(payload_path)
            manifest_path = module_dir / f"{stem}.devref.json"
            manifest = {
                "schema": "biointel.step161.development-reference-manifest.v1",
                "asset_id": f"step161-devref-{module_key}-{index:02d}",
                "module_key": module_key,
                "reference_name": reference,
                "version": "step161-demo-v1",
                "scope": "development-and-regression-only",
                "status": "verified-development-fixture",
                "local_path": payload_path.name,
                "sha256": checksum,
                "licence_class": "BioIntel synthetic fixture",
                "licence_accepted": True,
                "checksum_verified": True,
                "production_use_allowed": False,
                "replacement_required_for_confirmatory_use": True,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.extend([payload_path, manifest_path])
    return written


def development_reference_readiness(
    root: str | Path,
    module_keys: Iterable[str] | None = None,
) -> pd.DataFrame:
    root_path = Path(root).expanduser().resolve()
    keys = sorted(set(module_keys or MODULE_PROFILES))
    base = root_path / "data" / "step161" / "development_reference_kits"
    rows: list[dict[str, Any]] = []
    for module_key in keys:
        profile = MODULE_PROFILES[module_key]
        manifests = list((base / module_key).glob("*.devref.json")) if (base / module_key).exists() else []
        by_reference: dict[str, dict[str, Any]] = {}
        for path in manifests:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            by_reference[str(payload.get("reference_name") or "")] = {"path": path, **payload}
        for reference in profile.references:
            payload = by_reference.get(reference, {})
            manifest_path = payload.get("path")
            local_name = str(payload.get("local_path") or "")
            local_path = manifest_path.parent / local_name if isinstance(manifest_path, Path) and local_name else Path()
            exists = bool(local_name and local_path.is_file())
            actual = _sha256(local_path) if exists else ""
            expected = str(payload.get("sha256") or "")
            verified = bool(exists and expected and actual == expected)
            qualified = bool(
                verified
                and payload.get("scope") == "development-and-regression-only"
                and payload.get("production_use_allowed") is False
                and payload.get("licence_accepted") is True
            )
            rows.append(
                {
                    "module_key": module_key,
                    "reference": reference,
                    "manifest_present": bool(payload),
                    "fixture_present": exists,
                    "checksum_verified": verified,
                    "development_qualified": qualified,
                    "scope": str(payload.get("scope") or "missing"),
                    "production_use_allowed": bool(payload.get("production_use_allowed", False)),
                    "replacement_required_for_confirmatory_use": bool(payload.get("replacement_required_for_confirmatory_use", True)),
                    "manifest_path": str(manifest_path or ""),
                    "fixture_path": str(local_path) if exists else "",
                }
            )
    return pd.DataFrame(rows)


def development_reference_summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema": "biointel.step161.development-reference-summary.v1",
        "required_assets": int(len(frame)),
        "development_qualified": int(frame["development_qualified"].astype(bool).sum()) if not frame.empty else 0,
        "all_development_references_ready": bool(not frame.empty and frame["development_qualified"].astype(bool).all()),
        "production_references_not_inferred": True,
        "confirmatory_use_requires_replacement": True,
    }


__all__ = [
    "development_reference_readiness",
    "development_reference_summary",
    "ensure_development_reference_kits",
]
