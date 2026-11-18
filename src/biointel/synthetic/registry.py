from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .core import SyntheticGeneratedDataset, SyntheticSafetyError, payload_contains_synthetic, utc_now
from .exports import build_synthetic_dataset_package


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class SyntheticDataRegistry:
    """Separate registry and storage boundary for demo projects and outputs."""

    def __init__(self, database_path: str | Path, storage_root: str | Path):
        self.database_path = Path(database_path).resolve()
        self.storage_root = Path(storage_root).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        with self._connect():
            pass

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS synthetic_projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                project_type TEXT NOT NULL,
                module_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                seed INTEGER NOT NULL,
                data_origin TEXT NOT NULL CHECK(data_origin='synthetic'),
                is_synthetic INTEGER NOT NULL CHECK(is_synthetic=1),
                storage_path TEXT NOT NULL,
                status TEXT NOT NULL,
                reset_count INTEGER NOT NULL DEFAULT 0,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS synthetic_datasets (
                dataset_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                seed INTEGER NOT NULL,
                manifest_json TEXT NOT NULL,
                package_path TEXT NOT NULL,
                package_sha256 TEXT NOT NULL,
                data_origin TEXT NOT NULL CHECK(data_origin='synthetic'),
                is_synthetic INTEGER NOT NULL CHECK(is_synthetic=1),
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES synthetic_projects(project_id)
            );
            CREATE TABLE IF NOT EXISTS synthetic_runs (
                run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                data_origin TEXT NOT NULL CHECK(data_origin='synthetic'),
                is_synthetic INTEGER NOT NULL CHECK(is_synthetic=1),
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES synthetic_projects(project_id)
            );
            CREATE TABLE IF NOT EXISTS synthetic_recommendations (
                recommendation_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                data_origin TEXT NOT NULL CHECK(data_origin='synthetic'),
                is_synthetic INTEGER NOT NULL CHECK(is_synthetic=1),
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS synthetic_generation_jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS synthetic_audit_events (
                event_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                data_origin TEXT NOT NULL CHECK(data_origin='synthetic'),
                created_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_syn_dataset_project ON synthetic_datasets(project_id, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_syn_run_project ON synthetic_runs(project_id, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_syn_audit_project ON synthetic_audit_events(project_id, created_at_utc);
        """)
        connection.commit()
        return connection

    def audit(self, project_id: str, event_type: str, detail: Mapping[str, Any] | None = None, *, actor: str = "system") -> str:
        event_id = f"SYN-EVENT-{uuid.uuid4().hex[:16].upper()}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO synthetic_audit_events(event_id,project_id,event_type,actor,detail_json,data_origin,created_at_utc) VALUES(?,?,?,?,?,'synthetic',?)",
                (event_id, project_id, event_type, actor, json.dumps(dict(detail or {}), sort_keys=True, default=str), utc_now()),
            )
            connection.commit()
        return event_id

    def create_demo_project(self, project_type: str, module_id: str, scenario: str, seed: int, *, title: str | None = None, actor: str = "local_user") -> dict[str, Any]:
        project_id = f"SYN-DEMO-{uuid.uuid4().hex[:12].upper()}"
        created = utc_now()
        storage = (self.storage_root / project_id).resolve()
        if not storage.is_relative_to(self.storage_root):
            raise SyntheticSafetyError("Synthetic project storage escaped its configured root.")
        storage.mkdir(parents=True, exist_ok=False)
        project = {
            "project_id": project_id,
            "title": title or project_type,
            "project_type": project_type,
            "module_id": module_id,
            "scenario": scenario,
            "seed": int(seed),
            "data_origin": "synthetic",
            "is_synthetic": True,
            "storage_path": str(storage),
            "status": "active",
            "reset_count": 0,
            "created_at_utc": created,
            "updated_at_utc": created,
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO synthetic_projects(project_id,title,project_type,module_id,scenario,seed,data_origin,is_synthetic,storage_path,status,reset_count,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'synthetic',1,?,?,0,?,?)",
                (project_id, project["title"], project_type, module_id, scenario, int(seed), str(storage), "active", created, created),
            )
            connection.commit()
        (storage / "PROJECT_ORIGIN.json").write_text(json.dumps(project, indent=2), encoding="utf-8")
        self.audit(project_id, "demo_project_created", project, actor=actor)
        return project

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM synthetic_projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["is_synthetic"] = bool(item["is_synthetic"])
        return item

    def list_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM synthetic_projects ORDER BY updated_at_utc DESC LIMIT ?", (int(limit),)).fetchall()
        return [{**dict(row), "is_synthetic": bool(row["is_synthetic"])} for row in rows]

    def save_dataset(self, project_id: str, dataset: SyntheticGeneratedDataset, *, actor: str = "system") -> dict[str, Any]:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if not dataset.is_synthetic:
            raise SyntheticSafetyError("Only synthetic datasets can be stored in the synthetic registry.")
        dataset_id = f"SYN-DATASET-{uuid.uuid4().hex[:14].upper()}"
        folder = (Path(project["storage_path"]) / "datasets").resolve()
        if not folder.is_relative_to(self.storage_root):
            raise SyntheticSafetyError("Synthetic dataset storage escaped its configured root.")
        folder.mkdir(parents=True, exist_ok=True)
        package_path = folder / f"{dataset_id}.zip"
        content = build_synthetic_dataset_package(dataset)
        package_path.write_bytes(content)
        import hashlib
        digest = hashlib.sha256(content).hexdigest()
        manifest = dataset.manifest.to_dict()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO synthetic_datasets(dataset_id,project_id,module_id,scenario,seed,manifest_json,package_path,package_sha256,data_origin,is_synthetic,created_at_utc) VALUES(?,?,?,?,?,?,?,?, 'synthetic',1,?)",
                (dataset_id, project_id, dataset.config.module_id, dataset.config.scenario, dataset.config.seed, json.dumps(manifest, sort_keys=True, default=str), str(package_path), digest, utc_now()),
            )
            connection.execute("UPDATE synthetic_projects SET updated_at_utc=? WHERE project_id=?", (utc_now(), project_id))
            connection.commit()
        result = {"dataset_id": dataset_id, "project_id": project_id, "package_path": str(package_path), "package_sha256": digest, "data_origin": "synthetic", "is_synthetic": True}
        self.audit(project_id, "synthetic_dataset_saved", result, actor=actor)
        return result

    def list_datasets(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM synthetic_datasets WHERE project_id=? ORDER BY created_at_utc DESC", (project_id,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["manifest"] = json.loads(item.pop("manifest_json"))
            item["is_synthetic"] = True
            output.append(item)
        return output

    def register_run(self, project_id: str, dataset_id: str, run_type: str, payload: Mapping[str, Any], *, status: str = "completed", actor: str = "system") -> str:
        if self.get_project(project_id) is None:
            raise KeyError(project_id)
        if not payload_contains_synthetic(payload):
            raise SyntheticSafetyError("Synthetic run payload must preserve synthetic origin.")
        run_id = f"SYN-RUN-{uuid.uuid4().hex[:14].upper()}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO synthetic_runs(run_id,project_id,dataset_id,run_type,status,payload_json,data_origin,is_synthetic,created_at_utc) VALUES(?,?,?,?,?,?,'synthetic',1,?)",
                (run_id, project_id, dataset_id, run_type, status, json.dumps(dict(payload), sort_keys=True, default=str), utc_now()),
            )
            connection.commit()
        self.audit(project_id, "synthetic_run_registered", {"run_id": run_id, "dataset_id": dataset_id, "run_type": run_type, "status": status}, actor=actor)
        return run_id

    def register_recommendation(self, project_id: str, run_id: str, recommendation: Mapping[str, Any], *, actor: str = "system") -> str:
        if not payload_contains_synthetic(recommendation):
            raise SyntheticSafetyError("Synthetic recommendation lost its origin label.")
        recommendation_id = str(recommendation.get("recommendation_id") or f"SYN-REC-{uuid.uuid4().hex[:14].upper()}")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO synthetic_recommendations(recommendation_id,project_id,run_id,payload_json,data_origin,is_synthetic,created_at_utc) VALUES(?,?,?,?,'synthetic',1,?)",
                (recommendation_id, project_id, run_id, json.dumps(dict(recommendation), sort_keys=True, default=str), utc_now()),
            )
            connection.commit()
        self.audit(project_id, "synthetic_recommendation_registered", {"recommendation_id": recommendation_id, "run_id": run_id}, actor=actor)
        return recommendation_id

    def create_generation_job(self, project_id: str, request: Mapping[str, Any], *, actor: str = "system") -> str:
        if self.get_project(project_id) is None:
            raise KeyError(project_id)
        job_id = f"SYN-JOB-{uuid.uuid4().hex[:14].upper()}"
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO synthetic_generation_jobs(job_id,project_id,status,request_json,cancellation_requested,created_at_utc,updated_at_utc) VALUES(?,?,'queued',?,0,?,?)",
                (job_id, project_id, json.dumps(dict(request), sort_keys=True, default=str), now, now),
            )
            connection.commit()
        self.audit(project_id, "generation_job_created", {"job_id": job_id}, actor=actor)
        return job_id

    def list_generation_jobs(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM synthetic_generation_jobs WHERE project_id=? ORDER BY created_at_utc DESC LIMIT ?",
                (project_id, min(max(int(limit), 1), 100)),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["request"] = json.loads(item.pop("request_json"))
            item["cancellation_requested"] = bool(item["cancellation_requested"])
            output.append(item)
        return output
    def cancellation_requested(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT cancellation_requested FROM synthetic_generation_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return bool(row[0])

    def cancel_generation_job(self, job_id: str, *, actor: str = "local_user") -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM synthetic_generation_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            connection.execute("UPDATE synthetic_generation_jobs SET cancellation_requested=1,status='cancelled',updated_at_utc=? WHERE job_id=?", (utc_now(), job_id))
            connection.commit()
        self.audit(str(row["project_id"]), "generation_job_cancelled", {"job_id": job_id}, actor=actor)

    def complete_generation_job(self, job_id: str, status: str = "completed") -> None:
        with self._connect() as connection:
            connection.execute("UPDATE synthetic_generation_jobs SET status=?,updated_at_utc=? WHERE job_id=?", (status, utc_now(), job_id))
            connection.commit()

    def reset_project(self, project_id: str, *, actor: str = "local_user") -> dict[str, Any]:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        project_path = Path(project["storage_path"]).resolve()
        if not project_path.is_relative_to(self.storage_root) or not project_path.name.startswith("SYN-DEMO-"):
            raise SyntheticSafetyError("Refusing to reset a path outside the synthetic project boundary.")
        if project_path.exists():
            shutil.rmtree(project_path)
        project_path.mkdir(parents=True, exist_ok=False)
        with self._connect() as connection:
            connection.execute("DELETE FROM synthetic_recommendations WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM synthetic_runs WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM synthetic_datasets WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM synthetic_generation_jobs WHERE project_id=?", (project_id,))
            connection.execute("UPDATE synthetic_projects SET reset_count=reset_count+1,updated_at_utc=? WHERE project_id=?", (utc_now(), project_id))
            connection.commit()
        refreshed = self.get_project(project_id) or project
        (project_path / "PROJECT_ORIGIN.json").write_text(json.dumps(refreshed, indent=2, default=str), encoding="utf-8")
        self.audit(project_id, "demo_project_reset", {"reset_count": refreshed.get("reset_count")}, actor=actor)
        return refreshed

    def audit_events(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM synthetic_audit_events WHERE project_id=? ORDER BY created_at_utc DESC", (project_id,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json"))
            output.append(item)
        return output


__all__ = ["SyntheticDataRegistry"]
