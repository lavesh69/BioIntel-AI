from __future__ import annotations

"""Unified registry and fail-safe readiness probes for BioIntel integrations."""

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from biointel.integrations.runtime_manager import python_probe
from biointel.tools.runtime import resolve_tool, tool_version

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "config" / "biointel_scientific_integrations.json"


@dataclass(frozen=True)
class IntegrationSpec:
    integration_id: str
    public_key: str
    public_name: str
    category: str
    priority: str
    execution_mode: str
    backend: str
    runtime_profile: str
    target_modules: tuple[str, ...]
    module_pages: tuple[str, ...]
    capabilities: tuple[str, ...]
    operations: tuple[str, ...]
    python_modules: tuple[str, ...] = ()
    distributions: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    readiness_policy: str = "any"
    setup_profile: str = "BioIntel managed"
    weight_or_database_required: bool = False
    timeout_seconds: int = 300
    public_boundary: str = "Research-use integration."


@dataclass(frozen=True)
class IntegrationStatus:
    integration_id: str
    public_key: str
    public_name: str
    category: str
    priority: str
    execution_mode: str
    target_modules: tuple[str, ...]
    capabilities: tuple[str, ...]
    operations: tuple[str, ...]
    state: str
    ready: bool
    detected_components: int
    required_components: int
    version: str | None
    setup_profile: str
    qualification_note: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "public_key": self.public_key,
            "name": self.public_name,
            "priority": self.priority,
            "category": self.category,
            "state": self.state,
            "ready": self.ready,
            "execution_mode": self.execution_mode,
            "target_modules": list(self.target_modules),
            "capabilities": list(self.capabilities),
            "operations": list(self.operations),
            "detected_components": self.detected_components,
            "required_components": self.required_components,
            "version": self.version or "Managed by BioIntel",
            "setup_profile": self.setup_profile,
            "qualification_note": self.qualification_note,
        }


def _tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@lru_cache(maxsize=1)
def integration_catalog() -> tuple[IntegrationSpec, ...]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    rows = payload.get("integrations", [])
    catalog = tuple(
        IntegrationSpec(
            integration_id=str(row["integration_id"]),
            public_key=str(row["public_key"]),
            public_name=str(row["public_name"]),
            category=str(row["category"]),
            priority=str(row.get("priority", "P1")),
            execution_mode=str(row["execution_mode"]),
            backend=str(row.get("backend", "main_python")),
            runtime_profile=str(row.get("runtime_profile", "core")),
            target_modules=_tuple(row.get("target_modules")),
            module_pages=_tuple(row.get("module_pages")),
            capabilities=_tuple(row.get("capabilities")),
            operations=_tuple(row.get("operations")),
            python_modules=_tuple(row.get("probe", {}).get("python_modules")),
            distributions=_tuple(row.get("probe", {}).get("distributions")),
            tool_ids=_tuple(row.get("probe", {}).get("tool_ids")),
            readiness_policy=str(row.get("readiness_policy", "any")).casefold(),
            setup_profile=str(row.get("setup_profile", "BioIntel managed")),
            weight_or_database_required=bool(row.get("weight_or_database_required", False)),
            timeout_seconds=max(30, int(row.get("timeout_seconds", 300))),
            public_boundary=str(row.get("public_boundary", "Research-use integration.")),
        )
        for row in rows
        if isinstance(row, dict)
    )
    if len({item.integration_id for item in catalog}) != len(catalog):
        raise ValueError("Duplicate BioIntel integration identifiers are not allowed.")
    if len({item.public_key for item in catalog}) != len(catalog):
        raise ValueError("Duplicate BioIntel public integration keys are not allowed.")
    return catalog


def _tool_probe(tool_ids: tuple[str, ...]) -> tuple[int, int, str | None]:
    detected = 0
    version: str | None = None
    for tool_id in tool_ids:
        resolution = resolve_tool(tool_id)
        if resolution.available:
            detected += 1
            if version is None:
                raw = tool_version(tool_id)
                version = raw if not raw.startswith("Unavailable") else None
    return detected, len(tool_ids), version


def integration_status(spec: IntegrationSpec) -> IntegrationStatus:
    detected = 0
    required = 0
    version: str | None = None

    if spec.backend in {"main_python", "isolated_python", "desktop_companion"}:
        probe = python_probe(spec.runtime_profile, spec.python_modules, spec.distributions)
        detected += int(probe.get("detected", 0))
        required += int(probe.get("required", len(spec.python_modules)))
        version = str(probe.get("version")) if probe.get("version") else None

    if spec.tool_ids:
        tool_detected, tool_required, tool_runtime_version = _tool_probe(spec.tool_ids)
        detected += tool_detected
        required += tool_required
        version = version or tool_runtime_version

    if required == 0:
        ready = False
    elif spec.readiness_policy == "all":
        ready = detected == required
    else:
        ready = detected > 0

    if ready and spec.weight_or_database_required:
        state = "Runtime ready · assets require qualification"
        note = "The BioIntel runtime is detected; project-specific model assets or reference databases must pass qualification before scientific release."
    elif ready:
        state = "Ready"
        note = "The BioIntel execution adapter is available. Outputs remain subject to module-specific validation and review."
    else:
        state = "Setup required"
        note = f"Run BIOINTEL_ENGINE_SETUP.bat and select {spec.priority}. Core BioIntel remains usable while this optional integration is absent."

    return IntegrationStatus(
        integration_id=spec.integration_id,
        public_key=spec.public_key,
        public_name=spec.public_name,
        category=spec.category,
        priority=spec.priority,
        execution_mode=spec.execution_mode,
        target_modules=spec.target_modules,
        capabilities=spec.capabilities,
        operations=spec.operations,
        state=state,
        ready=ready,
        detected_components=detected,
        required_components=required,
        version=version,
        setup_profile=spec.setup_profile,
        qualification_note=note,
    )


def integration_status_rows() -> list[dict[str, Any]]:
    return [integration_status(spec).public_dict() for spec in integration_catalog()]


def integration_summary() -> dict[str, Any]:
    rows = integration_status_rows()
    ready = sum(bool(row["ready"]) for row in rows)
    by_priority = {
        priority: {
            "total": sum(row["priority"] == priority for row in rows),
            "ready": sum(row["priority"] == priority and bool(row["ready"]) for row in rows),
        }
        for priority in ("P0", "P1", "P2")
    }
    return {
        "schema": "biointel.scientific-integrations.public-status.v2",
        "total": len(rows),
        "ready": ready,
        "setup_required": len(rows) - ready,
        "priorities": by_priority,
        "integrations": rows,
        "identity_policy": "BioIntel public identities on normal product surfaces",
        "execution_contract": "Audited isolated execution with timeout, logs, artifacts and provenance",
        "legal_notices": "/legal/components",
    }


def integrations_for_page(page_path: str) -> tuple[IntegrationSpec, ...]:
    normalized = page_path.replace("\\", "/")
    return tuple(spec for spec in integration_catalog() if normalized in spec.module_pages)


def integrations_for_module(module_name: str) -> tuple[IntegrationSpec, ...]:
    key = module_name.strip().casefold()
    return tuple(spec for spec in integration_catalog() if any(key == name.casefold() for name in spec.target_modules))
