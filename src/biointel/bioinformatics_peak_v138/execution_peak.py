from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from typing import Any

from biointel.database.core import managed_connect


@dataclass(frozen=True)
class ResourcePlan:
    mode: str
    input_bytes: int
    rows: int
    columns: int
    estimated_ram_gb: float
    temporary_disk_gb: float
    cpu_threads: int
    gpu_required: bool
    runtime_range: str
    rationale: str


def plan_resources(*, input_bytes: int = 0, rows: int = 0, columns: int = 0, engine_count: int = 0, gpu_capable: bool = False) -> ResourcePlan:
    cells = max(0, rows) * max(1, columns)
    estimated_ram = max(0.5, input_bytes / (1024**3) * 3.0, cells * 24 / (1024**3))
    disk = max(1.0, input_bytes / (1024**3) * (4.0 if engine_count else 2.0))
    cpu = 1 if rows < 50_000 else (2 if rows < 1_000_000 else 4)
    gpu = bool(gpu_capable and rows > 500_000)
    if input_bytes > 2 * 1024**3 or estimated_ram > 16:
        mode, runtime, rationale = "External/HPC", "hours", "Input or estimated memory exceeds a typical local workstation profile."
    elif input_bytes > 500 * 1024**2 or rows > 1_000_000:
        mode, runtime, rationale = "Background local", "tens of minutes to hours", "Large input benefits from checkpointed background execution."
    elif input_bytes > 100 * 1024**2 or rows > 250_000:
        mode, runtime, rationale = "Low-memory staged", "minutes to tens of minutes", "Use indexed/chunked reads and bounded visual previews."
    else:
        mode, runtime, rationale = "Interactive", "seconds to minutes", "Input is suitable for bounded local execution."
    return ResourcePlan(mode, int(input_bytes), int(rows), int(columns), round(float(estimated_ram), 2), round(float(disk), 2), cpu, gpu, runtime, rationale)


class CheckpointStore:
    def __init__(self, project_root: str | Path):
        self.path = Path(project_root).resolve() / "UserData" / "workspace" / "bioinformatics_peak_v140" / "checkpoints.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS checkpoints (run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, input_hash TEXT NOT NULL, parameter_hash TEXT NOT NULL, tool_version TEXT NOT NULL, output_hash TEXT NOT NULL, payload_json TEXT NOT NULL, updated_at_utc TEXT NOT NULL, PRIMARY KEY(run_id, stage))")

    def _connect(self):
        db = managed_connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def digest(value: Any) -> str:
        return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

    def save(self, *, run_id: str, stage: str, status: str, input_hash: str, parameters: dict[str, Any], tool_version: str = "built-in", output_hash: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        record = {
            "run_id": run_id, "stage": stage, "status": status, "input_hash": input_hash,
            "parameter_hash": self.digest(parameters), "tool_version": tool_version,
            "output_hash": output_hash, "payload_json": json.dumps(payload or {}, sort_keys=True, default=str),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO checkpoints VALUES (:run_id,:stage,:status,:input_hash,:parameter_hash,:tool_version,:output_hash,:payload_json,:updated_at_utc)", record)
        return record

    def resume_state(self, run_id: str, *, input_hash: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        parameter_hash = self.digest(parameters)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM checkpoints WHERE run_id=? ORDER BY updated_at_utc", (run_id,)).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["resume_compatible"] = row["input_hash"] == input_hash and row["parameter_hash"] == parameter_hash and row["status"] == "completed"
        return result


_ERROR_RULES = (
    (("memory", "out of memory", "cannot allocate"), "Memory", "Use low-memory mode, reduce workers, or stage the run on an HPC profile."),
    (("no space", "disk full", "errno 28"), "Disk", "Free temporary storage or change the UserData/work directory."),
    (("not found", "missing executable", "command"), "Tool availability", "Install or configure the qualified specialist executable/container."),
    (("checksum", "hash mismatch"), "Integrity", "Re-stage the input/reference and verify that it was not modified."),
    (("timeout", "timed out"), "Timeout", "Increase the stage timeout or use background/HPC execution."),
    (("permission", "access denied"), "Permission", "Use a writable UserData workspace and avoid protected system folders."),
    (("schema", "column", "parse"), "Input/schema", "Validate file format, delimiter, required fields and genome/reference context."),
)


def diagnose_failure(error: BaseException | str, *, stage: str = "unknown") -> dict[str, Any]:
    message = str(error)
    lower = message.lower()
    category, recommendation = "Unknown", "Download diagnostics, inspect logs and retry with a smaller validated input."
    for tokens, candidate, fix in _ERROR_RULES:
        if any(token in lower for token in tokens):
            category, recommendation = candidate, fix
            break
    recovery_id = "BIO140-" + sha256(f"{stage}:{message}".encode()).hexdigest()[:12].upper()
    return {"recovery_id": recovery_id, "stage": stage, "category": category, "message": message, "recommended_fix": recommendation, "safe_retry": category not in {"Integrity"}}


__all__ = ["ResourcePlan", "plan_resources", "CheckpointStore", "diagnose_failure"]
