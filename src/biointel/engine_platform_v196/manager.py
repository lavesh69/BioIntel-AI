from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, detect_engine

from .catalog import adapter_catalog, engine_platform_catalog, release_manifest
from .packs import EnginePackError, extract_pack, inspect_pack, sha256_file
from .paths import engine_home, tools_root
from .services import production_service_status
from .state import EngineStateStore, utc_now


class PlanState(str, Enum):
    READY_OFFLINE_PACK = "ready-offline-pack"
    READY_QUALIFIED_ONLINE = "ready-qualified-online"
    ALREADY_AVAILABLE = "already-available"
    REQUIRES_RELEASE_MANIFEST = "requires-release-manifest"
    REQUIRES_REFERENCE_PACK = "requires-reference-pack"
    REQUIRES_MODEL_PACK = "requires-model-pack"
    REQUIRES_USER_AUTHORIZATION = "requires-user-authorization"
    REQUIRES_WSL2 = "requires-wsl2"
    BLOCKED_LEGAL_REVIEW = "blocked-legal-review"


@dataclass(frozen=True)
class InstallPlan:
    engine: str
    label: str
    state: PlanState
    backend: str
    pack_key: str
    commands: tuple[tuple[str, ...], ...]
    prerequisites: tuple[str, ...]
    blockers: tuple[str, ...]
    references: tuple[str, ...]
    estimated_tool_size: str
    estimated_reference_size: str
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["commands"] = [list(command) for command in self.commands]
        return payload


class EngineManager:
    def __init__(self, *, project: str | Path | None = None, user_data: str | Path | None = None, store: EngineStateStore | None = None) -> None:
        self.project = Path(project).resolve() if project else Path(__file__).resolve().parents[3]
        self.user_data = Path(user_data).resolve() if user_data else None
        self.home = engine_home(self.user_data)
        self.tools = tools_root(self.user_data)
        self.store = store or EngineStateStore(user_data=self.user_data)

    def catalog(self, *, probe_runtime: bool = False) -> pd.DataFrame:
        base = engine_platform_catalog(probe_runtime=probe_runtime, root=self.project)
        state = self.store.inventory()
        if state.empty:
            for column, default in (("state", "not-installed"), ("backend", ""), ("version", ""), ("executable", ""), ("qualified", 0), ("message", "")):
                base[f"local_{column}"] = default
            return base
        state = state.rename(columns={column: f"local_{column}" for column in state.columns if column != "engine"})
        return base.merge(state, on="engine", how="left").fillna({"local_state": "not-installed", "local_qualified": 0})

    def probe(self, engine: str) -> dict[str, Any]:
        key = str(engine).lower()
        if key not in ENGINE_REGISTRY:
            raise KeyError(key)
        existing = self.store.get_engine(key) or {}
        registered = Path(str(existing.get("executable", ""))).expanduser()
        status = None
        if registered.is_file():
            spec = ENGINE_REGISTRY[key]
            try:
                completed = subprocess.run(
                    [str(registered), *spec.version_args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
                )
                version = (completed.stdout + "\n" + completed.stderr).strip()[:2000]
                available = completed.returncode == 0 or bool(version)
                executable = str(registered.resolve())
                note = "Managed executable probe" if available else "Managed executable version probe failed"
            except (OSError, subprocess.TimeoutExpired) as exc:
                available = False
                version = ""
                executable = str(registered.resolve())
                note = f"Managed executable probe failed: {type(exc).__name__}"
            label = spec.label
        else:
            status = detect_engine(key, timeout_seconds=5.0)
            available = bool(status.available)
            version = status.version
            executable = status.executable or ""
            note = status.note
            label = status.label
        executable_hash = ""
        path = Path(executable) if executable else None
        if path and path.is_file() and path.name.lower() not in {"python", "python.exe"}:
            try:
                executable_hash = sha256_file(path)
            except OSError:
                executable_hash = ""
        state = "available-unqualified" if available else "not-installed"
        qualified = bool(existing.get("qualified", 0)) and available
        if qualified:
            state = "qualified-ready"
        self.store.upsert_engine(
            key,
            state=state,
            backend=str(existing.get("backend", "detected-path")),
            version=version,
            executable=executable,
            executable_sha256=executable_hash,
            qualified=qualified,
            last_probe_utc=utc_now(),
            message=note,
        )
        return {
            "engine": key,
            "label": label,
            "available": available,
            "qualified": qualified,
            "state": state,
            "executable": executable,
            "version": version,
            "executable_sha256": executable_hash,
            "note": note,
        }

    def probe_all(self) -> pd.DataFrame:
        return pd.DataFrame([self.probe(key) for key in sorted(ENGINE_REGISTRY)])

    def _catalog_row(self, engine: str) -> dict[str, Any]:
        frame = engine_platform_catalog(root=self.project)
        rows = frame.loc[frame["engine"] == engine]
        if rows.empty:
            raise KeyError(engine)
        return rows.iloc[0].to_dict()

    def plan(self, engine: str, *, offline_pack: str | Path | None = None, prefer_native: bool = True) -> InstallPlan:
        key = str(engine).lower()
        row = self._catalog_row(key)
        detected = detect_engine(key, timeout_seconds=3.0)
        blockers = [item.strip() for item in str(row.get("blockers", "")).split("|") if item.strip()]
        prerequisites: list[str] = []
        commands: list[tuple[str, ...]] = []
        references = [item.strip() for item in str(row.get("required_databases", "")).split("|") if item.strip()]
        backend = "offline-engine-pack"
        state = PlanState.REQUIRES_RELEASE_MANIFEST

        if detected.available:
            state = PlanState.ALREADY_AVAILABLE
            backend = "detected-path"
        elif bool(row.get("licence_acceptance_required")) or str(row.get("automatic_bundle_policy")) == "never-auto-bundle":
            state = PlanState.REQUIRES_USER_AUTHORIZATION
            backend = "manual-authorized-provider"
            if offline_pack:
                inspection = inspect_pack(offline_pack)
                declared = {str(item.get("engine", "")).lower() for item in inspection["engines"]}
                if key not in declared:
                    raise EnginePackError(f"Pack does not declare engine '{key}'.")
                blockers.append("A verified offline pack is present, but explicit licence authorization is still required before extraction.")
        elif offline_pack:
            inspection = inspect_pack(offline_pack)
            declared = {str(item.get("engine", "")).lower() for item in inspection["engines"]}
            if key not in declared:
                raise EnginePackError(f"Pack does not declare engine '{key}'.")
            state = PlanState.READY_OFFLINE_PACK
            backend = "offline-engine-pack"
        elif bool(row.get("model_weights_required")):
            state = PlanState.REQUIRES_MODEL_PACK
            backend = "offline-model-pack"
        elif str(row.get("automatic_bundle_policy")) == "do-not-bundle-until-legal-review":
            state = PlanState.BLOCKED_LEGAL_REVIEW
        elif bool(row.get("install_manifest_complete")):
            state = PlanState.READY_QUALIFIED_ONLINE
            backend = str(row.get("install_route") or "qualified-release")
            pins = release_manifest(self.project).get("engines", {}).get(key, {})
            command = pins.get("install_command", [])
            if command:
                commands.append(tuple(str(value) for value in command))
        elif references:
            state = PlanState.REQUIRES_REFERENCE_PACK

        windows_mode = str(row.get("windows_mode", ""))
        if "WSL2" in windows_mode and state not in {PlanState.ALREADY_AVAILABLE, PlanState.READY_OFFLINE_PACK}:
            prerequisites.append("WSL2 with an approved Linux distribution")
            if state == PlanState.REQUIRES_RELEASE_MANIFEST:
                state = PlanState.REQUIRES_WSL2
        if references:
            prerequisites.append("Qualified reference/database pack: " + ", ".join(references))
        if bool(row.get("gpu_optional")):
            prerequisites.append("GPU is optional; CPU fallback depends on the selected engine release")
        if not bool(row.get("install_manifest_complete")):
            blockers.append("Exact version, artifact SHA-256, licence SHA-256 and target-machine smoke evidence are incomplete.")

        return InstallPlan(
            engine=key,
            label=str(row["label"]),
            state=state,
            backend=backend,
            pack_key=str(row["pack_key"]),
            commands=tuple(commands),
            prerequisites=tuple(dict.fromkeys(prerequisites)),
            blockers=tuple(dict.fromkeys(blockers)),
            references=tuple(references),
            estimated_tool_size=str(row.get("tool_size_band", "unknown")),
            estimated_reference_size=str(row.get("reference_size_band", "unknown")),
            claim_boundary="An installation plan is not execution or scientific qualification. BioIntel records readiness only after target-machine evidence passes.",
        )

    def install_pack(self, pack_path: str | Path, *, engines: list[str] | None = None, accept_restricted_licences: bool = False) -> dict[str, Any]:
        inspection = inspect_pack(pack_path)
        pack_id = inspection["pack_id"]
        if not pack_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in pack_id):
            raise EnginePackError("Invalid pack_id.")
        target = self.tools / "EnginePacks" / pack_id
        declared_from_inspection = {str(item.get("engine", "")).lower(): item for item in inspection.get("engines", [])}
        selected = sorted(set(str(item).lower() for item in (engines or declared_from_inspection)))
        unknown = [key for key in selected if key not in declared_from_inspection or key not in ENGINE_REGISTRY]
        if unknown:
            raise EnginePackError("Unknown or undeclared engines: " + ", ".join(unknown))
        catalog = engine_platform_catalog(root=self.project).set_index("engine")
        restricted = [key for key in selected if bool(catalog.loc[key, "licence_acceptance_required"])]
        if restricted and not accept_restricted_licences:
            raise EnginePackError(
                "Explicit user licence acceptance is required before extracting: " + ", ".join(restricted)
            )
        operation_id = uuid.uuid4().hex
        self.store.start_operation(operation_id, "install-pack", request={"pack": str(pack_path), "engines": engines or [], "accept_restricted_licences": bool(accept_restricted_licences)})
        try:
            result = extract_pack(pack_path, target)
            manifest = result["manifest"]
            declared = {str(item.get("engine", "")).lower(): item for item in manifest.get("engines", [])}
            states = []
            for key in selected:
                item = declared[key]
                relative_executable = str(item.get("executable", "")).strip()
                executable = (target / relative_executable).resolve() if relative_executable else Path("")
                if relative_executable:
                    try:
                        executable.relative_to(target.resolve())
                    except ValueError as exc:
                        raise EnginePackError(f"Executable for {key} escapes the pack directory.") from exc
                available = executable.is_file() if relative_executable else False
                source_qualified_claim = bool(item.get("qualified", False))
                qualified = False
                state = "installed-unqualified" if available else "pack-installed-executable-missing"
                version = str(item.get("version", ""))
                executable_hash = sha256_file(executable) if available else ""
                expected_hash = str(item.get("executable_sha256", ""))
                if expected_hash and executable_hash != expected_hash:
                    raise EnginePackError(f"Executable SHA-256 mismatch for {key}.")
                self.store.upsert_engine(key, state=state, backend="offline-engine-pack", version=version, executable=str(executable) if available else "", executable_sha256=executable_hash, pack_id=pack_id, qualified=qualified, last_probe_utc=utc_now(), message="Imported from verified offline pack")
                self.store.record_evidence(
                    key,
                    "pack-manifest",
                    "passed",
                    sha256=inspection["manifest_sha256"],
                    details={
                        "pack_id": pack_id,
                        "source_qualified_claim": source_qualified_claim,
                        "target_machine_qualification_required": True,
                        "restricted_licence_accepted": key in restricted and bool(accept_restricted_licences),
                    },
                )
                states.append({"engine": key, "state": state, "qualified": False, "executable": str(executable) if available else "", "target_machine_qualification_required": True})
            self.store.register_pack(pack_id, inspection["pack_version"], inspection["manifest_sha256"], str(target), "installed", {"engines": selected, "archive_sha256": inspection["archive_sha256"]})
            output = {"operation_id": operation_id, "pack_id": pack_id, "target": str(target), "engines": states, "status": "completed"}
            self.store.finish_operation(operation_id, "completed", output)
            return output
        except Exception as exc:
            self.store.finish_operation(operation_id, "failed", {"error": type(exc).__name__, "message": str(exc)})
            raise

    def uninstall(self, engine: str, *, remove_pack_when_unused: bool = False) -> dict[str, Any]:
        key = str(engine).lower()
        current = self.store.get_engine(key)
        if not current:
            return {"engine": key, "status": "not-installed"}
        pack_id = str(current.get("pack_id", ""))
        self.store.upsert_engine(key, state="not-installed", backend="", version="", executable="", executable_sha256="", pack_id="", qualified=False, last_probe_utc=utc_now(), message="Removed from BioIntel engine registry")
        removed_pack = False
        if remove_pack_when_unused and pack_id:
            inventory = self.store.inventory()
            in_use = not inventory[(inventory["pack_id"] == pack_id) & (inventory["state"] != "not-installed")].empty if not inventory.empty else False
            if not in_use:
                target = self.tools / "EnginePacks" / pack_id
                if target.exists():
                    shutil.rmtree(target)
                    removed_pack = True
        return {"engine": key, "status": "removed", "pack_removed": removed_pack}

    def repair(self, engine: str) -> dict[str, Any]:
        key = str(engine).lower()
        current = self.store.get_engine(key)
        probe = self.probe(key)
        if probe["available"]:
            return {"engine": key, "status": "healthy" if probe["qualified"] else "available-unqualified", "probe": probe}
        if current and current.get("pack_id"):
            pack_path = self.tools / "EnginePacks" / str(current["pack_id"])
            self.store.upsert_engine(key, state="repair-required", qualified=False, message=f"Pack exists={pack_path.exists()} but executable probe failed")
            return {"engine": key, "status": "repair-required", "pack_path": str(pack_path), "pack_exists": pack_path.exists()}
        return {"engine": key, "status": "not-installed", "plan": self.plan(key).to_dict()}

    def adapter_status(self) -> pd.DataFrame:
        frame = adapter_catalog(root=self.project).copy()
        states = {row["engine"]: row for row in self.store.inventory().to_dict(orient="records")} if not self.store.inventory().empty else {}
        frame["linked_engine_state"] = frame["linked_engine"].map(lambda key: states.get(key, {}).get("state", "") if key else "")
        frame["ready"] = frame.apply(lambda row: bool(row["available"] or row["linked_engine_state"] == "qualified-ready"), axis=1)
        return frame

    def service_status(self) -> pd.DataFrame:
        return production_service_status()

    def module_readiness(self, module_key: str) -> dict[str, Any]:
        catalog = self.catalog()
        matches = catalog[catalog["linked_modules"].astype(str).map(lambda value: module_key in [part.strip() for part in value.split("|") if part.strip()])]
        rows = []
        for row in matches.to_dict(orient="records"):
            rows.append({"engine": row["engine"], "label": row["label"], "state": row.get("local_state", "not-installed"), "qualified": bool(row.get("local_qualified", 0)), "priority": row["priority_tier"]})
        return {"module": module_key, "required_engines": rows, "qualified": sum(1 for row in rows if row["qualified"]), "total": len(rows), "claim_boundary": "Module readiness does not replace method-specific scientific validation."}

    def health_report(self) -> dict[str, Any]:
        catalog = self.catalog()
        adapters = self.adapter_status()
        services = self.service_status()
        integrity = self.store.integrity_check()
        return {
            "schema": "biointel.engine-platform.health.v1",
            "generated_at_utc": utc_now(),
            "registered_engines": int(len(catalog)),
            "qualified_engines": int(catalog.get("local_qualified", pd.Series(dtype=int)).fillna(0).astype(bool).sum()),
            "available_or_registered": int(catalog.get("local_state", pd.Series(dtype=str)).fillna("").isin(["available-unqualified", "qualified-ready", "installed-unqualified"]).sum()),
            "advanced_adapters": int(len(adapters)),
            "ready_adapters": int(adapters["ready"].sum()),
            "production_services": int(len(services)),
            "configured_services": int(services["configured"].sum()),
            "database": integrity,
            "wsl_detected": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
            "gpu_hint": bool(os.environ.get("CUDA_VISIBLE_DEVICES", "").strip() not in {"", "-1"}),
            "claim_boundary": "This health report describes software readiness only. It is not clinical, regulatory or wet-lab validation.",
        }

    def export_report(self, destination: str | Path) -> Path:
        output = Path(destination).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = self.health_report()
        payload["engines"] = self.catalog().where(pd.notna(self.catalog()), None).to_dict(orient="records")
        payload["adapters"] = self.adapter_status().where(pd.notna(self.adapter_status()), None).to_dict(orient="records")
        payload["services"] = self.service_status().where(pd.notna(self.service_status()), None).to_dict(orient="records")
        output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return output
