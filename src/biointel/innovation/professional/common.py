from __future__ import annotations

"""Step 100 professional analysis and orchestration helpers.

This module adds dependency-light, locally executable capabilities for the
innovation pages.  It does not pretend that licensed databases, GPU model
weights, specialist executables, clinical interpretation, or wet-lab evidence
are bundled.  Every function returns explicit assumptions and review flags.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from hashlib import sha256
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.integrate import solve_ivp
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler


# ---------------------------------------------------------------------------
# Shared utilities and truthful capability discovery
# ---------------------------------------------------------------------------


def stable_frame_hash(frame: pd.DataFrame) -> str:
    if frame is None:
        return sha256(b"null").hexdigest()
    normalized = frame.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    payload = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256(payload).hexdigest()


def stable_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def _numeric(series: pd.Series | Sequence[Any], default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def _normalise_identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _split_tokens(value: Any) -> list[str]:
    return [token.strip().rstrip("+-") for token in re.split(r"[,;\s]+", str(value or "")) if token.strip()]


def _safe_run(command: Sequence[str], timeout: int = 5) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "ok": completed.returncode == 0,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc), "ok": False}


@dataclass(frozen=True)
class RuntimeCapability:
    capability: str
    executable: str
    detected: bool
    resolved_path: str
    version: str
    requirement: str
    status: str


TOOL_REQUIREMENTS: tuple[tuple[str, str, str], ...] = (
    ("Graph construction", "minigraph", "Optional specialist executable"),
    ("Graph manipulation", "odgi", "Optional specialist executable"),
    ("Graph mapping/genotyping", "vg", "Optional specialist executable and indexes"),
    ("Long-read assembly", "flye", "Optional specialist executable"),
    ("HiFi assembly", "hifiasm", "Optional specialist executable"),
    ("Long-read assembly alternative", "canu", "Optional specialist executable"),
    ("Assembly QC", "quast.py", "Optional specialist executable"),
    ("Gene completeness", "busco", "Optional specialist executable and lineage database"),
    ("ONT polishing", "medaka_consensus", "Optional specialist executable and model"),
    ("Consensus polishing", "racon", "Optional specialist executable"),
    ("K-mer validation", "merqury.sh", "Optional specialist executable"),
    ("Pooled CRISPR", "mageck", "Optional specialist executable"),
    ("Maximum-likelihood phylogeny", "iqtree2", "Optional specialist executable"),
    ("Recombination correction", "gubbins", "Optional specialist executable"),
    ("AMR screening", "amrfinder", "Optional specialist executable and database"),
    ("Protein sequence design", "proteinmpnn", "Optional model runtime and weights"),
    ("Diffusion protein design", "rfdiffusion", "Optional GPU runtime and weights"),
    ("Structure prediction", "colabfold_batch", "Optional runtime and sequence databases"),
    ("Protein stability", "FoldX", "Optional licensed executable"),
    ("Workflow orchestration", "nextflow", "Optional executable"),
    ("Workflow orchestration", "snakemake", "Optional executable"),
)


def _detect_version(executable: str) -> str:
    path = shutil.which(executable)
    if not path:
        return ""
    for option in ("--version", "-version", "-v"):
        result = _safe_run([path, option], timeout=3)
        text = (result["stdout"] or result["stderr"]).strip().splitlines()
        if text:
            return text[0][:180]
    return "Detected; version command unavailable"


@lru_cache(maxsize=1)
def _runtime_capability_records() -> tuple[tuple[tuple[str, Any], ...], ...]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for capability, executable, requirement in TOOL_REQUIREMENTS:
        key = (capability, executable)
        if key in seen:
            continue
        seen.add(key)
        resolved = shutil.which(executable) or ""
        detected = bool(resolved)
        rows.append(asdict(RuntimeCapability(
            capability=capability,
            executable=executable,
            detected=detected,
            resolved_path=resolved,
            version=_detect_version(executable) if detected else "",
            requirement=requirement,
            status="Ready" if detected else "External dependency missing",
        )))
    return tuple(tuple(sorted(row.items())) for row in rows)


def runtime_capability_scan(refresh: bool = False) -> pd.DataFrame:
    if refresh:
        _runtime_capability_records.cache_clear()
    return pd.DataFrame([dict(items) for items in _runtime_capability_records()])


@lru_cache(maxsize=4)
def _hardware_profile_cached(workspace_key: str) -> dict[str, Any]:
    target = Path(workspace_key).resolve()
    try:
        disk = shutil.disk_usage(target)
        disk_free_gb = round(disk.free / (1024 ** 3), 2)
        disk_total_gb = round(disk.total / (1024 ** 3), 2)
    except OSError:
        disk_free_gb = None
        disk_total_gb = None
    gpu = {"detected": False, "name": "", "memory_mb": None, "driver": ""}
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        result = _safe_run([
            nvidia,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ])
        if result["ok"] and result["stdout"].strip():
            values = [part.strip() for part in result["stdout"].splitlines()[0].split(",")]
            gpu = {
                "detected": True,
                "name": values[0] if values else "NVIDIA GPU",
                "memory_mb": float(values[1]) if len(values) > 1 and values[1].replace(".", "", 1).isdigit() else None,
                "driver": values[2] if len(values) > 2 else "",
            }
    profile = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count() or 1,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "gpu": gpu,
    }
    profile["profile_sha256"] = stable_payload_hash(profile)
    return profile


def hardware_profile(workspace: str | Path | None = None, refresh: bool = False) -> dict[str, Any]:
    key = str(Path(workspace or Path.cwd()).resolve())
    if refresh:
        _hardware_profile_cached.cache_clear()
    return dict(_hardware_profile_cached(key))
