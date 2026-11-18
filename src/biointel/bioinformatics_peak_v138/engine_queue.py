from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from biointel.jobs.local_queue import JobRecord, LocalJobQueue
from biointel.native.engines import build_engine_plan, detect_engine, plan_to_dict

from .native_profiles import AutoEnginePlan, compound_suffix, profile_for



@lru_cache(maxsize=64)
def cached_engine_status(engine_key: str):
    return detect_engine(engine_key, timeout_seconds=2.0)


def engine_readiness_rows(module_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in profile_for(module_key).engines:
        status = cached_engine_status(key)
        rows.append({
            "Engine": status.label, "Key": status.key, "Available": status.available,
            "Executable": status.executable or "Not found", "Version": status.version,
            "Category": status.category, "Capabilities": ", ".join(status.capabilities),
            "Reference data": ", ".join(status.required_databases) or "None declared",
            "GPU optional": status.gpu_optional, "Installation note": status.note,
        })
    return rows


def clear_engine_readiness_cache() -> None:
    cached_engine_status.cache_clear()

def compatible_auto_plans(module_key: str, staged_path: str | Path) -> tuple[AutoEnginePlan, ...]:
    extension = compound_suffix(Path(staged_path).name)
    return tuple(plan for plan in profile_for(module_key).auto_plans if extension in plan.compatible_extensions)


def _output_defaults(plan_key: str, workdir: Path, source: Path) -> dict[str, Any]:
    outputs: dict[str, dict[str, Any]] = {
        "samtools_depth": {"output": str(workdir / "coverage.tsv")},
        "bcftools_stats": {"output": str(workdir / "bcftools.stats.txt")},
        "mafft_align": {"output": str(workdir / "aligned.fasta")},
        "macs2_callpeak": {"output_dir": str(workdir / "macs2")},
        "deeptools_bamcoverage": {"output": str(workdir / "coverage.bw")},
        "anarci_number": {"output": str(workdir / "anarci_numbering.txt")},
        "openms_fileinfo": {"output": str(workdir / "openms_fileinfo.txt")},
        "sniffles_call": {"output": str(workdir / "sniffles.vcf.gz")},
        "busco_assembly": {"output_parent": str(workdir / "busco")},
    }
    values = dict(outputs.get(plan_key, {}))
    if plan_key == "macs2_callpeak":
        suffix = source.suffix.lower()
        values["format"] = "BAM" if suffix in {".bam", ".cram"} else "BED"
    return values


def engine_plan_parameters(auto_plan: AutoEnginePlan, staged_path: str | Path, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    source = Path(staged_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    workdir = source.parent.resolve()
    parameters = auto_plan.defaults()
    parameters[auto_plan.source_parameter] = str(source)
    parameters.update(_output_defaults(auto_plan.plan_key, workdir, source))
    parameters.update(dict(overrides or {}))
    parameters.setdefault("threads", 2)
    parameters.setdefault("memory_gb", 4)
    return parameters


def preview_engine_plan(auto_plan: AutoEnginePlan, staged_path: str | Path, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    source = Path(staged_path).expanduser().resolve()
    status = cached_engine_status(_engine_key_for_plan(auto_plan.plan_key))
    parameters = engine_plan_parameters(auto_plan, source, overrides=overrides)
    plan = build_engine_plan(auto_plan.plan_key, workdir=source.parent, **parameters)
    return {
        "available": status.available,
        "engine_status": asdict(status),
        "plan": plan_to_dict(plan),
        "parameters": parameters,
        "stdout_to_output": auto_plan.stdout_to_output,
    }


def _engine_key_for_plan(plan_key: str) -> str:
    # build_engine_plan is the source of truth; this lightweight map avoids exposing
    # the module's private requirements table in UI code.
    mapping = {
        "samtools_index": "samtools",
        "samtools_depth": "samtools",
        "bcftools_stats": "bcftools",
        "mafft_align": "mafft",
        "macs2_callpeak": "macs2",
        "deeptools_bamcoverage": "deeptools",
        "anarci_number": "anarci",
        "openms_fileinfo": "openms",
        "sniffles_call": "sniffles",
        "busco_assembly": "busco",
    }
    try:
        return mapping[plan_key]
    except KeyError as exc:
        raise KeyError(f"No safe auto-engine mapping for {plan_key}") from exc


def submit_engine_run(
    project_root: str | Path,
    auto_plan: AutoEnginePlan,
    staged_path: str | Path,
    *,
    overrides: dict[str, Any] | None = None,
    timeout_seconds: int = 3600,
    priority: int = 70,
) -> JobRecord:
    source = Path(staged_path).expanduser().resolve()
    status = cached_engine_status(_engine_key_for_plan(auto_plan.plan_key))
    if not status.available:
        raise RuntimeError(f"{status.label} is not available. {status.note or 'Install and verify the engine before execution.'}")
    parameters = engine_plan_parameters(auto_plan, source, overrides=overrides)
    # Build once before queueing so invalid paths or parameters fail immediately.
    build_engine_plan(auto_plan.plan_key, workdir=source.parent, **parameters)
    root = Path(project_root).resolve()
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    return queue.submit(
        "native_engine_execute",
        {
            "plan_key": auto_plan.plan_key,
            "workdir": str(source.parent),
            "parameters": parameters,
            "timeout_seconds": max(10, min(int(timeout_seconds), 86_400)),
            "stdout_to_output": bool(auto_plan.stdout_to_output),
        },
        priority=priority,
        max_attempts=2,
        stages=["plan", "execute", "validate"],
        resources={"cpu": "local", "memory": "bounded", "engine": status.label},
        estimated_seconds=120.0,
    )


__all__ = [
    "cached_engine_status",
    "clear_engine_readiness_cache",
    "compatible_auto_plans",
    "engine_readiness_rows",
    "engine_plan_parameters",
    "preview_engine_plan",
    "submit_engine_run",
]
