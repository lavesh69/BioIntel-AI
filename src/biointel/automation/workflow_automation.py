from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    title: str
    dependencies: tuple[str, ...] = ()
    page_key: str = ""


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    title: str
    description: str
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class WorkflowRunSnapshot:
    run_id: str
    workflow_key: str
    workflow_title: str
    status: str
    progress_percent: float
    current_step: str
    started_at_utc: str
    updated_at_utc: str
    steps: tuple[dict[str, Any], ...]
    failure_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = list(self.steps)
        return payload


DEFAULT_WORKFLOWS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        key="sequence_to_report",
        title="Sequence QC to reproducible report",
        description="Validate sequence input, compare sequences, inspect annotations and package a reproducible report.",
        steps=(
            WorkflowStep("sequence_qc", "Sequence analysis and QC", page_key="sequence_analyzer"),
            WorkflowStep("comparison", "Sequence comparison", ("sequence_qc",), "sequence_comparison"),
            WorkflowStep("annotation", "Protein or genomic annotation", ("comparison",), "protein_annotation"),
            WorkflowStep("report", "Research report bundle", ("annotation",), "report_studio"),
        ),
    ),
    WorkflowDefinition(
        key="target_to_lead",
        title="Target to lead triage",
        description="Move from target evidence through compounds, DTI, structure and ADMET with explicit decision gates.",
        steps=(
            WorkflowStep("target", "Target and pathway evidence", page_key="pathway_network"),
            WorkflowStep("compounds", "Compound preparation", ("target",), "drug_analyzer"),
            WorkflowStep("dti", "Drug-target prediction", ("compounds",), "dti_predictor"),
            WorkflowStep("structure", "Structural review", ("dti",), "structural_bioinformatics"),
            WorkflowStep("admet", "ADMET developability triage", ("structure",), "admet_discovery"),
            WorkflowStep("release", "Evidence and release review", ("admet",), "scientific_release_gate"),
        ),
    ),
    WorkflowDefinition(
        key="wet_lab_assay",
        title="Wet-lab assay to evidence package",
        description="Register samples, run assay analytics, review QC and export a traceable evidence package.",
        steps=(
            WorkflowStep("samples", "Sample and plate setup", page_key="wetlab_biotechnology"),
            WorkflowStep("analysis", "Assay analysis", ("samples",), "wetlab_biotechnology"),
            WorkflowStep("qc", "Quality and limitations review", ("analysis",), "platform_quality"),
            WorkflowStep("package", "Evidence package", ("qc",), "evidence_studio"),
        ),
    ),
    WorkflowDefinition(
        key="model_validation",
        title="Model training to governed release",
        description="Build features, train, evaluate leakage and external validity, then review the model release gate.",
        steps=(
            WorkflowStep("features", "Feature preparation", page_key="dti_features"),
            WorkflowStep("train", "Model training", ("features",), "model_training"),
            WorkflowStep("evaluate", "Model evaluation", ("train",), "model_evaluation"),
            WorkflowStep("leakage", "Leakage audit", ("evaluate",), "benchmark_leakage_lab"),
            WorkflowStep("external", "External validation", ("leakage",), "external_validation"),
            WorkflowStep("gate", "Scientific release gate", ("external",), "scientific_release_gate"),
        ),
    ),
)

_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workflow_definitions (
    workflow_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_key TEXT NOT NULL,
    workflow_title TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step TEXT NOT NULL DEFAULT '',
    failure_message TEXT NOT NULL DEFAULT '',
    started_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY(workflow_key) REFERENCES workflow_definitions(workflow_key)
);
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    run_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    title TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    dependencies_json TEXT NOT NULL,
    page_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    started_at_utc TEXT,
    completed_at_utc TEXT,
    message TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(run_id, step_key),
    FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workflow_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_key TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    occurred_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_updated ON workflow_runs(updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_status ON workflow_run_steps(run_id,status,ordinal);
CREATE INDEX IF NOT EXISTS idx_workflow_events_run ON workflow_events(run_id,event_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = managed_connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def ensure_workflow_automation(path: str | Path) -> Path:
    target = Path(path)
    with _connect(target) as connection:
        connection.executescript(_SCHEMA)
    return target


def register_default_workflows(path: str | Path) -> None:
    ensure_workflow_automation(path)
    timestamp = _now()
    with _connect(path) as connection:
        for definition in DEFAULT_WORKFLOWS:
            payload = {
                "key": definition.key,
                "title": definition.title,
                "description": definition.description,
                "steps": [asdict(step) for step in definition.steps],
            }
            connection.execute(
                """
                INSERT INTO workflow_definitions(workflow_key,title,description,definition_json,updated_at_utc)
                VALUES(?,?,?,?,?)
                ON CONFLICT(workflow_key) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    definition_json=excluded.definition_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (definition.key, definition.title, definition.description, json.dumps(payload, sort_keys=True), timestamp),
            )


def _definition(workflow_key: str) -> WorkflowDefinition:
    for definition in DEFAULT_WORKFLOWS:
        if definition.key == workflow_key:
            return definition
    raise ValueError(f"Unknown workflow definition: {workflow_key}")


def start_workflow_run(path: str | Path, workflow_key: str) -> str:
    register_default_workflows(path)
    definition = _definition(workflow_key)
    run_id = f"WFR-{uuid.uuid4().hex[:12].upper()}"
    timestamp = _now()
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO workflow_runs(run_id,workflow_key,workflow_title,status,current_step,started_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
            (run_id, definition.key, definition.title, "running", definition.steps[0].key if definition.steps else "", timestamp, timestamp),
        )
        for ordinal, step in enumerate(definition.steps):
            status = "ready" if not step.dependencies else "blocked"
            connection.execute(
                "INSERT INTO workflow_run_steps(run_id,step_key,title,ordinal,dependencies_json,page_key,status) VALUES(?,?,?,?,?,?,?)",
                (run_id, step.key, step.title, ordinal, json.dumps(step.dependencies), step.page_key, status),
            )
        connection.execute(
            "INSERT INTO workflow_events(run_id,event_type,message,occurred_at_utc) VALUES(?,?,?,?)",
            (run_id, "run_started", definition.title, timestamp),
        )
    return run_id


def _step_rows(connection: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(connection.execute("SELECT * FROM workflow_run_steps WHERE run_id=? ORDER BY ordinal", (run_id,)))


def _refresh_dependencies(connection: sqlite3.Connection, run_id: str) -> None:
    rows = _step_rows(connection, run_id)
    status_by_key = {str(row["step_key"]): str(row["status"]) for row in rows}
    for row in rows:
        if row["status"] not in {"blocked", "ready"}:
            continue
        dependencies = tuple(json.loads(row["dependencies_json"] or "[]"))
        ready = all(status_by_key.get(key) == "completed" for key in dependencies)
        desired = "ready" if ready else "blocked"
        if desired != row["status"]:
            connection.execute(
                "UPDATE workflow_run_steps SET status=? WHERE run_id=? AND step_key=?",
                (desired, run_id, row["step_key"]),
            )


def update_workflow_step(
    path: str | Path,
    run_id: str,
    step_key: str,
    status: str,
    *,
    message: str = "",
) -> WorkflowRunSnapshot:
    allowed = {"ready", "running", "completed", "failed", "skipped"}
    if status not in allowed:
        raise ValueError(f"Unsupported step status: {status}")
    timestamp = _now()
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM workflow_run_steps WHERE run_id=? AND step_key=?",
            (run_id, step_key),
        ).fetchone()
        if row is None:
            raise ValueError("Workflow step was not found.")
        dependencies = tuple(json.loads(row["dependencies_json"] or "[]"))
        if status in {"running", "completed"} and dependencies:
            completed = {
                value["step_key"]
                for value in connection.execute(
                    "SELECT step_key FROM workflow_run_steps WHERE run_id=? AND status='completed'",
                    (run_id,),
                )
            }
            missing = [key for key in dependencies if key not in completed]
            if missing:
                raise ValueError("Complete dependencies first: " + ", ".join(missing))
        started = timestamp if status == "running" and not row["started_at_utc"] else row["started_at_utc"]
        completed_at = timestamp if status in {"completed", "failed", "skipped"} else row["completed_at_utc"]
        connection.execute(
            "UPDATE workflow_run_steps SET status=?,started_at_utc=?,completed_at_utc=?,message=? WHERE run_id=? AND step_key=?",
            (status, started, completed_at, message[:4000], run_id, step_key),
        )
        connection.execute(
            "INSERT INTO workflow_events(run_id,step_key,event_type,message,occurred_at_utc) VALUES(?,?,?,?,?)",
            (run_id, step_key, f"step_{status}", message[:4000], timestamp),
        )
        _refresh_dependencies(connection, run_id)
        steps = _step_rows(connection, run_id)
        statuses = [str(item["status"]) for item in steps]
        if "failed" in statuses:
            run_status = "failed"
            failure_message = message[:4000]
        elif steps and all(value in {"completed", "skipped"} for value in statuses):
            run_status = "completed"
            failure_message = ""
        else:
            run_status = "running"
            failure_message = ""
        current = next((str(item["step_key"]) for item in steps if item["status"] in {"running", "ready"}), "")
        connection.execute(
            "UPDATE workflow_runs SET status=?,current_step=?,failure_message=?,updated_at_utc=? WHERE run_id=?",
            (run_status, current, failure_message, timestamp, run_id),
        )
    return workflow_run_snapshot(path, run_id)


def resume_workflow_run(path: str | Path, run_id: str) -> WorkflowRunSnapshot:
    timestamp = _now()
    with _connect(path) as connection:
        exists = connection.execute("SELECT 1 FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        if exists is None:
            raise ValueError("Workflow run was not found.")
        connection.execute(
            "UPDATE workflow_run_steps SET status='ready',message='' WHERE run_id=? AND status='failed'",
            (run_id,),
        )
        _refresh_dependencies(connection, run_id)
        rows = _step_rows(connection, run_id)
        current = next((str(row["step_key"]) for row in rows if row["status"] in {"running", "ready"}), "")
        connection.execute(
            "UPDATE workflow_runs SET status='running',current_step=?,failure_message='',updated_at_utc=? WHERE run_id=?",
            (current, timestamp, run_id),
        )
        connection.execute(
            "INSERT INTO workflow_events(run_id,event_type,message,occurred_at_utc) VALUES(?,?,?,?)",
            (run_id, "run_resumed", "Operator resumed workflow", timestamp),
        )
    return workflow_run_snapshot(path, run_id)


def workflow_run_snapshot(path: str | Path, run_id: str) -> WorkflowRunSnapshot:
    with _connect(path) as connection:
        run = connection.execute("SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("Workflow run was not found.")
        rows = _step_rows(connection, run_id)
    steps: list[dict[str, Any]] = []
    completed = 0
    for row in rows:
        payload = dict(row)
        payload["dependencies"] = json.loads(payload.pop("dependencies_json") or "[]")
        steps.append(payload)
        if row["status"] in {"completed", "skipped"}:
            completed += 1
    progress = (completed / len(rows) * 100.0) if rows else 100.0
    return WorkflowRunSnapshot(
        run_id=str(run["run_id"]),
        workflow_key=str(run["workflow_key"]),
        workflow_title=str(run["workflow_title"]),
        status=str(run["status"]),
        progress_percent=round(progress, 1),
        current_step=str(run["current_step"]),
        started_at_utc=str(run["started_at_utc"]),
        updated_at_utc=str(run["updated_at_utc"]),
        steps=tuple(steps),
        failure_message=str(run["failure_message"]),
    )


def list_workflow_runs(path: str | Path, limit: int = 50) -> list[WorkflowRunSnapshot]:
    register_default_workflows(path)
    with _connect(path) as connection:
        ids = [
            str(row["run_id"])
            for row in connection.execute(
                "SELECT run_id FROM workflow_runs ORDER BY updated_at_utc DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            )
        ]
    return [workflow_run_snapshot(path, run_id) for run_id in ids]


def workflow_events(path: str | Path, run_id: str) -> list[dict[str, Any]]:
    with _connect(path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM workflow_events WHERE run_id=? ORDER BY event_id",
                (run_id,),
            )
        ]
