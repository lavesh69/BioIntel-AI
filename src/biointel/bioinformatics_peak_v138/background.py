from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from biointel.jobs.local_queue import JobRecord, LocalJobQueue


def _user_root(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    return Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or root / "UserData").resolve()


def stage_dataframe(
    project_root: str | Path,
    frame: pd.DataFrame,
    *,
    module_key: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Cannot stage an empty scientific dataset.")
    user_root = _user_root(project_root)
    directory = user_root / "staged_uploads" / "bioinformatics_peak_v138"
    directory.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    path = directory / f"{module_key}-{token}.csv.gz"
    frame.to_csv(path, index=False, compression="gzip")
    digest = sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema": "biointel.bioinformatics_peak.background_input.v138",
        "module_key": module_key,
        "path": str(path),
        "rows": len(frame),
        "columns": len(frame.columns),
        "sha256": digest,
        "parameters": parameters,
    }
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path)}


def submit_background_analysis(
    project_root: str | Path,
    staged: dict[str, Any],
    *,
    priority: int = 80,
) -> JobRecord:
    root = Path(project_root).resolve()
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    rows = int(staged.get("rows", 0))
    estimated = max(10.0, min(3600.0, rows / 5_000))
    return queue.submit(
        "bioinformatics_peak_analysis_v138",
        {
            "module_key": staged["module_key"],
            "path": staged["path"],
            "manifest_path": staged.get("manifest_path", ""),
            "sha256": staged["sha256"],
            "parameters": dict(staged.get("parameters") or {}),
        },
        priority=priority,
        max_attempts=3,
        stages=["verify", "parse", "analyse", "export", "validate"],
        resources={"cpu": "local", "memory": "bounded", "execution": "resumable"},
        estimated_seconds=estimated,
    )


def stage_and_submit(
    project_root: str | Path,
    frame: pd.DataFrame,
    *,
    module_key: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    staged = stage_dataframe(project_root, frame, module_key=module_key, parameters=parameters)
    job = submit_background_analysis(project_root, staged)
    return {"staged": staged, "job": asdict(job)}
