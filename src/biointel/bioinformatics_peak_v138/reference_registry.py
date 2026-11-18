from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from functools import lru_cache
from typing import Any

import pandas as pd

from .native_profiles import profile_for


def _sha256_file(path: Path) -> str:
    stat = path.stat()
    return _cached_sha256_file(str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns))


@lru_cache(maxsize=512)
def _cached_sha256_file(path_text: str, size_bytes: int, modified_ns: int) -> str:
    # Size and mtime are part of the cache key, so changed reference assets are
    # re-hashed automatically while unchanged multi-GB assets avoid repeated I/O.
    del size_bytes, modified_ns
    digest = sha256()
    with Path(path_text).open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=32)
def _cached_available_assets(asset_root_text: str, limit: int, root_mtime_ns: int) -> tuple[tuple[str, int, float], ...]:
    del root_mtime_ns
    root = Path(asset_root_text)
    rows: list[tuple[str, int, float]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        rows.append((path.relative_to(root).as_posix(), int(stat.st_size), float(stat.st_mtime)))
        if len(rows) >= max(1, min(int(limit), 50_000)):
            break
    return tuple(rows)


class ReferenceRegistry:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.project_root / "UserData").resolve()
        self.state_dir = user_root / "bioinformatics_peak_v139"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.state_dir / "reference_bindings.json"
        self.asset_root = Path(os.environ.get("BIOINTEL_REFERENCE_ASSETS_DIR") or self.project_root / "data" / "reference_assets").resolve()
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {"schema": "biointel.bioinformatics.reference_bindings.v139", "modules": {}}
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Reference binding document must be an object")
            payload.setdefault("schema", "biointel.bioinformatics.reference_bindings.v139")
            payload.setdefault("modules", {})
            return payload
        except Exception as exc:
            raise ValueError(f"Reference binding file is invalid: {exc}") from exc

    def _save(self, payload: dict[str, Any]) -> None:
        payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        partial = self.config_path.with_suffix(".json.partial")
        partial.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        partial.replace(self.config_path)

    def available_assets(self, *, limit: int = 5000) -> pd.DataFrame:
        root_stat = self.asset_root.stat()
        cached = _cached_available_assets(str(self.asset_root), int(limit), int(root_stat.st_mtime_ns))
        return pd.DataFrame(cached, columns=["relative_path", "size_bytes", "modified_at"])

    @staticmethod
    def clear_caches() -> None:
        _cached_sha256_file.cache_clear()
        _cached_available_assets.cache_clear()

    def bind(self, module_key: str, requirement: str, relative_path: str, *, pin_checksum: bool = True) -> dict[str, Any]:
        profile = profile_for(module_key)
        if requirement not in profile.reference_assets:
            raise ValueError(f"Unknown reference requirement for {module_key}: {requirement}")
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ValueError("Reference path must be relative to the configured reference asset root")
        resolved = (self.asset_root / relative).resolve()
        try:
            resolved.relative_to(self.asset_root)
        except ValueError as exc:
            raise ValueError("Reference path escapes the configured asset root") from exc
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        digest = _sha256_file(resolved) if pin_checksum else ""
        payload = self._load()
        modules = payload.setdefault("modules", {})
        module = modules.setdefault(module_key, {})
        record = {
            "path": relative.as_posix(),
            "sha256": digest,
            "size_bytes": resolved.stat().st_size,
            "bound_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        module[requirement] = record
        self._save(payload)
        self.clear_caches()
        return {"requirement": requirement, **record}

    def unbind(self, module_key: str, requirement: str) -> None:
        payload = self._load()
        module = payload.setdefault("modules", {}).setdefault(module_key, {})
        module.pop(requirement, None)
        self._save(payload)
        self.clear_caches()

    def table(self, module_key: str) -> pd.DataFrame:
        profile = profile_for(module_key)
        payload = self._load()
        module = dict(payload.get("modules", {}).get(module_key, {}))
        rows: list[dict[str, Any]] = []
        for requirement in profile.reference_assets:
            binding = dict(module.get(requirement, {}))
            relative = str(binding.get("path", "")).strip()
            expected = str(binding.get("sha256", "")).lower().strip()
            status = "Not bound"
            actual = ""
            size = 0
            if relative:
                candidate = (self.asset_root / relative).resolve()
                try:
                    candidate.relative_to(self.asset_root)
                except ValueError:
                    status = "Unsafe path blocked"
                else:
                    if not candidate.is_file():
                        status = "Missing file"
                    else:
                        size = candidate.stat().st_size
                        actual = _sha256_file(candidate)
                        if expected:
                            status = "Verified" if actual == expected else "Checksum mismatch"
                        else:
                            status = "Present; checksum not pinned"
            rows.append({
                "Reference asset": requirement,
                "Binding": relative or "—",
                "Expected SHA-256": expected or "—",
                "Actual SHA-256": actual or "—",
                "Size bytes": size,
                "Status": status,
            })
        return pd.DataFrame(rows)

    def verified_paths(self, module_key: str) -> dict[str, str]:
        table = self.table(module_key)
        output: dict[str, str] = {}
        for _, row in table.iterrows():
            if row["Status"] == "Verified":
                output[str(row["Reference asset"])] = str((self.asset_root / str(row["Binding"])).resolve())
        return output


__all__ = ["ReferenceRegistry"]
