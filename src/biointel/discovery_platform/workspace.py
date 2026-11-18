from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .constants import MODEL_STATES, ROLES
from .models import (
    PlatformValidationError,
    canonical_json,
    check_permission,
    new_id,
    optional_text,
    require_text,
    utc_now,
    validate_choice,
)
from .storage import DiscoveryPlatformStore


class WorkspaceService:
    store: DiscoveryPlatformStore
    actor: str
    role: str

    def _authorize(self, permission: str) -> None:
        check_permission(self.role, permission)

    def _project(self, project_id: str) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        if project is None:
            raise KeyError(project_id)
        return project

    def grant_project_permission(
        self, project_id: str, principal: str, role: str
    ) -> dict[str, Any]:
        self._authorize("assign")
        self._project(project_id)
        validate_choice(role, ROLES, "role")
        identity = require_text(principal, "principal", 240)
        with self.store.connect(read_only=True) as connection:
            existing = connection.execute(
                "SELECT permission_id FROM project_permissions WHERE project_id=? AND principal=?",
                (project_id, identity),
            ).fetchone()
        if existing:
            self.store.update(
                "project_permissions", "permission_id", str(existing[0]), {"role": role}
            )
            permission_id = str(existing[0])
        else:
            permission_id = new_id("PERM")
            self.store.insert(
                "project_permissions",
                {
                    "permission_id": permission_id, "project_id": project_id,
                    "principal": identity, "role": role, "granted_by": self.actor,
                    "created_at_utc": utc_now(),
                },
            )
        self.store.audit(
            "project_permission_granted", "permission", permission_id,
            project_id=project_id, actor=self.actor, role=self.role,
            detail={"principal": identity, "role": role},
        )
        return self.store.row("project_permissions", "permission_id", permission_id) or {}

    def register_model(
        self,
        *,
        name: str,
        version: str,
        task: str,
        owner: str,
        artifact_path: str | Path,
        project_id: str | None = None,
        training_dataset_id: str | None = None,
        validation_dataset_id: str | None = None,
        feature_set: Sequence[str] = (),
        preprocessing: Mapping[str, Any] | None = None,
        hyperparameters: Mapping[str, Any] | None = None,
        random_seed: int | None = None,
        performance: Mapping[str, Any] | None = None,
        calibration: Mapping[str, Any] | None = None,
        subgroup_performance: Mapping[str, Any] | None = None,
        bias_analysis: Mapping[str, Any] | None = None,
        ood_checks: Mapping[str, Any] | None = None,
        drift_status: str = "Not assessed",
        explainability: Mapping[str, Any] | None = None,
        limitations: Sequence[str] = (),
        approval_status: str = "Experimental",
        deployment_status: str = "Not deployed",
        environment: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize("write")
        validate_choice(approval_status, MODEL_STATES, "model approval status")
        if project_id:
            self._project(project_id)
        for dataset_id in (training_dataset_id, validation_dataset_id):
            if dataset_id and self.store.row("datasets", "dataset_id", dataset_id) is None:
                raise PlatformValidationError(f"Model dataset was not found: {dataset_id}")
        path = Path(artifact_path).resolve()
        if not path.is_file():
            raise PlatformValidationError(f"Model artifact was not found: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        model_id = new_id("MODEL")
        now = utc_now()
        self.store.insert(
            "models",
            {
                "model_id": model_id, "project_id": project_id,
                "name": require_text(name, "model name", 240),
                "version": require_text(version, "model version", 120),
                "task": require_text(task, "model task", 240),
                "owner": require_text(owner, "model owner", 240),
                "training_dataset_id": training_dataset_id,
                "validation_dataset_id": validation_dataset_id,
                "feature_set_json": list(feature_set),
                "preprocessing_json": dict(preprocessing or {}),
                "hyperparameters_json": dict(hyperparameters or {}),
                "random_seed": random_seed,
                "performance_json": dict(performance or {}),
                "calibration_json": dict(calibration or {}),
                "subgroup_performance_json": dict(subgroup_performance or {}),
                "bias_analysis_json": dict(bias_analysis or {}),
                "ood_checks_json": dict(ood_checks or {}),
                "drift_status": optional_text(drift_status, 120),
                "explainability_json": dict(explainability or {}),
                "limitations_json": list(limitations),
                "approval_status": approval_status,
                "deployment_status": optional_text(deployment_status, 120),
                "deprecation_status": "Active",
                "artifact_paths_json": [str(path)],
                "model_hash": digest.hexdigest(),
                "environment_json": dict(environment or {}),
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self.store.audit(
            "model_registered", "model", model_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"name": name, "version": version, "hash": digest.hexdigest()},
        )
        return self.store.row("models", "model_id", model_id) or {}

    def update_model_state(
        self,
        model_id: str,
        approval_status: str,
        *,
        deployment_status: str | None = None,
        deprecation_status: str | None = None,
    ) -> dict[str, Any]:
        self._authorize("approve")
        validate_choice(approval_status, MODEL_STATES, "model approval status")
        model = self.store.row("models", "model_id", model_id)
        if model is None:
            raise KeyError(model_id)
        changes: dict[str, Any] = {
            "approval_status": approval_status,
            "updated_at_utc": utc_now(),
        }
        if deployment_status is not None:
            changes["deployment_status"] = optional_text(deployment_status, 120)
        if deprecation_status is not None:
            changes["deprecation_status"] = optional_text(deprecation_status, 120)
        self.store.update("models", "model_id", model_id, changes)
        self.store.audit(
            "model_state_updated", "model", model_id, project_id=model.get("project_id"),
            actor=self.actor, role=self.role, detail=changes,
        )
        return self.store.row("models", "model_id", model_id) or {}

    def compare_models(
        self,
        first_id: str | None = None,
        second_id: str | None = None,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if first_id is not None or second_id is not None:
            if not first_id or not second_id:
                raise PlatformValidationError("Two model identifiers are required")
            first = self.store.row("models", "model_id", first_id)
            second = self.store.row("models", "model_id", second_id)
            if first is None:
                raise KeyError(first_id)
            if second is None:
                raise KeyError(second_id)
            comparison_fields = (
                "task", "approval_status", "deployment_status", "performance",
                "calibration", "drift_status", "limitations", "model_hash",
            )
            return {
                "first": first,
                "second": second,
                "differences": {
                    field: {"first": first.get(field), "second": second.get(field)}
                    for field in comparison_fields
                    if first.get(field) != second.get(field)
                },
            }
        filters = {"project_id": project_id} if project_id else None
        models = self.store.rows(
            "models", filters=filters, order_by="updated_at_utc", limit=limit
        )
        return [
            {
                "model_id": item["model_id"], "name": item["name"], "version": item["version"],
                "task": item["task"], "approval_status": item["approval_status"],
                "deployment_status": item["deployment_status"],
                "performance": item.get("performance", {}),
                "calibration": item.get("calibration", {}),
                "drift_status": item["drift_status"],
                "limitations": item.get("limitations", []),
            }
            for item in models
        ]

    def record_explanation(
        self,
        model_id: str,
        *,
        dataset_id: str,
        run_id: str,
        input_hash: str,
        prediction_reference: str,
        explanation_type: str,
        values: Mapping[str, Any],
        parameters: Mapping[str, Any] | None = None,
        stability: Mapping[str, Any] | None = None,
        ood_warning: str = "",
    ) -> dict[str, Any]:
        self._authorize("write")
        model = self.store.row("models", "model_id", model_id)
        if model is None:
            raise KeyError(model_id)
        if self.store.row("datasets", "dataset_id", dataset_id) is None:
            raise KeyError(dataset_id)
        if self.store.row("runs", "run_id", run_id) is None:
            raise KeyError(run_id)
        explanation = {
            "explanation_id": new_id("XAI"), "model_id": model_id,
            "model_version": model["version"], "dataset_id": dataset_id,
            "run_id": run_id, "input_hash": require_text(input_hash, "input hash", 128),
            "prediction_reference": require_text(
                prediction_reference, "prediction reference", 500
            ),
            "explanation_type": require_text(explanation_type, "explanation type", 160),
            "values": dict(values), "parameters": dict(parameters or {}),
            "stability": dict(stability or {}), "ood_warning": optional_text(ood_warning, 1000),
            "created_at_utc": utc_now(),
        }
        history = dict(model.get("explainability") or {})
        entries = list(history.get("entries") or [])
        entries.append(explanation)
        history["entries"] = entries[-100:]
        self.store.update(
            "models", "model_id", model_id,
            {"explainability_json": history, "updated_at_utc": utc_now()},
        )
        self.store.audit(
            "model_explanation_recorded", "model", model_id,
            project_id=model.get("project_id"), actor=self.actor, role=self.role,
            detail={
                "explanation_id": explanation["explanation_id"],
                "type": explanation_type, "run_id": run_id,
            },
        )
        return explanation

    def create_notebook(
        self,
        project_id: str,
        *,
        title: str,
        content_markdown: str,
        tags: Sequence[str] = (),
        links: Mapping[str, Any] | None = None,
        attachments: Sequence[str] = (),
    ) -> dict[str, Any]:
        self._authorize("write")
        self._project(project_id)
        notebook_id = new_id("NOTEBOOK")
        now = utc_now()
        self.store.insert(
            "notebooks",
            {
                "notebook_id": notebook_id, "project_id": project_id,
                "title": require_text(title, "notebook title", 500),
                "tags_json": list(dict.fromkeys(str(tag) for tag in tags)),
                "created_by": self.actor, "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self.add_notebook_version(
            notebook_id, content_markdown=content_markdown,
            links=links, attachments=attachments,
        )
        self.store.audit(
            "notebook_created", "notebook", notebook_id, project_id=project_id,
            actor=self.actor, role=self.role, detail={"title": title},
        )
        return self.notebook(notebook_id)

    def add_notebook_version(
        self,
        notebook_id: str,
        *,
        content_markdown: str,
        links: Mapping[str, Any] | None = None,
        attachments: Sequence[str] = (),
    ) -> dict[str, Any]:
        self._authorize("write")
        notebook = self.store.row("notebooks", "notebook_id", notebook_id)
        if notebook is None:
            raise KeyError(notebook_id)
        content = require_text(content_markdown, "notebook content", 2_000_000)
        version_id = new_id("NOTEVER")
        now = utc_now()
        self.store.insert(
            "notebook_versions",
            {
                "version_id": version_id, "notebook_id": notebook_id,
                "content_markdown": content, "links_json": dict(links or {}),
                "attachments_json": list(attachments),
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "created_by": self.actor, "created_at_utc": now,
            },
        )
        self.store.update(
            "notebooks", "notebook_id", notebook_id, {"updated_at_utc": now}
        )
        self.store.audit(
            "notebook_version_added", "notebook", notebook_id,
            project_id=notebook["project_id"], actor=self.actor, role=self.role,
            detail={"version_id": version_id},
        )
        return self.store.row("notebook_versions", "version_id", version_id) or {}

    def notebook(self, notebook_id: str) -> dict[str, Any]:
        notebook = self.store.row("notebooks", "notebook_id", notebook_id)
        if notebook is None:
            raise KeyError(notebook_id)
        notebook["versions"] = self.store.rows(
            "notebook_versions", filters={"notebook_id": notebook_id},
            order_by="created_at_utc", limit=500,
        )
        return notebook

    def search_notebooks(
        self, project_id: str, query: str = "", *, limit: int = 100
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        pattern = f"%{query.strip()}%"
        with self.store.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT n.* FROM notebooks n
                LEFT JOIN notebook_versions v ON v.notebook_id=n.notebook_id
                WHERE n.project_id=? AND (?='' OR n.title LIKE ? OR v.content_markdown LIKE ?)
                ORDER BY n.updated_at_utc DESC LIMIT ?
                """,
                (project_id, query.strip(), pattern, pattern, max(1, min(limit, 1000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_report_record(
        self,
        project_id: str,
        *,
        title: str,
        sections: Mapping[str, Any],
        status: str = "Draft",
    ) -> dict[str, Any]:
        self._authorize("write")
        self._project(project_id)
        report_id = new_id("REPORT")
        now = utc_now()
        self.store.insert(
            "reports",
            {
                "report_id": report_id, "project_id": project_id,
                "title": require_text(title, "report title", 500),
                "sections_json": dict(sections), "review_required": 1,
                "status": optional_text(status, 120) or "Draft",
                "artifact_ids_json": [], "created_by": self.actor,
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self.store.audit(
            "report_draft_created", "report", report_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"title": title, "researcher_review_required": True},
        )
        return self.store.row("reports", "report_id", report_id) or {}


    def add_comment(
        self,
        project_id: str,
        *,
        entity_type: str,
        entity_id: str,
        body: str,
        mentions: Sequence[str] = (),
    ) -> dict[str, Any]:
        self._authorize("comment")
        self._project(project_id)
        comment_id = new_id("COMMENT")
        now = utc_now()
        self.store.insert(
            "comments",
            {
                "comment_id": comment_id, "project_id": project_id,
                "entity_type": require_text(entity_type, "entity type", 120),
                "entity_id": require_text(entity_id, "entity id", 200),
                "body": require_text(body, "comment", 10000),
                "mentions_json": list(dict.fromkeys(str(value) for value in mentions)),
                "author": self.actor, "resolved": 0,
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self.store.audit(
            "comment_added", "comment", comment_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"entity_type": entity_type, "entity_id": entity_id},
        )
        return self.store.row("comments", "comment_id", comment_id) or {}

    def review_action(
        self,
        project_id: str,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        note: str = "",
        due_date: str | None = None,
    ) -> dict[str, Any]:
        self._authorize("review")
        self._project(project_id)
        validate_choice(
            action,
            (
                "Review requested", "Approved", "Rejected", "Change requested",
                "Locked", "Finalized", "Assigned",
            ),
            "review action",
        )
        review_id = new_id("REVIEW")
        self.store.insert(
            "review_actions",
            {
                "review_id": review_id, "project_id": project_id,
                "entity_type": require_text(entity_type, "entity type", 120),
                "entity_id": require_text(entity_id, "entity id", 200),
                "action": action, "actor": self.actor, "role": self.role,
                "note": optional_text(note, 4000), "due_date": due_date,
                "created_at_utc": utc_now(),
            },
        )
        self.store.audit(
            "review_action_recorded", "review", review_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"entity_type": entity_type, "entity_id": entity_id, "action": action},
        )
        return self.store.row("review_actions", "review_id", review_id) or {}

    def create_job(
        self,
        *,
        job_type: str,
        project_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        priority: int = 50,
    ) -> dict[str, Any]:
        self._authorize("run")
        if project_id:
            self._project(project_id)
        job_id = new_id("JOB")
        now = utc_now()
        self.store.insert(
            "jobs",
            {
                "job_id": job_id, "project_id": project_id,
                "job_type": require_text(job_type, "job type", 200),
                "priority": max(0, min(100, int(priority))), "status": "Queued",
                "payload_json": dict(payload or {}), "progress": 0.0,
                "cancellation_requested": 0, "checkpoint_json": {},
                "error_json": {}, "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self.store.audit(
            "job_created", "job", job_id, project_id=project_id,
            actor=self.actor, role=self.role, detail={"job_type": job_type, "priority": priority},
        )
        return self.store.row("jobs", "job_id", job_id) or {}

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        checkpoint: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize("run")
        job = self.store.row("jobs", "job_id", job_id)
        if job is None:
            raise KeyError(job_id)
        changes: dict[str, Any] = {"updated_at_utc": utc_now()}
        if status is not None:
            validate_choice(
                status,
                ("Queued", "Running", "Paused", "Completed", "Failed", "Cancelled"),
                "job status",
            )
            changes["status"] = status
        if progress is not None:
            if not 0 <= float(progress) <= 1:
                raise PlatformValidationError("Job progress must be between 0 and 1")
            changes["progress"] = float(progress)
        if checkpoint is not None:
            changes["checkpoint_json"] = dict(checkpoint)
        if error is not None:
            changes["error_json"] = dict(error)
        self.store.update("jobs", "job_id", job_id, changes)
        return self.store.row("jobs", "job_id", job_id) or {}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.row("jobs", "job_id", job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] in {"Completed", "Failed", "Cancelled"}:
            raise PlatformValidationError("Finished jobs cannot be cancelled")
        self.store.update(
            "jobs", "job_id", job_id,
            {
                "cancellation_requested": 1, "status": "Cancelled",
                "updated_at_utc": utc_now(),
            },
        )
        self.store.audit(
            "job_cancelled", "job", job_id, project_id=job.get("project_id"),
            actor=self.actor, role=self.role, detail={"previous_status": job["status"]},
        )
        return self.store.row("jobs", "job_id", job_id) or {}

    def candidate_dossier(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.store.row("candidates", "candidate_id", candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        project_id = candidate["project_id"]
        evidence_ids = list(
            dict.fromkeys(
                list(candidate.get("supporting_evidence_ids", []))
                + list(candidate.get("contradictory_evidence_ids", []))
            )
        )
        evidence = [
            self.store.row("evidence", "evidence_id", evidence_id)
            for evidence_id in evidence_ids
        ]
        recommendations = self.store.rows(
            "recommendations", filters={"candidate_id": candidate_id},
            order_by="updated_at_utc", limit=500,
        )
        experiments = self.store.rows(
            "experiments", filters={"candidate_id": candidate_id},
            order_by="updated_at_utc", limit=500,
        )
        validations = self.store.rows(
            "validation_results", filters={"candidate_id": candidate_id},
            order_by="created_at_utc", limit=500,
        )
        graph = self.graph_view(project_id, limit=5000)
        candidate_nodes = {
            node["node_id"]
            for node in graph["nodes"]
            if node["entity_type"] == "Candidate" and node["entity_id"] == candidate_id
        }
        edges = [
            edge
            for edge in graph["edges"]
            if edge["source_node_id"] in candidate_nodes or edge["target_node_id"] in candidate_nodes
        ]
        return {
            "candidate": candidate,
            "evidence": [item for item in evidence if item],
            "recommendations": recommendations,
            "experiments": experiments,
            "validations": validations,
            "graph_edges": edges,
            "scientific_status": (
                "Validated" if candidate["lifecycle_state"] == "Validated"
                else "Research candidate; validation incomplete"
            ),
        }

    def activity_feed(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        return self.store.rows(
            "audit_events", filters={"project_id": project_id},
            order_by="occurred_at_utc", limit=limit, offset=offset,
        )

    def dashboard_summary(self, project_id: str | None = None) -> dict[str, Any]:
        filters = {"project_id": project_id} if project_id else None
        if project_id:
            self._project(project_id)
        tables = (
            "datasets", "samples", "runs", "candidates", "recommendations",
            "evidence", "hypotheses", "experiments", "validation_results",
            "models", "reports", "jobs",
        )
        counts: dict[str, int] = {}
        with self.store.connect(read_only=True) as connection:
            for table in tables:
                if project_id and "project_id" in {
                    str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
                }:
                    counts[table] = int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)
                        ).fetchone()[0]
                    )
                else:
                    counts[table] = int(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    )
            job_rows = connection.execute(
                "SELECT status,COUNT(*) AS count FROM jobs"
                + (" WHERE project_id=?" if project_id else "")
                + " GROUP BY status",
                ((project_id,) if project_id else ()),
            ).fetchall()
        return {
            "scope": project_id or "portfolio",
            "counts": counts,
            "jobs_by_status": {str(row["status"]): int(row["count"]) for row in job_rows},
            "database_integrity": self.store.integrity(),
            "audit_integrity": self.store.verify_audit_chain(),
            "generated_at_utc": utc_now(),
        }
