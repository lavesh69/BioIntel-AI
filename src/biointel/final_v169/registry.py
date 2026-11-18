from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Iterable

from biointel.scientific_depth.profiles import MODULE_PROFILES

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS modules (
    module_key TEXT PRIMARY KEY,
    module_title TEXT NOT NULL,
    internal_software_score REAL NOT NULL DEFAULT 10 CHECK(internal_software_score BETWEEN 0 AND 10),
    native_research_depth_score REAL NOT NULL DEFAULT 10 CHECK(native_research_depth_score BETWEEN 0 AND 10),
    evidence_framework_score REAL NOT NULL DEFAULT 10 CHECK(evidence_framework_score BETWEEN 0 AND 10)
);
CREATE TABLE IF NOT EXISTS evidence_artifacts (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key) ON DELETE CASCADE,
    axis TEXT NOT NULL CHECK(axis IN (
        'production_reference','independent_validation','prospective_or_orthogonal',
        'expert_signoff','formal_release_review','operating_history','physical_qualification'
    )),
    artifact_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    issuer TEXT NOT NULL DEFAULT '',
    identifier TEXT NOT NULL DEFAULT '',
    intended_use TEXT NOT NULL DEFAULT 'research',
    verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE(module_key, axis, artifact_path)
);
CREATE TABLE IF NOT EXISTS operating_metrics (
    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
    completed_runs INTEGER NOT NULL DEFAULT 0 CHECK(completed_runs >= 0),
    failed_runs INTEGER NOT NULL DEFAULT 0 CHECK(failed_runs >= 0),
    downtime_minutes REAL NOT NULL DEFAULT 0 CHECK(downtime_minutes >= 0),
    observed_days INTEGER NOT NULL DEFAULT 0 CHECK(observed_days >= 0),
    incident_log_attached INTEGER NOT NULL DEFAULT 0 CHECK(incident_log_attached IN (0,1)),
    capa_log_attached INTEGER NOT NULL DEFAULT 0 CHECK(capa_log_attached IN (0,1))
);
CREATE TABLE IF NOT EXISTS release_decisions (
    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
    decision TEXT NOT NULL DEFAULT 'research-only' CHECK(decision IN ('research-only','controlled-release','rejected','suspended')),
    intended_use TEXT NOT NULL DEFAULT 'research',
    reviewer TEXT NOT NULL DEFAULT '',
    decision_artifact_path TEXT NOT NULL DEFAULT '',
    decision_artifact_sha256 TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_key TEXT NOT NULL REFERENCES modules(module_key) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_module_axis ON evidence_artifacts(module_key, axis);
"""

AXES: tuple[str, ...] = (
    "production_reference",
    "independent_validation",
    "prospective_or_orthogonal",
    "expert_signoff",
    "formal_release_review",
    "operating_history",
    "physical_qualification",
)


@dataclass(frozen=True)
class VerifiedReleaseState:
    module_key: str
    axis_complete: dict[str, bool]
    artifact_counts: dict[str, int]
    artifact_integrity_failures: int
    operating_history_complete: bool
    formal_decision: str
    controlled_release_eligible: bool
    release_status: str

    @property
    def completion_fraction(self) -> float:
        return sum(self.axis_complete.values()) / len(AXES)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_step169_registry(root: str | Path) -> Path:
    project_root = Path(root)
    path = project_root / "data" / "databases" / "step169_verified_release.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [(key, profile.title, 10.0, 10.0, 10.0) for key, profile in sorted(MODULE_PROFILES.items())]
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.executemany(
            """
            INSERT INTO modules(module_key,module_title,internal_software_score,native_research_depth_score,evidence_framework_score)
            VALUES(?,?,?,?,?)
            ON CONFLICT(module_key) DO UPDATE SET
                module_title=excluded.module_title,
                internal_software_score=excluded.internal_software_score,
                native_research_depth_score=excluded.native_research_depth_score,
                evidence_framework_score=excluded.evidence_framework_score
            """,
            rows,
        )
        conn.commit()
    return path


def register_evidence_artifact(
    root: str | Path,
    *,
    module_key: str,
    axis: str,
    artifact_path: str | Path,
    issuer: str = "",
    identifier: str = "",
    intended_use: str = "research",
) -> int:
    if axis not in AXES:
        raise ValueError(f"Unsupported evidence axis: {axis}")
    project_root = Path(root).resolve()
    path = Path(artifact_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("Evidence artifacts must be stored inside the project root") from exc
    digest = sha256_file(path)
    db = ensure_step169_registry(project_root)
    created = _utc_now()
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.execute(
            """
            INSERT INTO evidence_artifacts(module_key,axis,artifact_path,sha256,issuer,identifier,intended_use,verified,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(module_key,axis,artifact_path) DO UPDATE SET
                sha256=excluded.sha256, issuer=excluded.issuer, identifier=excluded.identifier,
                intended_use=excluded.intended_use, verified=excluded.verified, created_at=excluded.created_at
            """,
            (module_key, axis, str(path.relative_to(project_root)), digest, issuer.strip(), identifier.strip(), intended_use.strip() or "research", 1, created),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def record_operating_metrics(
    root: str | Path,
    *,
    module_key: str,
    completed_runs: int,
    failed_runs: int,
    downtime_minutes: float,
    observed_days: int,
    incident_log_attached: bool,
    capa_log_attached: bool,
) -> None:
    if min(completed_runs, failed_runs, observed_days) < 0 or downtime_minutes < 0:
        raise ValueError("Operating metrics cannot be negative")
    db = ensure_step169_registry(root)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO operating_metrics(module_key,completed_runs,failed_runs,downtime_minutes,observed_days,incident_log_attached,capa_log_attached)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(module_key) DO UPDATE SET
                completed_runs=excluded.completed_runs, failed_runs=excluded.failed_runs,
                downtime_minutes=excluded.downtime_minutes, observed_days=excluded.observed_days,
                incident_log_attached=excluded.incident_log_attached, capa_log_attached=excluded.capa_log_attached
            """,
            (module_key, completed_runs, failed_runs, float(downtime_minutes), observed_days, int(incident_log_attached), int(capa_log_attached)),
        )
        conn.commit()


def record_release_decision(
    root: str | Path,
    *,
    module_key: str,
    decision: str,
    intended_use: str,
    reviewer: str,
    decision_artifact_path: str | Path,
) -> None:
    if decision not in {"research-only", "controlled-release", "rejected", "suspended"}:
        raise ValueError("Invalid release decision")
    project_root = Path(root).resolve()
    artifact = Path(decision_artifact_path).resolve()
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    try:
        relative = artifact.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("Decision artifact must be stored inside the project root") from exc
    digest = sha256_file(artifact)
    db = ensure_step169_registry(project_root)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO release_decisions(module_key,decision,intended_use,reviewer,decision_artifact_path,decision_artifact_sha256,decided_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(module_key) DO UPDATE SET
                decision=excluded.decision, intended_use=excluded.intended_use, reviewer=excluded.reviewer,
                decision_artifact_path=excluded.decision_artifact_path,
                decision_artifact_sha256=excluded.decision_artifact_sha256, decided_at=excluded.decided_at
            """,
            (module_key, decision, intended_use.strip() or "research", reviewer.strip(), str(relative), digest, _utc_now()),
        )
        conn.commit()


def _verified_artifacts(conn: sqlite3.Connection, root: Path, module_key: str) -> tuple[dict[str, int], int]:
    counts = {axis: 0 for axis in AXES}
    failures = 0
    rows = conn.execute(
        "SELECT axis,artifact_path,sha256,verified,issuer,identifier FROM evidence_artifacts WHERE module_key=?",
        (module_key,),
    ).fetchall()
    for axis, relative, expected, verified, issuer, identifier in rows:
        path = root / str(relative)
        valid = bool(verified) and bool(str(issuer).strip() or str(identifier).strip()) and path.is_file()
        if valid:
            try:
                valid = sha256_file(path) == expected
            except OSError:
                valid = False
        if valid:
            counts[str(axis)] += 1
        else:
            failures += 1
    return counts, failures


def verified_release_state(root: str | Path, module_key: str) -> VerifiedReleaseState:
    project_root = Path(root).resolve()
    db = ensure_step169_registry(project_root)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        counts, failures = _verified_artifacts(conn, project_root, module_key)
        operating_row = conn.execute(
            "SELECT completed_runs,failed_runs,downtime_minutes,observed_days,incident_log_attached,capa_log_attached FROM operating_metrics WHERE module_key=?",
            (module_key,),
        ).fetchone()
        operating_complete = False
        if operating_row:
            completed, failed, downtime, days, incident, capa = operating_row
            failure_rate = failed / max(completed + failed, 1)
            operating_complete = bool(completed >= 30 and days >= 30 and failure_rate <= 0.05 and downtime <= 240 and incident and capa)
        decision_row = conn.execute(
            "SELECT decision,reviewer,decision_artifact_path,decision_artifact_sha256 FROM release_decisions WHERE module_key=?",
            (module_key,),
        ).fetchone()
        formal_decision = "research-only"
        decision_valid = False
        if decision_row:
            decision, reviewer, relative, expected = decision_row
            artifact = project_root / str(relative)
            decision_valid = bool(str(reviewer).strip()) and artifact.is_file()
            if decision_valid:
                try:
                    decision_valid = sha256_file(artifact) == expected
                except OSError:
                    decision_valid = False
            if decision_valid:
                formal_decision = str(decision)

    axis_complete = {axis: counts[axis] > 0 for axis in AXES}
    axis_complete["operating_history"] = axis_complete["operating_history"] and operating_complete
    axis_complete["formal_release_review"] = axis_complete["formal_release_review"] and decision_valid and formal_decision == "controlled-release"
    eligible = failures == 0 and all(axis_complete.values()) and formal_decision == "controlled-release"
    return VerifiedReleaseState(
        module_key=module_key,
        axis_complete=axis_complete,
        artifact_counts=counts,
        artifact_integrity_failures=failures,
        operating_history_complete=operating_complete,
        formal_decision=formal_decision,
        controlled_release_eligible=eligible,
        release_status="eligible-for-controlled-release" if eligible else "research-only-fail-closed",
    )


def append_audit_event(root: str | Path, *, module_key: str, event_type: str, payload: dict[str, Any]) -> str:
    db = ensure_step169_registry(root)
    created = _utc_now()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        row = conn.execute("SELECT event_hash FROM audit_events WHERE module_key=? ORDER BY event_id DESC LIMIT 1", (module_key,)).fetchone()
        previous = str(row[0]) if row else ""
        event_hash = hashlib.sha256(f"{module_key}|{event_type}|{canonical}|{previous}|{created}".encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO audit_events(module_key,event_type,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?)",
            (module_key, event_type, canonical, previous, event_hash, created),
        )
        conn.commit()
    return event_hash


__all__ = [
    "AXES",
    "VerifiedReleaseState",
    "append_audit_event",
    "ensure_step169_registry",
    "record_operating_metrics",
    "record_release_decision",
    "register_evidence_artifact",
    "sha256_file",
    "verified_release_state",
]
