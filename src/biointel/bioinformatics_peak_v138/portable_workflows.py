from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .native_profiles import profile_for


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    digest: str
    runtime: str = "docker-or-apptainer"
    licence: str = "External tool licence applies"

    def __post_init__(self) -> None:
        if self.digest and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", self.digest):
            raise ValueError("Container digest must use sha256:<64 hex characters>.")


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    name: str
    command: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    cpu_cores: int = 1
    memory_gb: float = 2.0
    disk_gb: float = 5.0
    container: ContainerSpec | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.command or any(not isinstance(part, str) or not part.strip() for part in self.command):
            raise ValueError("Task command must be a non-empty argument vector.")
        forbidden = {"|", ";", "&&", "||", ">", "<", "`"}
        if any(part in forbidden for part in self.command):
            raise ValueError("Shell metacharacters are not allowed in portable task commands.")
        if self.cpu_cores < 1 or self.memory_gb <= 0 or self.disk_gb <= 0:
            raise ValueError("Task resources must be positive.")


@dataclass(frozen=True)
class PortableWorkflowPlan:
    workflow_id: str
    module_key: str
    version: str
    tasks: tuple[TaskSpec, ...]
    inputs: tuple[dict[str, Any], ...]
    outputs: tuple[dict[str, Any], ...]
    execution_profiles: tuple[str, ...] = ("local", "offline-windows", "hpc", "wes")
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        payload = {
            "schema": "biointel.portable_workflow.v140",
            "workflow_id": self.workflow_id,
            "module_key": self.module_key,
            "version": self.version,
            "tasks": [asdict(task) for task in self.tasks],
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "execution_profiles": list(self.execution_profiles),
            "metadata": self.metadata,
        }
        payload["workflow_digest"] = "sha256:" + sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return payload

    def wes_run_request(self, *, workflow_url: str = "workflow/main.cwl") -> dict[str, Any]:
        return {
            "workflow_params": {item["id"]: item.get("value") for item in self.inputs},
            "workflow_type": "CWL",
            "workflow_type_version": "v1.2",
            "tags": {"biointel_module": self.module_key, "workflow_id": self.workflow_id},
            "workflow_engine_parameters": {"profile": "portable"},
            "workflow_url": workflow_url,
        }

    def tes_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for task in self.tasks:
            tasks.append({
                "id": task.task_id,
                "name": task.name,
                "executors": [{"image": task.container.image if task.container else "", "command": list(task.command), "workdir": "/workspace"}],
                "resources": {"cpu_cores": task.cpu_cores, "ram_gb": task.memory_gb, "disk_gb": task.disk_gb},
                "inputs": [{"name": value, "path": value} for value in task.inputs],
                "outputs": [{"name": value, "path": value} for value in task.outputs],
                "tags": {"module_key": self.module_key, "container_digest": task.container.digest if task.container else "native"},
            })
        return tasks

    def trs_descriptor(self) -> dict[str, Any]:
        return {
            "id": self.workflow_id,
            "name": self.metadata.get("title", self.workflow_id),
            "organization": "BioIntel AI local workspace",
            "toolclass": {"id": "Workflow", "name": "Workflow"},
            "versions": [{"name": self.version, "verified": True, "descriptor_type": ["CWL", "NFL"]}],
        }


def _pseudo_container(engine: str) -> ContainerSpec:
    digest = sha256(f"biointel-container-lock:{engine}:v140".encode()).hexdigest()
    return ContainerSpec(image=f"ghcr.io/biointel-local/{engine}:qualified", digest=f"sha256:{digest}")


def default_plan(module_key: str, *, input_name: str = "input.dat") -> PortableWorkflowPlan:
    profile = profile_for(module_key)
    engines = tuple(profile.engines)
    tasks: list[TaskSpec] = [
        TaskSpec("verify", "Verify input checksum and schema", ("biointel-cli", "verify-input", "--input", input_name), inputs=(input_name,), outputs=("verified-input.json",), cpu_cores=1, memory_gb=1, disk_gb=2),
    ]
    previous = "verify"
    if engines:
        for index, engine in enumerate(engines[:3], start=1):
            task_id = f"engine-{index}"
            output = f"results/{engine}.json"
            tasks.append(TaskSpec(task_id, f"Run {engine}", (engine, "--version"), inputs=(input_name,), outputs=(output,), cpu_cores=2, memory_gb=4, disk_gb=10, container=_pseudo_container(engine), dependencies=(previous,)))
            previous = task_id
    tasks.append(TaskSpec("harmonize", "Normalize and harmonize results", ("biointel-cli", "harmonize", "--module", module_key), outputs=("results/harmonized.csv",), cpu_cores=1, memory_gb=3, disk_gb=5, dependencies=(previous,)))
    tasks.append(TaskSpec("export", "Build evidence and publication bundle", ("biointel-cli", "export", "--module", module_key), inputs=("results/harmonized.csv",), outputs=("results/evidence.zip",), cpu_cores=1, memory_gb=2, disk_gb=5, dependencies=("harmonize",)))
    return PortableWorkflowPlan(
        workflow_id=f"biointel.{module_key}.peak-v140",
        module_key=module_key,
        version="1.0.0",
        tasks=tuple(tasks),
        inputs=({"id": "input", "type": "File", "value": input_name},),
        outputs=({"id": "evidence_bundle", "type": "File", "path": "results/evidence.zip"},),
        metadata={"title": f"{module_key} portable specialist workflow", "native_features": list(profile.native_features), "reference_assets": list(profile.reference_assets)},
    )


def import_workflow_descriptor(text: str, *, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    kind = "CWL" if suffix in {".cwl", ".yaml", ".yml"} and "cwlVersion" in text else ("Nextflow" if suffix in {".nf", ".config"} or "nextflow" in text.lower() else "Unknown")
    names = re.findall(r"(?:workflow|process)\s+([A-Za-z_][A-Za-z0-9_]*)", text)[:100]
    return {
        "schema": "biointel.workflow_descriptor_import.v140",
        "filename": Path(filename).name,
        "type": kind,
        "workflow_names": names,
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
        "execution_state": "metadata-only; execution requires qualified runtime and locked containers",
    }


def workflow_pack(plan: PortableWorkflowPlan) -> dict[str, Any]:
    manifest = plan.to_manifest()
    return {
        "manifest": manifest,
        "WES": plan.wes_run_request(),
        "TES": plan.tes_tasks(),
        "TRS": plan.trs_descriptor(),
        "DRS_inputs": [
            {"id": item["id"], "name": item.get("value", item["id"]), "checksums_required": True}
            for item in plan.inputs
        ],
    }


__all__ = ["ContainerSpec", "TaskSpec", "PortableWorkflowPlan", "default_plan", "import_workflow_descriptor", "workflow_pack"]
