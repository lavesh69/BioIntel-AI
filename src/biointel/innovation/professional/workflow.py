from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.integrate import solve_ivp
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler

from .common import (
    _normalise_identifier, _numeric, _safe_run, _split_tokens,
    hardware_profile, runtime_capability_scan, stable_frame_hash, stable_payload_hash,
)

# ---------------------------------------------------------------------------
# Workflow builder and marketplace
# ---------------------------------------------------------------------------


def workflow_cache_key(node: Mapping[str, Any], input_hashes: Sequence[str], environment_hash: str = "") -> str:
    payload = {
        "node": {str(key): node[key] for key in sorted(node)},
        "input_hashes": sorted(str(value) for value in input_hashes),
        "environment_hash": environment_hash,
    }
    return stable_payload_hash(payload)


def workflow_container_audit(workflow: pd.DataFrame) -> pd.DataFrame:
    if workflow.empty:
        return pd.DataFrame()
    frame = workflow.copy()
    image_column = next((column for column in ("container", "container_image", "image") if column in frame), None)
    digest_pattern = re.compile(r"@sha256:[0-9a-f]{64}$", re.I)
    rows = []
    for index, row in frame.iterrows():
        image = str(row.get(image_column, "")) if image_column else ""
        rows.append({
            "node_id": row.get("id", index),
            "container_image": image,
            "container_declared": bool(image),
            "digest_pinned": bool(digest_pattern.search(image)),
            "status": "Pinned" if digest_pattern.search(image) else "Tag only" if image else "Host environment",
            "review": "Use an immutable digest for controlled execution" if image and not digest_pattern.search(image) else "" if image else "Environment snapshot required",
        })
    return pd.DataFrame(rows)


def workflow_resource_schedule(workflow: pd.DataFrame, total_cpu: int, total_ram_gb: float, total_gpu: int = 0) -> tuple[pd.DataFrame, dict[str, Any]]:
    if workflow.empty or "id" not in workflow:
        return pd.DataFrame(), {"valid": False, "reason": "Workflow is empty or missing id"}
    frame = workflow.copy()
    frame["id"] = frame["id"].astype(str)
    dependency_column = "depends_on" if "depends_on" in frame else None
    records = {str(row["id"]): row for _, row in frame.iterrows()}
    dependencies = {node_id: [value for value in _split_tokens(row.get(dependency_column, "")) if value] if dependency_column else [] for node_id, row in records.items()}
    indegree = {node_id: len([dep for dep in deps if dep in records]) for node_id, deps in dependencies.items()}
    children: dict[str, list[str]] = defaultdict(list)
    for node_id, deps in dependencies.items():
        for dep in deps:
            if dep in records:
                children[dep].append(node_id)
    ready = deque(sorted([node for node, degree in indegree.items() if degree == 0]))
    finish: dict[str, float] = {}
    schedule = []
    while ready:
        node_id = ready.popleft()
        row = records[node_id]
        start = max((finish.get(dep, 0.0) for dep in dependencies[node_id]), default=0.0)
        minutes = float(pd.to_numeric(pd.Series([row.get("minutes", row.get("duration_minutes", 1.0))]), errors="coerce").fillna(1.0).iloc[0])
        cpu = max(1, int(pd.to_numeric(pd.Series([row.get("cpu", 1)]), errors="coerce").fillna(1).iloc[0]))
        ram = max(0.1, float(pd.to_numeric(pd.Series([row.get("ram_gb", 1.0)]), errors="coerce").fillna(1.0).iloc[0]))
        gpu = max(0, int(pd.to_numeric(pd.Series([row.get("gpu", 0)]), errors="coerce").fillna(0).iloc[0]))
        blockers = []
        if cpu > total_cpu:
            blockers.append("CPU request exceeds capacity")
        if ram > total_ram_gb:
            blockers.append("RAM request exceeds capacity")
        if gpu > total_gpu:
            blockers.append("GPU request exceeds capacity")
        finish[node_id] = start + minutes
        schedule.append({
            "id": node_id,
            "start_minute": start,
            "finish_minute": finish[node_id],
            "duration_minutes": minutes,
            "cpu": cpu,
            "ram_gb": ram,
            "gpu": gpu,
            "status": "Blocked" if blockers else "Schedulable",
            "blockers": "; ".join(blockers),
        })
        for child in children[node_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    valid = len(schedule) == len(records)
    report = {
        "valid_dag": valid,
        "scheduled_nodes": len(schedule),
        "workflow_nodes": len(records),
        "critical_finish_minutes": max(finish.values(), default=0.0),
        "blocked_nodes": sum(row["status"] == "Blocked" for row in schedule),
        "capacity": {"cpu": total_cpu, "ram_gb": total_ram_gb, "gpu": total_gpu},
    }
    return pd.DataFrame(schedule), report


def workflow_test_matrix(workflow: pd.DataFrame) -> pd.DataFrame:
    if workflow.empty:
        return pd.DataFrame()
    rows = []
    for index, row in workflow.iterrows():
        node_id = row.get("id", index)
        block = row.get("block", row.get("name", "Unknown"))
        rows.extend([
            {"node_id": node_id, "block": block, "test": "Nominal fixture", "expected": "Successful output with schema match"},
            {"node_id": node_id, "block": block, "test": "Empty input", "expected": "Controlled validation failure"},
            {"node_id": node_id, "block": block, "test": "Malformed input", "expected": "No crash; actionable error"},
            {"node_id": node_id, "block": block, "test": "Resume/cache", "expected": "Hash-verified reuse or clean recompute"},
        ])
    return pd.DataFrame(rows)


def expand_scatter_plan(workflow: pd.DataFrame, scatter_column: str = "scatter_values") -> pd.DataFrame:
    if workflow.empty:
        return pd.DataFrame()
    rows = []
    for _, row in workflow.iterrows():
        values = _split_tokens(row.get(scatter_column, "")) if scatter_column in workflow else []
        if not values:
            record = row.to_dict()
            record["scatter_value"] = ""
            rows.append(record)
            continue
        for value in values:
            record = row.to_dict()
            record["parent_id"] = record.get("id")
            record["id"] = f"{record.get('id')}[{value}]"
            record["scatter_value"] = value
            rows.append(record)
    return pd.DataFrame(rows)
# ---------------------------------------------------------------------------
# Innovation hub and cross-module optimization
# ---------------------------------------------------------------------------


MODULE_DEPENDENCIES: tuple[dict[str, Any], ...] = (
    {"module": "Pangenome & Variation Graph", "executables": "minigraph,odgi,vg", "databases": "Reference genome + annotations", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Long-Read Assembly & T2T", "executables": "flye,hifiasm,canu,quast.py,busco", "databases": "BUSCO lineage + optional contamination database", "gpu": False, "internet": False, "minimum_ram_gb": 32},
    {"module": "AI Protein Design", "executables": "proteinmpnn,rfdiffusion,colabfold_batch,FoldX", "databases": "Model weights + optional structure databases", "gpu": True, "internet": False, "minimum_ram_gb": 32},
    {"module": "CRISPR Screen & Perturb-seq", "executables": "mageck", "databases": "Genome/transcript/off-target reference", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Pathogen Outbreak Genomics", "executables": "iqtree2,gubbins,amrfinder", "databases": "AMR/typing/virulence database releases", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Synthetic Biology", "executables": "", "databases": "Validated parts/chassis parameters", "gpu": False, "internet": False, "minimum_ram_gb": 8},
    {"module": "Rare Disease Interpretation", "executables": "bcftools,vep", "databases": "ClinVar, gnomAD, transcript and phenotype releases", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Biomedical Knowledge Graph", "executables": "", "databases": "Evidence corpus + ontology releases", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Multi-Omics Biomarker", "executables": "", "databases": "Independent cohort + annotation releases", "gpu": False, "internet": False, "minimum_ram_gb": 16},
    {"module": "Visual Workflow Builder", "executables": "nextflow,snakemake", "databases": "Workflow-specific", "gpu": False, "internet": False, "minimum_ram_gb": 8},
    {"module": "Innovation Modules Hub", "executables": "", "databases": "Capability registry", "gpu": False, "internet": False, "minimum_ram_gb": 4},
)


def module_dependency_matrix() -> pd.DataFrame:
    capabilities = runtime_capability_scan()
    executable_status = {row.executable: bool(row.detected) for row in capabilities.itertuples(index=False)}
    hardware = hardware_profile()
    available_ram_gb = _system_memory_gb()
    rows = []
    for item in MODULE_DEPENDENCIES:
        executables = [value for value in str(item["executables"]).split(",") if value]
        detected = [value for value in executables if executable_status.get(value, bool(shutil.which(value)))]
        missing = [value for value in executables if value not in detected]
        gpu_ok = not item["gpu"] or bool(hardware["gpu"].get("detected"))
        ram_ok = available_ram_gb is None or available_ram_gb >= item["minimum_ram_gb"]
        rows.append({
            **item,
            "detected_executables": ",".join(detected),
            "missing_executables": ",".join(missing),
            "gpu_ready": gpu_ok,
            "ram_available_gb": available_ram_gb,
            "ram_ready": ram_ok,
            "runtime_status": "Ready for local built-ins" if not missing and gpu_ok and ram_ok else "External setup required",
        })
    return pd.DataFrame(rows)


def _system_memory_gb() -> float | None:
    if os.name == "posix":
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * page_size / (1024 ** 3), 2)
        except (ValueError, OSError, AttributeError):
            return None
    try:
        result = _safe_run(["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"])
        match = re.search(r"TotalPhysicalMemory=(\d+)", result["stdout"])
        return round(int(match.group(1)) / (1024 ** 3), 2) if match else None
    except Exception:
        return None


def dependency_install_plan(module_name: str, matrix: pd.DataFrame | None = None) -> pd.DataFrame:
    matrix = module_dependency_matrix() if matrix is None else matrix
    match = matrix[matrix["module"].str.casefold() == str(module_name).casefold()]
    if match.empty:
        return pd.DataFrame()
    row = match.iloc[0]
    steps = [
        {"order": 1, "action": "Confirm hardware", "detail": f"Minimum RAM {row['minimum_ram_gb']} GB; GPU required: {row['gpu']}"},
        {"order": 2, "action": "Install missing executables", "detail": row["missing_executables"] or "No executable missing"},
        {"order": 3, "action": "Register reference assets", "detail": row["databases"]},
        {"order": 4, "action": "Capture versions and checksums", "detail": "Record executable versions, database releases, licences and SHA-256"},
        {"order": 5, "action": "Run smoke fixture", "detail": "Use a small known input and verify expected outputs before project data"},
        {"order": 6, "action": "Enable controlled execution", "detail": "Pin environment, resource limits, logs and provenance"},
    ]
    return pd.DataFrame(steps)


def optimisation_scorecard() -> pd.DataFrame:
    hardware = hardware_profile()
    tools = runtime_capability_scan()
    memory = _system_memory_gb()
    checks = [
        ("CPU parallelism", (os.cpu_count() or 1) >= 4, f"{os.cpu_count() or 1} logical CPUs"),
        ("Memory for advanced workflows", memory is None or memory >= 16, f"{memory if memory is not None else 'Unknown'} GB"),
        ("Free disk for large references", hardware["disk_free_gb"] is None or hardware["disk_free_gb"] >= 50, f"{hardware['disk_free_gb']} GB free"),
        ("GPU acceleration", bool(hardware["gpu"].get("detected")), hardware["gpu"].get("name") or "No NVIDIA GPU detected"),
        ("Specialist tools", int(tools["detected"].sum()) >= 5, f"{int(tools['detected'].sum())}/{len(tools)} detected"),
    ]
    return pd.DataFrame([
        {"area": area, "pass": passed, "detail": detail, "recommendation": "Ready" if passed else "Review resource/dependency setup"}
        for area, passed, detail in checks
    ])


def module_next_step_recommendations(matrix: pd.DataFrame, role: str, current_module: str | None = None) -> pd.DataFrame:
    frame = matrix.copy()
    role_tokens = {
        "Bioinformatician": {"Pangenome & Variation Graph", "Long-Read Assembly & T2T", "Pathogen Outbreak Genomics", "Visual Workflow Builder"},
        "ML Scientist": {"AI Protein Design", "Multi-Omics Biomarker", "Biomedical Knowledge Graph"},
        "Clinical Researcher": {"Rare Disease Interpretation", "Multi-Omics Biomarker", "Biomedical Knowledge Graph"},
        "Wet-Lab Scientist": {"CRISPR Screen & Perturb-seq", "Synthetic Biology", "AI Protein Design"},
    }
    preferred = role_tokens.get(role, set())
    frame["role_match"] = frame["module"].isin(preferred)
    frame["readiness_score"] = (
        frame["ram_ready"].astype(int) * 30
        + frame["gpu_ready"].astype(int) * 20
        + frame["missing_executables"].eq("").astype(int) * 30
        + frame["role_match"].astype(int) * 20
    )
    if current_module:
        frame.loc[frame["module"].eq(current_module), "readiness_score"] -= 10
    frame["next_action"] = np.where(
        frame["runtime_status"].eq("Ready for local built-ins"),
        "Open module and run a verified fixture",
        "Complete dependency plan first",
    )
    return frame.sort_values(["readiness_score", "module"], ascending=[False, True])
