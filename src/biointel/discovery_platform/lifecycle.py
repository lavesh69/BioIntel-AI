from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .constants import PROJECT_STAGES, STAGE_REQUIREMENTS
from .models import (
    PlatformConflictError,
    PlatformValidationError,
    ProjectCreate,
    canonical_json,
    check_permission,
    new_id,
    optional_text,
    require_text,
    utc_now,
    validate_choice,
    validate_origin,
)
from .storage import DiscoveryPlatformStore


class LifecycleService:
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

    def create_project(self, request: ProjectCreate) -> dict[str, Any]:
        self._authorize("write")
        item = request.normalized()
        project_id = new_id("PRJ")
        now = utc_now()
        self.store.insert(
            "projects",
            {
                "project_id": project_id,
                "title": item.title,
                "research_question": item.research_question,
                "scientific_objective": item.scientific_objective,
                "disease_context": item.disease_context,
                "organism": item.organism,
                "assay_types_json": item.assay_types,
                "principal_investigator": item.principal_investigator,
                "owner": item.owner,
                "contributors_json": item.contributors,
                "reviewers_json": item.reviewers,
                "start_date": item.start_date,
                "target_date": item.target_date,
                "current_stage": item.current_stage,
                "milestones_json": [],
                "dependencies_json": [],
                "risks_json": [],
                "blockers_json": [],
                "data_origin": item.data_origin,
                "is_synthetic": int(item.is_synthetic),
                "legacy_project_id": None,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        for stage in PROJECT_STAGES:
            self.store.insert(
                "project_stage_gates",
                {
                    "gate_id": new_id("GATE"),
                    "project_id": project_id,
                    "stage": stage,
                    "criteria_json": STAGE_REQUIREMENTS.get(stage, ()),
                    "artifact_ids_json": [],
                    "status": "Pending",
                    "reviewer": "",
                    "decision_note": "",
                    "decided_at_utc": None,
                    "updated_at_utc": now,
                },
            )
        self.store.insert(
            "project_permissions",
            {
                "permission_id": new_id("PERM"),
                "project_id": project_id,
                "principal": item.owner,
                "role": "Principal Investigator" if item.principal_investigator else self.role,
                "granted_by": self.actor,
                "created_at_utc": now,
            },
        )
        self.store.audit(
            "project_created",
            "project",
            project_id,
            project_id=project_id,
            actor=self.actor,
            role=self.role,
            detail={"title": item.title, "stage": item.current_stage, "origin": item.data_origin},
        )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        project = self._project(project_id)
        with self.store.connect(read_only=True) as connection:
            counts = {}
            for table in (
                "datasets", "runs", "candidates", "recommendations", "evidence",
                "hypotheses", "experiments", "validation_results", "reports",
            ):
                counts[table] = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)
                    ).fetchone()[0]
                )
        project["linked_counts"] = counts
        project["stage_gate"] = self.stage_gate(project_id, project["current_stage"])
        return project

    def list_projects(
        self, *, limit: int = 100, offset: int = 0, stage: str | None = None
    ) -> list[dict[str, Any]]:
        self._authorize("read")
        filters = {"current_stage": stage} if stage else None
        return self.store.rows(
            "projects",
            filters=filters,
            order_by="updated_at_utc",
            limit=limit,
            offset=offset,
        )

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any]:
        self._authorize("write")
        self._project(project_id)
        allowed = {
            "title", "research_question", "scientific_objective", "disease_context",
            "organism", "assay_types_json", "principal_investigator", "owner",
            "contributors_json", "reviewers_json", "start_date", "target_date",
            "milestones_json", "dependencies_json", "risks_json", "blockers_json",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise PlatformValidationError("Unsupported project fields: " + ", ".join(sorted(unknown)))
        normalized = dict(changes)
        for key in ("title", "research_question", "scientific_objective"):
            if key in normalized:
                normalized[key] = require_text(normalized[key], key.replace("_", " "), 4000)
        for key in ("assay_types_json", "contributors_json", "reviewers_json", "milestones_json",
                    "dependencies_json", "risks_json", "blockers_json"):
            if key in normalized and not isinstance(normalized[key], (list, tuple)):
                raise PlatformValidationError(f"{key} must be a list")
        normalized["updated_at_utc"] = utc_now()
        if not self.store.update("projects", "project_id", project_id, normalized):
            raise KeyError(project_id)
        self.store.audit(
            "project_updated", "project", project_id, project_id=project_id,
            actor=self.actor, role=self.role, detail={"fields": sorted(changes)},
        )
        return self.get_project(project_id)

    def _requirement_state(self, project_id: str, requirement: str) -> bool:
        project = self._project(project_id)
        if requirement in {"research_question", "scientific_objective"}:
            return bool(project.get(requirement))
        table_checks = {
            "hypothesis": ("hypotheses", "1=1"),
            "dataset": ("datasets", "1=1"),
            "completed_run": ("runs", "status='Completed'"),
            "candidate": ("candidates", "1=1"),
            "ranked_candidate": ("candidates", "lifecycle_state IN ('Prioritized','Shortlisted','Validated')"),
            "recommendation": ("recommendations", "1=1"),
            "validation_plan": ("experiments", "validation_plan_json != '{}'"),
            "experiment": ("experiments", "1=1"),
            "validation_result": ("validation_results", "1=1"),
            "notebook_entry": ("notebooks", "1=1"),
            "report": ("reports", "1=1"),
            "review_approval": ("review_actions", "action='Approved'"),
            "frozen_run": ("runs", "frozen=1"),
        }
        if requirement == "milestone":
            return bool(project.get("milestones"))
        if requirement == "study_design":
            gate = self.store.rows(
                "project_stage_gates",
                filters={"project_id": project_id, "stage": "Study Design"},
                limit=1,
            )
            return bool(gate and gate[0].get("artifact_ids"))
        if requirement == "qc_complete":
            with self.store.connect(read_only=True) as connection:
                row = connection.execute(
                    "SELECT COUNT(*),SUM(CASE WHEN lower(qc_status) IN ('pass','passed','complete','completed') THEN 1 ELSE 0 END) FROM datasets WHERE project_id=?",
                    (project_id,),
                ).fetchone()
            return bool(row[0] and row[0] == row[1])
        if requirement == "completion_gate":
            gates = self.store.rows(
                "project_stage_gates",
                filters={"project_id": project_id, "stage": "Completed"},
                limit=1,
            )
            return bool(gates and gates[0]["status"] == "Approved")
        if requirement == "archive_reason":
            gates = self.store.rows(
                "project_stage_gates",
                filters={"project_id": project_id, "stage": "Archived"},
                limit=1,
            )
            return bool(gates and gates[0].get("decision_note"))
        table_check = table_checks.get(requirement)
        if not table_check:
            return False
        table, clause = table_check
        with self.store.connect(read_only=True) as connection:
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id=? AND {clause}", (project_id,)
            ).fetchone()[0]
        return bool(count)

    def stage_gate(self, project_id: str, stage: str) -> dict[str, Any]:
        validate_choice(stage, PROJECT_STAGES, "project stage")
        self._project(project_id)
        rows = self.store.rows(
            "project_stage_gates",
            filters={"project_id": project_id, "stage": stage},
            limit=1,
        )
        if not rows:
            raise KeyError(f"{project_id}:{stage}")
        gate = rows[0]
        requirements = tuple(gate.get("criteria") or STAGE_REQUIREMENTS.get(stage, ()))
        checks = {requirement: self._requirement_state(project_id, requirement) for requirement in requirements}
        gate["checks"] = checks
        gate["complete"] = all(checks.values()) if checks else gate["status"] == "Approved"
        return gate

    def set_stage_gate(
        self,
        project_id: str,
        stage: str,
        *,
        artifact_ids: Sequence[str] = (),
        criteria: Sequence[str] | None = None,
        status: str = "Pending",
        note: str = "",
    ) -> dict[str, Any]:
        self._authorize("review")
        validate_choice(stage, PROJECT_STAGES, "project stage")
        validate_choice(status, ("Pending", "Conditional", "Approved", "Rejected"), "gate status")
        self._project(project_id)
        changes = {
            "artifact_ids_json": list(dict.fromkeys(str(value) for value in artifact_ids)),
            "status": status,
            "reviewer": self.actor,
            "decision_note": optional_text(note, 4000),
            "decided_at_utc": utc_now() if status != "Pending" else None,
            "updated_at_utc": utc_now(),
        }
        if criteria is not None:
            changes["criteria_json"] = list(dict.fromkeys(str(value) for value in criteria))
        with self.store.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE project_stage_gates SET artifact_ids_json=?,status=?,reviewer=?,
                decision_note=?,decided_at_utc=?,updated_at_utc=?
                """
                + (",criteria_json=?" if criteria is not None else "")
                + " WHERE project_id=? AND stage=?",
                (
                    canonical_json(changes["artifact_ids_json"]), status, self.actor,
                    changes["decision_note"], changes["decided_at_utc"], changes["updated_at_utc"],
                    *((canonical_json(changes["criteria_json"]),) if criteria is not None else ()),
                    project_id, stage,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"{project_id}:{stage}")
        self.store.audit(
            "stage_gate_updated", "stage_gate", stage, project_id=project_id,
            actor=self.actor, role=self.role, detail={"status": status, "artifacts": list(artifact_ids)},
        )
        return self.stage_gate(project_id, stage)

    def advance_stage(self, project_id: str, target_stage: str | None = None) -> dict[str, Any]:
        self._authorize("approve")
        project = self._project(project_id)
        current_index = PROJECT_STAGES.index(project["current_stage"])
        if current_index >= len(PROJECT_STAGES) - 1:
            raise PlatformConflictError("Project is already archived")
        expected = PROJECT_STAGES[current_index + 1]
        target = target_stage or expected
        if target != expected:
            raise PlatformConflictError(f"Next permitted stage is {expected}")
        gate = self.stage_gate(project_id, project["current_stage"])
        if not gate["complete"]:
            missing = [key for key, value in gate["checks"].items() if not value]
            raise PlatformConflictError("Stage gate is incomplete: " + ", ".join(missing))
        now = utc_now()
        with self.store.transaction() as connection:
            connection.execute(
                "UPDATE project_stage_gates SET status='Approved',reviewer=?,decided_at_utc=?,updated_at_utc=? WHERE project_id=? AND stage=?",
                (self.actor, now, now, project_id, project["current_stage"]),
            )
            connection.execute(
                "UPDATE projects SET current_stage=?,updated_at_utc=? WHERE project_id=?",
                (target, now, project_id),
            )
        self.store.audit(
            "project_stage_advanced", "project", project_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"from": project["current_stage"], "to": target},
        )
        return self.get_project(project_id)

    def register_dataset(
        self,
        project_id: str,
        *,
        name: str,
        description: str = "",
        assay_type: str = "",
        omics_type: str = "",
        organism: str = "",
        tissue: str = "",
        disease: str = "",
        cohort: str = "",
        platform: str = "",
        instrument: str = "",
        reference_build: str = "",
        annotation_release: str = "",
        sample_count: int = 0,
        feature_count: int = 0,
        file_formats: Sequence[str] = (),
        data_origin: str = "imported_external_result",
        consent_restrictions: str = "",
        qc_status: str = "Not assessed",
        processing_status: str = "Registered",
        parent_dataset_id: str | None = None,
        dataset_version: str = "1.0",
        provenance: Mapping[str, Any] | None = None,
        is_synthetic: bool = False,
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        validate_origin(data_origin)
        if bool(project["is_synthetic"]) != bool(is_synthetic):
            raise PlatformConflictError("Dataset origin must match its project boundary")
        if is_synthetic and data_origin != "synthetic_demo_output":
            raise PlatformValidationError("Synthetic dataset origin label is required")
        if parent_dataset_id and self.store.row("datasets", "dataset_id", parent_dataset_id) is None:
            raise PlatformValidationError("Parent dataset was not found")
        dataset_id = new_id("DATASET")
        now = utc_now()
        self.store.insert(
            "datasets",
            {
                "dataset_id": dataset_id, "project_id": project_id,
                "name": require_text(name, "dataset name", 240),
                "description": optional_text(description, 4000),
                "assay_type": optional_text(assay_type, 160),
                "omics_type": optional_text(omics_type, 160),
                "organism": optional_text(organism, 200),
                "tissue": optional_text(tissue, 200), "disease": optional_text(disease, 300),
                "cohort": optional_text(cohort, 300), "platform": optional_text(platform, 200),
                "instrument": optional_text(instrument, 200),
                "reference_build": optional_text(reference_build, 120),
                "annotation_release": optional_text(annotation_release, 120),
                "sample_count": max(0, int(sample_count)), "feature_count": max(0, int(feature_count)),
                "file_formats_json": list(dict.fromkeys(str(value).lower() for value in file_formats)),
                "data_origin": data_origin,
                "consent_restrictions": optional_text(consent_restrictions, 2000),
                "qc_status": optional_text(qc_status, 120) or "Not assessed",
                "processing_status": optional_text(processing_status, 120) or "Registered",
                "parent_dataset_id": parent_dataset_id,
                "dataset_version": require_text(dataset_version, "dataset version", 80),
                "provenance_json": dict(provenance or {"source": "local registration", "origin": data_origin}),
                "is_synthetic": int(is_synthetic), "created_at_utc": now, "imported_at_utc": now,
            },
        )
        self.store.audit(
            "dataset_registered", "dataset", dataset_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"name": name, "origin": data_origin, "synthetic": is_synthetic},
        )
        return self.store.row("datasets", "dataset_id", dataset_id) or {}

    def list_datasets(
        self, project_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        return self.store.rows(
            "datasets", filters={"project_id": project_id},
            order_by="imported_at_utc", limit=limit, offset=offset,
        )


    def add_samples(
        self,
        dataset_id: str,
        samples: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self._authorize("write")
        dataset = self.store.row("datasets", "dataset_id", dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        inserted: list[str] = []
        failures: list[dict[str, str]] = []
        required_metadata = ("subject_id", "group_label", "condition_label", "tissue", "batch")
        for index, source in enumerate(samples):
            try:
                sample_id = require_text(
                    source.get("sample_id") or new_id("SAMPLE"), "sample id", 160
                )
                if self.store.row("samples", "sample_id", sample_id):
                    raise PlatformConflictError(f"Sample ID already exists: {sample_id}")
                missing = [
                    field
                    for field in required_metadata
                    if not str(source.get(field, "")).strip()
                ]
                now = utc_now()
                self.store.insert(
                    "samples",
                    {
                        "sample_id": sample_id, "dataset_id": dataset_id,
                        "subject_id": optional_text(source.get("subject_id"), 160),
                        "group_label": optional_text(source.get("group_label") or source.get("group"), 160),
                        "condition_label": optional_text(
                            source.get("condition_label") or source.get("condition"), 160
                        ),
                        "treatment": optional_text(source.get("treatment"), 240),
                        "tissue": optional_text(source.get("tissue"), 200),
                        "timepoint": optional_text(source.get("timepoint"), 120),
                        "batch": optional_text(source.get("batch"), 120),
                        "plate": optional_text(source.get("plate"), 120),
                        "lane": optional_text(source.get("lane"), 120),
                        "biological_replicate": optional_text(
                            source.get("biological_replicate"), 120
                        ),
                        "technical_replicate": optional_text(
                            source.get("technical_replicate"), 120
                        ),
                        "sex": optional_text(source.get("sex"), 80),
                        "age_group": optional_text(source.get("age_group"), 80),
                        "platform": optional_text(source.get("platform"), 160),
                        "qc_status": optional_text(source.get("qc_status"), 120) or "Not assessed",
                        "inclusion_status": optional_text(
                            source.get("inclusion_status"), 120
                        ) or "Included",
                        "exclusion_reason": optional_text(source.get("exclusion_reason"), 1000),
                        "missing_metadata_json": missing,
                        "file_links_json": list(source.get("file_links") or []),
                        "derived_data_links_json": list(source.get("derived_data_links") or []),
                        "lineage_json": list(source.get("lineage") or []),
                        "metadata_json": dict(source.get("metadata") or {}),
                        "created_at_utc": now, "updated_at_utc": now,
                    },
                )
                inserted.append(sample_id)
            except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
                failures.append({"row": str(index + 1), "error": str(exc)})
        if inserted:
            with self.store.transaction() as connection:
                connection.execute(
                    "UPDATE datasets SET sample_count=(SELECT COUNT(*) FROM samples WHERE dataset_id=?) WHERE dataset_id=?",
                    (dataset_id, dataset_id),
                )
            self.store.audit(
                "samples_added", "dataset", dataset_id, project_id=dataset["project_id"],
                actor=self.actor, role=self.role,
                detail={"inserted": len(inserted), "failed": len(failures)},
            )
        return {
            "dataset_id": dataset_id,
            "inserted": inserted,
            "failures": failures,
            "partial_success": bool(inserted and failures),
        }

    def search_samples(
        self,
        dataset_id: str | None = None,
        *,
        query: str = "",
        qc_status: str | None = None,
        inclusion_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._authorize("read")
        clauses: list[str] = []
        parameters: list[Any] = []
        if dataset_id:
            clauses.append("dataset_id=?")
            parameters.append(dataset_id)
        if qc_status:
            clauses.append("qc_status=?")
            parameters.append(qc_status)
        if inclusion_status:
            clauses.append("inclusion_status=?")
            parameters.append(inclusion_status)
        if query.strip():
            clauses.append(
                "(sample_id LIKE ? OR subject_id LIKE ? OR group_label LIKE ? OR condition_label LIKE ? OR tissue LIKE ? OR batch LIKE ?)"
            )
            pattern = f"%{query.strip()}%"
            parameters.extend([pattern] * 6)
        sql = "SELECT * FROM samples"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at_utc DESC LIMIT ? OFFSET ?"
        parameters.extend((max(1, min(int(limit), 5000)), max(0, int(offset))))
        with self.store.connect(read_only=True) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            for key in list(item):
                if key.endswith("_json"):
                    item[key[:-5]] = json.loads(item.pop(key) or "null")
            output.append(item)
        return output

    def bulk_update_samples(
        self, sample_ids: Sequence[str], **changes: Any
    ) -> dict[str, Any]:
        self._authorize("write")
        allowed = {
            "group_label", "condition_label", "treatment", "tissue", "timepoint",
            "batch", "plate", "lane", "biological_replicate", "technical_replicate",
            "sex", "age_group", "platform", "qc_status", "inclusion_status",
            "exclusion_reason",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise PlatformValidationError("Unsupported sample fields: " + ", ".join(sorted(unknown)))
        ids = list(dict.fromkeys(require_text(value, "sample id", 160) for value in sample_ids))
        if not ids:
            return {"updated": 0, "sample_ids": []}
        prepared = {key: optional_text(value, 1000) for key, value in changes.items()}
        prepared["updated_at_utc"] = utc_now()
        assignments = ",".join(f"{key}=?" for key in prepared)
        placeholders = ",".join("?" for _ in ids)
        with self.store.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE samples SET {assignments} WHERE sample_id IN ({placeholders})",
                (*prepared.values(), *ids),
            )
        self.store.audit(
            "samples_bulk_updated", "sample", "", actor=self.actor, role=self.role,
            detail={"sample_ids": ids, "fields": sorted(changes), "updated": cursor.rowcount},
        )
        return {"updated": cursor.rowcount, "sample_ids": ids}

    def duplicate_samples(self, dataset_id: str) -> list[dict[str, Any]]:
        if self.store.row("datasets", "dataset_id", dataset_id) is None:
            raise KeyError(dataset_id)
        with self.store.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT subject_id,condition_label,tissue,timepoint,batch,
                       COUNT(*) AS duplicate_count,GROUP_CONCAT(sample_id) AS sample_ids
                FROM samples WHERE dataset_id=?
                GROUP BY subject_id,condition_label,tissue,timepoint,batch
                HAVING COUNT(*) > 1
                ORDER BY duplicate_count DESC
                """,
                (dataset_id,),
            ).fetchall()
        return [{**dict(row), "sample_ids": str(row["sample_ids"]).split(",")} for row in rows]

    def cross_dataset_sample_matches(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
        with self.store.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT s.subject_id,COUNT(DISTINCT s.dataset_id) AS dataset_count,
                       GROUP_CONCAT(DISTINCT s.dataset_id) AS dataset_ids,
                       GROUP_CONCAT(s.sample_id) AS sample_ids
                FROM samples s JOIN datasets d ON d.dataset_id=s.dataset_id
                WHERE d.project_id=? AND s.subject_id!=''
                GROUP BY s.subject_id HAVING COUNT(DISTINCT s.dataset_id)>1
                ORDER BY dataset_count DESC,s.subject_id
                """,
                (project_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "dataset_ids": str(row["dataset_ids"]).split(","),
                "sample_ids": str(row["sample_ids"]).split(","),
            }
            for row in rows
        ]

    def missing_metadata_report(self, dataset_id: str) -> list[dict[str, Any]]:
        samples = self.search_samples(dataset_id, limit=5000)
        return [
            {
                "sample_id": row["sample_id"],
                "missing_fields": row.get("missing_metadata", []),
                "missing_count": len(row.get("missing_metadata", [])),
            }
            for row in samples
            if row.get("missing_metadata")
        ]

    def exclude_sample(self, sample_id: str, reason: str) -> dict[str, Any]:
        self._authorize("write")
        sample = self.store.row("samples", "sample_id", sample_id)
        if sample is None:
            raise KeyError(sample_id)
        self.store.update(
            "samples", "sample_id", sample_id,
            {
                "inclusion_status": "Excluded",
                "exclusion_reason": require_text(reason, "exclusion reason", 1000),
                "updated_at_utc": utc_now(),
            },
        )
        dataset = self.store.row("datasets", "dataset_id", sample["dataset_id"]) or {}
        self.store.audit(
            "sample_excluded", "sample", sample_id, project_id=dataset.get("project_id"),
            actor=self.actor, role=self.role, detail={"reason": reason},
        )
        return self.store.row("samples", "sample_id", sample_id) or {}

    def dataset_lineage(self, project_id: str) -> dict[str, Any]:
        datasets = self.list_datasets(project_id, limit=5000)
        nodes = [
            {
                "dataset_id": item["dataset_id"],
                "name": item["name"],
                "version": item["dataset_version"],
                "origin": item["data_origin"],
            }
            for item in datasets
        ]
        edges = [
            {"parent": item["parent_dataset_id"], "child": item["dataset_id"]}
            for item in datasets
            if item.get("parent_dataset_id")
        ]
        return {"nodes": nodes, "edges": edges}

    def import_legacy_registries(self, project_root: str | Path) -> dict[str, Any]:
        self._authorize("write")
        root = Path(project_root).resolve()
        project_db = runtime_database_path(root, "projects.sqlite3")
        dataset_db = runtime_database_path(root, "datasets.sqlite3")
        imported_projects: list[str] = []
        imported_datasets: list[str] = []
        failures: list[dict[str, str]] = []
        if project_db.is_file():
            connection = sqlite3.connect(f"file:{project_db.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if "projects" in tables:
                    for row in connection.execute("SELECT * FROM projects"):
                        legacy_id = str(row["project_id"])
                        with self.store.connect(read_only=True) as current:
                            exists = current.execute(
                                "SELECT project_id FROM projects WHERE legacy_project_id=?",
                                (legacy_id,),
                            ).fetchone()
                        if exists:
                            continue
                        try:
                            status = str(row["status"])
                            stage = {
                                "Planning": "Research Question", "Active": "Analysis",
                                "Validation": "Validation Review", "Paused": "Analysis",
                                "Completed": "Completed", "Archived": "Archived",
                            }.get(status, "Research Question")
                            created = self.create_project(
                                ProjectCreate(
                                    title=str(row["name"]),
                                    research_question=str(row["objective"] or "Legacy research question requires review"),
                                    scientific_objective=str(row["objective"] or "Legacy objective requires review"),
                                    owner=str(row["owner_label"] or "local_user"),
                                    target_date=row["target_date"],
                                    current_stage=stage,
                                )
                            )
                            self.store.update(
                                "projects", "project_id", created["project_id"],
                                {"legacy_project_id": legacy_id, "updated_at_utc": utc_now()},
                            )
                            imported_projects.append(created["project_id"])
                        except (ValueError, TypeError, sqlite3.Error) as exc:
                            failures.append({"source": legacy_id, "error": str(exc)})
            finally:
                connection.close()
        if dataset_db.is_file():
            destination_project = imported_projects[0] if imported_projects else None
            if destination_project is None:
                existing = self.list_projects(limit=1)
                if existing:
                    destination_project = existing[0]["project_id"]
                else:
                    destination_project = self.create_project(
                        ProjectCreate(
                            title="Legacy Step219 data library",
                            research_question="Curate and review datasets migrated from the prior registry.",
                            scientific_objective="Preserve prior dataset provenance without changing source records.",
                        )
                    )["project_id"]
            connection = sqlite3.connect(f"file:{dataset_db.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if "datasets" in tables:
                    for row in connection.execute("SELECT * FROM datasets"):
                        legacy_hash = str(row["dataset_sha256"])
                        with self.store.connect(read_only=True) as current:
                            exists = current.execute(
                                "SELECT dataset_id FROM datasets WHERE provenance_json LIKE ?",
                                (f"%{legacy_hash}%",),
                            ).fetchone()
                        if exists:
                            continue
                        metadata = json.loads(row["metadata_json"] or "{}")
                        try:
                            dataset = self.register_dataset(
                                destination_project,
                                name=str(row["dataset_name"]),
                                description=str(row["source_description"]),
                                sample_count=int(row["row_count"]),
                                feature_count=len(json.loads(row["column_names_json"] or "[]")),
                                file_formats=("tabular",),
                                dataset_version=str(row["dataset_version"]),
                                provenance={
                                    "legacy_dataset_sha256": legacy_hash,
                                    "legacy_registry": str(dataset_db),
                                    "metadata": metadata,
                                },
                            )
                            imported_datasets.append(dataset["dataset_id"])
                        except (ValueError, TypeError, sqlite3.Error) as exc:
                            failures.append({"source": legacy_hash, "error": str(exc)})
            finally:
                connection.close()
        self.store.audit(
            "legacy_registry_imported", "migration", "", actor=self.actor, role=self.role,
            detail={
                "projects": len(imported_projects),
                "datasets": len(imported_datasets),
                "failures": failures,
            },
        )
        return {
            "projects": imported_projects,
            "datasets": imported_datasets,
            "failures": failures,
        }
