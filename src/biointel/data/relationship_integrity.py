from __future__ import annotations

from biointel.runtime_paths import runtime_database_directory, runtime_database_path

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from biointel.database.core import transaction


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS resource_nodes (
    node_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    native_database TEXT NOT NULL,
    native_key TEXT NOT NULL,
    label TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(native_database, resource_type, native_key)
);
CREATE INDEX IF NOT EXISTS idx_resource_nodes_type
ON resource_nodes(resource_type, scientific_status);

CREATE TABLE IF NOT EXISTS resource_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    validation_message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(source_node_id, target_node_id, relation_type),
    FOREIGN KEY(source_node_id) REFERENCES resource_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY(target_node_id) REFERENCES resource_nodes(node_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_resource_edges_source ON resource_edges(source_node_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_resource_edges_target ON resource_edges(target_node_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_resource_edges_status ON resource_edges(validation_status, relation_type);

CREATE TABLE IF NOT EXISTS relationship_validation_runs (
    run_id TEXT PRIMARY KEY,
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    valid_edges INTEGER NOT NULL,
    warning_edges INTEGER NOT NULL,
    broken_edges INTEGER NOT NULL,
    orphan_findings INTEGER NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    native_database TEXT,
    native_table TEXT,
    native_key TEXT,
    message TEXT NOT NULL,
    resolution_status TEXT NOT NULL DEFAULT 'open',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES relationship_validation_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_relationship_findings_status
ON relationship_findings(resolution_status, severity, category);
"""


@dataclass(frozen=True)
class RelationshipSummary:
    node_count: int
    edge_count: int
    valid_edges: int
    warning_edges: int
    broken_edges: int
    orphan_findings: int
    database_count: int
    generated_at_utc: str


@lru_cache(maxsize=16)
def _initialize_relationship_registry_once(path_text: str) -> None:
    with transaction(path_text) as connection:
        connection.executescript(SCHEMA)


def initialize_relationship_registry(path: str | Path) -> None:
    _initialize_relationship_registry_once(str(Path(path).resolve()))


def clear_relationship_schema_cache() -> None:
    _initialize_relationship_registry_once.cache_clear()


def _node_id(database: str, resource_type: str, native_key: str) -> str:
    raw = f"{database}|{resource_type}|{native_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _edge_id(source: str, target: str, relation: str) -> str:
    return hashlib.sha256(f"{source}|{target}|{relation}".encode("utf-8")).hexdigest()[:32]


def _upsert_node(
    connection: sqlite3.Connection,
    *,
    database: str,
    resource_type: str,
    native_key: str,
    label: str,
    scientific_status: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    node_id = _node_id(database, resource_type, native_key)
    now = utc_now()
    connection.execute(
        """
        INSERT INTO resource_nodes(
            node_id,resource_type,native_database,native_key,label,scientific_status,
            metadata_json,created_at_utc,updated_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(node_id) DO UPDATE SET
            label=excluded.label,
            scientific_status=excluded.scientific_status,
            metadata_json=excluded.metadata_json,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            node_id,
            resource_type,
            database,
            native_key,
            label,
            scientific_status,
            json.dumps(metadata or {}, sort_keys=True, default=str),
            now,
            now,
        ),
    )
    return node_id


def _upsert_edge(
    connection: sqlite3.Connection,
    *,
    source: str,
    target: str,
    relation: str,
    status: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    edge_id = _edge_id(source, target, relation)
    now = utc_now()
    connection.execute(
        """
        INSERT INTO resource_edges(
            edge_id,source_node_id,target_node_id,relation_type,validation_status,
            validation_message,metadata_json,created_at_utc,updated_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(edge_id) DO UPDATE SET
            validation_status=excluded.validation_status,
            validation_message=excluded.validation_message,
            metadata_json=excluded.metadata_json,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            edge_id,
            source,
            target,
            relation,
            status,
            message,
            json.dumps(metadata or {}, sort_keys=True, default=str),
            now,
            now,
        ),
    )


def _fetch_rows(
    path: Path, query: str, parameters: tuple[object, ...] = ()
) -> list[sqlite3.Row]:
    if not path.is_file():
        return []
    try:
        with managed_connect(path) as connection:
            connection.row_factory = sqlite3.Row
            return list(connection.execute(query, parameters))
    except sqlite3.OperationalError as exc:
        message = str(exc).casefold()
        if message.startswith("no such table:") or message.startswith("no such column:"):
            return []
        raise


def rebuild_relationship_registry(root: str | Path) -> RelationshipSummary:
    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "relationships.sqlite3")
    initialize_relationship_registry(registry)
    databases = runtime_database_directory(project_root)
    pending_findings: list[dict[str, Any]] = []
    with transaction(registry) as connection:
        connection.execute("DELETE FROM resource_edges")
        connection.execute("DELETE FROM resource_nodes")
        connection.execute("DELETE FROM relationship_findings")
        connection.execute("DELETE FROM relationship_validation_runs")

        dataset_nodes: dict[str, str] = {}
        for row in _fetch_rows(
            databases / "datasets.sqlite3",
            "SELECT dataset_sha256,dataset_name,dataset_version,task_type,metadata_json FROM datasets",
        ):
            metadata = json.loads(row["metadata_json"] or "{}")
            status = (
                "release_eligible"
                if metadata.get("scientific_release_eligible")
                else (
                    "demo_reference"
                    if metadata.get("synthetic") or metadata.get("demo_only")
                    else "needs_review"
                )
            )
            dataset_nodes[row["dataset_sha256"]] = _upsert_node(
                connection,
                database="datasets.sqlite3",
                resource_type="dataset",
                native_key=row["dataset_sha256"],
                label=f"{row['dataset_name']} · {row['dataset_version']}",
                scientific_status=status,
                metadata={"task_type": row["task_type"]},
            )

        experiment_nodes: dict[str, str] = {}
        model_nodes: dict[str, str] = {}
        for row in _fetch_rows(
            databases / "experiments.sqlite3",
            "SELECT experiment_id,model_name,model_version,dataset_sha256,synthetic_demo FROM experiments",
        ):
            status = "demo_reference" if int(row["synthetic_demo"] or 0) else "needs_review"
            exp_node = _upsert_node(
                connection,
                database="experiments.sqlite3",
                resource_type="experiment",
                native_key=row["experiment_id"],
                label=f"{row['model_name']} · {row['model_version']}",
                scientific_status=status,
            )
            experiment_nodes[row["experiment_id"]] = exp_node
            model_key = f"{row['model_name']}|{row['model_version']}"
            model_node = model_nodes.setdefault(
                model_key,
                _upsert_node(
                    connection,
                    database="experiments.sqlite3",
                    resource_type="model",
                    native_key=model_key,
                    label=f"{row['model_name']} · {row['model_version']}",
                    scientific_status=status,
                ),
            )
            _upsert_edge(
                connection,
                source=exp_node,
                target=model_node,
                relation="produces_model",
                status="valid",
            )
            dataset_node = dataset_nodes.get(row["dataset_sha256"])
            if dataset_node:
                _upsert_edge(
                    connection,
                    source=exp_node,
                    target=dataset_node,
                    relation="trained_on",
                    status="valid",
                )
            else:
                alias = _fetch_rows(
                    databases / "datasets.sqlite3",
                    "SELECT canonical_dataset_sha256 FROM dataset_aliases WHERE alias_sha256=? LIMIT 1",
                    (row["dataset_sha256"],),
                )
                resolved = (
                    dataset_nodes.get(alias[0]["canonical_dataset_sha256"]) if alias else None
                )
                if resolved:
                    _upsert_edge(
                        connection,
                        source=exp_node,
                        target=resolved,
                        relation="trained_on_alias",
                        status="warning",
                        message="Historical dataset hash resolved through explicit alias",
                    )
                else:
                    unresolved = _upsert_node(
                        connection,
                        database="experiments.sqlite3",
                        resource_type="unresolved_dataset_reference",
                        native_key=row["dataset_sha256"],
                        label=f"Unresolved dataset · {str(row['dataset_sha256'])[:12]}",
                        scientific_status="unresolved_reference",
                        metadata={"referenced_by_experiment": row["experiment_id"]},
                    )
                    _upsert_edge(
                        connection,
                        source=exp_node,
                        target=unresolved,
                        relation="trained_on_unresolved_dataset",
                        status="warning",
                        message="Historical dataset hash is not present in the local dataset registry",
                    )
                    finding_id = hashlib.sha256(
                        f"unresolved-dataset|{row['experiment_id']}|{row['dataset_sha256']}".encode()
                    ).hexdigest()[:32]
                    pending_findings.append(
                        {
                            "finding_id": finding_id,
                            "severity": "warning",
                            "category": "unresolved_dataset_reference",
                            "native_database": "experiments.sqlite3",
                            "native_table": "experiments",
                            "native_key": row["experiment_id"],
                            "message": (
                                "Historical synthetic dataset hash is unresolved; "
                                "no silent remapping was performed."
                            ),
                            "resolution_status": "open",
                            "metadata_json": json.dumps(
                                {"dataset_sha256": row["dataset_sha256"]}, sort_keys=True
                            ),
                            "created_at_utc": utc_now(),
                        }
                    )

        project_nodes: dict[str, str] = {}
        for row in _fetch_rows(
            databases / "projects.sqlite3", "SELECT project_id,name,status FROM projects"
        ):
            project_nodes[row["project_id"]] = _upsert_node(
                connection,
                database="projects.sqlite3",
                resource_type="project",
                native_key=row["project_id"],
                label=row["name"],
                scientific_status="demo_reference"
                if str(row["project_id"]).startswith("DEMO")
                else "needs_review",
                metadata={"status": row["status"]},
            )
        for row in _fetch_rows(
            databases / "projects.sqlite3",
            "SELECT project_id,resource_type,resource_id,relation_type,status FROM project_resources",
        ):
            source = project_nodes.get(row["project_id"])
            target = None
            if row["resource_type"] == "dataset":
                target = dataset_nodes.get(row["resource_id"])
            elif row["resource_type"] == "model":
                target = model_nodes.get(row["resource_id"])
                if target is None:
                    target = _upsert_node(
                        connection,
                        database="projects.sqlite3",
                        resource_type="model_reference",
                        native_key=row["resource_id"],
                        label=row["resource_id"],
                        scientific_status="needs_review",
                    )
            else:
                target = _upsert_node(
                    connection,
                    database="projects.sqlite3",
                    resource_type=row["resource_type"],
                    native_key=row["resource_id"],
                    label=row["resource_id"],
                    scientific_status="needs_review",
                )
            if source and target:
                _upsert_edge(
                    connection,
                    source=source,
                    target=target,
                    relation=row["relation_type"],
                    status="valid"
                    if row["status"] in {"active", "linked", "verified"}
                    else "warning",
                    metadata={"resource_status": row["status"]},
                )

        source_nodes: dict[str, str] = {}
        for row in _fetch_rows(
            databases / "evidence.sqlite3",
            "SELECT source_id,source_name,source_release,license_id,record_count,metadata_json FROM evidence_sources",
        ):
            source_nodes[row["source_id"]] = _upsert_node(
                connection,
                database="evidence.sqlite3",
                resource_type="evidence_source",
                native_key=row["source_id"],
                label=row["source_name"],
                scientific_status="demo_reference"
                if "Demonstration" in row["source_name"]
                else "needs_review",
                metadata={
                    "source_release": row["source_release"],
                    "license_id": row["license_id"],
                    "record_count": row["record_count"],
                },
            )
        for row in _fetch_rows(
            databases / "evidence.sqlite3",
            "SELECT dataset_sha256,evidence_key,source_id FROM dataset_evidence_links",
        ):
            dataset_node = dataset_nodes.get(row["dataset_sha256"])
            evidence_node = _upsert_node(
                connection,
                database="evidence.sqlite3",
                resource_type="evidence_record",
                native_key=row["evidence_key"],
                label=row["evidence_key"],
                scientific_status="demo_reference",
            )
            if dataset_node:
                _upsert_edge(
                    connection,
                    source=dataset_node,
                    target=evidence_node,
                    relation="supported_by",
                    status="valid",
                )
            source_node = source_nodes.get(row["source_id"])
            if source_node:
                _upsert_edge(
                    connection,
                    source=evidence_node,
                    target=source_node,
                    relation="reported_by",
                    status="valid",
                )

        for row in _fetch_rows(
            databases / "document_history.sqlite3",
            "SELECT run_id,source_name,status,source_sha256 FROM document_extraction_runs",
        ):
            _upsert_node(
                connection,
                database="document_history.sqlite3",
                resource_type="document_run",
                native_key=row["run_id"],
                label=row["source_name"],
                scientific_status="demo_reference",
                metadata={"status": row["status"], "sha256": row["source_sha256"]},
            )

        for row in _fetch_rows(
            databases / "internet_downloads.sqlite3",
            "SELECT source_key,provider,records_available,local_status,COALESCE(reference_record_count,0) reference_record_count,COALESCE(data_scope,'connector_only') data_scope FROM scientific_source_catalog",
        ):
            _upsert_node(
                connection,
                database="internet_downloads.sqlite3",
                resource_type="provider_profile",
                native_key=row["source_key"],
                label=row["provider"],
                scientific_status="verified_public_reference"
                if int(row["reference_record_count"] or 0) > 0
                else "connector_only",
                metadata={
                    "status": row["local_status"],
                    "records_available": row["records_available"],
                    "reference_record_count": row["reference_record_count"],
                    "data_scope": row["data_scope"],
                },
            )

        connection.execute(
            "UPDATE resource_edges SET validation_status='broken',validation_message='Source or target missing' WHERE source_node_id NOT IN (SELECT node_id FROM resource_nodes) OR target_node_id NOT IN (SELECT node_id FROM resource_nodes)"
        )
        node_count = connection.execute("SELECT COUNT(*) FROM resource_nodes").fetchone()[0]
        edge_count = connection.execute("SELECT COUNT(*) FROM resource_edges").fetchone()[0]
        valid_edges = connection.execute(
            "SELECT COUNT(*) FROM resource_edges WHERE validation_status='valid'"
        ).fetchone()[0]
        warning_edges = connection.execute(
            "SELECT COUNT(*) FROM resource_edges WHERE validation_status='warning'"
        ).fetchone()[0]
        broken_edges = connection.execute(
            "SELECT COUNT(*) FROM resource_edges WHERE validation_status='broken'"
        ).fetchone()[0]
        orphan_findings = len(pending_findings)
        run_id = hashlib.sha256(f"relationship-run|{utc_now()}".encode()).hexdigest()[:24]
        now = utc_now()
        summary = RelationshipSummary(
            node_count=node_count,
            edge_count=edge_count,
            valid_edges=valid_edges,
            warning_edges=warning_edges,
            broken_edges=broken_edges,
            orphan_findings=orphan_findings,
            database_count=len(list(databases.glob("*.sqlite3"))),
            generated_at_utc=now,
        )
        connection.execute(
            """
            INSERT INTO relationship_validation_runs(
                run_id,started_at_utc,completed_at_utc,node_count,edge_count,valid_edges,
                warning_edges,broken_edges,orphan_findings,summary_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                now,
                now,
                node_count,
                edge_count,
                valid_edges,
                warning_edges,
                broken_edges,
                orphan_findings,
                json.dumps(asdict(summary), sort_keys=True),
            ),
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO relationship_findings(
                finding_id,run_id,severity,category,native_database,native_table,
                native_key,message,resolution_status,metadata_json,created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    item["finding_id"],
                    run_id,
                    item["severity"],
                    item["category"],
                    item["native_database"],
                    item["native_table"],
                    item["native_key"],
                    item["message"],
                    item["resolution_status"],
                    item["metadata_json"],
                    item["created_at_utc"],
                )
                for item in pending_findings
            ],
        )
    return summary


def relationship_summary(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "relationships.sqlite3")
    if not registry.is_file():
        return asdict(rebuild_relationship_registry(project_root))
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM relationship_validation_runs ORDER BY completed_at_utc DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return asdict(rebuild_relationship_registry(project_root))
        return dict(row)


def relationship_edges(root: str | Path, *, limit: int = 1000) -> list[dict[str, Any]]:
    path = runtime_database_path(Path(root).resolve(), "relationships.sqlite3")
    initialize_relationship_registry(path)
    with managed_connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT e.edge_id,e.relation_type,e.validation_status,e.validation_message,
                       s.resource_type source_type,s.label source_label,s.scientific_status source_status,
                       t.resource_type target_type,t.label target_label,t.scientific_status target_status
                FROM resource_edges e
                JOIN resource_nodes s ON s.node_id=e.source_node_id
                JOIN resource_nodes t ON t.node_id=e.target_node_id
                ORDER BY CASE e.validation_status WHEN 'broken' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,e.relation_type
                LIMIT ?
                """,
                (int(limit),),
            )
        ]
