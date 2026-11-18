from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from typing import Any, Mapping, Sequence

from .constants import WORKFLOW_TEMPLATES
from .models import (
    PlatformConflictError,
    PlatformValidationError,
    canonical_json,
    new_id,
    require_text,
    utc_now,
)
from .storage import DiscoveryPlatformStore


def validate_dag(
    nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    keys = [require_text(node.get("key"), "workflow node key", 120) for node in nodes]
    if len(keys) != len(set(keys)):
        raise PlatformValidationError("Workflow node keys must be unique")
    known = set(keys)
    successors: dict[str, list[str]] = defaultdict(list)
    indegree = dict.fromkeys(keys, 0)
    for edge in edges:
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        if source not in known or target not in known:
            raise PlatformValidationError(f"Workflow edge references an unknown node: {source}->{target}")
        if source == target:
            raise PlatformValidationError("Workflow self-edges are not permitted")
        if target not in successors[source]:
            successors[source].append(target)
            indegree[target] += 1
    ready = deque(sorted(key for key, degree in indegree.items() if degree == 0))
    order: list[str] = []
    levels: list[list[str]] = []
    current_indegree = dict(indegree)
    while ready:
        level = list(ready)
        ready.clear()
        levels.append(level)
        for source in level:
            order.append(source)
            for target in successors[source]:
                current_indegree[target] -= 1
                if current_indegree[target] == 0:
                    ready.append(target)
        ready = deque(sorted(ready))
    if len(order) != len(keys):
        cyclic = sorted(set(keys) - set(order))
        raise PlatformValidationError("Workflow contains a cycle involving: " + ", ".join(cyclic))
    return {
        "valid": True,
        "topological_order": order,
        "parallel_levels": levels,
        "root_nodes": sorted(key for key, degree in indegree.items() if degree == 0),
        "terminal_nodes": sorted(key for key in keys if not successors[key]),
    }


class WorkflowRegistry:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store

    def create(
        self,
        *,
        name: str,
        nodes: Sequence[Mapping[str, Any]],
        edges: Sequence[Mapping[str, Any]],
        project_id: str | None = None,
        template_key: str = "",
        version: str = "1.0",
        created_by: str = "local_user",
    ) -> dict[str, Any]:
        if project_id and self.store.row("projects", "project_id", project_id) is None:
            raise KeyError(project_id)
        dag = validate_dag(nodes, edges)
        workflow_id = new_id("WORKFLOW")
        workflow_version_id = new_id("WFVER")
        now = utc_now()
        definition = {
            "name": name,
            "template_key": template_key,
            "nodes": [dict(node) for node in nodes],
            "edges": [dict(edge) for edge in edges],
            "dag": dag,
        }
        digest = hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO workflows(
                    workflow_id,project_id,name,template_key,active_version_id,status,
                    created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,'Active',?,?)
                """,
                (
                    workflow_id, project_id, require_text(name, "workflow name", 500),
                    template_key, workflow_version_id, now, now,
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow_versions(
                    workflow_version_id,workflow_id,version,definition_json,
                    definition_sha256,created_by,created_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    workflow_version_id, workflow_id,
                    require_text(version, "workflow version", 80),
                    canonical_json(definition), digest, created_by, now,
                ),
            )
            node_ids: dict[str, str] = {}
            for node in nodes:
                node_key = str(node["key"])
                node_id = new_id("WFNODE")
                node_ids[node_key] = node_id
                connection.execute(
                    """
                    INSERT INTO workflow_nodes(
                        node_id,workflow_version_id,node_key,title,node_type,parameters_json,
                        retry_limit,timeout_seconds,cache_enabled,condition_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        node_id, workflow_version_id, node_key,
                        require_text(node.get("title") or node_key, "workflow node title", 500),
                        require_text(node.get("node_type") or "control", "workflow node type", 120),
                        canonical_json(node.get("parameters") or {}),
                        max(0, int(node.get("retry_limit", 0))),
                        max(1, int(node.get("timeout_seconds", 3600))),
                        int(bool(node.get("cache_enabled", True))),
                        canonical_json(node.get("condition") or {}),
                    ),
                )
            for edge in edges:
                connection.execute(
                    """
                    INSERT INTO workflow_edges(
                        edge_id,workflow_version_id,source_node_id,target_node_id,condition_json
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        new_id("WFEDGE"), workflow_version_id,
                        node_ids[str(edge["source"])], node_ids[str(edge["target"])],
                        canonical_json(edge.get("condition") or {}),
                    ),
                )
        self.store.audit(
            "workflow_created", "workflow", workflow_id, project_id=project_id,
            actor=created_by, detail={
                "version": version, "definition_sha256": digest,
                "node_count": len(nodes), "edge_count": len(edges),
            },
        )
        return self.manifest(workflow_version_id)

    def create_template(
        self,
        template_key: str,
        *,
        project_id: str | None = None,
        created_by: str = "local_user",
    ) -> dict[str, Any]:
        if template_key not in WORKFLOW_TEMPLATES:
            raise PlatformValidationError(f"Unknown workflow template: {template_key}")
        step_keys = WORKFLOW_TEMPLATES[template_key]
        nodes = [
            {
                "key": key,
                "title": key.replace("_", " ").title(),
                "node_type": "control" if key in {"ingest", "report", "review", "gaps"} else "analysis",
                "parameters": {},
                "retry_limit": 1,
                "timeout_seconds": 3600,
                "cache_enabled": True,
            }
            for key in step_keys
        ]
        edges = [
            {"source": step_keys[index], "target": step_keys[index + 1]}
            for index in range(len(step_keys) - 1)
        ]
        return self.create(
            name=template_key.replace("_", " ").title(),
            nodes=nodes,
            edges=edges,
            project_id=project_id,
            template_key=template_key,
            created_by=created_by,
        )

    def manifest(self, workflow_version_id: str) -> dict[str, Any]:
        version = self.store.row(
            "workflow_versions", "workflow_version_id", workflow_version_id
        )
        if version is None:
            raise KeyError(workflow_version_id)
        workflow = self.store.row("workflows", "workflow_id", version["workflow_id"]) or {}
        nodes = self.store.rows(
            "workflow_nodes",
            filters={"workflow_version_id": workflow_version_id},
            limit=5000,
        )
        edges = self.store.rows(
            "workflow_edges",
            filters={"workflow_version_id": workflow_version_id},
            limit=5000,
        )
        id_to_key = {node["node_id"]: node["node_key"] for node in nodes}
        normalized_edges = [
            {
                **edge,
                "source": id_to_key[edge["source_node_id"]],
                "target": id_to_key[edge["target_node_id"]],
            }
            for edge in edges
        ]
        dag = validate_dag(
            [{"key": node["node_key"]} for node in nodes], normalized_edges
        )
        return {
            "workflow": workflow,
            "version": version,
            "nodes": nodes,
            "edges": normalized_edges,
            "dag": dag,
        }

    def create_version(
        self,
        workflow_id: str,
        *,
        version: str,
        nodes: Sequence[Mapping[str, Any]],
        edges: Sequence[Mapping[str, Any]],
        created_by: str = "local_user",
    ) -> dict[str, Any]:
        workflow = self.store.row("workflows", "workflow_id", workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        temporary = self.create(
            name=workflow["name"],
            nodes=nodes,
            edges=edges,
            project_id=workflow.get("project_id"),
            template_key=workflow.get("template_key", ""),
            version=version,
            created_by=created_by,
        )
        new_workflow_id = temporary["workflow"]["workflow_id"]
        new_version_id = temporary["version"]["workflow_version_id"]
        with self.store.transaction() as connection:
            connection.execute(
                "UPDATE workflow_versions SET workflow_id=? WHERE workflow_version_id=?",
                (workflow_id, new_version_id),
            )
            connection.execute("DELETE FROM workflows WHERE workflow_id=?", (new_workflow_id,))
            connection.execute(
                "UPDATE workflows SET active_version_id=?,updated_at_utc=? WHERE workflow_id=?",
                (new_version_id, utc_now(), workflow_id),
            )
        return self.manifest(new_version_id)

    def compare_versions(self, first_id: str, second_id: str) -> dict[str, Any]:
        first = self.manifest(first_id)
        second = self.manifest(second_id)
        first_nodes = {node["node_key"]: node for node in first["nodes"]}
        second_nodes = {node["node_key"]: node for node in second["nodes"]}
        return {
            "first": first_id,
            "second": second_id,
            "added_nodes": sorted(set(second_nodes) - set(first_nodes)),
            "removed_nodes": sorted(set(first_nodes) - set(second_nodes)),
            "changed_nodes": sorted(
                key
                for key in set(first_nodes) & set(second_nodes)
                if canonical_json(first_nodes[key]) != canonical_json(second_nodes[key])
            ),
            "definition_hash_changed": (
                first["version"]["definition_sha256"]
                != second["version"]["definition_sha256"]
            ),
        }

    def list_workflows(
        self, *, project_id: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        filters = {"project_id": project_id} if project_id else None
        return self.store.rows(
            "workflows", filters=filters, order_by="updated_at_utc", limit=limit
        )


__all__ = ["WorkflowRegistry", "validate_dag"]
