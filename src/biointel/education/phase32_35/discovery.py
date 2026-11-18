from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .base import (
    Conflict,
    Missing,
    PermissionDenied,
    PlatformStore,
    ResearchPlatformError,
    canonical_json,
    new_id,
    now_utc,
)
from .compute import ResearchCompute

COMMON_PROHIBITED_ACTIONS = {
    "unrestricted_shell",
    "unauthorized_dataset_access",
    "restricted_data_export",
    "publish_paper",
    "submit_manuscript",
    "claim_clinical_validation",
    "claim_medical_discovery",
    "diagnose",
    "recommend_treatment",
    "approve_ethics",
    "official_ip_claim",
    "alter_final_record",
    "delete_evidence",
    "modify_permissions",
    "paid_compute",
    "external_communication",
}

AGENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "literature_discovery": {
        "name": "Literature Discovery Agent",
        "purpose": "Search and rank registered scientific evidence with citation provenance.",
        "permissions": ["evidence_read", "saved_search_write"],
    },
    "evidence_synthesis": {
        "name": "Evidence Synthesis Agent",
        "purpose": "Compare studies, methods, limitations, conflicts, and certainty.",
        "permissions": ["evidence_read", "claim_graph_write"],
    },
    "hypothesis_generation": {
        "name": "Hypothesis Generation Agent",
        "purpose": "Draft evidence-grounded, falsifiable hypotheses for human review.",
        "permissions": ["evidence_read", "hypothesis_draft", "claim_graph_write"],
    },
    "experimental_design": {
        "name": "Experimental Design Agent",
        "purpose": "Draft controlled experimental plans without granting ethics approval.",
        "permissions": ["hypothesis_read", "experiment_draft"],
    },
    "bioinformatics_workflow": {
        "name": "Bioinformatics Workflow Agent",
        "purpose": "Draft plans using project datasets and approved Research Compute tools.",
        "permissions": [
            "dataset_metadata_read",
            "tool_registry_read",
            "compute_plan_draft",
        ],
    },
    "statistical_analysis": {
        "name": "Statistical Analysis Agent",
        "purpose": "Draft assumption-aware statistical analysis plans.",
        "permissions": ["dataset_metadata_read", "analysis_plan_draft"],
    },
    "systems_biology": {
        "name": "Systems Biology Agent",
        "purpose": "Draft pathway, network, mechanism, and Digital Twin scenario concepts.",
        "permissions": [
            "evidence_read",
            "claim_graph_write",
            "digital_twin_plan_draft",
        ],
    },
    "biomarker_discovery": {
        "name": "Biomarker Discovery Agent",
        "purpose": "Draft leakage-aware candidate-screening plans without clinical claims.",
        "permissions": [
            "dataset_metadata_read",
            "analysis_plan_draft",
            "claim_graph_write",
        ],
    },
    "drug_target_prioritization": {
        "name": "Drug Target Prioritization Agent",
        "purpose": "Organize target evidence without therapeutic recommendations.",
        "permissions": ["evidence_read", "claim_graph_write"],
    },
    "reproducibility": {
        "name": "Reproducibility Agent",
        "purpose": "Verify Research Compute provenance, checksums, and missing information.",
        "permissions": ["compute_result_read", "reproducibility_report_write"],
    },
    "scientific_reviewer": {
        "name": "Scientific Reviewer Agent",
        "purpose": "Flag evidence gaps, inappropriate methods, and overclaims for human review.",
        "permissions": [
            "evidence_read",
            "claim_graph_read",
            "review_draft",
        ],
    },
    "research_integrity": {
        "name": "Research Integrity Agent",
        "purpose": "Flag metadata anomalies without accusing anyone of misconduct.",
        "permissions": [
            "evidence_read",
            "claim_graph_read",
            "integrity_flags_write",
        ],
    },
}

DEFAULT_POLICY = {
    "allowed_agent_permissions": sorted(
        {
            permission
            for definition in AGENT_DEFINITIONS.values()
            for permission in definition["permissions"]
        }
    ),
    "dataset_scope": "bound_research_project",
    "compute_scope": "bound_research_project",
    "digital_twin_project_ids": [],
    "external_communication": False,
    "restricted_export": False,
    "paid_compute": False,
    "clinical_claims": False,
    "ethics_approval": False,
}

HYPOTHESIS_TRANSITIONS = {
    "Draft": {"Evidence Collection", "Human Review", "Rejected", "Archived"},
    "Evidence Collection": {"Human Review", "Revised", "Rejected", "Archived"},
    "Human Review": {"Approved for Testing", "Revised", "Rejected", "Archived"},
    "Approved for Testing": {"Experiment Planned", "Revised", "Rejected", "Archived"},
    "Experiment Planned": {"Testing", "Revised", "Rejected", "Archived"},
    "Testing": {"Supported", "Not Supported", "Inconclusive", "Revised", "Archived"},
    "Supported": {"Revised", "Archived"},
    "Not Supported": {"Revised", "Archived"},
    "Inconclusive": {"Revised", "Archived"},
    "Revised": {"Evidence Collection", "Human Review", "Rejected", "Archived"},
    "Rejected": {"Archived"},
    "Archived": set(),
}

DISCOVERY_STEPS = [
    ("research_question", None, False),
    ("literature_discovery", "literature_discovery", False),
    ("evidence_synthesis", "evidence_synthesis", False),
    ("hypothesis_generation", "hypothesis_generation", False),
    ("human_hypothesis_review", None, True),
    ("experimental_design", "experimental_design", False),
    ("ethics_safety_metadata_review", None, True),
    ("bioinformatics_workflow", "bioinformatics_workflow", False),
    ("human_execution_approval", None, True),
    ("research_compute_job", None, True),
    ("statistical_analysis", "statistical_analysis", False),
    ("systems_or_biomarker_analysis", "systems_biology", False),
    ("reproducibility_review", "reproducibility", False),
    ("scientific_review", "scientific_reviewer", False),
    ("human_interpretation", None, True),
    ("draft_report_publication_asset", None, True),
]

NOVELTY_DISCLAIMER = (
    "Automated novelty screening is incomplete and requires expert review."
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}")
_QUERY_EXPANSIONS = {
    "cancer": ["tumour", "neoplasm"],
    "tumor": ["tumour", "neoplasm"],
    "gene": ["genomic", "genetic"],
    "protein": ["proteomic", "peptide"],
    "microbiome": ["metagenomic", "microbial"],
    "biomarker": ["marker", "feature"],
    "drug": ["compound", "therapeutic"],
}


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text)}


class DiscoveryEcosystem:
    def __init__(self, database: str | Path, storage_root: str | Path):
        self.store = PlatformStore(database)
        self.compute = ResearchCompute(database, storage_root)
        self.seed_agent_registry()

    def _audit(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        object_type: str,
        object_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_integrity_audit VALUES(?,?,?,?,?,?,?,?)""",
                (
                    new_id("discoveryaudit"),
                    tenant_id,
                    actor_id,
                    action,
                    object_type,
                    object_id,
                    canonical_json(details or {}),
                    now_utc(),
                ),
            )

    def seed_agent_registry(self) -> int:
        timestamp = now_utc()
        with self.store.connection() as connection:
            for key, definition in AGENT_DEFINITIONS.items():
                connection.execute(
                    """INSERT INTO education_p35_agent_definitions
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(agent_key) DO UPDATE SET
                    name=excluded.name,version=excluded.version,
                    purpose=excluded.purpose,permissions_json=excluded.permissions_json,
                    prohibited_actions_json=excluded.prohibited_actions_json,
                    output_schema_json=excluded.output_schema_json,
                    validation_status=excluded.validation_status,
                    state='active',updated_at_utc=excluded.updated_at_utc""",
                    (
                        key,
                        definition["name"],
                        "1.0.0",
                        definition["purpose"],
                        canonical_json(definition["permissions"]),
                        canonical_json(sorted(COMMON_PROHIBITED_ACTIONS)),
                        canonical_json(
                            {
                                "required": [
                                    "summary",
                                    "evidence_table",
                                    "scientific_claims",
                                    "uncertainty",
                                    "limitations",
                                    "human_review_required",
                                ]
                            }
                        ),
                        "Deterministic Fixture Validation",
                        "active",
                        timestamp,
                    ),
                )
        return len(AGENT_DEFINITIONS)

    def agent_registry(self) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT * FROM education_p35_agent_definitions
            WHERE state='active' ORDER BY agent_key"""
        )

    def create_workspace(
        self,
        research_project_id: str,
        owner_id: str,
        *,
        title: str = "",
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self.store.one(
            """SELECT * FROM education_p34_research_projects
            WHERE project_id=? AND state='active'""",
            (research_project_id,),
        )
        if not project:
            raise Missing("Active Phase 34 research project not found.")
        existing = self.store.one(
            """SELECT * FROM education_p35_research_workspaces
            WHERE tenant_id=? AND research_project_id=?""",
            (project["tenant_id"], research_project_id),
        )
        if existing:
            return existing
        configured_policy = dict(DEFAULT_POLICY)
        configured_policy.update(policy or {})
        if configured_policy.get("clinical_claims") or configured_policy.get("ethics_approval"):
            raise PermissionDenied("Clinical claims and agent ethics approval cannot be enabled.")
        workspace_id = new_id("discovery")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_research_workspaces
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    workspace_id,
                    project["tenant_id"],
                    research_project_id,
                    owner_id,
                    project["institution_id"],
                    (title or project["title"])[:300],
                    canonical_json(configured_policy),
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            project["tenant_id"],
            owner_id,
            "discovery_workspace_created",
            "workspace",
            workspace_id,
        )
        return self.workspace(workspace_id)

    def workspace(self, workspace_id: str) -> dict[str, Any]:
        row = self.store.one(
            """SELECT * FROM education_p35_research_workspaces
            WHERE workspace_id=? AND state='active'""",
            (workspace_id,),
        )
        if not row:
            raise Missing("Active discovery workspace not found.")
        return row

    def workspaces(self, tenant_id: str) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT * FROM education_p35_research_workspaces
            WHERE tenant_id=? AND state='active' ORDER BY updated_at_utc DESC""",
            (tenant_id,),
        )

    def set_policy(
        self,
        workspace_id: str,
        administrator_id: str,
        *,
        administrator_role: str,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        workspace = self.workspace(workspace_id)
        if administrator_role not in {"institution_administrator", "platform_administrator"}:
            raise PermissionDenied("Administrator role is required for agent policy changes.")
        configured = dict(DEFAULT_POLICY)
        configured.update(policy)
        if configured.get("clinical_claims") or configured.get("ethics_approval"):
            raise PermissionDenied("Clinical claims and agent ethics approval cannot be enabled.")
        if configured.get("external_communication") or configured.get("paid_compute"):
            raise PermissionDenied(
                "External communication and paid compute require an unavailable external approval adapter."
            )
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_research_workspaces
                SET policy_json=?,updated_at_utc=? WHERE workspace_id=?""",
                (canonical_json(configured), now_utc(), workspace_id),
            )
        self._audit(
            workspace["tenant_id"],
            administrator_id,
            "discovery_policy_updated",
            "workspace",
            workspace_id,
        )
        return self.workspace(workspace_id)

    def register_evidence(
        self,
        workspace_id: str,
        actor_id: str,
        *,
        source_type: str,
        title: str,
        citation: str,
        abstract_text: str,
        methodology_text: str = "",
        limitations_text: str = "",
        claims: list[str] | None = None,
        persistent_identifier: str = "",
        publication_date: str = "",
        metadata: dict[str, Any] | None = None,
        retraction_status: str = "not_checked",
    ) -> dict[str, Any]:
        workspace = self.workspace(workspace_id)
        allowed_retraction = {
            "not_checked",
            "not_retracted_as_of_record",
            "retracted",
            "expression_of_concern",
        }
        if retraction_status not in allowed_retraction:
            raise ResearchPlatformError("Unsupported retraction status.")
        if not title.strip() or not citation.strip():
            raise ResearchPlatformError("Evidence title and citation are required.")
        content = {
            "title": title,
            "citation": citation,
            "persistent_identifier": persistent_identifier,
            "abstract_text": abstract_text,
            "methodology_text": methodology_text,
            "limitations_text": limitations_text,
            "claims": claims or [],
            "metadata": metadata or {},
        }
        digest = hashlib.sha256(canonical_json(content).encode()).hexdigest()
        existing = self.store.one(
            """SELECT * FROM education_p35_evidence_sources
            WHERE workspace_id=? AND content_sha256=?""",
            (workspace_id, digest),
        )
        if existing:
            return existing
        source_id = new_id("evidence")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_evidence_sources
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    workspace_id,
                    workspace["tenant_id"],
                    source_type[:80],
                    title[:500],
                    citation[:2000],
                    persistent_identifier[:500],
                    publication_date[:80],
                    abstract_text[:50_000],
                    methodology_text[:50_000],
                    limitations_text[:50_000],
                    canonical_json(claims or []),
                    canonical_json(metadata or {}),
                    retraction_status,
                    "registered_local_record",
                    digest,
                    now_utc(),
                    actor_id,
                ),
            )
        self._audit(
            workspace["tenant_id"],
            actor_id,
            "evidence_registered",
            "evidence",
            source_id,
            {"retraction_status": retraction_status},
        )
        return self.store.one(
            "SELECT * FROM education_p35_evidence_sources WHERE source_id=?",
            (source_id,),
        ) or {}

    def evidence_sources(self, workspace_id: str) -> list[dict[str, Any]]:
        self.workspace(workspace_id)
        return self.store.all(
            """SELECT * FROM education_p35_evidence_sources
            WHERE workspace_id=? ORDER BY created_at_utc DESC""",
            (workspace_id,),
        )

    def search_literature(
        self,
        workspace_id: str,
        actor_id: str,
        *,
        topic: str,
        source_types: list[str] | None = None,
        include_retracted: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        self.workspace(workspace_id)
        query_tokens = _tokens(topic)
        expanded = set(query_tokens)
        for token in query_tokens:
            expanded.update(_QUERY_EXPANSIONS.get(token, []))
        sources = self.store.all(
            """SELECT * FROM education_p35_evidence_sources
            WHERE workspace_id=? ORDER BY created_at_utc""",
            (workspace_id,),
        )
        ranked = []
        seen = set()
        for source in sources:
            if source_types and source["source_type"] not in source_types:
                continue
            if not include_retracted and source["retraction_status"] == "retracted":
                continue
            identity = source["persistent_identifier"] or source["content_sha256"]
            if identity in seen:
                continue
            seen.add(identity)
            haystack = _tokens(
                " ".join(
                    (
                        source["title"],
                        source["abstract_text"],
                        source["methodology_text"],
                        source["citation"],
                    )
                )
            )
            overlap = expanded.intersection(haystack)
            if not overlap:
                continue
            score = len(overlap) / max(1, len(expanded))
            ranked.append(
                {
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "citation": source["citation"],
                    "persistent_identifier": source["persistent_identifier"],
                    "retraction_status": source["retraction_status"],
                    "existence_status": source["existence_status"],
                    "relevance_score": round(score, 6),
                    "matched_terms": sorted(overlap),
                }
            )
        ranked.sort(key=lambda row: (-row["relevance_score"], row["title"]))
        ranked = ranked[: max(1, min(limit, 500))]
        graph_edges = []
        source_claims = {
            row["source_id"]: set(json.loads(row["claims_json"]))
            for row in sources
            if row["source_id"] in {result["source_id"] for result in ranked}
        }
        source_ids = sorted(source_claims)
        for index, left in enumerate(source_ids):
            for right in source_ids[index + 1 :]:
                shared = source_claims[left].intersection(source_claims[right])
                if shared:
                    graph_edges.append(
                        {"source": left, "target": right, "shared_claims": sorted(shared)}
                    )
        search_id = new_id("savedsearch")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_saved_searches
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    search_id,
                    workspace_id,
                    topic[:2000],
                    canonical_json(sorted(expanded)),
                    canonical_json(
                        {
                            "source_types": source_types or [],
                            "include_retracted": include_retracted,
                        }
                    ),
                    canonical_json([row["source_id"] for row in ranked]),
                    canonical_json({"edges": graph_edges}),
                    canonical_json(["BioIntel registered local evidence"]),
                    now_utc(),
                    (
                        "No external database or live retraction service was queried; "
                        "source status is limited to registered metadata."
                    ),
                    actor_id,
                ),
            )
        return {
            "search_id": search_id,
            "topic": topic,
            "expanded_queries": sorted(expanded),
            "results": ranked,
            "citation_graph": {"edges": graph_edges},
            "databases_queried": ["BioIntel registered local evidence"],
            "external_search_performed": False,
            "retraction_check_boundary": (
                "Stored retraction metadata only; no live retraction check was performed."
            ),
        }

    def _validate_bound_resources(
        self,
        workspace: dict[str, Any],
        task_input: dict[str, Any],
    ) -> dict[str, list[str]]:
        validated = {"dataset_ids": [], "compute_run_ids": [], "digital_twin_scenario_ids": []}
        for dataset_id in task_input.get("dataset_ids", []):
            row = self.store.one(
                """SELECT dataset_id FROM education_p34_datasets
                WHERE dataset_id=? AND project_id=? AND tenant_id=?
                AND archive_state='active'""",
                (
                    dataset_id,
                    workspace["research_project_id"],
                    workspace["tenant_id"],
                ),
            )
            if not row:
                raise PermissionDenied("Dataset access is outside the bound research workspace.")
            validated["dataset_ids"].append(dataset_id)
        for run_id in task_input.get("compute_run_ids", []):
            row = self.store.one(
                """SELECT run_id FROM education_p34_runs
                WHERE run_id=? AND project_id=? AND tenant_id=?""",
                (
                    run_id,
                    workspace["research_project_id"],
                    workspace["tenant_id"],
                ),
            )
            if not row:
                raise PermissionDenied("Compute-job access is outside the bound research workspace.")
            validated["compute_run_ids"].append(run_id)
        policy = json.loads(workspace["policy_json"])
        allowed_twin_projects = set(policy.get("digital_twin_project_ids", []))
        for scenario_id in task_input.get("digital_twin_scenario_ids", []):
            row = self.store.one(
                """SELECT s.scenario_id,s.project_id
                FROM education_p33_twin_scenarios s WHERE s.scenario_id=?""",
                (scenario_id,),
            )
            if not row or row["project_id"] not in allowed_twin_projects:
                raise PermissionDenied("Digital Twin scenario permission is not granted.")
            validated["digital_twin_scenario_ids"].append(scenario_id)
        for tool_name in task_input.get("scientific_tools", []):
            tool = self.store.one(
                """SELECT tool_id FROM education_p34_tools
                WHERE tool_name=? AND approved=1 AND state='active'""",
                (tool_name,),
            )
            if not tool:
                raise PermissionDenied("Scientific tool is not approved.")
        return validated

    @staticmethod
    def _unsafe_request(task_input: dict[str, Any]) -> str:
        action = str(task_input.get("requested_action", "")).lower().strip()
        text = " ".join(
            str(task_input.get(key, ""))
            for key in ("requested_action", "question", "objective", "instruction")
        ).lower()
        direct = {
            "diagnose": "Agents cannot issue a diagnosis.",
            "recommend_treatment": "Agents cannot recommend treatment.",
            "approve_ethics": "Agents cannot approve ethics.",
            "publish_paper": "Agents cannot publish or submit manuscripts.",
            "unrestricted_shell": "Agents cannot execute unrestricted shell commands.",
            "external_communication": "Agents cannot communicate externally without approval.",
            "claim_clinical_validation": "Agents cannot claim clinical validation.",
            "claim_medical_discovery": "Agents cannot claim a medical discovery.",
        }
        if action in direct:
            return direct[action]
        prohibited_phrases = {
            "diagnose this patient": "Agents cannot issue a diagnosis.",
            "prescribe": "Agents cannot prescribe or recommend treatment.",
            "clinically validated": "Agents cannot claim clinical validation.",
            "guaranteed discovery": "Agents cannot guarantee a scientific discovery.",
            "scientifically proven": "Agents cannot mark a hypothesis scientifically proven.",
            "approve the ethics": "Agents cannot approve ethics.",
            "submit the manuscript": "Agents cannot submit manuscripts.",
        }
        for phrase, message in prohibited_phrases.items():
            if phrase in text:
                return message
        return ""

    def create_agent_task(
        self,
        workspace_id: str,
        requested_by: str,
        *,
        agent_key: str,
        task_input: dict[str, Any],
        evidence_ids: list[str] | None = None,
        requested_permissions: list[str] | None = None,
        idempotency_key: str,
        phase24_parent_task_id: str = "",
    ) -> dict[str, Any]:
        existing = self.store.one(
            "SELECT * FROM education_p35_agent_tasks WHERE idempotency_key=?",
            (idempotency_key,),
        )
        if existing:
            return existing
        workspace = self.workspace(workspace_id)
        definition = self.store.one(
            """SELECT * FROM education_p35_agent_definitions
            WHERE agent_key=? AND state='active'""",
            (agent_key,),
        )
        if not definition:
            raise Missing("Scientific agent is not active.")
        allowed = set(json.loads(definition["permissions_json"]))
        permissions = requested_permissions or sorted(allowed)
        if set(permissions).difference(allowed):
            raise PermissionDenied("Requested permission is outside this agent definition.")
        policy = json.loads(workspace["policy_json"])
        if set(permissions).difference(policy["allowed_agent_permissions"]):
            raise PermissionDenied("Institution policy blocks an agent permission.")
        validated_resources = self._validate_bound_resources(workspace, task_input)
        evidence_ids = list(dict.fromkeys(evidence_ids or []))
        evidence_rows = []
        for source_id in evidence_ids:
            source = self.store.one(
                """SELECT * FROM education_p35_evidence_sources
                WHERE source_id=? AND workspace_id=? AND tenant_id=?""",
                (source_id, workspace_id, workspace["tenant_id"]),
            )
            if not source:
                raise PermissionDenied("Evidence source is outside the bound workspace.")
            evidence_rows.append(source)
        refusal = self._unsafe_request(task_input)
        task_id = new_id("scientifictask")
        timestamp = now_utc()
        provenance = {
            "runtime": "phase35_extension_of_phase24",
            "phase24_parent_task_id": phase24_parent_task_id or None,
            "workspace_id": workspace_id,
            "tenant_id": workspace["tenant_id"],
            "evidence_sha256": {
                row["source_id"]: row["content_sha256"] for row in evidence_rows
            },
            "validated_resources": validated_resources,
            "provider": "deterministic_local",
            "external_ai_called": False,
        }
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_agent_tasks
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    idempotency_key[:240],
                    workspace_id,
                    workspace["tenant_id"],
                    agent_key,
                    phase24_parent_task_id or None,
                    requested_by,
                    canonical_json(task_input),
                    canonical_json(evidence_ids),
                    canonical_json(permissions),
                    "refused" if refusal else "planned",
                    "not_required",
                    "{}",
                    "{}",
                    "not_started",
                    canonical_json(provenance),
                    refusal,
                    new_id("support"),
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            workspace["tenant_id"],
            requested_by,
            "agent_task_refused" if refusal else "agent_task_created",
            "agent_task",
            task_id,
            {"agent_key": agent_key, "reason": refusal},
        )
        return self.task(task_id)

    def task(self, task_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p35_agent_tasks WHERE task_id=?",
            (task_id,),
        )
        if not row:
            raise Missing("Scientific agent task not found.")
        return row

    def tasks(self, workspace_id: str) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT * FROM education_p35_agent_tasks
            WHERE workspace_id=? ORDER BY created_at_utc DESC""",
            (workspace_id,),
        )

    def _evidence_rows(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        ids = json.loads(task["evidence_ids_json"])
        if not ids:
            return []
        rows = self.store.all(
            f"""SELECT * FROM education_p35_evidence_sources
            WHERE workspace_id=? AND source_id IN ({','.join('?' for _ in ids)})""",
            (task["workspace_id"], *ids),
        )
        by_id = {row["source_id"]: row for row in rows}
        return [by_id[source_id] for source_id in ids if source_id in by_id]

    @staticmethod
    def _evidence_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source_id": row["source_id"],
                "title": row["title"],
                "citation": row["citation"],
                "persistent_identifier": row["persistent_identifier"],
                "methodology": row["methodology_text"],
                "limitations": row["limitations_text"],
                "retraction_status": row["retraction_status"],
                "existence_status": row["existence_status"],
                "claims": json.loads(row["claims_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _certainty(rows: list[dict[str, Any]]) -> str:
        active = [row for row in rows if row["retraction_status"] != "retracted"]
        if not active:
            return "insufficient"
        if len(active) == 1:
            return "very_low"
        methods = {row["methodology_text"].strip().lower() for row in active if row["methodology_text"].strip()}
        return "moderate" if len(methods) > 1 else "low"

    def _base_output(
        self,
        task: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "agent_key": task["agent_key"],
            "summary": "",
            "evidence_table": self._evidence_table(rows),
            "scientific_claims": [],
            "uncertainty": {
                "classification": self._certainty(rows),
                "source_count": len(rows),
                "external_source_check_performed": False,
            },
            "limitations": [
                "Uses registered local evidence only.",
                "Requires human scientific interpretation.",
                "Does not establish clinical validity, novelty, or scientific truth.",
            ],
            "human_review_required": True,
            "clinical_use": False,
            "autonomous_discovery_claimed": False,
        }

    def _build_agent_output(
        self,
        task: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        task_input = json.loads(task["input_json"])
        output = self._base_output(task, rows)
        agent = task["agent_key"]
        source_ids = [row["source_id"] for row in rows if row["retraction_status"] != "retracted"]
        question = str(
            task_input.get("question")
            or task_input.get("topic")
            or task_input.get("objective")
            or "the registered research question"
        ).strip()
        claim = {
            "statement": f"Registered evidence may inform: {question}",
            "direct_evidence_ids": source_ids,
            "indirect_evidence_ids": [],
            "conflicting_evidence_ids": [
                row["source_id"]
                for row in rows
                if row["retraction_status"] in {"retracted", "expression_of_concern"}
            ],
            "unsupported": not bool(source_ids),
            "confidence": min(0.8, 0.2 + 0.15 * len(source_ids)) if source_ids else 0.0,
        }
        if agent == "literature_discovery":
            search = self.search_literature(
                task["workspace_id"],
                task["requested_by"],
                topic=question,
            )
            output.update(
                {
                    "summary": "Ranked local evidence search completed.",
                    "search": search,
                    "query_expansion": search["expanded_queries"],
                    "duplicate_removal": True,
                    "retraction_checks": search["retraction_check_boundary"],
                    "relevant_paper_ranking": search["results"],
                    "scientific_claims": [],
                }
            )
        elif agent == "evidence_synthesis":
            all_claims = [set(json.loads(row["claims_json"])) for row in rows]
            conflicts = []
            for index, left in enumerate(all_claims):
                for right in all_claims[index + 1 :]:
                    if left and right and not left.intersection(right):
                        conflicts.append({"study_pair": [index, index + 1], "status": "possible_conflict"})
            output.update(
                {
                    "summary": "Evidence, methodology, limitations, and possible conflicts compared.",
                    "study_comparison": output["evidence_table"],
                    "methodology_comparison": [
                        {"source_id": row["source_id"], "methodology": row["methodology_text"]}
                        for row in rows
                    ],
                    "limitation_extraction": [
                        {"source_id": row["source_id"], "limitations": row["limitations_text"]}
                        for row in rows
                    ],
                    "conflict_detection": conflicts,
                    "certainty_classification": self._certainty(rows),
                    "claim_to_source_mapping": {
                        row["source_id"]: json.loads(row["claims_json"]) for row in rows
                    },
                    "scientific_claims": [claim],
                }
            )
        elif agent == "hypothesis_generation":
            statement = str(
                task_input.get("hypothesis_statement")
                or f"If the evidence-linked mechanism is active, a measurable change related to {question} will occur."
            )
            output.update(
                {
                    "summary": "Falsifiable hypothesis draft created for human review.",
                    "hypothesis": {
                        "statement": statement,
                        "biological_context": task_input.get("biological_context", question),
                        "assumptions": task_input.get(
                            "assumptions",
                            ["Registered evidence is relevant to the proposed context."],
                        ),
                        "testable_predictions": task_input.get(
                            "predictions",
                            ["The prespecified primary endpoint changes in the predicted direction."],
                        ),
                        "alternative_explanations": task_input.get(
                            "alternative_explanations",
                            ["The observation is driven by a confounder or measurement artifact."],
                        ),
                        "falsification_criteria": task_input.get(
                            "falsification_criteria",
                            ["The prespecified effect is absent under adequate power and valid controls."],
                        ),
                        "unsupported_speculation_risk": "high" if not source_ids else "moderate",
                        "adoption_state": "human_approval_required",
                    },
                    "scientific_claims": [
                        {
                            **claim,
                            "statement": statement,
                        }
                    ],
                }
            )
        elif agent == "experimental_design":
            output.update(
                {
                    "summary": "Experimental design draft created; ethics and safety remain human decisions.",
                    "experiment_plan": {
                        "objective": question,
                        "groups": task_input.get("groups", ["test", "control"]),
                        "controls": task_input.get(
                            "controls",
                            ["negative control", "positive or reference control where justified"],
                        ),
                        "variables": task_input.get(
                            "variables",
                            {"independent": [], "dependent": [], "controlled": []},
                        ),
                        "endpoints": task_input.get("endpoints", ["prespecified primary endpoint"]),
                        "sampling_plan": task_input.get("sampling_plan", {}),
                        "randomization_suggestions": ["Use a reproducible allocation sequence where feasible."],
                        "blinding_suggestions": ["Blind outcome assessment where feasible."],
                        "power_analysis_adapter": {
                            "status": "not_executed",
                            "required_inputs": ["effect size", "variance", "alpha", "power"],
                        },
                        "confounder_checklist": task_input.get(
                            "confounders",
                            ["batch", "age/sex where relevant", "site", "measurement drift"],
                        ),
                        "resource_estimate": task_input.get("resource_estimate", {}),
                        "safety_ethics_flags": task_input.get(
                            "safety_ethics_flags",
                            ["Specialist review required if human, animal, pathogen, or hazardous material is involved."],
                        ),
                        "ethics_approval_granted": False,
                    },
                    "scientific_claims": [],
                }
            )
        elif agent == "bioinformatics_workflow":
            workspace = self.workspace(task["workspace_id"])
            datasets = [
                self.compute.dataset(dataset_id)
                for dataset_id in task_input.get("dataset_ids", [])
            ]
            tools = self.compute.approved_tools()
            compatible = [
                tool
                for tool in tools
                if not datasets
                or set(json.loads(tool["expected_inputs_json"])).issuperset(
                    {
                        file_row["format"]
                        for dataset in datasets
                        for file_row in dataset["files"]
                    }
                )
            ]
            output.update(
                {
                    "summary": "Approved-tool workflow plan drafted; no compute was executed.",
                    "dataset_inspection": [
                        {
                            "dataset_id": dataset["dataset_id"],
                            "format": dataset["format"],
                            "manifest_sha256": dataset["manifest_sha256"],
                            "total_size_bytes": dataset["total_size_bytes"],
                        }
                        for dataset in datasets
                    ],
                    "workflow_selection": task_input.get("workflow_preference", "human selection required"),
                    "parameter_suggestions": task_input.get("parameter_context", {}),
                    "resource_estimate": {
                        "cpu": 1,
                        "memory_mb": 1024,
                        "disk_mb": max(
                            1024,
                            sum(dataset["total_size_bytes"] for dataset in datasets) // 1024**2 * 2,
                        ),
                    },
                    "approved_tool_selection": [
                        {
                            "tool_name": tool["tool_name"],
                            "version": tool["tool_version"],
                            "checksum": tool["checksum"],
                        }
                        for tool in compatible
                    ],
                    "draft_run_plan": {
                        "project_id": workspace["research_project_id"],
                        "dataset_ids": [dataset["dataset_id"] for dataset in datasets],
                        "state": "human_execution_approval_required",
                    },
                    "compute_executed": False,
                    "scientific_claims": [],
                }
            )
        elif agent == "statistical_analysis":
            output.update(
                {
                    "summary": "Assumption-aware statistical analysis plan drafted.",
                    "analysis_plan": {
                        "objective": question,
                        "assumption_checks": [
                            "independence",
                            "distribution and residual behavior",
                            "variance structure",
                            "missingness mechanism",
                        ],
                        "test_selection_support": (
                            "Select the test after design, scale, pairing, and assumptions are confirmed."
                        ),
                        "multiple_testing": "Prespecify families and control FDR or FWER where applicable.",
                        "effect_size_reporting": "Report effect estimates with uncertainty intervals.",
                        "diagnostic_plots": [
                            "residual plot",
                            "Q-Q plot where applicable",
                            "influence diagnostics",
                        ],
                        "significance_claim_generated": False,
                    },
                    "scientific_claims": [],
                }
            )
        elif agent == "systems_biology":
            output.update(
                {
                    "summary": "Evidence-linked systems model and Digital Twin scenario draft created.",
                    "pathway_mapping": task_input.get("pathways", []),
                    "interaction_network": task_input.get("interactions", []),
                    "candidate_mechanism": question,
                    "digital_twin_scenario_draft": {
                        "status": "draft_only",
                        "variables": task_input.get("variables", []),
                        "human_approval_required": True,
                    },
                    "model_limitations": [
                        "Network edges are hypotheses unless directly evidenced.",
                        "Digital Twin output would remain non-clinical.",
                    ],
                    "scientific_claims": [claim],
                }
            )
        elif agent == "biomarker_discovery":
            features = list(dict.fromkeys(task_input.get("features", [])))
            output.update(
                {
                    "summary": "Candidate-screening plan drafted without a clinical biomarker claim.",
                    "feature_screening_workflow": [
                        "separate train/validation/test before screening",
                        "fit preprocessing only on training partitions",
                        "rank with uncertainty and stability",
                    ],
                    "candidate_ranking": [
                        {"feature": feature, "rank": index + 1, "status": "unvalidated_candidate"}
                        for index, feature in enumerate(features)
                    ],
                    "leakage_checks": [
                        "outcome-derived features",
                        "duplicate subjects across splits",
                        "batch/site leakage",
                        "future information leakage",
                    ],
                    "validation_split_required": True,
                    "confounder_checks": task_input.get(
                        "confounders",
                        ["age/sex/site/batch as scientifically applicable"],
                    ),
                    "explainability": "Use held-out permutation or model-specific explanations cautiously.",
                    "clinical_biomarker_claim": False,
                    "scientific_claims": [],
                }
            )
        elif agent == "drug_target_prioritization":
            targets = list(dict.fromkeys(task_input.get("targets", [])))
            output.update(
                {
                    "summary": "Target evidence worksheet drafted; no therapeutic recommendation was made.",
                    "target_evidence": [
                        {
                            "target": target,
                            "disease_association": "requires evidence review",
                            "pathway_role": "requires evidence review",
                            "tractability": "metadata not independently validated",
                            "safety_signals": "specialist review required",
                            "literature_support_ids": source_ids,
                            "uncertainty": "high",
                        }
                        for target in targets
                    ],
                    "therapeutic_recommendation": False,
                    "scientific_claims": [claim] if targets else [],
                }
            )
        elif agent == "reproducibility":
            reports = []
            for run_id in task_input.get("compute_run_ids", []):
                explorer = self.compute.result_explorer(run_id)
                reports.append(
                    {
                        "run_id": run_id,
                        "state": explorer["run"]["state"],
                        "workflow_version": explorer["run"]["workflow_version"],
                        "environment": json.loads(explorer["run"]["environment_json"]),
                        "input_checksum_verified_at_registration": True,
                        "output_checksums": [
                            artifact["sha256"] for artifact in explorer["artifacts"]
                        ],
                        "completed_steps": explorer["quality_metrics"]["completed_steps"],
                        "total_steps": explorer["quality_metrics"]["total_steps"],
                        "missing_information": (
                            []
                            if explorer["run"]["state"] == "completed"
                            else ["Run is not complete."]
                        ),
                    }
                )
            output.update(
                {
                    "summary": "Stored workflow provenance and checksums inspected.",
                    "reproducibility_reports": reports,
                    "rerun_comparison": task_input.get("comparison_run_ids", []),
                    "scientific_claims": [],
                }
            )
        elif agent == "scientific_reviewer":
            proposed = task_input.get("claims", [])
            overclaim_terms = {
                "proven",
                "guaranteed",
                "clinically validated",
                "causes",
                "cures",
            }
            revisions = []
            for statement in proposed:
                matches = sorted(term for term in overclaim_terms if term in statement.lower())
                if matches:
                    revisions.append(
                        {
                            "claim": statement,
                            "issue": "overclaim",
                            "matched_terms": matches,
                        }
                    )
            output.update(
                {
                    "summary": "Scientific review draft completed for human adjudication.",
                    "evidence_consistency": "requires human confirmation",
                    "method_appropriateness": task_input.get(
                        "method_context",
                        "insufficient method detail for definitive assessment",
                    ),
                    "overclaim_detection": revisions,
                    "missing_controls": task_input.get("missing_controls", []),
                    "unsupported_conclusions": [
                        statement for statement in proposed if not source_ids
                    ],
                    "citation_validation": [
                        {
                            "source_id": row["source_id"],
                            "exists_as_registered_record": True,
                            "live_validation_performed": False,
                        }
                        for row in rows
                    ],
                    "revision_requests": revisions,
                    "scientific_claims": [],
                }
            )
        elif agent == "research_integrity":
            image_hashes: dict[str, list[str]] = {}
            for row in rows:
                image_hash = json.loads(row["metadata_json"]).get("image_sha256")
                if image_hash:
                    image_hashes.setdefault(image_hash, []).append(row["source_id"])
            duplicate_flags = [
                {"image_sha256": digest, "source_ids": source_list}
                for digest, source_list in image_hashes.items()
                if len(source_list) > 1
            ]
            output.update(
                {
                    "summary": "Metadata-level research-integrity checks completed.",
                    "duplicate_image_metadata_flags": duplicate_flags,
                    "statistical_inconsistency_flags": task_input.get(
                        "deterministic_statistical_flags",
                        [],
                    ),
                    "retraction_alerts": [
                        {
                            "source_id": row["source_id"],
                            "status": row["retraction_status"],
                        }
                        for row in rows
                        if row["retraction_status"] != "not_retracted_as_of_record"
                    ],
                    "citation_anomalies": [
                        row["source_id"] for row in rows if not row["persistent_identifier"]
                    ],
                    "provenance_gaps": [
                        row["source_id"] for row in rows if not row["methodology_text"]
                    ],
                    "misconduct_accusation": False,
                    "human_investigation_required": bool(duplicate_flags),
                    "scientific_claims": [],
                }
            )
        else:
            raise Missing("Scientific agent implementation is unavailable.")
        return output

    def _upsert_graph_node(
        self,
        workspace_id: str,
        actor_id: str,
        *,
        node_type: str,
        external_id: str,
        label: str,
        metadata: dict[str, Any],
        confidence: float,
        unsupported: bool,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        node_id = new_id("claimnode")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_claim_nodes
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(workspace_id,node_type,external_id) DO UPDATE SET
                label=excluded.label,metadata_json=excluded.metadata_json,
                confidence=excluded.confidence,unsupported=excluded.unsupported,
                provenance_json=excluded.provenance_json""",
                (
                    node_id,
                    workspace_id,
                    node_type,
                    external_id,
                    label[:2000],
                    canonical_json(metadata),
                    max(0.0, min(float(confidence), 1.0)),
                    int(unsupported),
                    canonical_json(provenance),
                    now_utc(),
                    actor_id,
                ),
            )
        return self.store.one(
            """SELECT * FROM education_p35_claim_nodes
            WHERE workspace_id=? AND node_type=? AND external_id=?""",
            (workspace_id, node_type, external_id),
        ) or {}

    def _link_graph_nodes(
        self,
        workspace_id: str,
        actor_id: str,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        confidence: float,
        provenance: dict[str, Any],
    ) -> None:
        with self.store.connection() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO education_p35_claim_edges
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("claimedge"),
                    workspace_id,
                    source_node_id,
                    target_node_id,
                    relation,
                    max(0.0, min(float(confidence), 1.0)),
                    canonical_json(provenance),
                    now_utc(),
                    actor_id,
                ),
            )

    def _record_output_claims(
        self,
        task: dict[str, Any],
        output: dict[str, Any],
    ) -> list[str]:
        node_ids = []
        provenance = json.loads(task["provenance_json"])
        evidence = {
            row["source_id"]: row
            for row in self._evidence_rows(task)
        }
        for index, claim in enumerate(output.get("scientific_claims", []), start=1):
            claim_node = self._upsert_graph_node(
                task["workspace_id"],
                task["requested_by"],
                node_type="claim",
                external_id=f"{task['task_id']}:{index}",
                label=claim["statement"],
                metadata={
                    "direct_evidence_ids": claim.get("direct_evidence_ids", []),
                    "indirect_evidence_ids": claim.get("indirect_evidence_ids", []),
                    "conflicting_evidence_ids": claim.get("conflicting_evidence_ids", []),
                    "agent_key": task["agent_key"],
                },
                confidence=claim.get("confidence", 0),
                unsupported=bool(claim.get("unsupported", True)),
                provenance=provenance,
            )
            node_ids.append(claim_node["node_id"])
            relations = (
                ("direct_evidence_ids", "direct_evidence"),
                ("indirect_evidence_ids", "indirect_evidence"),
                ("conflicting_evidence_ids", "conflicting_evidence"),
            )
            for field, relation in relations:
                for source_id in claim.get(field, []):
                    if source_id not in evidence:
                        continue
                    source = evidence[source_id]
                    source_node = self._upsert_graph_node(
                        task["workspace_id"],
                        task["requested_by"],
                        node_type="source",
                        external_id=source_id,
                        label=source["citation"],
                        metadata={
                            "content_sha256": source["content_sha256"],
                            "retraction_status": source["retraction_status"],
                            "existence_status": source["existence_status"],
                        },
                        confidence=1.0,
                        unsupported=False,
                        provenance={"registered_source_id": source_id},
                    )
                    self._link_graph_nodes(
                        task["workspace_id"],
                        task["requested_by"],
                        source_node["node_id"],
                        claim_node["node_id"],
                        relation,
                        claim.get("confidence", 0),
                        provenance,
                    )
        return node_ids

    def execute_agent_task(self, task_id: str) -> dict[str, Any]:
        task = self.task(task_id)
        if task["state"] == "refused":
            raise PermissionDenied(task["safe_message"])
        if task["state"] != "planned":
            raise Conflict("Scientific agent task is not executable.")
        with self.store.connection() as connection:
            claimed = connection.execute(
                """UPDATE education_p35_agent_tasks
                SET state='running',updated_at_utc=? WHERE task_id=? AND state='planned'""",
                (now_utc(), task_id),
            )
            if claimed.rowcount != 1:
                raise Conflict("Duplicate scientific agent execution was prevented.")
        try:
            task = self.task(task_id)
            rows = self._evidence_rows(task)
            output = self._build_agent_output(task, rows)
            claim_node_ids = self._record_output_claims(task, output)
            output["claim_graph_node_ids"] = claim_node_ids
            output["provenance"] = json.loads(task["provenance_json"])
            output["safety_boundary"] = (
                "Human-supervised research support only; no autonomous discovery, "
                "clinical validity, diagnosis, treatment, or guaranteed correctness."
            )
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p35_agent_tasks
                    SET state='completed',approval_state='pending',
                    output_json=?,uncertainty_json=?,novelty_status=?,
                    safe_message='Draft completed; human scientific review is required.',
                    updated_at_utc=? WHERE task_id=?""",
                    (
                        canonical_json(output),
                        canonical_json(output["uncertainty"]),
                        "not_applicable"
                        if task["agent_key"] != "hypothesis_generation"
                        else "expert_review_required",
                        now_utc(),
                        task_id,
                    ),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO education_p35_agent_approvals
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        new_id("agentapproval"),
                        task_id,
                        "task_output_review",
                        task["requested_by"],
                        "pending",
                        None,
                        "",
                        now_utc(),
                        None,
                    ),
                )
            self._audit(
                task["tenant_id"],
                task["requested_by"],
                "agent_task_completed",
                "agent_task",
                task_id,
                {"claim_nodes": claim_node_ids},
            )
        except Exception as exc:
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p35_agent_tasks
                    SET state='failed',safe_message=?,updated_at_utc=? WHERE task_id=?""",
                    (
                        f"Agent draft failed safely ({type(exc).__name__}).",
                        now_utc(),
                        task_id,
                    ),
                )
            raise
        return self.task(task_id)

    def decide_approval(
        self,
        task_id: str,
        reviewer_id: str,
        *,
        reviewer_role: str,
        operation: str,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
        task = self.task(task_id)
        if reviewer_role not in {
            "scientific_reviewer",
            "research_lead",
            "institution_administrator",
            "platform_administrator",
        }:
            raise PermissionDenied("Authorized human reviewer role is required.")
        approval = self.store.one(
            """SELECT * FROM education_p35_agent_approvals
            WHERE task_id=? AND operation=?""",
            (task_id, operation),
        )
        if not approval:
            raise Missing("Agent approval checkpoint not found.")
        if approval["decision"] != "pending":
            raise Conflict("Agent approval checkpoint is already decided.")
        if approval["requested_by"] == reviewer_id:
            raise PermissionDenied("A second authorized human must decide this checkpoint.")
        if decision not in {"approved", "rejected"}:
            raise ResearchPlatformError("Approval decision must be approved or rejected.")
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_agent_approvals
                SET decision=?,decided_by=?,decision_note=?,decided_at_utc=?
                WHERE approval_id=?""",
                (decision, reviewer_id, note[:10_000], now_utc(), approval["approval_id"]),
            )
            if operation == "task_output_review":
                connection.execute(
                    """UPDATE education_p35_agent_tasks
                    SET approval_state=?,state=?,updated_at_utc=? WHERE task_id=?""",
                    (
                        decision,
                        "completed" if decision == "approved" else "revision_required",
                        now_utc(),
                        task_id,
                    ),
                )
        self._audit(
            task["tenant_id"],
            reviewer_id,
            "agent_approval_decided",
            "agent_task",
            task_id,
            {"operation": operation, "decision": decision},
        )
        return self.store.one(
            "SELECT * FROM education_p35_agent_approvals WHERE approval_id=?",
            (approval["approval_id"],),
        ) or {}

    def request_consequential_action(
        self,
        task_id: str,
        actor_id: str,
        *,
        operation: str,
        target_id: str,
    ) -> dict[str, Any]:
        task = self.task(task_id)
        if task["requested_by"] != actor_id:
            raise PermissionDenied("Only the task owner may request a consequential action.")
        if task["state"] != "completed" or task["approval_state"] != "approved":
            raise PermissionDenied("The agent draft must first pass human scientific review.")
        allowed = {"compute_execute", "publish_draft", "restricted_export"}
        if operation not in allowed:
            raise PermissionDenied("This consequential operation is prohibited or unavailable.")
        if operation == "compute_execute":
            if task["agent_key"] != "bioinformatics_workflow":
                raise PermissionDenied("Only a reviewed workflow-agent task may request compute.")
            workspace = self.workspace(task["workspace_id"])
            run = self.store.one(
                """SELECT * FROM education_p34_runs
                WHERE run_id=? AND project_id=? AND tenant_id=?""",
                (target_id, workspace["research_project_id"], workspace["tenant_id"]),
            )
            if not run:
                raise PermissionDenied("Compute run is outside the bound research workspace.")
        operation_key = f"{operation}:{target_id}"
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_agent_approvals
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("agentapproval"),
                    task_id,
                    operation_key,
                    actor_id,
                    "pending",
                    None,
                    "",
                    now_utc(),
                    None,
                ),
            )
        return self.store.one(
            """SELECT * FROM education_p35_agent_approvals
            WHERE task_id=? AND operation=?""",
            (task_id, operation_key),
        ) or {}

    def execute_approved_compute(
        self,
        task_id: str,
        run_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        task = self.task(task_id)
        approval = self.store.one(
            """SELECT * FROM education_p35_agent_approvals
            WHERE task_id=? AND operation=? AND decision='approved'""",
            (task_id, f"compute_execute:{run_id}"),
        )
        if not approval:
            raise PermissionDenied("Human compute-execution approval is required.")
        result = self.compute.execute_run(run_id)
        self._audit(
            task["tenant_id"],
            actor_id,
            "approved_compute_executed",
            "compute_run",
            run_id,
            {"task_id": task_id, "approval_id": approval["approval_id"]},
        )
        return result

    def claim_evidence_graph(self, workspace_id: str) -> dict[str, Any]:
        self.workspace(workspace_id)
        nodes = self.store.all(
            """SELECT * FROM education_p35_claim_nodes
            WHERE workspace_id=? ORDER BY created_at_utc,node_id""",
            (workspace_id,),
        )
        edges = self.store.all(
            """SELECT * FROM education_p35_claim_edges
            WHERE workspace_id=? ORDER BY created_at_utc,edge_id""",
            (workspace_id,),
        )
        return {
            "schema": "biointel.phase35.claim-evidence-graph.v1",
            "workspace_id": workspace_id,
            "nodes": nodes,
            "edges": edges,
            "claim_count": sum(row["node_type"] == "claim" for row in nodes),
            "unsupported_claim_count": sum(
                row["node_type"] == "claim" and bool(row["unsupported"]) for row in nodes
            ),
        }

    def record_novelty_search(
        self,
        workspace_id: str,
        actor_id: str,
        *,
        queries: list[str],
        related_hypothesis_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not queries:
            raise ResearchPlatformError("At least one novelty-screening query is required.")
        workspace = self.workspace(workspace_id)
        search_results = [
            self.search_literature(
                workspace_id,
                actor_id,
                topic=query,
                include_retracted=True,
            )
            for query in queries
        ]
        results = [
            {
                "query": result["topic"],
                "source_ids": [row["source_id"] for row in result["results"]],
                "external_search_performed": False,
            }
            for result in search_results
        ]
        result_source_ids = {
            source_id for result in results for source_id in result["source_ids"]
        }
        similar_methods = [
            {
                "source_id": row["source_id"],
                "methodology": row["methodology_text"],
            }
            for row in self.evidence_sources(workspace_id)
            if row["source_id"] in result_source_ids and row["methodology_text"]
        ]
        novelty_id = new_id("novelty")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_novelty_searches
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    novelty_id,
                    workspace_id,
                    canonical_json(queries),
                    now_utc(),
                    canonical_json(["BioIntel registered local evidence"]),
                    canonical_json(results),
                    canonical_json(related_hypothesis_ids or []),
                    canonical_json(similar_methods),
                    NOVELTY_DISCLAIMER,
                    0,
                    0,
                    actor_id,
                ),
            )
        self._audit(
            workspace["tenant_id"],
            actor_id,
            "novelty_screen_recorded",
            "novelty_search",
            novelty_id,
            {"external_search_performed": False},
        )
        return self.store.one(
            """SELECT * FROM education_p35_novelty_searches
            WHERE novelty_search_id=?""",
            (novelty_id,),
        ) or {}

    def create_hypothesis_from_task(
        self,
        task_id: str,
        actor_id: str,
        *,
        novelty_search_id: str | None = None,
    ) -> dict[str, Any]:
        task = self.task(task_id)
        if task["agent_key"] != "hypothesis_generation" or task["state"] != "completed":
            raise Conflict("A completed Hypothesis Generation Agent task is required.")
        if task["requested_by"] != actor_id:
            raise PermissionDenied("Only the task owner may register its hypothesis draft.")
        output = json.loads(task["output_json"])
        draft = output["hypothesis"]
        claim = output["scientific_claims"][0]
        if novelty_search_id:
            novelty = self.store.one(
                """SELECT novelty_search_id FROM education_p35_novelty_searches
                WHERE novelty_search_id=? AND workspace_id=?""",
                (novelty_search_id, task["workspace_id"]),
            )
            if not novelty:
                raise Missing("Novelty screening record not found in this workspace.")
        hypothesis_id = new_id("hypothesis")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_hypotheses
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    hypothesis_id,
                    task["workspace_id"],
                    task["tenant_id"],
                    draft["statement"][:10_000],
                    draft["biological_context"][:10_000],
                    canonical_json(claim["direct_evidence_ids"]),
                    canonical_json(claim["conflicting_evidence_ids"]),
                    canonical_json(draft["assumptions"]),
                    canonical_json(draft["testable_predictions"]),
                    canonical_json(draft["falsification_criteria"]),
                    novelty_search_id,
                    claim["confidence"],
                    canonical_json(output["uncertainty"]),
                    actor_id,
                    task_id,
                    None,
                    "pending",
                    "Human Review",
                    "[]",
                    "[]",
                    "[]",
                    "[]",
                    "{}",
                    "Not evaluated; never scientifically proven by this system.",
                    timestamp,
                    timestamp,
                ),
            )
        self._upsert_graph_node(
            task["workspace_id"],
            actor_id,
            node_type="hypothesis",
            external_id=hypothesis_id,
            label=draft["statement"],
            metadata={"state": "Human Review", "agent_task_id": task_id},
            confidence=claim["confidence"],
            unsupported=claim["unsupported"],
            provenance={"task_id": task_id},
        )
        self._audit(
            task["tenant_id"],
            actor_id,
            "hypothesis_registered_for_human_review",
            "hypothesis",
            hypothesis_id,
        )
        return self.hypothesis(hypothesis_id)

    def hypothesis(self, hypothesis_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p35_hypotheses WHERE hypothesis_id=?",
            (hypothesis_id,),
        )
        if not row:
            raise Missing("Hypothesis not found.")
        return row

    def hypotheses(self, workspace_id: str) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT * FROM education_p35_hypotheses
            WHERE workspace_id=? ORDER BY created_at_utc DESC""",
            (workspace_id,),
        )

    def link_hypothesis_resources(
        self,
        hypothesis_id: str,
        actor_id: str,
        *,
        dataset_ids: list[str] | None = None,
        workflow_ids: list[str] | None = None,
        digital_twin_scenario_ids: list[str] | None = None,
        results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hypothesis = self.hypothesis(hypothesis_id)
        workspace = self.workspace(hypothesis["workspace_id"])
        validated = self._validate_bound_resources(
            workspace,
            {
                "dataset_ids": dataset_ids or [],
                "digital_twin_scenario_ids": digital_twin_scenario_ids or [],
            },
        )
        validated_workflows = []
        for workflow_id in workflow_ids or []:
            row = self.store.one(
                """SELECT workflow_id FROM education_p34_workflows
                WHERE workflow_id=? AND project_id=?""",
                (workflow_id, workspace["research_project_id"]),
            )
            if not row:
                raise PermissionDenied("Workflow is outside the bound research workspace.")
            validated_workflows.append(workflow_id)
        linked_datasets = sorted(
            set(json.loads(hypothesis["linked_datasets_json"]))
            | set(validated["dataset_ids"])
        )
        linked_workflows = sorted(
            set(json.loads(hypothesis["linked_workflows_json"]))
            | set(validated_workflows)
        )
        linked_twin = sorted(
            set(json.loads(hypothesis["linked_twin_scenarios_json"]))
            | set(validated["digital_twin_scenario_ids"])
        )
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_hypotheses
                SET linked_datasets_json=?,linked_workflows_json=?,
                linked_twin_scenarios_json=?,results_json=?,updated_at_utc=?
                WHERE hypothesis_id=?""",
                (
                    canonical_json(linked_datasets),
                    canonical_json(linked_workflows),
                    canonical_json(linked_twin),
                    canonical_json(results or json.loads(hypothesis["results_json"])),
                    now_utc(),
                    hypothesis_id,
                ),
            )
        self._audit(
            hypothesis["tenant_id"],
            actor_id,
            "hypothesis_resources_linked",
            "hypothesis",
            hypothesis_id,
        )
        return self.hypothesis(hypothesis_id)

    def transition_hypothesis(
        self,
        hypothesis_id: str,
        actor_id: str,
        *,
        actor_role: str,
        new_state: str,
        outcome: str = "",
        results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hypothesis = self.hypothesis(hypothesis_id)
        if new_state.lower() in {"proven", "scientifically proven"}:
            raise PermissionDenied("Hypotheses can never be marked scientifically proven.")
        if new_state not in HYPOTHESIS_TRANSITIONS.get(hypothesis["state"], set()):
            raise Conflict(
                f"Invalid hypothesis transition: {hypothesis['state']} -> {new_state}."
            )
        reviewer_id = hypothesis["reviewer_id"]
        approval_status = hypothesis["approval_status"]
        if new_state == "Approved for Testing":
            if actor_role not in {
                "scientific_reviewer",
                "research_lead",
                "institution_administrator",
            }:
                raise PermissionDenied("Human scientific reviewer approval is required.")
            if actor_id == hypothesis["creator_id"]:
                raise PermissionDenied("A second human must approve a hypothesis for testing.")
            reviewer_id = actor_id
            approval_status = "approved_for_testing"
        if new_state in {"Supported", "Not Supported", "Inconclusive"}:
            if actor_role not in {"scientific_reviewer", "research_lead"}:
                raise PermissionDenied("Human scientific interpretation is required.")
            outcome = (
                outcome
                or f"{new_state} by current recorded evidence; not scientifically proven."
            )
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_hypotheses
                SET state=?,reviewer_id=?,approval_status=?,results_json=?,
                outcome=?,updated_at_utc=? WHERE hypothesis_id=?""",
                (
                    new_state,
                    reviewer_id,
                    approval_status,
                    canonical_json(results or json.loads(hypothesis["results_json"])),
                    outcome[:10_000],
                    now_utc(),
                    hypothesis_id,
                ),
            )
        self._audit(
            hypothesis["tenant_id"],
            actor_id,
            "hypothesis_state_changed",
            "hypothesis",
            hypothesis_id,
            {"from": hypothesis["state"], "to": new_state},
        )
        return self.hypothesis(hypothesis_id)

    def create_experiment_plan(
        self,
        hypothesis_id: str,
        actor_id: str,
        *,
        objective: str,
        design: dict[str, Any],
        variables: dict[str, Any],
        controls: list[Any],
        samples: dict[str, Any],
        replicates: dict[str, Any],
        randomization: dict[str, Any],
        blinding: dict[str, Any],
        inclusion_criteria: list[str],
        exclusion_criteria: list[str],
        endpoints: list[dict[str, Any]],
        analysis_plan: dict[str, Any],
        resources: dict[str, Any],
        timeline: dict[str, Any],
        risks: list[dict[str, Any]],
        ethics_status: str = "pending_specialist_review",
        ethics_record_asset_id: str | None = None,
        safety_status: str = "pending_specialist_review",
        protocol_version: str = "1.0.0",
    ) -> dict[str, Any]:
        hypothesis = self.hypothesis(hypothesis_id)
        if hypothesis["state"] != "Approved for Testing":
            raise PermissionDenied("Hypothesis must be human-approved for testing first.")
        if not controls or not endpoints:
            raise ResearchPlatformError("Experiment plan requires controls and endpoints.")
        if ethics_status.lower() in {"approved", "biointel_approved"}:
            raise PermissionDenied("BioIntel cannot approve ethics.")
        if ethics_record_asset_id:
            workspace = self.workspace(hypothesis["workspace_id"])
            record = self.store.one(
                """SELECT asset_id FROM education_p34_project_assets
                WHERE asset_id=? AND project_id=? AND asset_type='approval'
                AND archive_state='active'""",
                (ethics_record_asset_id, workspace["research_project_id"]),
            )
            if not record:
                raise Missing("Linked ethics record asset was not found.")
            ethics_status = "external_record_linked_not_verified_by_biointel"
        specialist_flags = []
        design_text = canonical_json(design).lower()
        risk_text = canonical_json(risks).lower()
        for topic in ("human", "animal", "pathogen", "hazard", "clinical", "patient"):
            if topic in design_text or topic in risk_text:
                specialist_flags.append(f"{topic}_specialist_review_required")
        experiment_id = new_id("experiment")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_experiments
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    experiment_id,
                    hypothesis["workspace_id"],
                    hypothesis_id,
                    objective[:10_000],
                    canonical_json(design),
                    canonical_json(variables),
                    canonical_json(controls),
                    canonical_json(samples),
                    canonical_json(replicates),
                    canonical_json(randomization),
                    canonical_json(blinding),
                    canonical_json(inclusion_criteria),
                    canonical_json(exclusion_criteria),
                    canonical_json(endpoints),
                    canonical_json(analysis_plan),
                    canonical_json(resources),
                    canonical_json(timeline),
                    canonical_json(risks),
                    ethics_status,
                    ethics_record_asset_id,
                    safety_status,
                    canonical_json(specialist_flags),
                    protocol_version[:80],
                    "pending",
                    "human_review",
                    timestamp,
                    actor_id,
                    timestamp,
                ),
            )
            linked = json.loads(hypothesis["linked_experiments_json"])
            linked.append(experiment_id)
            connection.execute(
                """UPDATE education_p35_hypotheses
                SET state='Experiment Planned',linked_experiments_json=?,
                updated_at_utc=? WHERE hypothesis_id=?""",
                (canonical_json(linked), timestamp, hypothesis_id),
            )
        self._audit(
            hypothesis["tenant_id"],
            actor_id,
            "experiment_plan_created",
            "experiment",
            experiment_id,
            {"specialist_review": specialist_flags, "ethics_status": ethics_status},
        )
        return self.experiment(experiment_id)

    def experiment(self, experiment_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p35_experiments WHERE experiment_id=?",
            (experiment_id,),
        )
        if not row:
            raise Missing("Experiment plan not found.")
        return row

    def review_experiment(
        self,
        experiment_id: str,
        reviewer_id: str,
        *,
        reviewer_role: str,
        decision: str,
    ) -> dict[str, Any]:
        experiment = self.experiment(experiment_id)
        if reviewer_role not in {
            "scientific_reviewer",
            "research_lead",
            "institution_administrator",
        }:
            raise PermissionDenied("Authorized human experiment reviewer is required.")
        if reviewer_id == experiment["created_by"]:
            raise PermissionDenied("A second human must review the experiment plan.")
        if decision not in {"approved", "rejected"}:
            raise ResearchPlatformError("Experiment decision must be approved or rejected.")
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_experiments
                SET approval_status=?,state=?,updated_at_utc=? WHERE experiment_id=?""",
                (
                    decision,
                    "approved" if decision == "approved" else "rejected",
                    now_utc(),
                    experiment_id,
                ),
            )
        return self.experiment(experiment_id)

    def create_discovery_workflow(
        self,
        workspace_id: str,
        actor_id: str,
        *,
        research_question: str,
    ) -> dict[str, Any]:
        self.workspace(workspace_id)
        if not research_question.strip():
            raise ResearchPlatformError("Research question is required.")
        workflow_id = new_id("discoveryworkflow")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_discovery_workflows
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    workflow_id,
                    workspace_id,
                    research_question[:10_000],
                    "active",
                    1,
                    timestamp,
                    actor_id,
                    timestamp,
                ),
            )
            for sequence, (step_key, agent_key, human_checkpoint) in enumerate(
                DISCOVERY_STEPS,
                start=1,
            ):
                connection.execute(
                    """INSERT INTO education_p35_discovery_steps
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        new_id("discoverystep"),
                        workflow_id,
                        sequence,
                        step_key,
                        agent_key,
                        int(human_checkpoint),
                        "ready" if sequence == 1 else "pending",
                        None,
                        "",
                        "{}",
                        None,
                    ),
                )
        return self.discovery_workflow(workflow_id)

    def discovery_workflow(self, discovery_workflow_id: str) -> dict[str, Any]:
        row = self.store.one(
            """SELECT * FROM education_p35_discovery_workflows
            WHERE discovery_workflow_id=?""",
            (discovery_workflow_id,),
        )
        if not row:
            raise Missing("Discovery workflow not found.")
        row["steps"] = self.store.all(
            """SELECT * FROM education_p35_discovery_steps
            WHERE discovery_workflow_id=? ORDER BY sequence""",
            (discovery_workflow_id,),
        )
        return row

    def complete_discovery_step(
        self,
        discovery_workflow_id: str,
        actor_id: str,
        *,
        artifact_reference: str,
        task_id: str | None = None,
        human_approved: bool = False,
    ) -> dict[str, Any]:
        workflow = self.discovery_workflow(discovery_workflow_id)
        if workflow["state"] not in {"active", "awaiting_human"}:
            raise Conflict("Discovery workflow is not active.")
        current = next(
            (step for step in workflow["steps"] if step["sequence"] == workflow["current_step"]),
            None,
        )
        if not current or current["state"] not in {"ready", "awaiting_human"}:
            raise Conflict("Current discovery step is not ready.")
        if current["human_checkpoint"] and not human_approved:
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p35_discovery_steps
                    SET state='awaiting_human' WHERE discovery_step_id=?""",
                    (current["discovery_step_id"],),
                )
                connection.execute(
                    """UPDATE education_p35_discovery_workflows
                    SET state='awaiting_human',updated_at_utc=?
                    WHERE discovery_workflow_id=?""",
                    (now_utc(), discovery_workflow_id),
                )
            return self.discovery_workflow(discovery_workflow_id)
        if current["agent_key"]:
            task = self.task(task_id or "")
            if (
                task["workspace_id"] != workflow["workspace_id"]
                or task["agent_key"] != current["agent_key"]
                or task["state"] != "completed"
                or task["approval_state"] != "approved"
            ):
                raise PermissionDenied(
                    "A matching, completed, human-reviewed agent task is required."
                )
        provenance = {
            "actor_id": actor_id,
            "task_id": task_id,
            "human_approved": human_approved,
            "completed_at_utc": now_utc(),
        }
        next_sequence = current["sequence"] + 1
        completed = next_sequence > len(workflow["steps"])
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p35_discovery_steps
                SET state='completed',task_id=?,artifact_reference=?,
                provenance_json=?,completed_at_utc=? WHERE discovery_step_id=?""",
                (
                    task_id,
                    artifact_reference[:2000],
                    canonical_json(provenance),
                    now_utc(),
                    current["discovery_step_id"],
                ),
            )
            if not completed:
                next_step = workflow["steps"][next_sequence - 1]
                connection.execute(
                    """UPDATE education_p35_discovery_steps SET state=?
                    WHERE discovery_step_id=?""",
                    (
                        "awaiting_human" if next_step["human_checkpoint"] else "ready",
                        next_step["discovery_step_id"],
                    ),
                )
            connection.execute(
                """UPDATE education_p35_discovery_workflows
                SET state=?,current_step=?,updated_at_utc=?
                WHERE discovery_workflow_id=?""",
                (
                    "completed"
                    if completed
                    else "awaiting_human"
                    if workflow["steps"][next_sequence - 1]["human_checkpoint"]
                    else "active",
                    current["sequence"] if completed else next_sequence,
                    now_utc(),
                    discovery_workflow_id,
                ),
            )
        return self.discovery_workflow(discovery_workflow_id)

    def run_evaluation_suite(
        self,
        workspace_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        self.workspace(workspace_id)
        tasks = self.tasks(workspace_id)
        completed = [task for task in tasks if task["state"] == "completed"]
        refused = [task for task in tasks if task["state"] == "refused"]
        outputs = [
            (task, json.loads(task["output_json"]))
            for task in completed
            if task["output_json"] != "{}"
        ]
        evidence = self.store.all(
            """SELECT * FROM education_p35_evidence_sources WHERE workspace_id=?""",
            (workspace_id,),
        )
        evidence_ids = {row["source_id"] for row in evidence}
        cited_ids = [
            source_id
            for _task, output in outputs
            for claim in output.get("scientific_claims", [])
            for source_id in (
                claim.get("direct_evidence_ids", [])
                + claim.get("indirect_evidence_ids", [])
                + claim.get("conflicting_evidence_ids", [])
            )
        ]
        claims = [
            claim
            for _task, output in outputs
            for claim in output.get("scientific_claims", [])
        ]
        experiments = self.store.all(
            """SELECT * FROM education_p35_experiments WHERE workspace_id=?""",
            (workspace_id,),
        )
        hypotheses = self.hypotheses(workspace_id)

        def metric(name: str, passed: bool, measured: Any) -> dict[str, Any]:
            return {"name": name, "passed": bool(passed), "measured": measured}

        metrics = [
            metric(
                "citation_precision",
                bool(cited_ids) and all(source_id in evidence_ids for source_id in cited_ids),
                {"cited": len(cited_ids), "registered": len(evidence_ids)},
            ),
            metric(
                "source_existence",
                bool(evidence)
                and all(row["existence_status"] == "registered_local_record" for row in evidence),
                {"registered_local_records": len(evidence)},
            ),
            metric(
                "evidence_completeness",
                bool(outputs)
                and all("evidence_table" in output and "limitations" in output for _, output in outputs),
                {"completed_outputs": len(outputs)},
            ),
            metric(
                "unsupported_claim_rate",
                bool(claims)
                and sum(bool(claim.get("unsupported")) for claim in claims) / len(claims) <= 0.25,
                {
                    "unsupported": sum(bool(claim.get("unsupported")) for claim in claims),
                    "claims": len(claims),
                },
            ),
            metric(
                "hypothesis_testability",
                bool(hypotheses)
                and all(
                    json.loads(row["predicted_observations_json"])
                    and json.loads(row["falsification_criteria_json"])
                    for row in hypotheses
                ),
                {"hypotheses": len(hypotheses)},
            ),
            metric(
                "methodology_quality",
                bool(experiments)
                and all(
                    json.loads(row["controls_json"])
                    and json.loads(row["endpoints_json"])
                    for row in experiments
                ),
                {"experiment_plans": len(experiments)},
            ),
            metric(
                "confounder_identification",
                any(
                    task["agent_key"] == "experimental_design"
                    and output.get("experiment_plan", {}).get("confounder_checklist")
                    for task, output in outputs
                ),
                {"experimental_design_outputs": sum(task["agent_key"] == "experimental_design" for task, _ in outputs)},
            ),
            metric(
                "statistical_appropriateness",
                any(
                    task["agent_key"] == "statistical_analysis"
                    and output.get("analysis_plan", {}).get("assumption_checks")
                    and output.get("analysis_plan", {}).get("effect_size_reporting")
                    for task, output in outputs
                ),
                {"statistical_outputs": sum(task["agent_key"] == "statistical_analysis" for task, _ in outputs)},
            ),
            metric(
                "tool_selection_correctness",
                any(
                    task["agent_key"] == "bioinformatics_workflow"
                    and output.get("approved_tool_selection") is not None
                    and output.get("compute_executed") is False
                    for task, output in outputs
                ),
                {"workflow_outputs": sum(task["agent_key"] == "bioinformatics_workflow" for task, _ in outputs)},
            ),
            metric(
                "data_permission_compliance",
                all(task["tenant_id"] == self.workspace(workspace_id)["tenant_id"] for task in tasks),
                {"tasks_checked": len(tasks)},
            ),
            metric(
                "tenant_isolation",
                all(task["workspace_id"] == workspace_id for task in tasks),
                {"cross_workspace_tasks": sum(task["workspace_id"] != workspace_id for task in tasks)},
            ),
            metric(
                "reproducibility",
                any(
                    task["agent_key"] == "reproducibility"
                    and output.get("reproducibility_reports")
                    for task, output in outputs
                ),
                {"reproducibility_outputs": sum(task["agent_key"] == "reproducibility" for task, _ in outputs)},
            ),
            metric(
                "unsafe_request_refusal",
                bool(refused),
                {"refused_tasks": len(refused)},
            ),
            metric(
                "overclaim_detection",
                any(
                    task["agent_key"] == "scientific_reviewer"
                    and output.get("overclaim_detection")
                    for task, output in outputs
                ),
                {"reviewer_outputs": sum(task["agent_key"] == "scientific_reviewer" for task, _ in outputs)},
            ),
            metric(
                "research_integrity_behavior",
                any(
                    task["agent_key"] == "research_integrity"
                    and output.get("misconduct_accusation") is False
                    for task, output in outputs
                ),
                {"integrity_outputs": sum(task["agent_key"] == "research_integrity" for task, _ in outputs)},
            ),
        ]
        passed = sum(row["passed"] for row in metrics)
        fixture_manifest = {
            "workspace_id": workspace_id,
            "task_ids": sorted(task["task_id"] for task in tasks),
            "evidence_sha256": sorted(row["content_sha256"] for row in evidence),
            "hypothesis_ids": sorted(row["hypothesis_id"] for row in hypotheses),
            "experiment_ids": sorted(row["experiment_id"] for row in experiments),
        }
        evaluation_id = new_id("agentevaluation")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p35_agent_evaluations
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation_id,
                    workspace_id,
                    "1.0.0",
                    hashlib.sha256(canonical_json(fixture_manifest).encode()).hexdigest(),
                    canonical_json(metrics),
                    passed,
                    len(metrics) - passed,
                    now_utc(),
                    actor_id,
                ),
            )
        return {
            "evaluation_id": evaluation_id,
            "suite_version": "1.0.0",
            "metrics": metrics,
            "passed_count": passed,
            "failed_count": len(metrics) - passed,
            "fabricated_results": False,
            "external_services_used": False,
        }
