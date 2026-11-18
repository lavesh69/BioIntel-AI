from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

import pandas as pd

from biointel.runtime_v170.catalog import engine_catalog, reference_catalog

from .catalog import TARGET_MODULES


@dataclass(frozen=True)
class EngineProbe:
    engine: str
    label: str
    required: bool
    discovered: bool
    executable: str
    version: str
    probe_status: str
    platform_target: str
    install_route: str


@dataclass(frozen=True)
class ReferenceProbe:
    reference_id: str
    label: str
    required: bool
    path: str
    present: bool
    release_pinned: bool
    checksum_verified: bool
    licence_accepted: bool
    schema_validated: bool
    scientific_reviewed: bool
    qualification_status: str


def _module_match(value: Any, module_key: str) -> bool:
    return module_key in {item.strip() for item in str(value or "").split(",") if item.strip()}


def required_engines(module_key: str) -> pd.DataFrame:
    if module_key not in TARGET_MODULES:
        raise KeyError(module_key)
    frame = engine_catalog()
    return frame[frame["modules"].map(lambda value: _module_match(value, module_key))].reset_index(drop=True)


def required_references(module_key: str) -> pd.DataFrame:
    if module_key not in TARGET_MODULES:
        raise KeyError(module_key)
    frame = reference_catalog()
    return frame[frame["modules"].map(lambda value: _module_match(value, module_key))].reset_index(drop=True)


def _version_probe(executable: str, smoke_test: str, *, execute: bool) -> tuple[str, str]:
    if not execute:
        return "not executed", "discovered"
    command = [item.strip() for item in str(smoke_test or "").split(",") if item.strip()]
    if not command:
        command = [executable, "--version"]
    else:
        command[0] = executable
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc), "probe-failed"
    output = (completed.stdout or completed.stderr or "").strip().replace("\x00", " ")
    output = " ".join(output.split())[:500]
    return output or f"exit={completed.returncode}", "pass" if completed.returncode == 0 else "probe-failed"


def probe_engines(module_key: str, *, execute_smoke_tests: bool = False) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in required_engines(module_key).to_dict(orient="records"):
        engine = str(item["engine"])
        candidates = [engine, str(item.get("label") or "").split()[0].lower()]
        executable = next((path for name in candidates if name and (path := shutil.which(name))), "")
        version, status = _version_probe(executable, str(item.get("smoke_test") or ""), execute=execute_smoke_tests) if executable else ("not found", "missing")
        rows.append(asdict(EngineProbe(
            engine=engine,
            label=str(item.get("label") or engine),
            required=True,
            discovered=bool(executable),
            executable=executable,
            version=version,
            probe_status=status,
            platform_target=str(item.get("platform_target") or ""),
            install_route=str(item.get("install_route") or ""),
        )))
    return pd.DataFrame(rows)


def _reference_roots(root: str | Path) -> list[Path]:
    project = Path(root).resolve()
    env_root = os.environ.get("BIOINTEL_REFERENCE_ROOT", "").strip()
    candidates = [
        Path(env_root).expanduser() if env_root else None,
        project / "UserData" / "reference_databases",
        project / "UserData" / "step170" / "references",
        project / "data" / "references",
    ]
    return [path.resolve() for path in candidates if path is not None]


def _manifest_flags(folder: Path) -> dict[str, bool]:
    import json
    manifests = [folder / "qualification_manifest.json", folder / "manifest.json", folder / "reference_manifest.json"]
    manifest = next((path for path in manifests if path.is_file()), None)
    if manifest is None:
        return {"release_pinned": False, "checksum_verified": False, "licence_accepted": False, "schema_validated": False, "scientific_reviewed": False}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"release_pinned": False, "checksum_verified": False, "licence_accepted": False, "schema_validated": False, "scientific_reviewed": False}
    aliases = {
        "release_pinned": ("release_pinned", "release_pin_complete", "version_locked"),
        "checksum_verified": ("checksum_verified", "sha256_verified", "provider_checksum_verified"),
        "licence_accepted": ("licence_accepted", "license_accepted", "terms_accepted"),
        "schema_validated": ("schema_validated", "schema_validation_complete"),
        "scientific_reviewed": ("scientific_reviewed", "scientific_review_complete"),
    }
    return {name: any(bool(payload.get(alias)) for alias in names) for name, names in aliases.items()}


def probe_references(root: str | Path, module_key: str) -> pd.DataFrame:
    roots = _reference_roots(root)
    rows: list[dict[str, Any]] = []
    for item in required_references(module_key).to_dict(orient="records"):
        reference_id = str(item["reference_id"])
        folder = next((base / reference_id for base in roots if (base / reference_id).exists()), roots[0] / reference_id)
        flags = _manifest_flags(folder) if folder.exists() else {"release_pinned": False, "checksum_verified": False, "licence_accepted": False, "schema_validated": False, "scientific_reviewed": False}
        qualified = bool(folder.exists() and all(flags.values()))
        rows.append(asdict(ReferenceProbe(
            reference_id=reference_id,
            label=str(item.get("label") or reference_id),
            required=True,
            path=str(folder),
            present=folder.exists(),
            release_pinned=flags["release_pinned"],
            checksum_verified=flags["checksum_verified"],
            licence_accepted=flags["licence_accepted"],
            schema_validated=flags["schema_validated"],
            scientific_reviewed=flags["scientific_reviewed"],
            qualification_status="qualified" if qualified else "review",
        )))
    return pd.DataFrame(rows)


def host_summary() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "cpu_threads": os.cpu_count() or 0,
        "wsl_available": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
    }


__all__ = ["EngineProbe", "ReferenceProbe", "host_summary", "probe_engines", "probe_references", "required_engines", "required_references"]
