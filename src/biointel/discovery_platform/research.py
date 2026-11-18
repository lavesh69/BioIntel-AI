from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from .constants import (
    CANDIDATE_STATES,
    CANDIDATE_TYPES,
    EVIDENCE_TYPES,
    HYPOTHESIS_STATES,
    MODEL_STATES,
    RECOMMENDATION_STATES,
)
from .models import (
    PlatformConflictError,
    PlatformValidationError,
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

PMID_RE = re.compile(r"^[1-9][0-9]{0,8}$")
DOI_RE = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)

RELATIONSHIPS = frozenset(
    {
        "Gene-Variant", "Gene-Transcript", "Gene-Protein", "Gene-Pathway",
        "Protein-Drug", "Protein-Structure", "Variant-Phenotype", "Variant-Disease",
        "Cell type-Disease", "Cell type-Pathway", "Metabolite-Pathway",
        "Microbe-Function", "Target-Evidence", "Candidate-Evidence",
        "Candidate-Recommendation",
        "Candidate-Experiment", "Candidate-Validation", "Hypothesis-Evidence",
        "Dataset-Run", "Run-Result", "Recommendation-Validation Result",
    }
)


class ResearchService:
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

    def _ensure_origin(self, project: Mapping[str, Any], origin: str) -> None:
        validate_origin(origin)
        synthetic = bool(project["is_synthetic"])
        if synthetic != (origin == "synthetic_demo_output"):
            raise PlatformConflictError("Entity origin does not match the project boundary")

    def _upsert_graph_node(
        self,
        project_id: str,
        entity_type: str,
        entity_id: str,
        label: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> str:
        with self.store.connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT node_id FROM graph_nodes WHERE project_id=? AND entity_type=? AND entity_id=?",
                (project_id, entity_type, entity_id),
            ).fetchone()
        if row:
            self.store.update(
                "graph_nodes", "node_id", str(row[0]),
                {"label": label, "attributes_json": dict(attributes or {})},
            )
            return str(row[0])
        node_id = new_id("NODE")
        self.store.insert(
            "graph_nodes",
            {
                "node_id": node_id, "project_id": project_id,
                "entity_type": entity_type, "entity_id": entity_id,
                "label": require_text(label, "graph label", 500),
                "attributes_json": dict(attributes or {}),
                "provenance_json": dict(provenance or {}),
                "created_at_utc": utc_now(),
            },
        )
        return node_id

    def link_graph(
        self,
        project_id: str,
        *,
        source_type: str,
        source_id: str,
        source_label: str,
        target_type: str,
        target_id: str,
        target_label: str,
        relationship_type: str,
        direction: str = "directed",
        strength: float | None = None,
        confidence: float | None = None,
        evidence_ids: Sequence[str] = (),
        source: str = "BioIntel local workspace",
        version: str = "",
        contradiction_state: str = "None",
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize("write")
        self._project(project_id)
        if relationship_type not in RELATIONSHIPS:
            raise PlatformValidationError(f"Unsupported graph relationship: {relationship_type}")
        if strength is not None and not 0 <= float(strength) <= 1:
            raise PlatformValidationError("Graph strength must be between 0 and 1")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise PlatformValidationError("Graph confidence must be between 0 and 1")
        source_node = self._upsert_graph_node(
            project_id, source_type, source_id, source_label, provenance=provenance
        )
        target_node = self._upsert_graph_node(
            project_id, target_type, target_id, target_label, provenance=provenance
        )
        edge_id = new_id("EDGE")
        try:
            self.store.insert(
                "graph_edges",
                {
                    "edge_id": edge_id, "project_id": project_id,
                    "source_node_id": source_node, "target_node_id": target_node,
                    "relationship_type": relationship_type, "direction": direction,
                    "strength": strength, "evidence_ids_json": list(evidence_ids),
                    "confidence": confidence, "source": require_text(source, "edge source", 500),
                    "version": optional_text(version, 100),
                    "provenance_json": dict(provenance or {}),
                    "contradiction_state": optional_text(contradiction_state, 120) or "None",
                    "created_at_utc": utc_now(),
                },
            )
        except sqlite3.IntegrityError:
            with self.store.connect(read_only=True) as connection:
                row = connection.execute(
                    """
                    SELECT edge_id FROM graph_edges
                    WHERE project_id=? AND source_node_id=? AND target_node_id=?
                      AND relationship_type=? AND source=?
                    """,
                    (project_id, source_node, target_node, relationship_type, source),
                ).fetchone()
            if row is None:
                raise
            edge_id = str(row[0])
        return self.store.row("graph_edges", "edge_id", edge_id) or {}

    def graph_view(
        self,
        project_id: str,
        *,
        relationship_type: str | None = None,
        contradiction_only: bool = False,
        limit: int = 1000,
    ) -> dict[str, Any]:
        self._project(project_id)
        clauses = ["e.project_id=?"]
        parameters: list[Any] = [project_id]
        if relationship_type:
            clauses.append("e.relationship_type=?")
            parameters.append(relationship_type)
        if contradiction_only:
            clauses.append("e.contradiction_state!='None'")
        parameters.append(max(1, min(int(limit), 5000)))
        with self.store.connect(read_only=True) as connection:
            edges = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT e.*,s.entity_type AS source_type,s.entity_id AS source_entity_id,
                           s.label AS source_label,t.entity_type AS target_type,
                           t.entity_id AS target_entity_id,t.label AS target_label
                    FROM graph_edges e
                    JOIN graph_nodes s ON s.node_id=e.source_node_id
                    JOIN graph_nodes t ON t.node_id=e.target_node_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY e.created_at_utc DESC LIMIT ?
                    """,
                    parameters,
                )
            ]
        node_ids = {row["source_node_id"] for row in edges} | {
            row["target_node_id"] for row in edges
        }
        nodes = [
            self.store.row("graph_nodes", "node_id", node_id)
            for node_id in sorted(node_ids)
        ]
        return {"nodes": [node for node in nodes if node], "edges": edges}

    def create_candidate(
        self,
        project_id: str,
        *,
        candidate_type: str,
        identity: str,
        data_source: str,
        synonyms: Sequence[str] = (),
        discovery_run_ids: Sequence[str] = (),
        scores: Mapping[str, float] | None = None,
        confidence: float | None = None,
        qc: Mapping[str, Any] | None = None,
        supporting_evidence_ids: Sequence[str] = (),
        contradictory_evidence_ids: Sequence[str] = (),
        cross_module_support: Mapping[str, Any] | None = None,
        risks: Sequence[str] = (),
        limitations: Sequence[str] = (),
        action_plan: Mapping[str, Any] | None = None,
        timeline: Mapping[str, Any] | None = None,
        owner: str = "",
        provenance: Mapping[str, Any] | None = None,
        origin: str = "real_calculation",
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        self._ensure_origin(project, origin)
        validate_choice(candidate_type, CANDIDATE_TYPES, "candidate type")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise PlatformValidationError("Candidate confidence must be between 0 and 1")
        candidate_id = new_id("CAND")
        now = utc_now()
        try:
            self.store.insert(
                "candidates",
                {
                    "candidate_id": candidate_id, "project_id": project_id,
                    "candidate_type": candidate_type,
                    "identity": require_text(identity, "candidate identity", 500),
                    "synonyms_json": list(dict.fromkeys(str(value) for value in synonyms)),
                    "data_source": require_text(data_source, "candidate data source", 500),
                    "discovery_run_ids_json": list(discovery_run_ids),
                    "scores_json": dict(scores or {}), "confidence": confidence,
                    "qc_json": dict(qc or {}),
                    "supporting_evidence_ids_json": list(supporting_evidence_ids),
                    "contradictory_evidence_ids_json": list(contradictory_evidence_ids),
                    "cross_module_support_json": dict(cross_module_support or {}),
                    "risks_json": list(risks), "limitations_json": list(limitations),
                    "validation_status": "Not planned",
                    "action_plan_json": dict(action_plan or {}),
                    "timeline_json": dict(timeline or {}),
                    "lifecycle_state": "Detected", "owner": optional_text(owner, 240),
                    "review_status": "Pending",
                    "provenance_json": {
                        **dict(provenance or {}), "origin": origin,
                        "scientific_status": "candidate, not validated",
                    },
                    "created_at_utc": now, "updated_at_utc": now,
                },
            )
        except sqlite3.IntegrityError as exc:
            with self.store.connect(read_only=True) as connection:
                existing = connection.execute(
                    "SELECT candidate_id FROM candidates WHERE project_id=? AND candidate_type=? AND identity=?",
                    (project_id, candidate_type, identity.strip()),
                ).fetchone()
            if existing is None:
                raise
            raise PlatformConflictError(
                f"Candidate already exists as {existing[0]}"
            ) from exc
        self._upsert_graph_node(
            project_id, "Candidate", candidate_id, identity,
            attributes={"candidate_type": candidate_type, "state": "Detected"},
            provenance={"origin": origin},
        )
        self.store.audit(
            "candidate_created", "candidate", candidate_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"candidate_type": candidate_type, "identity": identity, "origin": origin},
        )
        return self.store.row("candidates", "candidate_id", candidate_id) or {}

    def list_candidates(
        self,
        project_id: str,
        *,
        candidate_type: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        filters: dict[str, Any] = {"project_id": project_id}
        if candidate_type:
            validate_choice(candidate_type, CANDIDATE_TYPES, "candidate type")
            filters["candidate_type"] = candidate_type
        if lifecycle_state:
            validate_choice(lifecycle_state, CANDIDATE_STATES, "candidate lifecycle state")
            filters["lifecycle_state"] = lifecycle_state
        return self.store.rows(
            "candidates", filters=filters, order_by="updated_at_utc",
            limit=limit, offset=offset,
        )

    def update_candidate_state(
        self, candidate_id: str, state: str, *, review_status: str | None = None
    ) -> dict[str, Any]:
        self._authorize("review")
        validate_choice(state, CANDIDATE_STATES, "candidate lifecycle state")
        candidate = self.store.row("candidates", "candidate_id", candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        changes: dict[str, Any] = {"lifecycle_state": state, "updated_at_utc": utc_now()}
        if review_status is not None:
            changes["review_status"] = optional_text(review_status, 120)
        self.store.update("candidates", "candidate_id", candidate_id, changes)
        self.store.audit(
            "candidate_state_updated", "candidate", candidate_id,
            project_id=candidate["project_id"], actor=self.actor, role=self.role,
            detail={"from": candidate["lifecycle_state"], "to": state},
        )
        return self.store.row("candidates", "candidate_id", candidate_id) or {}

    def rank_candidates(
        self, project_id: str, weights: Mapping[str, float]
    ) -> list[dict[str, Any]]:
        self._authorize("run")
        candidates = self.list_candidates(project_id, limit=5000)
        if not candidates:
            return []
        clean_weights = {str(key): float(value) for key, value in weights.items() if float(value) >= 0}
        total = sum(clean_weights.values())
        if total <= 0:
            raise PlatformValidationError("At least one positive ranking weight is required")
        normalized = {key: value / total for key, value in clean_weights.items()}
        ranked = []
        for candidate in candidates:
            scores = candidate.get("scores") or {}
            available = {
                key: float(scores[key])
                for key in normalized
                if key in scores and scores[key] is not None
            }
            covered_weight = sum(normalized[key] for key in available)
            if not covered_weight:
                rank_score = None
            else:
                rank_score = sum(
                    available[key] * normalized[key] for key in available
                ) / covered_weight
            ranked.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "identity": candidate["identity"],
                    "candidate_type": candidate["candidate_type"],
                    "rank_score": rank_score,
                    "coverage": covered_weight,
                    "missing_metrics": sorted(set(normalized) - set(available)),
                }
            )
        ranked.sort(
            key=lambda item: (
                item["rank_score"] is None,
                -(item["rank_score"] or 0),
                item["identity"],
            )
        )
        for position, item in enumerate(ranked, 1):
            item["rank"] = position if item["rank_score"] is not None else None
            if item["rank_score"] is not None:
                self.store.update(
                    "candidates", "candidate_id", item["candidate_id"],
                    {
                        "lifecycle_state": "Prioritized",
                        "updated_at_utc": utc_now(),
                    },
                )
        self.store.audit(
            "candidates_ranked", "candidate", "", project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"weights": normalized, "candidate_count": len(ranked)},
        )
        return ranked


    def add_evidence(
        self,
        project_id: str,
        *,
        source: str,
        title: str,
        evidence_type: str,
        identifier: str = "",
        study_type: str = "",
        direction: str = "Neutral",
        strength: str = "Unrated",
        independence: str = "Unknown",
        pmid: str = "",
        doi: str = "",
        database_name: str = "",
        database_version: str = "",
        cohort: str = "",
        sample_size: int | None = None,
        species: str = "",
        tissue: str = "",
        quality: str = "Unrated",
        risk_of_bias: str = "Not assessed",
        retraction_state: str = "Not checked",
        correction_state: str = "Not checked",
        verification_state: str = "Unverified",
        limitations: Sequence[str] = (),
        linked_candidates: Sequence[str] = (),
        linked_recommendations: Sequence[str] = (),
        linked_hypotheses: Sequence[str] = (),
        linked_experiments: Sequence[str] = (),
        provenance: Mapping[str, Any] | None = None,
        origin: str = "imported_external_result",
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        self._ensure_origin(project, origin)
        validate_choice(evidence_type, EVIDENCE_TYPES, "evidence type")
        pmid = pmid.strip()
        doi = doi.strip()
        if pmid and not PMID_RE.fullmatch(pmid):
            raise PlatformValidationError("PMID format is invalid")
        if doi and not DOI_RE.fullmatch(doi):
            raise PlatformValidationError("DOI format is invalid")
        if project["is_synthetic"] and (pmid or doi):
            raise PlatformConflictError("Synthetic evidence cannot carry real-looking PMID or DOI values")
        if project["is_synthetic"] and evidence_type != "Synthetic fixture":
            raise PlatformConflictError("Synthetic projects may only register Synthetic fixture evidence")
        for candidate_id in linked_candidates:
            candidate = self.store.row("candidates", "candidate_id", candidate_id)
            if candidate is None or candidate["project_id"] != project_id:
                raise PlatformValidationError(f"Candidate link is invalid: {candidate_id}")
        evidence_id = new_id("EVID")
        now = utc_now()
        payload = {
            "source": source, "identifier": identifier, "title": title,
            "study_type": study_type, "evidence_type": evidence_type,
            "direction": direction, "strength": strength, "independence": independence,
            "pmid": pmid, "doi": doi, "database": database_name,
            "database_version": database_version, "cohort": cohort,
            "sample_size": sample_size, "species": species, "tissue": tissue,
            "quality": quality, "risk_of_bias": risk_of_bias,
            "retraction_state": retraction_state, "correction_state": correction_state,
            "verification_state": verification_state, "limitations": list(limitations),
            "origin": origin,
        }
        self.store.insert(
            "evidence",
            {
                "evidence_id": evidence_id, "project_id": project_id,
                "source": require_text(source, "evidence source", 500),
                "identifier": optional_text(identifier, 500),
                "title": require_text(title, "evidence title", 1000),
                "study_type": optional_text(study_type, 200),
                "evidence_type": evidence_type,
                "direction": optional_text(direction, 120) or "Neutral",
                "strength": optional_text(strength, 120) or "Unrated",
                "independence": optional_text(independence, 120) or "Unknown",
                "pmid": pmid, "doi": doi,
                "database_name": optional_text(database_name, 200),
                "database_version": optional_text(database_version, 120),
                "cohort": optional_text(cohort, 500),
                "sample_size": int(sample_size) if sample_size is not None else None,
                "species": optional_text(species, 200), "tissue": optional_text(tissue, 200),
                "quality": optional_text(quality, 120) or "Unrated",
                "risk_of_bias": optional_text(risk_of_bias, 300) or "Not assessed",
                "retraction_state": optional_text(retraction_state, 120) or "Not checked",
                "correction_state": optional_text(correction_state, 120) or "Not checked",
                "verification_state": optional_text(verification_state, 120) or "Unverified",
                "limitations_json": list(limitations),
                "linked_candidates_json": list(linked_candidates),
                "linked_recommendations_json": list(linked_recommendations),
                "linked_hypotheses_json": list(linked_hypotheses),
                "linked_experiments_json": list(linked_experiments),
                "provenance_json": {**dict(provenance or {}), "origin": origin},
                "payload_sha256": hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self._upsert_graph_node(
            project_id, "Evidence", evidence_id, title,
            attributes={"type": evidence_type, "direction": direction, "verification": verification_state},
            provenance={"origin": origin, "source": source},
        )
        for candidate_id in linked_candidates:
            candidate = self.store.row("candidates", "candidate_id", candidate_id) or {}
            field = (
                "contradictory_evidence_ids_json"
                if direction.lower() in {"oppose", "negative", "contradictory"}
                else "supporting_evidence_ids_json"
            )
            current = list(
                candidate.get(
                    "contradictory_evidence_ids" if field.startswith("contradictory") else "supporting_evidence_ids",
                    [],
                )
            )
            if evidence_id not in current:
                current.append(evidence_id)
            self.store.update(
                "candidates", "candidate_id", candidate_id,
                {field: current, "updated_at_utc": now},
            )
            self.link_graph(
                project_id,
                source_type="Candidate", source_id=candidate_id,
                source_label=candidate.get("identity", candidate_id),
                target_type="Evidence", target_id=evidence_id, target_label=title,
                relationship_type="Candidate-Evidence",
                source=source, evidence_ids=(evidence_id,),
                contradiction_state=(
                    "Contradictory" if direction.lower() in {"oppose", "negative", "contradictory"} else "None"
                ),
                provenance={"origin": origin},
            )
        self.store.audit(
            "evidence_added", "evidence", evidence_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={
                "source": source, "identifier": identifier,
                "verification": verification_state, "origin": origin,
            },
        )
        return self.store.row("evidence", "evidence_id", evidence_id) or {}

    def list_evidence(
        self,
        project_id: str,
        *,
        evidence_type: str | None = None,
        verification_state: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        filters: dict[str, Any] = {"project_id": project_id}
        if evidence_type:
            validate_choice(evidence_type, EVIDENCE_TYPES, "evidence type")
            filters["evidence_type"] = evidence_type
        if verification_state:
            filters["verification_state"] = verification_state
        return self.store.rows(
            "evidence", filters=filters, order_by="updated_at_utc",
            limit=limit, offset=offset,
        )

    def evidence_contradictions(self, project_id: str) -> list[dict[str, Any]]:
        evidence = self.list_evidence(project_id, limit=5000)
        by_candidate: dict[str, list[dict[str, Any]]] = {}
        for item in evidence:
            for candidate_id in item.get("linked_candidates", []):
                by_candidate.setdefault(candidate_id, []).append(item)
        output = []
        support = {"support", "positive", "increased", "protective"}
        oppose = {"oppose", "negative", "contradictory", "decreased", "harmful"}
        for candidate_id, items in by_candidate.items():
            positive = [item["evidence_id"] for item in items if item["direction"].lower() in support]
            negative = [item["evidence_id"] for item in items if item["direction"].lower() in oppose]
            if positive and negative:
                output.append(
                    {
                        "candidate_id": candidate_id,
                        "supporting_evidence": positive,
                        "contradictory_evidence": negative,
                        "status": "Contradictory evidence requires review",
                    }
                )
        return output

    def create_hypothesis(
        self,
        project_id: str,
        *,
        statement: str,
        null_hypothesis: str,
        biological_mechanism: str = "",
        supporting_observations: Sequence[str] = (),
        contradictory_observations: Sequence[str] = (),
        competing_hypotheses: Sequence[str] = (),
        causal_dag: Mapping[str, Any] | None = None,
        predictions: Sequence[str] = (),
        falsification_criteria: Sequence[str] = (),
        evidence_gaps: Sequence[str] = (),
        candidate_links: Sequence[str] = (),
        experiment_links: Sequence[str] = (),
        expected_outcomes: Sequence[str] = (),
        failure_interpretation: str = "",
        confidence: float | None = None,
        novelty: str = "Unassessed",
        status: str = "Draft",
        provenance: Mapping[str, Any] | None = None,
        origin: str = "hypothesis",
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        if project["is_synthetic"]:
            if origin != "synthetic_demo_output":
                raise PlatformConflictError("Synthetic hypotheses must preserve synthetic origin")
        elif origin not in {"hypothesis", "rule_based_guidance", "user_entered_interpretation"}:
            raise PlatformValidationError("Unsupported hypothesis origin")
        validate_choice(status, HYPOTHESIS_STATES, "hypothesis status")
        if not supporting_observations:
            raise PlatformValidationError("At least one supporting observation is required")
        if not falsification_criteria:
            raise PlatformValidationError("At least one falsification criterion is required")
        with self.store.connect(read_only=True) as connection:
            evidence_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE project_id=?", (project_id,)
                ).fetchone()[0]
            )
            verified_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE project_id=? AND lower(verification_state) IN ('verified','checked','confirmed')",
                    (project_id,),
                ).fetchone()[0]
            )
            candidate_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE project_id=?", (project_id,)
                ).fetchone()[0]
            )
        if evidence_count == 0 and candidate_count == 0:
            raise PlatformConflictError(
                "Hypotheses require at least one linked observation, evidence record, or candidate"
            )
        if confidence is not None:
            if not 0 <= float(confidence) <= 1:
                raise PlatformValidationError("Hypothesis confidence must be between 0 and 1")
            if float(confidence) > 0.6 and verified_count == 0:
                raise PlatformConflictError(
                    "High-confidence hypotheses require independently verified evidence"
                )
        hypothesis_id = new_id("HYP")
        now = utc_now()
        self.store.insert(
            "hypotheses",
            {
                "hypothesis_id": hypothesis_id, "project_id": project_id,
                "statement": require_text(statement, "hypothesis statement", 4000),
                "biological_mechanism": optional_text(biological_mechanism, 8000),
                "supporting_observations_json": list(supporting_observations),
                "contradictory_observations_json": list(contradictory_observations),
                "competing_hypotheses_json": list(competing_hypotheses),
                "null_hypothesis": require_text(null_hypothesis, "null hypothesis", 4000),
                "causal_dag_json": dict(causal_dag or {}),
                "predictions_json": list(predictions),
                "falsification_criteria_json": list(falsification_criteria),
                "evidence_gaps_json": list(evidence_gaps),
                "candidate_links_json": list(candidate_links),
                "experiment_links_json": list(experiment_links),
                "expected_outcomes_json": list(expected_outcomes),
                "failure_interpretation": optional_text(failure_interpretation, 4000),
                "confidence": confidence, "novelty": optional_text(novelty, 200),
                "status": status, "review_history_json": [],
                "provenance_json": {
                    **dict(provenance or {}), "origin": origin,
                    "evidence_count_at_creation": evidence_count,
                    "verified_evidence_count_at_creation": verified_count,
                },
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self._upsert_graph_node(
            project_id, "Hypothesis", hypothesis_id, statement,
            attributes={"status": status, "confidence": confidence},
            provenance={"origin": origin},
        )
        for evidence_item in self.list_evidence(project_id, limit=5000):
            if hypothesis_id in evidence_item.get("linked_hypotheses", []):
                self.link_graph(
                    project_id,
                    source_type="Hypothesis", source_id=hypothesis_id, source_label=statement,
                    target_type="Evidence", target_id=evidence_item["evidence_id"],
                    target_label=evidence_item["title"],
                    relationship_type="Hypothesis-Evidence",
                    evidence_ids=(evidence_item["evidence_id"],),
                    source=evidence_item["source"],
                    provenance={"origin": origin},
                )
        self.store.audit(
            "hypothesis_created", "hypothesis", hypothesis_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"status": status, "confidence": confidence, "origin": origin},
        )
        return self.store.row("hypotheses", "hypothesis_id", hypothesis_id) or {}

    def list_hypotheses(
        self, project_id: str, *, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"project_id": project_id}
        if status:
            validate_choice(status, HYPOTHESIS_STATES, "hypothesis status")
            filters["status"] = status
        return self.store.rows(
            "hypotheses", filters=filters, order_by="updated_at_utc",
            limit=limit, offset=offset,
        )


    def register_recommendation(
        self,
        project_id: str,
        recommendation: Mapping[str, Any],
        *,
        dataset_id: str | None = None,
        run_id: str | None = None,
        candidate_id: str | None = None,
        hypothesis_id: str | None = None,
        state: str = "Generated",
        coverage: Mapping[str, float | None] | None = None,
        provenance: Mapping[str, Any] | None = None,
        origin: str = "rule_based_guidance",
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        self._ensure_origin(project, origin)
        validate_choice(state, RECOMMENDATION_STATES, "recommendation state")
        links = {
            "datasets": ("dataset_id", dataset_id),
            "runs": ("run_id", run_id),
            "candidates": ("candidate_id", candidate_id),
            "hypotheses": ("hypothesis_id", hypothesis_id),
        }
        for table, (column, value) in links.items():
            if value:
                linked = self.store.row(table, column, value)
                if linked is None or linked.get("project_id") != project_id:
                    raise PlatformValidationError(f"Invalid recommendation link: {value}")
        metrics = dict(coverage or {})
        fields = (
            "engine_implementation", "runtime_execution", "input_completeness",
            "qc_completion", "evidence_coverage", "external_validation",
            "scientific_validation",
        )
        for key in fields:
            value = metrics.get(key)
            if value is not None and not 0 <= float(value) <= 1:
                raise PlatformValidationError(f"{key} must be between 0 and 1")
        recommendation_id = str(recommendation.get("recommendation_id") or new_id("REC"))
        now = utc_now()
        self.store.insert(
            "recommendations",
            {
                "recommendation_id": recommendation_id, "project_id": project_id,
                "dataset_id": dataset_id, "run_id": run_id,
                "candidate_id": candidate_id, "hypothesis_id": hypothesis_id,
                "state": state, "recommendation_json": dict(recommendation),
                **{key: metrics.get(key) for key in fields},
                "provenance_json": {
                    **dict(provenance or {}), "origin": origin,
                    "coverage_metrics_are_separate": True,
                },
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self._upsert_graph_node(
            project_id, "Recommendation", recommendation_id,
            str(recommendation.get("title") or recommendation.get("summary") or recommendation_id),
            attributes={"state": state}, provenance={"origin": origin},
        )
        if candidate_id:
            candidate = self.store.row("candidates", "candidate_id", candidate_id) or {}
            self.link_graph(
                project_id,
                source_type="Candidate", source_id=candidate_id,
                source_label=candidate.get("identity", candidate_id),
                target_type="Recommendation", target_id=recommendation_id,
                target_label=str(recommendation.get("title") or recommendation_id),
                relationship_type="Candidate-Recommendation",
                source="BioIntel recommendation engine",
                provenance={"origin": origin},
            )
        self.store.audit(
            "recommendation_registered", "recommendation", recommendation_id,
            project_id=project_id, actor=self.actor, role=self.role,
            detail={"state": state, "origin": origin},
        )
        return self.store.row("recommendations", "recommendation_id", recommendation_id) or {}

    def create_experiment(
        self,
        project_id: str,
        *,
        assay: str,
        validation_plan: Mapping[str, Any],
        acceptance_criteria: Sequence[str],
        failure_criteria: Sequence[str],
        recommendation_id: str | None = None,
        candidate_id: str | None = None,
        hypothesis_id: str | None = None,
        protocol: str = "",
        sop: str = "",
        samples: Sequence[str] = (),
        controls: Sequence[str] = (),
        replicates: Mapping[str, Any] | None = None,
        randomization: str = "",
        blinding: str = "",
        reagents: Sequence[str] = (),
        instruments: Sequence[str] = (),
        plate_layout: Mapping[str, Any] | None = None,
        operator: str = "",
        start_date: str | None = None,
        completion_date: str | None = None,
        expected_result: str = "",
        provenance: Mapping[str, Any] | None = None,
        origin: str = "user_entered_interpretation",
    ) -> dict[str, Any]:
        self._authorize("write")
        project = self._project(project_id)
        self._ensure_origin(project, origin)
        if not validation_plan:
            raise PlatformValidationError("Validation plan is required")
        if not acceptance_criteria or not failure_criteria:
            raise PlatformValidationError("Acceptance and failure criteria are required")
        for table, column, value in (
            ("recommendations", "recommendation_id", recommendation_id),
            ("candidates", "candidate_id", candidate_id),
            ("hypotheses", "hypothesis_id", hypothesis_id),
        ):
            if value:
                linked = self.store.row(table, column, value)
                if linked is None or linked.get("project_id") != project_id:
                    raise PlatformValidationError(f"Experiment link is invalid: {value}")
        experiment_id = new_id("EXP")
        now = utc_now()
        self.store.insert(
            "experiments",
            {
                "experiment_id": experiment_id, "project_id": project_id,
                "recommendation_id": recommendation_id, "candidate_id": candidate_id,
                "hypothesis_id": hypothesis_id,
                "validation_plan_json": dict(validation_plan),
                "protocol": optional_text(protocol, 12000), "sop": optional_text(sop, 12000),
                "assay": require_text(assay, "assay", 500),
                "samples_json": list(samples), "controls_json": list(controls),
                "replicates_json": dict(replicates or {}),
                "randomization": optional_text(randomization, 2000),
                "blinding": optional_text(blinding, 2000),
                "reagents_json": list(reagents), "instruments_json": list(instruments),
                "plate_layout_json": dict(plate_layout or {}),
                "operator": optional_text(operator, 240), "start_date": start_date,
                "completion_date": completion_date,
                "expected_result": optional_text(expected_result, 4000),
                "acceptance_criteria_json": list(acceptance_criteria),
                "failure_criteria_json": list(failure_criteria),
                "observed_result": "", "deviations_json": [], "qc_json": {},
                "attachments_json": [], "interpretation": "", "final_status": "Planned",
                "provenance_json": {**dict(provenance or {}), "origin": origin},
                "created_at_utc": now, "updated_at_utc": now,
            },
        )
        self._upsert_graph_node(
            project_id, "Experiment", experiment_id, f"{assay} validation",
            attributes={"status": "Planned"}, provenance={"origin": origin},
        )
        if candidate_id:
            candidate = self.store.row("candidates", "candidate_id", candidate_id) or {}
            self.store.update(
                "candidates", "candidate_id", candidate_id,
                {"lifecycle_state": "Validation Planned", "validation_status": "Planned", "updated_at_utc": now},
            )
            self.link_graph(
                project_id,
                source_type="Candidate", source_id=candidate_id,
                source_label=candidate.get("identity", candidate_id),
                target_type="Experiment", target_id=experiment_id,
                target_label=f"{assay} validation",
                relationship_type="Candidate-Experiment",
                source="BioIntel validation manager", provenance={"origin": origin},
            )
        if recommendation_id:
            self.store.update(
                "recommendations", "recommendation_id", recommendation_id,
                {"state": "Validation Pending", "updated_at_utc": now},
            )
        self.store.audit(
            "experiment_created", "experiment", experiment_id, project_id=project_id,
            actor=self.actor, role=self.role,
            detail={"assay": assay, "candidate_id": candidate_id, "origin": origin},
        )
        return self.store.row("experiments", "experiment_id", experiment_id) or {}

    def record_validation_result(
        self,
        experiment_id: str,
        *,
        outcome: str,
        observed_result: str,
        acceptance_met: bool,
        qc_status: str,
        interpretation: str,
        deviations: Sequence[str] = (),
    ) -> dict[str, Any]:
        self._authorize("review")
        validate_choice(outcome, ("Supported", "Partially Supported", "Failed", "Inconclusive"), "validation outcome")
        experiment = self.store.row("experiments", "experiment_id", experiment_id)
        if experiment is None:
            raise KeyError(experiment_id)
        project = self._project(experiment["project_id"])
        synthetic = bool(project["is_synthetic"])
        if not qc_status.strip():
            raise PlatformValidationError("Validation QC status is required")
        if qc_status.lower() in {"failed", "block", "blocked"} and acceptance_met:
            raise PlatformConflictError("Failed QC cannot satisfy acceptance criteria")
        candidate = (
            self.store.row("candidates", "candidate_id", experiment["candidate_id"])
            if experiment.get("candidate_id")
            else None
        )
        confidence_before = candidate.get("confidence") if candidate else None
        confidence_after = None
        if confidence_before is not None:
            delta = 0.10 if acceptance_met and qc_status.lower() in {"pass", "passed"} else -0.15
            confidence_after = round(max(0.0, min(1.0, float(confidence_before) + delta)), 6)
        origin = "synthetic_demo_output" if synthetic else "validation_result"
        evidence = self.add_evidence(
            experiment["project_id"],
            source="Synthetic validation exercise" if synthetic else "Internal experiment registry",
            title=f"{experiment['assay']} validation result",
            evidence_type="Synthetic fixture" if synthetic else "Experimental validation",
            identifier=f"SYN-VALIDATION-{experiment_id}" if synthetic else experiment_id,
            study_type=experiment["assay"],
            direction="Support" if acceptance_met else "Contradictory",
            strength="Synthetic only" if synthetic else ("QC accepted" if qc_status.lower() in {"pass", "passed"} else "QC limited"),
            verification_state="Synthetic exercise" if synthetic else "Internally recorded",
            linked_candidates=([experiment["candidate_id"]] if experiment.get("candidate_id") else []),
            linked_recommendations=([experiment["recommendation_id"]] if experiment.get("recommendation_id") else []),
            linked_hypotheses=([experiment["hypothesis_id"]] if experiment.get("hypothesis_id") else []),
            linked_experiments=(experiment_id,),
            limitations=(
                ["Synthetic result cannot validate a real recommendation"]
                if synthetic
                else ["Internal validation is not independent external validation"]
            ),
            provenance={
                "origin": origin, "qc_status": qc_status,
                "confidence_recalculation": "fixed transparent rule: +0.10 accepted, -0.15 otherwise",
            },
            origin=origin,
        )
        validation_id = new_id("VALID")
        self.store.insert(
            "validation_results",
            {
                "validation_id": validation_id, "experiment_id": experiment_id,
                "project_id": experiment["project_id"],
                "recommendation_id": experiment.get("recommendation_id"),
                "candidate_id": experiment.get("candidate_id"),
                "outcome": outcome,
                "observed_result": require_text(observed_result, "observed result", 12000),
                "acceptance_met": int(bool(acceptance_met)), "qc_status": qc_status.strip(),
                "evidence_id": evidence["evidence_id"],
                "confidence_before": confidence_before, "confidence_after": confidence_after,
                "interpretation": require_text(interpretation, "validation interpretation", 12000),
                "provenance_json": {
                    "origin": origin, "synthetic": synthetic,
                    "scientific_boundary": (
                        "Synthetic exercise only" if synthetic
                        else "Internal evidence; independent confirmation remains separate"
                    ),
                },
                "created_at_utc": utc_now(),
            },
        )
        final_status = (
            "Synthetic exercise complete"
            if synthetic
            else ("Accepted" if acceptance_met and qc_status.lower() in {"pass", "passed"} else "Failed")
        )
        self.store.update(
            "experiments", "experiment_id", experiment_id,
            {
                "observed_result": observed_result,
                "deviations_json": list(deviations),
                "qc_json": {"status": qc_status},
                "interpretation": interpretation,
                "final_status": final_status,
                "completion_date": utc_now()[:10],
                "updated_at_utc": utc_now(),
            },
        )
        if candidate:
            candidate_changes: dict[str, Any] = {
                "confidence": confidence_after,
                "validation_status": final_status,
                "updated_at_utc": utc_now(),
            }
            if synthetic:
                candidate_changes["lifecycle_state"] = "Under Review"
            else:
                candidate_changes["lifecycle_state"] = "Validated" if acceptance_met else "Rejected"
            self.store.update("candidates", "candidate_id", candidate["candidate_id"], candidate_changes)
            self.link_graph(
                experiment["project_id"],
                source_type="Candidate", source_id=candidate["candidate_id"],
                source_label=candidate["identity"],
                target_type="Validation", target_id=validation_id,
                target_label=f"{experiment['assay']} result",
                relationship_type="Candidate-Validation",
                source="BioIntel validation manager", evidence_ids=(evidence["evidence_id"],),
                provenance={"origin": origin},
            )
        recommendation_id = experiment.get("recommendation_id")
        if recommendation_id:
            state = "Completed" if synthetic else ("Validated" if acceptance_met else "Failed Validation")
            self.store.update(
                "recommendations", "recommendation_id", recommendation_id,
                {"state": state, "updated_at_utc": utc_now()},
            )
            recommendation = self.store.row(
                "recommendations", "recommendation_id", recommendation_id
            ) or {}
            self.link_graph(
                experiment["project_id"],
                source_type="Recommendation", source_id=recommendation_id,
                source_label=str(
                    recommendation.get("recommendation", {}).get("title")
                    or recommendation_id
                ),
                target_type="Validation", target_id=validation_id,
                target_label=f"{experiment['assay']} result",
                relationship_type="Recommendation-Validation Result",
                source="BioIntel validation manager", evidence_ids=(evidence["evidence_id"],),
                provenance={"origin": origin},
            )
        hypothesis_id = experiment.get("hypothesis_id")
        if hypothesis_id:
            hypothesis_status = (
                "Inconclusive" if synthetic or outcome == "Inconclusive"
                else ("Supported" if acceptance_met else "Rejected")
            )
            self.store.update(
                "hypotheses", "hypothesis_id", hypothesis_id,
                {"status": hypothesis_status, "updated_at_utc": utc_now()},
            )
        self.store.audit(
            "validation_result_recorded", "validation", validation_id,
            project_id=experiment["project_id"], actor=self.actor, role=self.role,
            detail={
                "outcome": outcome, "acceptance_met": acceptance_met,
                "qc_status": qc_status, "synthetic": synthetic,
                "confidence_before": confidence_before, "confidence_after": confidence_after,
            },
        )
        return self.store.row("validation_results", "validation_id", validation_id) or {}

    def list_experiments(
        self, project_id: str, *, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"project_id": project_id}
        if status:
            filters["final_status"] = status
        return self.store.rows(
            "experiments", filters=filters, order_by="updated_at_utc",
            limit=limit, offset=offset,
        )

    def list_validations(
        self, project_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self.store.rows(
            "validation_results", filters={"project_id": project_id},
            order_by="created_at_utc", limit=limit, offset=offset,
        )
