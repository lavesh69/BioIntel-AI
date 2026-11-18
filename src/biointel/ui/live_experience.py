from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from biointel.database.core import managed_connect

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _state_root() -> Path:
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    base = Path(configured).expanduser() if configured else PROJECT_ROOT / "UserData"
    target = base.resolve() / "workspace"
    target.mkdir(parents=True, exist_ok=True)
    return target


def default_store_path() -> Path:
    override = os.environ.get("BIOINTEL_LIVE_EXPERIENCE_DB", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return _state_root() / "live_experience.sqlite3"


@dataclass(frozen=True)
class LiveRun:
    run_id: str
    workflow: str
    page_key: str
    status: str
    progress: float
    current_stage: str
    detail: str
    started_at_utc: str
    updated_at_utc: str
    completed_at_utc: str | None
    elapsed_seconds: float | None
    error: str


@dataclass(frozen=True)
class LiveStage:
    event_id: int
    run_id: str
    sequence_no: int
    label: str
    detail: str
    progress: float | None
    status: str
    occurred_at_utc: str


@dataclass(frozen=True)
class ScientificNotification:
    notification_id: str
    dedupe_key: str
    level: str
    title: str
    message: str
    source: str
    page_key: str
    action_label: str
    action_target: str
    related_run_id: str
    created_at_utc: str
    updated_at_utc: str
    read_at_utc: str | None
    dismissed_at_utc: str | None
    occurrence_count: int


class LiveExperienceStore:
    """Persistent timeline and notification store for desktop/session continuity."""

    LEVELS = {"info", "success", "warning", "error", "critical"}
    RUN_STATUSES = {"running", "completed", "failed", "cancelled", "paused", "queued"}

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or default_store_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_analysis_runs(
                    run_id TEXT PRIMARY KEY,
                    workflow TEXT NOT NULL,
                    page_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0 CHECK(progress >= 0 AND progress <= 1),
                    current_stage TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    started_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT,
                    elapsed_seconds REAL,
                    error TEXT NOT NULL DEFAULT '',
                    manifest_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS live_analysis_stages(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    progress REAL,
                    status TEXT NOT NULL DEFAULT 'running',
                    occurred_at_utc TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES live_analysis_runs(run_id) ON DELETE CASCADE,
                    UNIQUE(run_id, sequence_no)
                );
                CREATE TABLE IF NOT EXISTS scientific_notifications(
                    notification_id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'application',
                    page_key TEXT NOT NULL DEFAULT '',
                    action_label TEXT NOT NULL DEFAULT '',
                    action_target TEXT NOT NULL DEFAULT '',
                    related_run_id TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    read_at_utc TEXT,
                    dismissed_at_utc TEXT,
                    occurrence_count INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_live_runs_status_updated
                    ON live_analysis_runs(status, updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_live_stages_run_sequence
                    ON live_analysis_stages(run_id, sequence_no);
                CREATE INDEX IF NOT EXISTS idx_notifications_unread
                    ON scientific_notifications(dismissed_at_utc, read_at_utc, updated_at_utc DESC);
                """
            )

    @staticmethod
    def _run(row: sqlite3.Row) -> LiveRun:
        return LiveRun(
            run_id=str(row["run_id"]), workflow=str(row["workflow"]),
            page_key=str(row["page_key"]), status=str(row["status"]),
            progress=float(row["progress"]), current_stage=str(row["current_stage"]),
            detail=str(row["detail"]), started_at_utc=str(row["started_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]), completed_at_utc=row["completed_at_utc"],
            elapsed_seconds=(float(row["elapsed_seconds"]) if row["elapsed_seconds"] is not None else None),
            error=str(row["error"]),
        )

    @staticmethod
    def _stage(row: sqlite3.Row) -> LiveStage:
        return LiveStage(
            event_id=int(row["event_id"]), run_id=str(row["run_id"]),
            sequence_no=int(row["sequence_no"]), label=str(row["label"]), detail=str(row["detail"]),
            progress=(float(row["progress"]) if row["progress"] is not None else None),
            status=str(row["status"]), occurred_at_utc=str(row["occurred_at_utc"]),
        )

    @staticmethod
    def _notification(row: sqlite3.Row) -> ScientificNotification:
        return ScientificNotification(
            notification_id=str(row["notification_id"]), dedupe_key=str(row["dedupe_key"]),
            level=str(row["level"]), title=str(row["title"]), message=str(row["message"]),
            source=str(row["source"]), page_key=str(row["page_key"]),
            action_label=str(row["action_label"]), action_target=str(row["action_target"]),
            related_run_id=str(row["related_run_id"]), created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]), read_at_utc=row["read_at_utc"],
            dismissed_at_utc=row["dismissed_at_utc"], occurrence_count=int(row["occurrence_count"]),
        )

    def start_run(self, workflow: str, *, page_key: str = "", run_id: str | None = None) -> str:
        identifier = run_id or f"run-{uuid4().hex}"
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO live_analysis_runs(
                    run_id, workflow, page_key, status, progress, current_stage, detail,
                    started_at_utc, updated_at_utc, completed_at_utc, elapsed_seconds, error, manifest_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (identifier, str(workflow), str(page_key), "running", 0.0, "Preparing", "", now, now, None, None, "", "{}"),
            )
        return identifier

    def add_stage(
        self,
        run_id: str,
        *,
        sequence_no: int,
        label: str,
        detail: str = "",
        progress: float | None = None,
        status: str = "running",
    ) -> None:
        now = _utc_now()
        normalized_progress = None if progress is None else min(max(float(progress), 0.0), 1.0)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO live_analysis_stages(
                    run_id, sequence_no, label, detail, progress, status, occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(run_id, sequence_no) DO UPDATE SET
                    label=excluded.label, detail=excluded.detail, progress=excluded.progress,
                    status=excluded.status, occurred_at_utc=excluded.occurred_at_utc""",
                (run_id, int(sequence_no), str(label), str(detail), normalized_progress, str(status), now),
            )
            connection.execute(
                """UPDATE live_analysis_runs SET current_stage=?, detail=?,
                    progress=MAX(progress, COALESCE(?, progress)), updated_at_utc=?
                    WHERE run_id=?""",
                (str(label), str(detail), normalized_progress, now, run_id),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        elapsed_seconds: float | None,
        error: str = "",
        manifest: dict[str, Any] | None = None,
    ) -> None:
        normalized = status if status in self.RUN_STATUSES else "failed"
        now = _utc_now()
        progress = 1.0 if normalized == "completed" else None
        with self._connect() as connection:
            connection.execute(
                """UPDATE live_analysis_runs SET status=?, progress=COALESCE(?, progress),
                    current_stage=?, updated_at_utc=?, completed_at_utc=?, elapsed_seconds=?,
                    error=?, manifest_json=? WHERE run_id=?""",
                (
                    normalized, progress, normalized.title(), now, now,
                    elapsed_seconds, str(error)[:4000],
                    json.dumps(manifest or {}, sort_keys=True, default=str), run_id,
                ),
            )
            connection.execute(
                """UPDATE live_analysis_stages SET status=CASE
                    WHEN ?='completed' THEN 'completed'
                    WHEN status='running' THEN ? ELSE status END
                    WHERE run_id=?""",
                (normalized, normalized, run_id),
            )

    def recent_runs(self, *, limit: int = 20, statuses: Iterable[str] | None = None) -> list[LiveRun]:
        query = "SELECT * FROM live_analysis_runs"
        parameters: list[Any] = []
        selected = [value for value in (statuses or []) if value in self.RUN_STATUSES]
        if selected:
            placeholders = ",".join("?" for _ in selected)
            query += f" WHERE status IN ({placeholders})"
            parameters.extend(selected)
        query += " ORDER BY updated_at_utc DESC LIMIT ?"
        parameters.append(min(max(int(limit), 1), 200))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._run(row) for row in rows]

    def stages(self, run_id: str) -> list[LiveStage]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM live_analysis_stages WHERE run_id=? ORDER BY sequence_no, event_id",
                (run_id,),
            ).fetchall()
        return [self._stage(row) for row in rows]

    def mark_stale_runs(self, *, after_minutes: int = 180) -> int:
        cutoff = (datetime.now(UTC) - timedelta(minutes=max(5, int(after_minutes)))).isoformat(timespec="seconds")
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE live_analysis_runs SET status='failed', current_stage='Interrupted',
                    error='The previous process ended before this run completed.', updated_at_utc=?, completed_at_utc=?
                    WHERE status='running' AND updated_at_utc < ?""",
                (now, now, cutoff),
            )
            count = int(cursor.rowcount or 0)
        if count:
            self.notify(
                "Interrupted analyses detected",
                f"{count} stale analysis run(s) were marked failed after an application restart.",
                level="warning", source="timeline", dedupe_key=f"stale-runs:{cutoff[:10]}",
                action_label="Open jobs", action_target="performance_jobs",
            )
        return count

    def notify(
        self,
        title: str,
        message: str,
        *,
        level: str = "info",
        source: str = "application",
        page_key: str = "",
        action_label: str = "",
        action_target: str = "",
        related_run_id: str = "",
        dedupe_key: str = "",
        reopen: bool = True,
    ) -> str:
        normalized_level = level if level in self.LEVELS else "info"
        raw_key = dedupe_key or "|".join((source, title, message, page_key, action_target, related_run_id))
        stable_key = hashlib.sha256(raw_key.encode("utf-8", errors="replace")).hexdigest()
        now = _utc_now()
        notification_id = f"notice-{uuid4().hex}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT notification_id FROM scientific_notifications WHERE dedupe_key=?",
                (stable_key,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO scientific_notifications(
                        notification_id, dedupe_key, level, title, message, source, page_key,
                        action_label, action_target, related_run_id, created_at_utc, updated_at_utc,
                        read_at_utc, dismissed_at_utc, occurrence_count
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (
                        notification_id, stable_key, normalized_level, str(title), str(message), str(source),
                        str(page_key), str(action_label), str(action_target), str(related_run_id), now, now, None, None,
                    ),
                )
            else:
                notification_id = str(existing["notification_id"])
                if reopen:
                    connection.execute(
                        """UPDATE scientific_notifications SET level=?, title=?, message=?, source=?, page_key=?,
                            action_label=?, action_target=?, related_run_id=?, updated_at_utc=?, read_at_utc=NULL,
                            dismissed_at_utc=NULL, occurrence_count=occurrence_count+1 WHERE notification_id=?""",
                        (
                            normalized_level, str(title), str(message), str(source), str(page_key), str(action_label),
                            str(action_target), str(related_run_id), now, notification_id,
                        ),
                    )
        return notification_id

    def notifications(
        self,
        *,
        limit: int = 50,
        include_read: bool = True,
        levels: Iterable[str] | None = None,
    ) -> list[ScientificNotification]:
        clauses = ["dismissed_at_utc IS NULL"]
        parameters: list[Any] = []
        if not include_read:
            clauses.append("read_at_utc IS NULL")
        selected = [level for level in (levels or []) if level in self.LEVELS]
        if selected:
            placeholders = ",".join("?" for _ in selected)
            clauses.append(f"level IN ({placeholders})")
            parameters.extend(selected)
        query = "SELECT * FROM scientific_notifications WHERE " + " AND ".join(clauses)
        query += " ORDER BY CASE level WHEN 'critical' THEN 0 WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, updated_at_utc DESC LIMIT ?"
        parameters.append(min(max(int(limit), 1), 500))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._notification(row) for row in rows]

    def unread_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM scientific_notifications WHERE dismissed_at_utc IS NULL AND read_at_utc IS NULL"
            ).fetchone()
        return int(row["count"] if row else 0)

    def mark_read(self, notification_ids: Iterable[str] | None = None) -> int:
        now = _utc_now()
        identifiers = [str(value) for value in (notification_ids or []) if value]
        with self._connect() as connection:
            if identifiers:
                placeholders = ",".join("?" for _ in identifiers)
                cursor = connection.execute(
                    f"UPDATE scientific_notifications SET read_at_utc=COALESCE(read_at_utc, ?) WHERE notification_id IN ({placeholders})",
                    [now, *identifiers],
                )
            else:
                cursor = connection.execute(
                    "UPDATE scientific_notifications SET read_at_utc=COALESCE(read_at_utc, ?) WHERE dismissed_at_utc IS NULL",
                    (now,),
                )
        return int(cursor.rowcount or 0)

    def dismiss(self, notification_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE scientific_notifications SET dismissed_at_utc=?, read_at_utc=COALESCE(read_at_utc, ?) WHERE notification_id=?",
                (_utc_now(), _utc_now(), str(notification_id)),
            )

    def clear(self) -> int:
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE scientific_notifications SET dismissed_at_utc=?, read_at_utc=COALESCE(read_at_utc, ?) WHERE dismissed_at_utc IS NULL",
                (now, now),
            )
        return int(cursor.rowcount or 0)

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": "biointel.live_experience.v1",
            "exported_at_utc": _utc_now(),
            "runs": [asdict(item) for item in self.recent_runs(limit=100)],
            "notifications": [asdict(item) for item in self.notifications(limit=200)],
        }


def get_live_store() -> LiveExperienceStore:
    return LiveExperienceStore()
