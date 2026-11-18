from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.innovation.advanced_engines import validate_workflow_dag

from .builtins import task_for_block
from .models import StepExecutionRecord, WorkflowExecutionRecord
from .provenance import (
    artifact_record,
    atomic_write_json,
    environment_snapshot,
    hash_json,
    utc_now,
)
from .registry import WorkflowRegistry
from .scientific_quality import assess_quality


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "workflow"


def _parse_dependencies(value: Any) -> list[str]:
    return [token.strip() for token in str(value or "").split(",") if token.strip()]


def _status_allows(condition: str, dependencies: list[dict[str, Any]]) -> tuple[bool, str]:
    statuses = [str(item.get("status", "")) for item in dependencies]
    condition = str(condition or "always").strip().lower()
    if condition == "manual_approval":
        return False, "Manual approval is required before execution."
    if condition == "on_success":
        return all(status == "completed" for status in statuses), "Dependency did not complete successfully."
    if condition == "on_failure":
        return any(status == "failed" for status in statuses), "No dependency failure triggered this branch."
    if any(status == "failed" for status in statuses):
        return False, "A dependency failed."
    return True, ""


def execute_workflow_v3(
    frame: pd.DataFrame,
    output_root: str | Path,
    workflow_name: str,
    *,
    parameters: dict[str, Any] | None = None,
    resume: bool = True,
    retries: int = 1,
    fail_fast: bool = True,
    registry_path: str | Path | None = None,
    source_kind: str = "user_supplied",
    synthetic: bool = False,
) -> WorkflowExecutionRecord:
    validated, summary = validate_workflow_dag(frame)
    if not summary["valid"]:
        raise ValueError("Workflow is not valid: " + "; ".join(summary["warnings"]))
    parameters = dict(parameters or {})
    workflow_payload = {
        "schema": "biointel.workflow.v3",
        "name": workflow_name,
        "steps": validated.fillna("").to_dict(orient="records"),
        "parameters": parameters,
    }
    workflow_sha = hash_json(workflow_payload)
    run_id = f"{_safe_name(workflow_name)}-{workflow_sha[:12]}"
    root = Path(output_root).expanduser().resolve() / run_id
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "run_state.json"
    summary_path = root / "run_summary.json"
    manifest_path = root / "run_manifest.json"
    cancel_path = root / "CANCEL"
    registry = WorkflowRegistry(registry_path or (Path(output_root).expanduser().resolve() / "workflow_runs.sqlite3"))

    existing: dict[str, Any] = {}
    if resume and state_path.is_file():
        try:
            existing = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing_steps = {str(item.get("step_id")): item for item in existing.get("steps", []) if item.get("step_id")}
    resumed = bool(existing_steps)
    environment = environment_snapshot()
    started_at = utc_now()
    start_clock = time.perf_counter()
    quality = assess_quality(source_kind=source_kind, synthetic=synthetic)
    warnings = list(summary.get("warnings", []))
    run_record = WorkflowExecutionRecord(
        run_id=run_id,
        workflow_name=workflow_name,
        workflow_sha256=workflow_sha,
        status="running",
        started_at=started_at,
        finished_at="",
        duration_seconds=0,
        output_directory=str(root),
        resumed=resumed,
        implementation_readiness=quality.implementation_readiness,
        scientific_evidence_score=quality.scientific_evidence_score,
        steps=[],
        artifacts=[],
        warnings=warnings,
        environment=environment,
        parameters=parameters,
    )
    registry.upsert_run(run_record.to_dict())
    registry.audit(run_id, "workflow_started", "Workflow execution started.", {"workflow_sha256": workflow_sha, "resumed": resumed})
    atomic_write_json(manifest_path, {**workflow_payload, "run_id": run_id, "workflow_sha256": workflow_sha, "environment": environment, "quality_assessment": quality.to_dict()})

    results_by_id: dict[str, dict[str, Any]] = {}
    all_artifacts: list[dict[str, Any]] = []
    for row in validated.itertuples(index=False):
        if not bool(row.enabled):
            continue
        step_id = str(row.id)
        dependencies = _parse_dependencies(row.depends_on)
        dependency_results = [results_by_id[dep] for dep in dependencies if dep in results_by_id]
        should_run, skipped_reason = _status_allows(str(row.condition), dependency_results)
        prior = existing_steps.get(step_id)
        if resume and prior and prior.get("status") == "completed":
            existing_artifacts = [item for item in prior.get("artifacts", []) if Path(str(item.get("path", ""))).is_file()]
            hashes_match = all(
                artifact_record(item["path"], step_id=step_id, role=item.get("role", "output"))["sha256"] == item.get("sha256")
                for item in existing_artifacts
            ) if existing_artifacts else bool(prior.get("metrics"))
            if hashes_match:
                prior = dict(prior)
                prior["resumed"] = True
                results_by_id[step_id] = prior
                all_artifacts.extend(existing_artifacts)
                continue
        if cancel_path.exists():
            run_record.status = "cancelled"
            warnings.append("Execution was cancelled by the run cancellation marker.")
            break
        if not should_run:
            now = utc_now()
            record = StepExecutionRecord(
                run_id=run_id,
                step_id=step_id,
                block=str(row.block),
                status="skipped",
                started_at=now,
                finished_at=now,
                duration_seconds=0,
                attempt=0,
                depends_on=dependencies,
                skipped_reason=skipped_reason,
            ).to_dict()
            results_by_id[step_id] = record
            registry.upsert_step(record)
            continue

        step_dir = root / step_id
        step_dir.mkdir(parents=True, exist_ok=True)
        upstream_artifacts = [artifact for dep in dependency_results for artifact in dep.get("artifacts", [])]
        final_record: dict[str, Any] | None = None
        for attempt in range(1, max(1, int(retries) + 1) + 1):
            step_started = utc_now()
            step_clock = time.perf_counter()
            stdout_path = step_dir / f"attempt_{attempt}.stdout.log"
            stderr_path = step_dir / f"attempt_{attempt}.stderr.log"
            result_path = step_dir / "result.json"
            try:
                context = {
                    "run_id": run_id,
                    "workflow_name": workflow_name,
                    "workflow_sha256": workflow_sha,
                    "step_id": step_id,
                    "block": str(row.block),
                    "step_directory": str(step_dir),
                    "parameters": parameters,
                    "depends_on": dependencies,
                    "upstream_results": dependency_results,
                    "upstream_artifacts": upstream_artifacts,
                    "all_results": list(results_by_id.values()),
                    "all_artifacts": all_artifacts,
                }
                payload = task_for_block(str(row.block))(context)
                step_finished = utc_now()
                duration = time.perf_counter() - step_clock
                step_warnings = [str(value) for value in payload.get("warnings", [])]
                warnings.extend(step_warnings)
                record = StepExecutionRecord(
                    run_id=run_id,
                    step_id=step_id,
                    block=str(row.block),
                    status=str(payload.get("status", "completed")),
                    started_at=step_started,
                    finished_at=step_finished,
                    duration_seconds=round(duration, 6),
                    attempt=attempt,
                    depends_on=dependencies,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    result_path=str(result_path),
                    metrics=dict(payload.get("metrics", {})),
                    artifacts=list(payload.get("artifacts", [])),
                ).to_dict()
                stdout_path.write_text("BioIntel internal task completed successfully.\n", encoding="utf-8")
                stderr_path.write_text("", encoding="utf-8")
                atomic_write_json(result_path, record)
                registry.upsert_step(record)
                registry.add_artifacts(run_id, record["artifacts"])
                registry.audit(run_id, "step_completed", f"{step_id} completed.", {"block": row.block, "attempt": attempt})
                final_record = record
                break
            except Exception as exc:
                step_finished = utc_now()
                duration = time.perf_counter() - step_clock
                error_text = f"{type(exc).__name__}: {exc}"
                stderr_path.write_text(traceback.format_exc(), encoding="utf-8")
                stdout_path.write_text("", encoding="utf-8")
                record = StepExecutionRecord(
                    run_id=run_id,
                    step_id=step_id,
                    block=str(row.block),
                    status="failed",
                    started_at=step_started,
                    finished_at=step_finished,
                    duration_seconds=round(duration, 6),
                    attempt=attempt,
                    depends_on=dependencies,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    result_path=str(result_path),
                    error=error_text,
                ).to_dict()
                atomic_write_json(result_path, record)
                registry.upsert_step(record)
                registry.audit(run_id, "step_failed", f"{step_id} failed.", {"block": row.block, "attempt": attempt, "error": error_text})
                final_record = record
                if attempt <= int(retries):
                    time.sleep(min(2.0, 0.2 * attempt))
                    continue
                break
        assert final_record is not None
        results_by_id[step_id] = final_record
        all_artifacts.extend(final_record.get("artifacts", []))
        atomic_write_json(state_path, {"schema": "biointel.workflow.state.v3", "run_id": run_id, "workflow_sha256": workflow_sha, "steps": list(results_by_id.values()), "artifacts": all_artifacts, "updated_at": utc_now()})
        if final_record["status"] == "failed" and fail_fast:
            run_record.status = "failed"
            break

    if run_record.status == "running":
        statuses = [item.get("status") for item in results_by_id.values()]
        run_record.status = "failed" if "failed" in statuses else "completed"
    run_record.finished_at = utc_now()
    run_record.duration_seconds = round(time.perf_counter() - start_clock, 6)
    run_record.steps = list(results_by_id.values())
    run_record.artifacts = all_artifacts
    run_record.warnings = sorted(dict.fromkeys(warnings))
    registry.upsert_run(run_record.to_dict())
    registry.audit(run_id, "workflow_finished", f"Workflow finished with status {run_record.status}.", {"duration_seconds": run_record.duration_seconds})
    atomic_write_json(summary_path, run_record.to_dict())
    summary_artifact = artifact_record(summary_path, step_id="workflow", role="run_summary", media_type="application/json")
    manifest_artifact = artifact_record(manifest_path, step_id="workflow", role="run_manifest", media_type="application/json")
    # Do not rewrite the summary after hashing it: a self-referential file hash
    # cannot be stable. The in-memory result and registry include the detached
    # summary/manifest evidence while the summary file remains immutable.
    run_record.artifacts.extend([summary_artifact, manifest_artifact])
    registry.add_artifacts(run_id, [summary_artifact, manifest_artifact])
    return run_record
