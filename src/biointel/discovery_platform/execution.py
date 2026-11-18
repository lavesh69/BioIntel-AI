from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .constants import MODULE_DEPENDENCIES, MODULE_LABELS
from .models import (
    PlatformConflictError,
    PlatformValidationError,
    canonical_json,
    new_id,
    utc_now,
)
from .provenance import environment_manifest, file_hashes
from .storage import DiscoveryPlatformStore

CancellationCallback = Callable[[], bool]
AnalysisCallable = Callable[[Mapping[str, Any]], Mapping[str, Any]]

TOOL_SETUP = {
    "fastqc": "Install FastQC and add fastqc.bat to PATH.",
    "multiqc": "Install MultiQC in the managed Python environment.",
    "star": "Install STAR through WSL2/Conda and configure its executable path.",
    "hisat2": "Install HISAT2 through WSL2/Conda and configure its executable path.",
    "bwa-mem2": "Install BWA-MEM2 and add the executable directory to PATH.",
    "minimap2": "Install minimap2 and add it to PATH.",
    "samtools": "Install samtools through WSL2/Conda and validate with samtools --version.",
    "picard": "Install Picard and configure its launcher.",
    "Rscript": "Install R and required Bioconductor packages; add Rscript.exe to PATH.",
    "bcftools": "Install bcftools through WSL2/Conda.",
    "vep": "Install Ensembl VEP plus a versioned offline cache.",
    "snpEff": "Install SnpEff and its configured reference database.",
    "msconvert": "Install ProteoWizard and add msconvert.exe to PATH.",
    "diann": "Install DIA-NN and record its executable path.",
    "qiime": "Install QIIME2 in a supported Conda/WSL2 environment.",
    "kraken2": "Install Kraken2 plus a versioned local database.",
    "bracken": "Install Bracken with a database matching the Kraken2 build.",
    "metaphlan": "Install MetaPhlAn plus a versioned local database.",
    "humann": "Install HUMAnN plus nucleotide and protein databases.",
}

VERSION_ARGUMENTS = {
    "java": ("-version",),
    "Rscript": ("--version",),
    "picard": ("--version",),
}


def probe_tool(tool_name: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    executable = shutil.which(tool_name)
    checked = utc_now()
    if not executable:
        return {
            "tool_name": tool_name,
            "installed": False,
            "version": "",
            "path": "",
            "health_status": "Missing",
            "setup_instructions": TOOL_SETUP.get(
                tool_name, f"Install {tool_name} and add it to PATH."
            ),
            "checked_at_utc": checked,
        }
    arguments = [executable, *VERSION_ARGUMENTS.get(tool_name, ("--version",))]
    version = ""
    health = "Installed"
    detail = ""
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
            shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        version = next((line.strip() for line in combined.splitlines() if line.strip()), "")
        if result.returncode not in {0, 1}:
            health = "Installed but validation failed"
            detail = f"Version probe exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        health = "Installed but validation timed out"
        detail = "Version probe timed out"
    except OSError as exc:
        health = "Installed but unavailable"
        detail = str(exc)
    return {
        "tool_name": tool_name,
        "installed": True,
        "version": version[:500],
        "path": executable,
        "health_status": health,
        "detail": detail,
        "setup_instructions": TOOL_SETUP.get(tool_name, ""),
        "checked_at_utc": checked,
    }


class DependencyManager:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store

    def check_all(self) -> list[dict[str, Any]]:
        modules_by_tool: dict[str, list[str]] = {}
        for module_id, tools in MODULE_DEPENDENCIES.items():
            for tool in tools:
                modules_by_tool.setdefault(tool, []).append(module_id)
        output = []
        for tool in sorted(modules_by_tool):
            check = probe_tool(tool)
            dependency_id = new_id("DEP")
            self.store.insert(
                "dependency_checks",
                {
                    "dependency_id": dependency_id, "tool_name": tool,
                    "installed": int(check["installed"]), "version": check["version"],
                    "executable_path": check["path"],
                    "health_status": check["health_status"],
                    "compatible_modules_json": modules_by_tool[tool],
                    "required": 0,
                    "setup_instructions": check["setup_instructions"],
                    "offline_instructions": (
                        f"Place an approved offline {tool} package in engine-packs and "
                        "record its SHA-256 before configuration."
                    ),
                    "validation_json": {"detail": check.get("detail", "")},
                    "checked_at_utc": check["checked_at_utc"],
                },
            )
            output.append(
                {
                    **check,
                    "dependency_id": dependency_id,
                    "compatible_modules": modules_by_tool[tool],
                    "required": False,
                }
            )
        return output

    def module_status(self, module_id: str) -> dict[str, Any]:
        if module_id not in MODULE_DEPENDENCIES:
            raise KeyError(module_id)
        checks = [probe_tool(tool) for tool in MODULE_DEPENDENCIES[module_id]]
        missing = [item["tool_name"] for item in checks if not item["installed"]]
        return {
            "module_id": module_id,
            "module": MODULE_LABELS.get(module_id, module_id),
            "external_tools": checks,
            "missing": missing,
            "ready_for_external_execution": not missing,
            "native_platform_available": True,
            "boundary": (
                "Missing external tools block only the corresponding external execution path; "
                "BioIntel never substitutes fabricated results."
            ),
        }


class ExecutionEngine:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store

    def _run_folder(self, run_id: str) -> Path:
        folder = (self.store.artifact_root / "runs" / Path(run_id).name).resolve()
        if not folder.is_relative_to(self.store.artifact_root):
            raise PlatformValidationError("Run path escaped the artifact root")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _create_run(
        self,
        *,
        project_id: str,
        dataset_id: str | None,
        workflow_version_id: str | None,
        module_id: str,
        tool: str,
        tool_version: str,
        parameters: Mapping[str, Any],
        input_hashes: Mapping[str, str],
        random_seed: int | None,
        provenance: Mapping[str, Any],
        parent_run_id: str | None = None,
    ) -> str:
        if self.store.row("projects", "project_id", project_id) is None:
            raise KeyError(project_id)
        if dataset_id and self.store.row("datasets", "dataset_id", dataset_id) is None:
            raise KeyError(dataset_id)
        run_id = new_id("RUN")
        self.store.insert(
            "runs",
            {
                "run_id": run_id, "project_id": project_id, "dataset_id": dataset_id,
                "workflow_version_id": workflow_version_id, "module_id": module_id,
                "tool": tool, "tool_version": tool_version, "status": "Running",
                "parameters_json": dict(parameters), "input_hashes_json": dict(input_hashes),
                "output_hashes_json": {}, "started_at_utc": utc_now(), "ended_at_utc": None,
                "logs_path": "", "warnings_json": [], "errors_json": [],
                "resource_usage_json": {}, "environment_json": environment_manifest(),
                "random_seed": random_seed, "provenance_json": dict(provenance),
                "frozen": 0, "parent_run_id": parent_run_id,
            },
        )
        return run_id

    def _register_artifact(
        self,
        *,
        project_id: str,
        run_id: str,
        path: Path,
        artifact_type: str,
        media_type: str,
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not path.is_file():
            raise PlatformValidationError(f"Expected output was not created: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        artifact_id = new_id("ART")
        self.store.insert(
            "artifacts",
            {
                "artifact_id": artifact_id, "project_id": project_id,
                "run_id": run_id, "artifact_type": artifact_type,
                "name": path.name, "path": str(path), "sha256": digest.hexdigest(),
                "size_bytes": path.stat().st_size, "media_type": media_type,
                "provenance_json": dict(provenance), "created_at_utc": utc_now(),
            },
        )
        return self.store.row("artifacts", "artifact_id", artifact_id) or {}

    def run_python(
        self,
        *,
        project_id: str,
        module_id: str,
        function: AnalysisCallable,
        payload: Mapping[str, Any],
        dataset_id: str | None = None,
        workflow_version_id: str | None = None,
        random_seed: int | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        function_name = getattr(function, "__qualname__", getattr(function, "__name__", "python_function"))
        origin = str((provenance or {}).get("origin", "real_calculation"))
        input_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        run_id = self._create_run(
            project_id=project_id, dataset_id=dataset_id,
            workflow_version_id=workflow_version_id, module_id=module_id,
            tool=function_name, tool_version="BioIntel native",
            parameters=payload, input_hashes={"payload": input_hash},
            random_seed=random_seed,
            provenance={
                **dict(provenance or {}), "origin": origin, "execution_type": "python_function",
            },
        )
        folder = self._run_folder(run_id)
        log_path = folder / "run.log"
        output_path = folder / "result.json"
        started = time.perf_counter()
        try:
            result = dict(function(payload))
            output_path.write_text(
                json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
            )
            artifact = self._register_artifact(
                project_id=project_id, run_id=run_id, path=output_path,
                artifact_type="analysis_result", media_type="application/json",
                provenance={"origin": origin, "function": function_name},
            )
            log_path.write_text(
                f"Completed {function_name} at {utc_now()}\n", encoding="utf-8"
            )
            self.store.update(
                "runs", "run_id", run_id,
                {
                    "status": "Completed", "ended_at_utc": utc_now(),
                    "logs_path": str(log_path),
                    "output_hashes_json": {artifact["name"]: artifact["sha256"]},
                    "resource_usage_json": {
                        "wall_seconds": round(time.perf_counter() - started, 6)
                    },
                },
            )
        except (ValueError, TypeError, RuntimeError, OSError) as exc:
            log_path.write_text(
                f"Failed {function_name}: {type(exc).__name__}: {exc}\n", encoding="utf-8"
            )
            self.store.update(
                "runs", "run_id", run_id,
                {
                    "status": "Failed", "ended_at_utc": utc_now(),
                    "logs_path": str(log_path),
                    "errors_json": [
                        {
                            "type": type(exc).__name__, "message": str(exc),
                            "partial_results_usable": output_path.exists(),
                        }
                    ],
                    "resource_usage_json": {
                        "wall_seconds": round(time.perf_counter() - started, 6)
                    },
                },
            )
            raise PlatformConflictError(f"Python analysis failed in {run_id}: {exc}") from exc
        self.store.audit(
            "analysis_run_completed", "run", run_id, project_id=project_id,
            detail={"module_id": module_id, "tool": function_name},
        )
        return self.run_snapshot(run_id)


    def run_subprocess(
        self,
        *,
        project_id: str,
        module_id: str,
        arguments: Sequence[str],
        dataset_id: str | None = None,
        workflow_version_id: str | None = None,
        expected_outputs: Sequence[str] = (),
        timeout_seconds: int = 3600,
        cancelled: CancellationCallback | None = None,
        environment: Mapping[str, str] | None = None,
        random_seed: int | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not arguments:
            raise PlatformValidationError("Subprocess argument list cannot be empty")
        clean_arguments = [str(value) for value in arguments]
        if any("\x00" in value for value in clean_arguments):
            raise PlatformValidationError("Subprocess arguments contain a null byte")
        executable = clean_arguments[0]
        resolved = (
            str(Path(executable).resolve())
            if Path(executable).is_file()
            else shutil.which(executable)
        )
        probe = probe_tool(Path(executable).stem)
        tool_version = probe.get("version", "")
        input_hash = hashlib.sha256(
            canonical_json({"arguments": clean_arguments, "dataset_id": dataset_id}).encode("utf-8")
        ).hexdigest()
        run_id = self._create_run(
            project_id=project_id, dataset_id=dataset_id,
            workflow_version_id=workflow_version_id, module_id=module_id,
            tool=Path(executable).name, tool_version=tool_version,
            parameters={
                "arguments": clean_arguments,
                "expected_outputs": list(expected_outputs),
                "timeout_seconds": timeout_seconds,
            },
            input_hashes={"command_plan": input_hash}, random_seed=random_seed,
            provenance={
                **dict(provenance or {}), "origin": "real_calculation",
                "execution_type": "local_subprocess", "shell": False,
            },
        )
        if not resolved:
            self.store.update(
                "runs", "run_id", run_id,
                {
                    "status": "Blocked", "ended_at_utc": utc_now(),
                    "errors_json": [
                        {
                            "type": "MissingDependency",
                            "message": f"Executable not found: {executable}",
                            "setup": TOOL_SETUP.get(
                                Path(executable).stem,
                                f"Install {Path(executable).stem} and add it to PATH.",
                            ),
                            "partial_results_usable": False,
                        }
                    ],
                },
            )
            return self.run_snapshot(run_id)
        clean_arguments[0] = resolved
        folder = self._run_folder(run_id)
        stdout_path = folder / "stdout.log"
        stderr_path = folder / "stderr.log"
        denied = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "PRIVATE_KEY")
        child_environment = dict(os.environ)
        for key, value in (environment or {}).items():
            if any(marker in key.upper() for marker in denied):
                raise PlatformValidationError(
                    f"Secret-like environment variable cannot be persisted or overridden: {key}"
                )
            child_environment[str(key)] = str(value)
        started = time.perf_counter()
        peak_rss = 0
        status = "Running"
        return_code: int | None = None
        warning_rows: list[dict[str, Any]] = []
        error_rows: list[dict[str, Any]] = []
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_handle:
            process = subprocess.Popen(
                clean_arguments,
                cwd=folder,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                shell=False,
                env=child_environment,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
            try:
                import psutil
            except ImportError:
                monitored_process = None
            else:
                monitored_process = psutil.Process(process.pid)
            while process.poll() is None:
                if cancelled and cancelled():
                    status = "Cancelled"
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
                elapsed = time.perf_counter() - started
                if elapsed > max(1, int(timeout_seconds)):
                    status = "Timed out"
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
                if monitored_process is not None:
                    try:
                        peak_rss = max(peak_rss, int(monitored_process.memory_info().rss))
                    except (psutil.Error, OSError):
                        monitored_process = None
                time.sleep(0.1)
            return_code = process.wait()
        outputs: list[dict[str, Any]] = []
        missing_outputs: list[str] = []
        if status == "Running":
            status = "Completed" if return_code == 0 else "Failed"
        for output_name in expected_outputs:
            candidate = (folder / Path(output_name).name).resolve()
            if not candidate.is_relative_to(folder):
                raise PlatformValidationError("Expected output path escaped the run directory")
            if candidate.is_file():
                outputs.append(
                    self._register_artifact(
                        project_id=project_id, run_id=run_id, path=candidate,
                        artifact_type="analysis_output",
                        media_type="application/octet-stream",
                        provenance={"origin": "real_calculation", "tool": Path(executable).name},
                    )
                )
            else:
                missing_outputs.append(str(output_name))
        if missing_outputs and status == "Completed":
            status = "Failed"
            error_rows.append(
                {
                    "type": "OutputValidationError",
                    "message": "Expected outputs were not created: " + ", ".join(missing_outputs),
                    "partial_results_usable": bool(outputs),
                }
            )
        if return_code not in {0, None}:
            error_rows.append(
                {
                    "type": "ExitCodeError",
                    "message": f"Process exited with code {return_code}",
                    "partial_results_usable": bool(outputs),
                }
            )
        if status == "Timed out":
            error_rows.append(
                {
                    "type": "Timeout",
                    "message": f"Execution exceeded {timeout_seconds} seconds",
                    "partial_results_usable": bool(outputs),
                }
            )
        if status == "Cancelled":
            warning_rows.append(
                {
                    "type": "Cancellation",
                    "message": "Operator requested cancellation",
                    "partial_results_usable": bool(outputs),
                }
            )
        self.store.update(
            "runs", "run_id", run_id,
            {
                "status": status, "ended_at_utc": utc_now(),
                "logs_path": str(folder), "warnings_json": warning_rows,
                "errors_json": error_rows,
                "output_hashes_json": {
                    item["name"]: item["sha256"] for item in outputs
                },
                "resource_usage_json": {
                    "wall_seconds": round(time.perf_counter() - started, 6),
                    "peak_rss_bytes": peak_rss or None,
                    "return_code": return_code,
                    "temporary_storage_bytes": sum(
                        path.stat().st_size for path in folder.glob("*") if path.is_file()
                    ),
                },
            },
        )
        self.store.audit(
            "subprocess_run_finished", "run", run_id, project_id=project_id,
            detail={
                "module_id": module_id, "tool": Path(executable).name,
                "status": status, "return_code": return_code,
                "partial_outputs": len(outputs),
            },
        )
        return self.run_snapshot(run_id)

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        run = self.store.row("runs", "run_id", run_id)
        if run is None:
            raise KeyError(run_id)
        run["steps"] = self.store.rows(
            "run_steps", filters={"run_id": run_id},
            order_by="started_at_utc", descending=False, limit=5000,
        )
        run["artifacts"] = self.store.rows(
            "artifacts", filters={"run_id": run_id},
            order_by="created_at_utc", descending=False, limit=5000,
        )
        return run

    def clone_run(self, run_id: str) -> dict[str, Any]:
        source = self.run_snapshot(run_id)
        clone_id = self._create_run(
            project_id=source["project_id"], dataset_id=source.get("dataset_id"),
            workflow_version_id=source.get("workflow_version_id"),
            module_id=source["module_id"], tool=source["tool"],
            tool_version=source["tool_version"], parameters=source.get("parameters", {}),
            input_hashes=source.get("input_hashes", {}),
            random_seed=source.get("random_seed"),
            provenance={
                **dict(source.get("provenance") or {}),
                "cloned_from_run_id": run_id, "exact_parameter_clone": True,
            },
            parent_run_id=run_id,
        )
        self.store.update(
            "runs", "run_id", clone_id,
            {"status": "Queued", "started_at_utc": utc_now()},
        )
        self.store.audit(
            "run_cloned", "run", clone_id, project_id=source["project_id"],
            detail={"source_run_id": run_id},
        )
        return self.run_snapshot(clone_id)

    def freeze_run(self, run_id: str) -> dict[str, Any]:
        run = self.run_snapshot(run_id)
        if run["status"] != "Completed":
            raise PlatformConflictError("Only completed runs can be frozen")
        verification = {}
        for artifact in run["artifacts"]:
            path = Path(artifact["path"])
            if not path.is_file():
                verification[artifact["artifact_id"]] = "missing"
                continue
            digest = file_hashes([path])[str(path)]
            verification[artifact["artifact_id"]] = (
                "verified" if digest == artifact["sha256"] else "hash_mismatch"
            )
        if any(value != "verified" for value in verification.values()):
            raise PlatformConflictError("Run artifacts failed hash verification")
        self.store.update("runs", "run_id", run_id, {"frozen": 1})
        self.store.audit(
            "run_frozen", "run", run_id, project_id=run["project_id"],
            detail={"artifact_verification": verification},
        )
        return self.run_snapshot(run_id)

    def compare_runs(self, first_id: str, second_id: str) -> dict[str, Any]:
        first = self.run_snapshot(first_id)
        second = self.run_snapshot(second_id)
        return {
            "first_run_id": first_id,
            "second_run_id": second_id,
            "same_inputs": first.get("input_hashes") == second.get("input_hashes"),
            "same_parameters": first.get("parameters") == second.get("parameters"),
            "same_environment": first.get("environment") == second.get("environment"),
            "same_outputs": first.get("output_hashes") == second.get("output_hashes"),
            "status": {"first": first["status"], "second": second["status"]},
            "resource_usage": {
                "first": first.get("resource_usage", {}),
                "second": second.get("resource_usage", {}),
            },
        }


__all__ = [
    "DependencyManager",
    "ExecutionEngine",
    "TOOL_SETUP",
    "probe_tool",
]
