from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import platform as py_platform
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import traceback
import uuid

from biointel.runtime_paths import user_data_root
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import pandas as pd

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

from .catalog import PROFILES


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def digest_path(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def safe_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "item"


def redact_text(text: str) -> str:
    patterns = (
        (r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
        (r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |OPENSSH )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]"),
    )
    output = str(text)
    for pattern, replacement in patterns:
        output = re.sub(pattern, replacement, output, flags=re.DOTALL)
    return output


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    initialise_schema(conn)
    return conn


def initialise_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects(
          project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
          owner TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS samples(
          sample_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          display_name TEXT NOT NULL, organism TEXT NOT NULL, assay TEXT NOT NULL,
          metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets(
          asset_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          sample_id TEXT REFERENCES samples(sample_id) ON DELETE SET NULL, module_key TEXT NOT NULL,
          role TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
          mime_type TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS engines(
          engine_id TEXT PRIMARY KEY, name TEXT NOT NULL, module_key TEXT NOT NULL, executable TEXT,
          version TEXT, status TEXT NOT NULL, source TEXT NOT NULL, checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS references_registry(
          reference_id TEXT PRIMARY KEY, module_key TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL,
          path TEXT NOT NULL, sha256 TEXT NOT NULL, licence TEXT NOT NULL, permission_status TEXT NOT NULL,
          status TEXT NOT NULL, created_at TEXT NOT NULL, supersedes TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs(
          job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          module_key TEXT NOT NULL, job_type TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL,
          progress REAL NOT NULL, attempt INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
          payload_json TEXT NOT NULL, checkpoint_json TEXT NOT NULL, result_json TEXT NOT NULL,
          error_code TEXT, worker_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, heartbeat_at TEXT
        );
        CREATE TABLE IF NOT EXISTS handoffs(
          handoff_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          source_module TEXT NOT NULL, target_module TEXT NOT NULL, asset_ids_json TEXT NOT NULL,
          contract_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provenance(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, project_id TEXT NOT NULL,
          module_key TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
          previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews(
          review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          module_key TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL, from_status TEXT NOT NULL,
          to_status TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metrics(
          metric_id TEXT PRIMARY KEY, module_key TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL,
          unit TEXT NOT NULL, dimensions_json TEXT NOT NULL, recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS errors(
          error_id TEXT PRIMARY KEY, module_key TEXT NOT NULL, stage TEXT NOT NULL, error_code TEXT NOT NULL,
          message TEXT NOT NULL, suggested_fix TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority DESC, created_at);
        CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, module_key);
        CREATE INDEX IF NOT EXISTS idx_metrics_module_name ON metrics(module_key, name, recorded_at);
        """
    )
    conn.commit()


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    status: str


class ProjectRegistry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create_project(self, name: str, description: str, owner: str = "local-user", *, project_id: str | None = None) -> ProjectRecord:
        project_id = project_id or f"PRJ-{uuid.uuid4().hex[:12].upper()}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects(project_id,name,description,owner,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (project_id, name.strip(), description.strip(), owner, "active", now, now),
            )
        return ProjectRecord(project_id, name.strip(), "active")

    def add_sample(self, project_id: str, display_name: str, organism: str, assay: str, metadata: Mapping[str, Any], *, sample_id: str | None = None) -> str:
        sample_id = sample_id or f"SMP-{uuid.uuid4().hex[:12].upper()}"
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO samples(sample_id,project_id,display_name,organism,assay,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (sample_id, project_id, display_name, organism, assay, stable_json(dict(metadata)), utc_now()),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE project_id=?", (utc_now(), project_id))
        return sample_id

    def register_asset(self, project_id: str, module_key: str, path: Path, role: str, *, sample_id: str | None = None, mime_type: str = "application/octet-stream") -> str:
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        asset_id = f"AST-{digest_bytes(f'{project_id}|{module_key}|{path}|{digest_path(path)}'.encode())[:16].upper()}"
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assets(asset_id,project_id,sample_id,module_key,role,path,sha256,size_bytes,mime_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (asset_id, project_id, sample_id, module_key, role, str(path), digest_path(path), path.stat().st_size, mime_type, utc_now()),
            )
        return asset_id

    def project_snapshot(self, project_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            project = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(project_id)
            samples = [dict(r) for r in conn.execute("SELECT * FROM samples WHERE project_id=? ORDER BY sample_id", (project_id,))]
            assets = [dict(r) for r in conn.execute("SELECT * FROM assets WHERE project_id=? ORDER BY asset_id", (project_id,))]
        return {"project": dict(project), "samples": samples, "assets": assets}

    def portable_bundle(self, project_id: str) -> bytes:
        snapshot = self.project_snapshot(project_id)
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project_snapshot.json", json.dumps(snapshot, indent=2, sort_keys=True))
            for asset in snapshot["assets"]:
                path = Path(asset["path"])
                if path.is_file():
                    archive.write(path, f"assets/{asset['asset_id']}_{path.name}")
            archive.writestr("MANIFEST.json", json.dumps({
                "schema": "biointel.step189.portable_project.v1",
                "project_id": project_id,
                "created_at": utc_now(),
                "asset_count": len(snapshot["assets"]),
            }, indent=2))
        return memory.getvalue()


@dataclass(frozen=True)
class EngineStatus:
    name: str
    executable: str | None
    version: str | None
    status: str
    source: str


class EngineHub:
    VERSION_FLAGS: tuple[tuple[str, ...], ...] = (("--version",), ("-version",), ("version",))

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def detect(self, module_key: str, engine_name: str) -> EngineStatus:
        candidates = [engine_name, engine_name.replace("2", ""), engine_name.replace("-", "")]
        executable = next((shutil.which(c) for c in candidates if shutil.which(c)), None)
        version = None
        status = "available" if executable else "demo_fallback"
        source = "system_path" if executable else "safe_internal_demo_adapter"
        if executable:
            for flag in self.VERSION_FLAGS:
                try:
                    completed = subprocess.run([executable, *flag], capture_output=True, text=True, timeout=4, check=False)
                    text = (completed.stdout or completed.stderr).strip().splitlines()
                    if text:
                        version = redact_text(text[0])[:200]
                        break
                except (OSError, subprocess.SubprocessError):
                    continue
        record = EngineStatus(engine_name, executable, version, status, source)
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO engines(engine_id,name,module_key,executable,version,status,source,checked_at) VALUES(?,?,?,?,?,?,?,?)",
                (f"{module_key}:{engine_name}", engine_name, module_key, executable, version, status, source, utc_now()),
            )
        return record

    def detect_for_module(self, module_key: str) -> list[EngineStatus]:
        return [self.detect(module_key, name) for name in PROFILES[module_key].recommended_engines]

    def safe_demo_execute(self, module_key: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        if frame.empty:
            raise ValueError("Input dataset is empty")
        output = frame.copy()
        numeric = list(output.select_dtypes(include=["number"]).columns)
        if numeric:
            series = output[numeric[0]].astype(float)
            std = float(series.std(ddof=0)) or 1.0
            output["step189_score"] = ((series - float(series.mean())) / std).round(6)
        else:
            output["step189_score"] = output.iloc[:, 0].astype(str).str.len().astype(float)
        output["step189_confidence"] = (1 / (1 + output["step189_score"].abs())).clip(0.05, 0.99).round(6)
        output["step189_decision"] = output["step189_confidence"].map(lambda x: "review" if x < 0.25 else "pass")
        output["step189_module_key"] = module_key
        summary = {
            "adapter": "safe_internal_demo_adapter",
            "records": len(output),
            "output_sha256": digest_bytes(output.to_csv(index=False).encode()),
            "mean_confidence": round(float(output["step189_confidence"].mean()), 6),
        }
        return output, summary


class ReferenceManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def register(self, module_key: str, name: str, version: str, path: Path, licence: str, permission_status: str, *, supersedes: str | None = None) -> str:
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        reference_id = f"REF-{safe_slug(module_key)}-{safe_slug(name)}-{safe_slug(version)}"
        status = "qualified_demo" if permission_status in {"redistributable_demo", "accepted"} else "blocked"
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO references_registry(reference_id,module_key,name,version,path,sha256,licence,permission_status,status,created_at,supersedes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (reference_id, module_key, name, version, str(path), digest_path(path), licence, permission_status, status, utc_now(), supersedes),
            )
        return reference_id

    def verify(self, reference_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM references_registry WHERE reference_id=?", (reference_id,)).fetchone()
        if row is None:
            raise KeyError(reference_id)
        payload = dict(row)
        path = Path(payload["path"])
        payload["file_exists"] = path.is_file()
        payload["checksum_matches"] = path.is_file() and digest_path(path) == payload["sha256"]
        payload["qualified"] = bool(payload["file_exists"] and payload["checksum_matches"] and payload["status"] == "qualified_demo")
        return payload

    def rollback(self, current_id: str, previous_id: str) -> dict[str, Any]:
        current = self.verify(current_id)
        previous = self.verify(previous_id)
        if current["module_key"] != previous["module_key"] or current["name"] != previous["name"]:
            raise ValueError("Rollback references must belong to the same module and reference family")
        return {"from": current_id, "to": previous_id, "status": "rollback_ready", "verified_at": utc_now()}


ALLOWED_JOB_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "cancel_requested", "queued"},
    "cancel_requested": {"cancelled", "running"},
    "failed": {"queued"},
    "completed": set(),
    "cancelled": set(),
}


class DurableJobQueue:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def enqueue(self, project_id: str, module_key: str, job_type: str, payload: Mapping[str, Any], priority: int = 50, max_attempts: int = 3) -> str:
        job_id = f"JOB-{uuid.uuid4().hex[:16].upper()}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO jobs(job_id,project_id,module_key,job_type,status,priority,progress,attempt,max_attempts,payload_json,checkpoint_json,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, project_id, module_key, job_type, "queued", int(priority), 0.0, 0, int(max_attempts), stable_json(dict(payload)), "{}", "{}", now, now),
            )
        return job_id

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at LIMIT 1").fetchone()
            if row is None:
                conn.rollback()
                return None
            now = utc_now()
            conn.execute(
                "UPDATE jobs SET status='running',attempt=attempt+1,worker_id=?,updated_at=?,heartbeat_at=? WHERE job_id=? AND status='queued'",
                (worker_id, now, now, row["job_id"]),
            )
            conn.commit()
        return self.get(row["job_id"])

    def get(self, job_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def transition(self, job_id: str, new_status: str, *, progress: float | None = None, checkpoint: Mapping[str, Any] | None = None, result: Mapping[str, Any] | None = None, error_code: str | None = None) -> None:
        current = self.get(job_id)
        if new_status not in ALLOWED_JOB_TRANSITIONS.get(current["status"], set()):
            raise ValueError(f"Invalid job transition {current['status']} -> {new_status}")
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET status=?,progress=?,checkpoint_json=?,result_json=?,error_code=?,updated_at=?,heartbeat_at=? WHERE job_id=?",
                (
                    new_status,
                    float(progress if progress is not None else current["progress"]),
                    stable_json(dict(checkpoint)) if checkpoint is not None else current["checkpoint_json"],
                    stable_json(dict(result)) if result is not None else current["result_json"],
                    error_code,
                    utc_now(), utc_now(), job_id,
                ),
            )

    def heartbeat(self, job_id: str, progress: float, checkpoint: Mapping[str, Any]) -> None:
        current = self.get(job_id)
        if current["status"] not in {"running", "cancel_requested"}:
            raise ValueError("Heartbeat requires an active job")
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET progress=?,checkpoint_json=?,updated_at=?,heartbeat_at=? WHERE job_id=?",
                (max(0.0, min(1.0, float(progress))), stable_json(dict(checkpoint)), utc_now(), utc_now(), job_id),
            )

    def recover_stale(self, stale_before_iso: str) -> list[str]:
        recovered: list[str] = []
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT job_id,attempt,max_attempts FROM jobs WHERE status='running' AND heartbeat_at<?", (stale_before_iso,)).fetchall()
            for row in rows:
                status = "queued" if row["attempt"] < row["max_attempts"] else "failed"
                conn.execute("UPDATE jobs SET status=?,worker_id=NULL,error_code=?,updated_at=? WHERE job_id=?", (status, "STALE_WORKER", utc_now(), row["job_id"]))
                recovered.append(row["job_id"])
        return recovered


class ProvenanceLedger:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def append(self, project_id: str, module_key: str, event_type: str, payload: Mapping[str, Any]) -> str:
        with connect(self.db_path) as conn:
            previous = conn.execute("SELECT event_hash FROM provenance WHERE project_id=? ORDER BY sequence DESC LIMIT 1", (project_id,)).fetchone()
            previous_hash = previous["event_hash"] if previous else "0" * 64
            event_id = f"EVT-{uuid.uuid4().hex[:16].upper()}"
            created_at = utc_now()
            canonical = stable_json({"event_id": event_id, "project_id": project_id, "module_key": module_key, "event_type": event_type, "payload": dict(payload), "previous_hash": previous_hash, "created_at": created_at})
            event_hash = digest_bytes(canonical.encode())
            conn.execute(
                "INSERT INTO provenance(event_id,project_id,module_key,event_type,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (event_id, project_id, module_key, event_type, stable_json(dict(payload)), previous_hash, event_hash, created_at),
            )
        return event_hash

    def verify(self, project_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM provenance WHERE project_id=? ORDER BY sequence", (project_id,))]
        previous_hash = "0" * 64
        blockers: list[str] = []
        for row in rows:
            if row["previous_hash"] != previous_hash:
                blockers.append(f"previous_hash_mismatch:{row['event_id']}")
            canonical = stable_json({
                "event_id": row["event_id"], "project_id": row["project_id"], "module_key": row["module_key"],
                "event_type": row["event_type"], "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"], "created_at": row["created_at"],
            })
            expected = digest_bytes(canonical.encode())
            if expected != row["event_hash"]:
                blockers.append(f"event_hash_mismatch:{row['event_id']}")
            previous_hash = row["event_hash"]
        return {"project_id": project_id, "events": len(rows), "valid": not blockers, "blockers": blockers, "head_hash": previous_hash}


REVIEW_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_review", "archived"},
    "in_review": {"changes_requested", "approved", "rejected"},
    "changes_requested": {"draft", "in_review"},
    "approved": {"released", "superseded"},
    "released": {"superseded"},
    "rejected": {"draft", "archived"},
    "superseded": set(),
    "archived": set(),
}
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "analyst": {"draft", "in_review"},
    "reviewer": {"changes_requested", "approved", "rejected"},
    "scientist": {"changes_requested", "approved", "rejected"},
    "administrator": set().union(*REVIEW_TRANSITIONS.values()),
    "clinical_reviewer": {"changes_requested", "approved", "rejected"},
    "read_only": set(),
}


class ReviewWorkflow:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def current_status(self, project_id: str, module_key: str) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT to_status FROM reviews WHERE project_id=? AND module_key=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (project_id, module_key)).fetchone()
        return row["to_status"] if row else "draft"

    def transition(self, project_id: str, module_key: str, actor: str, role: str, to_status: str, comment: str) -> str:
        from_status = self.current_status(project_id, module_key)
        if to_status not in REVIEW_TRANSITIONS.get(from_status, set()):
            raise ValueError(f"Invalid review transition {from_status} -> {to_status}")
        if to_status not in ROLE_PERMISSIONS.get(role, set()):
            raise PermissionError(f"Role {role} cannot set status {to_status}")
        review_id = f"REV-{uuid.uuid4().hex[:16].upper()}"
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO reviews(review_id,project_id,module_key,actor,role,from_status,to_status,comment,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (review_id, project_id, module_key, actor, role, from_status, to_status, redact_text(comment), utc_now()),
            )
        return review_id


class HandoffManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create(self, project_id: str, source_module: str, target_module: str, asset_ids: Sequence[str], contract: Mapping[str, Any]) -> str:
        if source_module == target_module:
            raise ValueError("Cross-module handoff requires a different target module")
        handoff_id = f"HOF-{uuid.uuid4().hex[:16].upper()}"
        with connect(self.db_path) as conn:
            if asset_ids:
                placeholders = ",".join("?" for _ in asset_ids)
                rows = conn.execute(f"SELECT asset_id FROM assets WHERE project_id=? AND asset_id IN ({placeholders})", (project_id, *asset_ids)).fetchall()
                if len(rows) != len(set(asset_ids)):
                    raise ValueError("Handoff contains unknown assets")
            conn.execute(
                "INSERT INTO handoffs(handoff_id,project_id,source_module,target_module,asset_ids_json,contract_json,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (handoff_id, project_id, source_module, target_module, stable_json(list(asset_ids)), stable_json(dict(contract)), "ready", utc_now()),
            )
        return handoff_id


@dataclass(frozen=True)
class DiagnosticRecord:
    error_id: str
    error_code: str
    message: str
    suggested_fix: str


class DiagnosticCenter:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def capture(self, module_key: str, stage: str, exc: BaseException, suggested_fix: str) -> DiagnosticRecord:
        error_id = f"ERR-{uuid.uuid4().hex[:12].upper()}"
        code = f"{safe_slug(module_key).upper()[:10]}-{safe_slug(stage).upper()[:8]}-{digest_bytes(type(exc).__name__.encode())[:6].upper()}"
        message = redact_text(str(exc))[:1000]
        details = redact_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))[:20000]
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO errors(error_id,module_key,stage,error_code,message,suggested_fix,details,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (error_id, module_key, stage, code, message, suggested_fix, details, utc_now()),
            )
        return DiagnosticRecord(error_id, code, message, suggested_fix)

    def support_bundle(self, module_key: str, project_id: str | None = None) -> bytes:
        with connect(self.db_path) as conn:
            errors = [dict(r) for r in conn.execute("SELECT * FROM errors WHERE module_key=? ORDER BY created_at DESC LIMIT 50", (module_key,))]
            engines = [dict(r) for r in conn.execute("SELECT * FROM engines WHERE module_key=?", (module_key,))]
            refs = [dict(r) for r in conn.execute("SELECT * FROM references_registry WHERE module_key=?", (module_key,))]
            jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE module_key=? ORDER BY created_at DESC LIMIT 50", (module_key,))]
        payload = {
            "schema": "biointel.step189.support_bundle.v1", "module_key": module_key,
            "project_id": project_id, "created_at": utc_now(), "errors": errors, "engines": engines,
            "references": refs, "jobs": jobs, "environment": environment_manifest(),
        }
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("diagnostics.json", redact_text(json.dumps(payload, indent=2, default=str)))
            archive.writestr("README.txt", "BioIntel AI redacted support bundle. Secrets and direct identifiers are removed.\n")
        return data.getvalue()


class MonitoringCenter:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def record(self, module_key: str, name: str, value: float, unit: str, dimensions: Mapping[str, Any] | None = None) -> str:
        metric_id = f"MET-{uuid.uuid4().hex[:16].upper()}"
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO metrics(metric_id,module_key,name,value,unit,dimensions_json,recorded_at) VALUES(?,?,?,?,?,?,?)",
                (metric_id, module_key, name, float(value), unit, stable_json(dict(dimensions or {})), utc_now()),
            )
        return metric_id

    def snapshot(self, module_key: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            metrics = [dict(r) for r in conn.execute("SELECT * FROM metrics WHERE module_key=? ORDER BY recorded_at", (module_key,))]
            jobs = [dict(r) for r in conn.execute("SELECT status,COUNT(*) AS count FROM jobs WHERE module_key=? GROUP BY status", (module_key,))]
            errors = conn.execute("SELECT COUNT(*) AS n FROM errors WHERE module_key=?", (module_key,)).fetchone()["n"]
        latest: dict[str, float] = {}
        for row in metrics:
            latest[row["name"]] = row["value"]
        alerts = []
        if latest.get("error_rate", 0) > 0.05:
            alerts.append({"severity": "high", "metric": "error_rate", "owner": "module-owner"})
        if latest.get("peak_memory_mb", 0) > 4096:
            alerts.append({"severity": "medium", "metric": "peak_memory_mb", "owner": "platform-operations"})
        return {"module_key": module_key, "latest_metrics": latest, "job_counts": jobs, "error_count": errors, "alerts": alerts, "captured_at": utc_now()}


def environment_manifest() -> dict[str, Any]:
    memory_mb = None
    disk_free_mb = None
    if psutil is not None:
        try:
            memory_mb = round(psutil.virtual_memory().available / 1024 / 1024, 2)
            disk_free_mb = round(psutil.disk_usage(str(Path.cwd())).free / 1024 / 1024, 2)
        except Exception:
            pass
    return {
        "python": py_platform.python_version(), "platform": py_platform.platform(),
        "machine": py_platform.machine(), "processor": py_platform.processor(),
        "available_memory_mb": memory_mb, "free_disk_mb": disk_free_mb,
        "captured_at": utc_now(),
    }


def validate_dataframe(frame: pd.DataFrame) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append({"check": "non_empty", "status": "pass" if not frame.empty else "fail", "detail": len(frame)})
    checks.append({"check": "unique_columns", "status": "pass" if frame.columns.is_unique else "fail", "detail": len(frame.columns)})
    if "record_id" in frame.columns:
        duplicate = int(frame["record_id"].astype(str).duplicated().sum())
        checks.append({"check": "unique_record_id", "status": "pass" if duplicate == 0 else "fail", "detail": duplicate})
    else:
        checks.append({"check": "record_id_present", "status": "warn", "detail": "generated during ingestion"})
    numeric = frame.select_dtypes(include=["number"])
    finite = True
    if not numeric.empty:
        import numpy as np
        finite = bool(np.isfinite(numeric.to_numpy(dtype=float)).all())
    checks.append({"check": "finite_numeric", "status": "pass" if finite else "fail", "detail": len(numeric.columns)})
    text = frame.select_dtypes(include=["object", "string"]).astype(str) if not frame.empty else pd.DataFrame()
    dangerous = False
    secret = False
    if not text.empty:
        dangerous = bool(text.apply(lambda s: s.str.match(r"^[=@]|^[+]\s*(?:[A-Za-z_]|\()|^-\s*(?:cmd|powershell|wscript|bash|sh)\b", case=False, na=False)).any().any())
        secret = bool(text.apply(lambda s: s.str.contains(r"PRIVATE KEY|api[_-]?key\s*[:=]|password\s*[:=]|\.\./|<script", case=False, regex=True, na=False)).any().any())
    checks.append({"check": "formula_or_command_injection", "status": "fail" if dangerous else "pass", "detail": int(dangerous)})
    checks.append({"check": "secret_or_path_traversal", "status": "fail" if secret else "pass", "detail": int(secret)})
    return checks


def preflight(root: Path, module_key: str, frame: pd.DataFrame, engine_statuses: Sequence[EngineStatus], reference_checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    root = Path(root)
    checks = validate_dataframe(frame)
    user_data = user_data_root(root)
    checks.append({"check": "output_directory_writable", "status": "pass" if os.access(user_data, os.W_OK) else "fail", "detail": str(user_data)})
    free_disk = shutil.disk_usage(root).free / 1024 / 1024
    checks.append({"check": "free_disk_mb", "status": "pass" if free_disk >= 250 else "fail", "detail": round(free_disk, 2)})
    available_memory = None
    if psutil is not None:
        try:
            available_memory = psutil.virtual_memory().available / 1024 / 1024
        except Exception:
            available_memory = None
    checks.append({"check": "available_memory_mb", "status": "pass" if available_memory is None or available_memory >= 256 else "warn", "detail": None if available_memory is None else round(available_memory, 2)})
    checks.append({"check": "engine_adapter", "status": "pass" if all(e.status in {"available", "demo_fallback"} for e in engine_statuses) else "fail", "detail": len(engine_statuses)})
    checks.append({"check": "reference_integrity", "status": "pass" if reference_checks and all(bool(r.get("qualified")) for r in reference_checks) else "fail", "detail": len(reference_checks)})
    blockers = [c["check"] for c in checks if c["status"] == "fail"]
    warnings = [c["check"] for c in checks if c["status"] == "warn"]
    decision = "BLOCKED" if blockers else ("WARNING" if warnings else "READY")
    return {"schema": "biointel.step189.preflight.v1", "module_key": module_key, "decision": decision, "checks": checks, "blockers": blockers, "warnings": warnings, "created_at": utc_now()}


def generate_report_bundle(output_dir: Path, module_key: str, project_snapshot: Mapping[str, Any], preflight_result: Mapping[str, Any], analysis_summary: Mapping[str, Any], provenance_result: Mapping[str, Any], monitoring_snapshot: Mapping[str, Any]) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = PROFILES[module_key]
    payload = {
        "schema": "biointel.step189.reproducible_report.v1", "module_key": module_key,
        "title": profile.title, "created_at": utc_now(), "project": project_snapshot,
        "preflight": preflight_result, "analysis": analysis_summary, "provenance": provenance_result,
        "monitoring": monitoring_snapshot, "limitations": profile.boundary,
        "controlled_release_eligible": False,
    }
    json_path = output_dir / "report.json"
    write_json(json_path, payload)
    md = (
        f"# {profile.title} — Step 189 Reproducible Report\n\n"
        f"**Module:** `{module_key}`  \n**Created:** {payload['created_at']}  \n"
        f"**Preflight:** {preflight_result['decision']}  \n**Controlled release:** PENDING external evidence\n\n"
        "## Analysis summary\n\n```json\n" + json.dumps(analysis_summary, indent=2, default=str) + "\n```\n\n"
        "## Provenance verification\n\n```json\n" + json.dumps(provenance_result, indent=2, default=str) + "\n```\n\n"
        "## Limitations and boundary\n\n" + profile.boundary + "\n"
    )
    md_path = output_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    html_path = output_dir / "report.html"
    html_path.write_text("<html><body><pre>" + md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre></body></html>", encoding="utf-8")
    csv_path = output_dir / "report.csv"
    pd.DataFrame([{
        "module_key": module_key, "title": profile.title, "preflight": preflight_result["decision"],
        "records": analysis_summary.get("records", 0), "mean_confidence": analysis_summary.get("mean_confidence"),
        "provenance_valid": provenance_result.get("valid"), "controlled_release_eligible": False,
    }]).to_csv(csv_path, index=False)

    docx_path = output_dir / "report.docx"
    try:
        from docx import Document  # type: ignore
        doc = Document()
        doc.add_heading(profile.title, 0)
        doc.add_paragraph(f"Module: {module_key}")
        doc.add_paragraph(f"Preflight: {preflight_result['decision']}")
        doc.add_heading("Analysis summary", level=1)
        doc.add_paragraph(json.dumps(analysis_summary, indent=2, default=str))
        doc.add_heading("Limitations", level=1)
        doc.add_paragraph(profile.boundary)
        doc.save(docx_path)
    except Exception as exc:  # pragma: no cover
        docx_path.write_text(f"DOCX export unavailable: {exc}\n", encoding="utf-8")

    pdf_path = output_dir / "report.pdf"
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        width, height = A4
        y = height - 50
        for line in (profile.title, f"Module: {module_key}", f"Preflight: {preflight_result['decision']}", "Controlled release: PENDING external evidence", "", "Analysis summary:"):
            c.drawString(50, y, line[:110]); y -= 18
        for line in json.dumps(analysis_summary, indent=2, default=str).splitlines():
            if y < 60: c.showPage(); y = height - 50
            c.drawString(50, y, line[:110]); y -= 14
        c.save()
    except Exception as exc:  # pragma: no cover
        pdf_path.write_text(f"PDF export unavailable: {exc}\n", encoding="utf-8")

    files = [json_path, md_path, html_path, csv_path, docx_path, pdf_path]
    manifest = {p.name: digest_path(p) for p in files}
    write_json(output_dir / "report_manifest.json", manifest)
    bundle_path = output_dir / "report_bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files + [output_dir / "report_manifest.json"]:
            archive.write(path, path.name)
    return {p.suffix.lstrip(".") or p.name: str(p) for p in files} | {"bundle": str(bundle_path)}


def benchmark_adapter(engine_hub: EngineHub, module_key: str, base_frame: pd.DataFrame, tiers: Sequence[int] = (250, 2500, 10000)) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for records in tiers:
        repeats = (records + len(base_frame) - 1) // len(base_frame)
        frame = pd.concat([base_frame] * repeats, ignore_index=True).head(records).copy()
        if "record_id" in frame.columns:
            frame["record_id"] = [f"R{i:07d}" for i in range(len(frame))]
        start = time.perf_counter()
        output, summary = engine_hub.safe_demo_execute(module_key, frame)
        elapsed = max(time.perf_counter() - start, 1e-9)
        rows.append({
            "records": records, "runtime_seconds": round(elapsed, 6),
            "records_per_second": round(records / elapsed, 2),
            "estimated_memory_mb": round((frame.memory_usage(deep=True).sum() + output.memory_usage(deep=True).sum()) / 1024 / 1024, 3),
            "output_sha256": summary["output_sha256"], "status": "pass",
        })
    return pd.DataFrame(rows)


__all__ = [
    "ProjectRegistry", "EngineHub", "ReferenceManager", "DurableJobQueue", "ProvenanceLedger",
    "ReviewWorkflow", "HandoffManager", "DiagnosticCenter", "MonitoringCenter", "EngineStatus",
    "connect", "preflight", "generate_report_bundle", "benchmark_adapter", "environment_manifest",
    "digest_path", "digest_bytes", "write_json", "utc_now", "redact_text", "validate_dataframe",
]
