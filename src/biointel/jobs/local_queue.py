from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    status: str
    priority: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str
    attempts: int
    max_attempts: int
    created_at_utc: str
    started_at_utc: str | None
    completed_at_utc: str | None
    cancel_requested: bool
    pause_requested: bool = False
    resources: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    estimated_seconds: float | None = None
    heartbeat_at_utc: str = ""
    progress_percent: float = 0.0
    current_stage: str = ""
    worker_id: str = ""
    updated_at_utc: str = ""


class LocalJobQueue:
    """Persistent local job orchestration with stages, events, dependencies and artifacts."""

    VALID_STATUSES = {"queued", "running", "paused", "completed", "failed", "cancelled", "blocked"}

    def __init__(self, path: str | Path) -> None:
        requested = Path(path).expanduser().resolve()
        self.requested_path = requested
        self.path = self._select_writable_path(requested)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _target_is_writable(path: Path) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(path.parent, os.W_OK):
                return False
            if path.exists() and not os.access(path, os.W_OK):
                return False
            probe = path.parent / f".biointel-write-probe-{os.getpid()}"
            probe.write_bytes(b"ok")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    @classmethod
    def _select_writable_path(cls, requested: Path) -> Path:
        if cls._target_is_writable(requested):
            return requested

        configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured).expanduser())
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidates.append(Path(local_app_data) / "BioIntelAI" / "UserData")
        try:
            candidates.append(Path.home() / ".biointel_ai" / "UserData")
        except RuntimeError:
            pass
        candidates.append(Path(tempfile.gettempdir()) / "BioIntelAI" / "UserData")

        namespace = hashlib.sha256(str(requested).encode("utf-8")).hexdigest()[:12]
        for base in candidates:
            fallback = (base / "runtime" / "jobs" / namespace / requested.name).resolve()
            if not cls._target_is_writable(fallback):
                continue
            fallback.parent.mkdir(parents=True, exist_ok=True)
            if requested.is_file() and not fallback.exists():
                try:
                    shutil.copy2(requested, fallback)
                except OSError:
                    pass
            return fallback
        raise PermissionError(f"No writable job-queue location is available for {requested}")

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
        except sqlite3.OperationalError:
            pass
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info('{table}')")}

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS local_jobs(
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    created_at_utc TEXT NOT NULL,
                    started_at_utc TEXT,
                    completed_at_utc TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0, 1)),
                    pause_requested INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN (0, 1)),
                    resources_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    estimated_seconds REAL,
                    heartbeat_at_utc TEXT NOT NULL DEFAULT '',
                    progress_percent REAL NOT NULL DEFAULT 0 CHECK(progress_percent >= 0 AND progress_percent <= 100),
                    current_stage TEXT NOT NULL DEFAULT '',
                    worker_id TEXT NOT NULL DEFAULT '',
                    updated_at_utc TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS job_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '',
                    progress_percent REAL,
                    message TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at_utc TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES local_jobs(job_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS job_stages(
                    job_id TEXT NOT NULL,
                    stage_key TEXT NOT NULL,
                    stage_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress_percent REAL NOT NULL DEFAULT 0,
                    started_at_utc TEXT,
                    completed_at_utc TEXT,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(job_id, stage_key),
                    FOREIGN KEY(job_id) REFERENCES local_jobs(job_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS job_dependencies(
                    job_id TEXT NOT NULL,
                    depends_on_job_id TEXT NOT NULL,
                    required_status TEXT NOT NULL DEFAULT 'completed',
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY(job_id, depends_on_job_id),
                    FOREIGN KEY(job_id) REFERENCES local_jobs(job_id) ON DELETE CASCADE,
                    FOREIGN KEY(depends_on_job_id) REFERENCES local_jobs(job_id) ON DELETE CASCADE,
                    CHECK(job_id <> depends_on_job_id)
                );
                CREATE TABLE IF NOT EXISTS job_artifacts(
                    artifact_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES local_jobs(job_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS worker_heartbeats(
                    worker_id TEXT PRIMARY KEY,
                    worker_type TEXT NOT NULL DEFAULT 'local',
                    status TEXT NOT NULL DEFAULT 'online',
                    capabilities_json TEXT NOT NULL DEFAULT '{}',
                    current_job_id TEXT,
                    last_heartbeat_utc TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(current_job_id) REFERENCES local_jobs(job_id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_local_jobs_status_priority
                    ON local_jobs(status, priority, created_at_utc);
                CREATE INDEX IF NOT EXISTS idx_local_jobs_type_status
                    ON local_jobs(job_type, status);
                CREATE INDEX IF NOT EXISTS idx_job_events_job_time
                    ON job_events(job_id, occurred_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_job_dependencies_parent
                    ON job_dependencies(depends_on_job_id);
                CREATE INDEX IF NOT EXISTS idx_job_artifacts_job
                    ON job_artifacts(job_id, created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_time
                    ON worker_heartbeats(last_heartbeat_utc DESC);
                """
            )
            # Upgrade older Step 32 databases in place.
            columns = self._columns(connection, "local_jobs")
            additions = {
                "progress_percent": "REAL NOT NULL DEFAULT 0",
                "current_stage": "TEXT NOT NULL DEFAULT ''",
                "worker_id": "TEXT NOT NULL DEFAULT ''",
                "updated_at_utc": "TEXT NOT NULL DEFAULT ''",
                "pause_requested": "INTEGER NOT NULL DEFAULT 0",
                "resources_json": "TEXT NOT NULL DEFAULT '{}'",
                "checkpoint_json": "TEXT NOT NULL DEFAULT '{}'",
                "estimated_seconds": "REAL",
                "heartbeat_at_utc": "TEXT NOT NULL DEFAULT ''",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE local_jobs ADD COLUMN {name} {definition}")
            connection.execute(
                "UPDATE local_jobs SET updated_at_utc=COALESCE(NULLIF(updated_at_utc,''), created_at_utc)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_local_jobs_worker_status ON local_jobs(worker_id, status)"
            )

    @staticmethod
    def _row(record: sqlite3.Row) -> JobRecord:
        keys = set(record.keys())
        return JobRecord(
            job_id=str(record["job_id"]),
            job_type=str(record["job_type"]),
            status=str(record["status"]),
            priority=int(record["priority"]),
            payload=json.loads(record["payload_json"]),
            result=(json.loads(record["result_json"]) if record["result_json"] else None),
            error=str(record["error"]),
            attempts=int(record["attempts"]),
            max_attempts=int(record["max_attempts"]),
            created_at_utc=str(record["created_at_utc"]),
            started_at_utc=record["started_at_utc"],
            completed_at_utc=record["completed_at_utc"],
            cancel_requested=bool(record["cancel_requested"]),
            pause_requested=bool(record["pause_requested"]) if "pause_requested" in keys else False,
            resources=(json.loads(record["resources_json"]) if "resources_json" in keys and record["resources_json"] else {}),
            checkpoint=(json.loads(record["checkpoint_json"]) if "checkpoint_json" in keys and record["checkpoint_json"] else {}),
            estimated_seconds=(float(record["estimated_seconds"]) if "estimated_seconds" in keys and record["estimated_seconds"] is not None else None),
            heartbeat_at_utc=str(record["heartbeat_at_utc"]) if "heartbeat_at_utc" in keys else "",
            progress_percent=float(record["progress_percent"]) if "progress_percent" in keys else 0.0,
            current_stage=str(record["current_stage"]) if "current_stage" in keys else "",
            worker_id=str(record["worker_id"]) if "worker_id" in keys else "",
            updated_at_utc=str(record["updated_at_utc"]) if "updated_at_utc" in keys else "",
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        job_id: str,
        event_type: str,
        *,
        stage: str = "",
        progress_percent: float | None = None,
        message: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO job_events(
                job_id, event_type, stage, progress_percent, message, detail_json, occurred_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                event_type,
                stage,
                progress_percent,
                message[:2000],
                json.dumps(detail or {}, sort_keys=True, default=str),
                _utc_now(),
            ),
        )

    def submit(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        priority: int = 100,
        max_attempts: int = 3,
        dependencies: list[str] | None = None,
        stages: list[str] | None = None,
        resources: dict[str, Any] | None = None,
        estimated_seconds: float | None = None,
    ) -> JobRecord:
        if not job_type.strip():
            raise ValueError("job_type is required")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        job_id = "job-" + uuid4().hex
        now = _utc_now()
        dependencies = list(dict.fromkeys(dependencies or []))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for dependency in dependencies:
                if connection.execute(
                    "SELECT 1 FROM local_jobs WHERE job_id=?", (dependency,)
                ).fetchone() is None:
                    raise KeyError(f"Unknown dependency job: {dependency}")
            status = "blocked" if dependencies else "queued"
            connection.execute(
                """
                INSERT INTO local_jobs(
                    job_id, job_type, status, priority, payload_json,
                    max_attempts, created_at_utc, updated_at_utc, resources_json, estimated_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job_type.strip(),
                    status,
                    int(priority),
                    json.dumps(payload, sort_keys=True, default=str),
                    int(max_attempts),
                    now,
                    now,
                    json.dumps(resources or {}, sort_keys=True, default=str),
                    float(estimated_seconds) if estimated_seconds is not None else None,
                ),
            )
            for dependency in dependencies:
                connection.execute(
                    """
                    INSERT INTO job_dependencies(job_id, depends_on_job_id, created_at_utc)
                    VALUES (?, ?, ?)
                    """,
                    (job_id, dependency, now),
                )
            for index, stage in enumerate(stages or ["prepare", "execute", "validate", "finalize"]):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO job_stages(job_id, stage_key, stage_order)
                    VALUES (?, ?, ?)
                    """,
                    (job_id, str(stage), index),
                )
            self._event(connection, job_id, "submitted", message=f"Job submitted with status {status}")
            connection.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM local_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row(row)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[JobRecord]:
        if status is not None and status not in self.VALID_STATUSES:
            raise ValueError("Unsupported job status")
        query = "SELECT * FROM local_jobs"
        parameters: list[Any] = []
        if status is not None:
            query += " WHERE status=?"
            parameters.append(status)
        query += " ORDER BY created_at_utc DESC LIMIT ?"
        parameters.append(min(max(int(limit), 1), 5000))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row(row) for row in rows]

    def _release_dependencies(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE local_jobs
            SET status='queued', updated_at_utc=?
            WHERE status='blocked'
              AND NOT EXISTS (
                SELECT 1
                FROM job_dependencies dependency
                JOIN local_jobs parent ON parent.job_id=dependency.depends_on_job_id
                WHERE dependency.job_id=local_jobs.job_id
                  AND parent.status <> dependency.required_status
              )
            """,
            (_utc_now(),),
        )

    def claim_next(self, *, job_type: str | None = None, worker_id: str = "local-worker") -> JobRecord | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._release_dependencies(connection)
            query = (
                "SELECT job_id FROM local_jobs "
                "WHERE status='queued' AND cancel_requested=0 AND pause_requested=0 AND attempts < max_attempts"
            )
            parameters: list[Any] = []
            if job_type is not None:
                query += " AND job_type=?"
                parameters.append(job_type)
            query += " ORDER BY priority ASC, created_at_utc ASC LIMIT 1"
            row = connection.execute(query, parameters).fetchone()
            if row is None:
                connection.commit()
                return None
            job_id = str(row["job_id"])
            now = _utc_now()
            connection.execute(
                """
                UPDATE local_jobs
                SET status='running', attempts=attempts+1,
                    started_at_utc=?, completed_at_utc=NULL, error='',
                    worker_id=?, current_stage='prepare', progress_percent=1,
                    heartbeat_at_utc=?, updated_at_utc=?
                WHERE job_id=? AND status='queued'
                """,
                (now, worker_id, now, now, job_id),
            )
            connection.execute(
                """
                UPDATE job_stages SET status='running', started_at_utc=?
                WHERE job_id=? AND stage_key=(
                    SELECT stage_key FROM job_stages WHERE job_id=? ORDER BY stage_order LIMIT 1
                )
                """,
                (now, job_id, job_id),
            )
            self._event(connection, job_id, "claimed", stage="prepare", progress_percent=1, detail={"worker_id": worker_id})
            connection.commit()
        self.heartbeat(worker_id, current_job_id=job_id, status="busy")
        return self.get(job_id)

    def update_progress(
        self,
        job_id: str,
        *,
        progress_percent: float,
        stage: str,
        message: str = "",
        detail: dict[str, Any] | None = None,
    ) -> JobRecord:
        progress = min(max(float(progress_percent), 0.0), 100.0)
        now = _utc_now()
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM local_jobs WHERE job_id=?", (job_id,)).fetchone() is None:
                raise KeyError(job_id)
            connection.execute(
                """
                UPDATE local_jobs
                SET progress_percent=?, current_stage=?, heartbeat_at_utc=?, updated_at_utc=?,
                    estimated_seconds=CASE
                        WHEN started_at_utc IS NOT NULL AND ? > 1 AND ? < 100
                        THEN MAX(0, (julianday(?) - julianday(started_at_utc))*86400.0 * (100.0-?)/?)
                        ELSE estimated_seconds END
                WHERE job_id=?
                """,
                (progress, stage, now, now, progress, progress, now, progress, progress, job_id),
            )
            connection.execute(
                """
                INSERT INTO job_stages(job_id, stage_key, stage_order, status, progress_percent, started_at_utc, detail_json)
                VALUES (?, ?, 999, 'running', ?, ?, ?)
                ON CONFLICT(job_id, stage_key) DO UPDATE SET
                    status='running', progress_percent=excluded.progress_percent,
                    started_at_utc=COALESCE(job_stages.started_at_utc, excluded.started_at_utc),
                    detail_json=excluded.detail_json
                """,
                (job_id, stage, progress, now, json.dumps(detail or {}, sort_keys=True, default=str)),
            )
            self._event(connection, job_id, "progress", stage=stage, progress_percent=progress, message=message, detail=detail)
        return self.get(job_id)

    def complete(self, job_id: str, result: dict[str, Any]) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT status, cancel_requested, worker_id FROM local_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if current is None:
                raise KeyError(job_id)
            status = "cancelled" if bool(current["cancel_requested"]) else "completed"
            connection.execute(
                """
                UPDATE local_jobs
                SET status=?, result_json=?, completed_at_utc=?, progress_percent=?,
                    current_stage=?, pause_requested=0, heartbeat_at_utc=?, updated_at_utc=?
                WHERE job_id=?
                """,
                (
                    status,
                    json.dumps(result, sort_keys=True, default=str),
                    now,
                    100.0 if status == "completed" else 0.0,
                    "complete" if status == "completed" else "cancelled",
                    now,
                    now,
                    job_id,
                ),
            )
            connection.execute(
                """
                UPDATE job_stages SET status='completed', progress_percent=100,
                    completed_at_utc=COALESCE(completed_at_utc, ?)
                WHERE job_id=? AND status IN ('pending','running')
                """,
                (now, job_id),
            )
            self._event(connection, job_id, status, stage="complete", progress_percent=100 if status == "completed" else 0, detail={"result_keys": sorted(result)})
            worker_id = str(current["worker_id"])
        if worker_id:
            self.heartbeat(worker_id, current_job_id=None, status="online")
        return self.get(job_id)

    def fail(self, job_id: str, error: str, *, retry: bool = True) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts, cancel_requested, worker_id FROM local_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if bool(row["cancel_requested"]):
                status = "cancelled"
            elif retry and int(row["attempts"]) < int(row["max_attempts"]):
                status = "queued"
            else:
                status = "failed"
            connection.execute(
                """
                UPDATE local_jobs
                SET status=?, error=?, completed_at_utc=?, updated_at_utc=?,
                    current_stage=?, pause_requested=0, heartbeat_at_utc=?,
                    worker_id=CASE WHEN ?='queued' THEN '' ELSE worker_id END
                WHERE job_id=?
                """,
                (status, str(error)[:4000], now, now, status, now, status, job_id),
            )
            self._event(connection, job_id, "failed" if status != "queued" else "retry_scheduled", stage="error", message=str(error)[:1000], detail={"retry": retry, "next_status": status})
            worker_id = str(row["worker_id"])
        if worker_id:
            self.heartbeat(worker_id, current_job_id=None, status="online")
        return self.get(job_id)

    def request_cancel(self, job_id: str) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM local_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in {"queued", "blocked"}:
                connection.execute(
                    """
                    UPDATE local_jobs
                    SET cancel_requested=1, status='cancelled', completed_at_utc=?,
                        current_stage='cancelled', updated_at_utc=?
                    WHERE job_id=?
                    """,
                    (now, now, job_id),
                )
            else:
                connection.execute(
                    "UPDATE local_jobs SET cancel_requested=1, updated_at_utc=? WHERE job_id=?",
                    (now, job_id),
                )
            self._event(connection, job_id, "cancel_requested", stage="cancel", message="Cancellation requested by operator")
        return self.get(job_id)

    def retry(self, job_id: str) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, attempts, max_attempts FROM local_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            connection.execute(
                """
                UPDATE local_jobs
                SET status='queued', cancel_requested=0, pause_requested=0, error='', result_json=NULL,
                    completed_at_utc=NULL, current_stage='', progress_percent=0,
                    worker_id='', updated_at_utc=?, max_attempts=MAX(max_attempts, attempts+1)
                WHERE job_id=?
                """,
                (now, job_id),
            )
            connection.execute(
                """
                UPDATE job_stages SET status='pending', progress_percent=0,
                    started_at_utc=NULL, completed_at_utc=NULL WHERE job_id=?
                """,
                (job_id,),
            )
            self._event(connection, job_id, "retried", message="Job returned to queue")
        return self.get(job_id)

    def request_pause(self, job_id: str) -> JobRecord:
        """Pause a queued job immediately or request cooperative pause for a running job."""
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM local_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            status = str(row["status"])
            if status in {"queued", "blocked"}:
                connection.execute(
                    "UPDATE local_jobs SET status='paused', pause_requested=1, current_stage='paused', updated_at_utc=? WHERE job_id=?",
                    (now, job_id),
                )
            elif status == "running":
                connection.execute(
                    "UPDATE local_jobs SET pause_requested=1, updated_at_utc=? WHERE job_id=?",
                    (now, job_id),
                )
            elif status != "paused":
                raise ValueError(f"Job in status {status!r} cannot be paused.")
            self._event(connection, job_id, "pause_requested", stage="pause", message="Pause requested by operator")
        return self.get(job_id)

    def mark_paused(self, job_id: str, *, checkpoint: dict[str, Any] | None = None) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM local_jobs WHERE job_id=?", (job_id,)).fetchone() is None:
                raise KeyError(job_id)
            connection.execute(
                """
                UPDATE local_jobs SET status='paused', pause_requested=1, worker_id='',
                    current_stage='paused', checkpoint_json=?, heartbeat_at_utc=?, updated_at_utc=?
                WHERE job_id=?
                """,
                (json.dumps(checkpoint or {}, sort_keys=True, default=str), now, now, job_id),
            )
            self._event(connection, job_id, "paused", stage="pause", message="Worker paused job cooperatively", detail=checkpoint)
        return self.get(job_id)

    def resume(self, job_id: str) -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM local_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if str(row["status"]) != "paused":
                raise ValueError("Only paused jobs can be resumed.")
            connection.execute(
                "UPDATE local_jobs SET status='queued', pause_requested=0, worker_id='', current_stage='resume', updated_at_utc=? WHERE job_id=?",
                (now, job_id),
            )
            self._event(connection, job_id, "resumed", stage="resume", message="Job returned to queue")
        return self.get(job_id)

    def save_checkpoint(self, job_id: str, checkpoint: dict[str, Any], *, stage: str = "") -> JobRecord:
        now = _utc_now()
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM local_jobs WHERE job_id=?", (job_id,)).fetchone() is None:
                raise KeyError(job_id)
            connection.execute(
                "UPDATE local_jobs SET checkpoint_json=?, heartbeat_at_utc=?, updated_at_utc=? WHERE job_id=?",
                (json.dumps(checkpoint, sort_keys=True, default=str), now, now, job_id),
            )
            self._event(connection, job_id, "checkpoint", stage=stage, message="Checkpoint saved", detail=checkpoint)
        return self.get(job_id)

    def control_state(self, job_id: str) -> dict[str, bool]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested, pause_requested FROM local_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return {"cancel_requested": bool(row["cancel_requested"]), "pause_requested": bool(row["pause_requested"])}

    def recover_orphaned_jobs(self, *, stale_after_seconds: int = 120) -> dict[str, int]:
        """Return stale running jobs to the queue after a worker/process crash."""
        cutoff = (datetime.now(UTC) - timedelta(seconds=max(30, int(stale_after_seconds)))).isoformat(timespec="seconds")
        now = _utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id FROM local_jobs
                WHERE status='running' AND COALESCE(NULLIF(heartbeat_at_utc,''), updated_at_utc) < ?
                """,
                (cutoff,),
            ).fetchall()
            for row in rows:
                job_id = str(row["job_id"])
                connection.execute(
                    """
                    UPDATE local_jobs SET status='queued', worker_id='', current_stage='recovered',
                        error='Recovered after stale worker heartbeat', updated_at_utc=?
                    WHERE job_id=?
                    """,
                    (now, job_id),
                )
                self._event(connection, job_id, "orphan_recovered", stage="recovery", message="Stale running job returned to queue")
        return {"recovered": len(rows)}

    def heartbeat_job(self, job_id: str, *, worker_id: str = "") -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE local_jobs SET heartbeat_at_utc=?, updated_at_utc=?, worker_id=COALESCE(NULLIF(?,''), worker_id) WHERE job_id=?",
                (now, now, worker_id, job_id),
            )

    def add_artifact(
        self,
        job_id: str,
        *,
        artifact_type: str,
        relative_path: str,
        sha256: str = "",
        size_bytes: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = "artifact-" + uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO job_artifacts(
                    artifact_id, job_id, artifact_type, relative_path, sha256,
                    size_bytes, metadata_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    artifact_type,
                    relative_path,
                    sha256,
                    max(int(size_bytes), 0),
                    json.dumps(metadata or {}, sort_keys=True, default=str),
                    _utc_now(),
                ),
            )
            self._event(connection, job_id, "artifact_created", detail={"artifact_id": artifact_id, "path": relative_path})
        return {"artifact_id": artifact_id, "job_id": job_id, "artifact_type": artifact_type, "relative_path": relative_path, "sha256": sha256, "size_bytes": size_bytes}

    def timeline(self, job_id: str) -> dict[str, Any]:
        self.get(job_id)
        with self._connect() as connection:
            events = [dict(row) for row in connection.execute(
                "SELECT * FROM job_events WHERE job_id=? ORDER BY event_id", (job_id,)
            ).fetchall()]
            stages = [dict(row) for row in connection.execute(
                "SELECT * FROM job_stages WHERE job_id=? ORDER BY stage_order, stage_key", (job_id,)
            ).fetchall()]
            dependencies = [dict(row) for row in connection.execute(
                """
                SELECT d.*, parent.status AS dependency_status, parent.job_type AS dependency_type
                FROM job_dependencies d JOIN local_jobs parent ON parent.job_id=d.depends_on_job_id
                WHERE d.job_id=? ORDER BY d.created_at_utc
                """,
                (job_id,),
            ).fetchall()]
            artifacts = [dict(row) for row in connection.execute(
                "SELECT * FROM job_artifacts WHERE job_id=? ORDER BY created_at_utc", (job_id,)
            ).fetchall()]
        return {"job": self.get(job_id).__dict__, "events": events, "stages": stages, "dependencies": dependencies, "artifacts": artifacts}

    def backfill_existing_history(self) -> dict[str, int]:
        """Create deterministic orchestration stages/events for pre-Step-33 jobs.

        This does not create new jobs or claim scientific work. It only makes the existing
        persisted job lifecycle visible in the upgraded timeline UI.
        """
        stage_keys = ["prepare", "execute", "validate", "finalize"]
        jobs_updated = 0
        events_added = 0
        stages_added = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM local_jobs ORDER BY created_at_utc").fetchall()
            for row in rows:
                job_id = str(row["job_id"])
                existing_stages = int(connection.execute("SELECT COUNT(*) FROM job_stages WHERE job_id=?", (job_id,)).fetchone()[0])
                existing_events = int(connection.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0])
                status = str(row["status"])
                created = str(row["created_at_utc"])
                started = row["started_at_utc"] or created
                completed = row["completed_at_utc"] or started
                if existing_stages == 0:
                    for order, stage_key in enumerate(stage_keys):
                        stage_status = "pending"
                        progress = 0.0
                        stage_started = None
                        stage_completed = None
                        if status == "completed":
                            stage_status, progress, stage_started, stage_completed = "completed", 100.0, started, completed
                        elif status == "running":
                            if order == 0:
                                stage_status, progress, stage_started, stage_completed = "completed", 100.0, started, started
                            elif order == 1:
                                stage_status, progress, stage_started = "running", 50.0, started
                        elif status == "failed":
                            if order == 0:
                                stage_status, progress, stage_started, stage_completed = "completed", 100.0, started, started
                            elif order == 1:
                                stage_status, progress, stage_started, stage_completed = "failed", 50.0, started, completed
                        elif status == "cancelled" and order == 0:
                            stage_status, progress, stage_started, stage_completed = "cancelled", 0.0, created, completed
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO job_stages(
                                job_id,stage_key,stage_order,status,progress_percent,
                                started_at_utc,completed_at_utc,detail_json
                            ) VALUES(?,?,?,?,?,?,?,?)
                            """,
                            (job_id, stage_key, order, stage_status, progress, stage_started, stage_completed, json.dumps({"backfilled": True, "source_status": status})),
                        )
                        stages_added += 1
                if existing_events == 0:
                    self._event(connection, job_id, "submitted", message="Historical job registered", detail={"backfilled": True})
                    events_added += 1
                    if status != "queued":
                        self._event(
                            connection,
                            job_id,
                            status,
                            stage=str(row["current_stage"] or "execute") if "current_stage" in row.keys() else "execute",
                            progress_percent=float(row["progress_percent"] or (100 if status == "completed" else 0)) if "progress_percent" in row.keys() else (100 if status == "completed" else 0),
                            message=f"Historical terminal/current status: {status}",
                            detail={"backfilled": True},
                        )
                        events_added += 1
                if existing_stages == 0 or existing_events == 0:
                    jobs_updated += 1
            connection.commit()
        return {"jobs_updated": jobs_updated, "stages_added": stages_added, "events_added": events_added}

    def heartbeat(
        self,
        worker_id: str,
        *,
        worker_type: str = "local",
        status: str = "online",
        capabilities: dict[str, Any] | None = None,
        current_job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO worker_heartbeats(
                    worker_id, worker_type, status, capabilities_json,
                    current_job_id, last_heartbeat_utc, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    worker_type=excluded.worker_type,
                    status=excluded.status,
                    capabilities_json=excluded.capabilities_json,
                    current_job_id=excluded.current_job_id,
                    last_heartbeat_utc=excluded.last_heartbeat_utc,
                    metadata_json=excluded.metadata_json
                """,
                (
                    worker_id,
                    worker_type,
                    status,
                    json.dumps(capabilities or {}, sort_keys=True, default=str),
                    current_job_id,
                    _utc_now(),
                    json.dumps(metadata or {}, sort_keys=True, default=str),
                ),
            )

    def workers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM worker_heartbeats ORDER BY last_heartbeat_utc DESC"
            ).fetchall()]

    def orchestration_summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            statuses = {str(row["status"]): int(row["count"]) for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM local_jobs GROUP BY status"
            ).fetchall()}
            counts = {
                "jobs": int(connection.execute("SELECT COUNT(*) FROM local_jobs").fetchone()[0]),
                "events": int(connection.execute("SELECT COUNT(*) FROM job_events").fetchone()[0]),
                "stages": int(connection.execute("SELECT COUNT(*) FROM job_stages").fetchone()[0]),
                "dependencies": int(connection.execute("SELECT COUNT(*) FROM job_dependencies").fetchone()[0]),
                "artifacts": int(connection.execute("SELECT COUNT(*) FROM job_artifacts").fetchone()[0]),
                "workers": int(connection.execute("SELECT COUNT(*) FROM worker_heartbeats").fetchone()[0]),
            }
        return {"statuses": statuses, **counts}
