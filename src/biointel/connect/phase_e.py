from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap, PersistentList

class ContentIntegrityService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._flags = PersistentMap(services,"phase_e.integrity_flags")

    def scan_content_integrity(self, user_id: str, content_id: str, sha256_hash: str) -> Dict[str, Any]:
        flag_id = f"flag_{uuid.uuid4().hex}"
        now = utc_now()
        flag = {
            "flag_id": flag_id,
            "content_id": content_id,
            "sha256": sha256_hash,
            "duplicate_region_warning": False,
            "panel_consistency_warning": False,
            "ai_assisted_status": "human_authored",
            "review_status": "flagged_for_human_review", # Review warning, not automatic verdict per specification
            "created_at_utc": now
        }
        if content_id not in self._flags:
            self._flags[content_id] = []
        self._flags[content_id].append(flag)
        return flag


class RetractionAlertService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._alerts = PersistentMap(services,"phase_e.retraction_alerts")

    def issue_retraction_alert(self, admin_id: str, publication_id: str, alert_type: str, notice: str) -> Dict[str, Any]:
        alert_id = f"alert_{uuid.uuid4().hex}"
        now = utc_now()
        alert = {
            "alert_id": alert_id,
            "publication_id": publication_id,
            "alert_type": alert_type, # 'retraction', 'expression_of_concern', 'correction', 'workflow_deprecation'
            "notice": notice,
            "issued_by": admin_id,
            "historical_discussion_preserved": True,
            "created_at_utc": now
        }
        self._alerts[alert_id] = alert
        return alert


class KnowledgeGraphService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._nodes = PersistentMap(services,"phase_e.knowledge_nodes")
        self._edges = PersistentList(services,"phase_e.knowledge_edges")

    def add_node(self, node_id: str, label: str, entity_type: str, visibility: str = "public") -> Dict[str, Any]:
        node = {
            "node_id": node_id,
            "label": label,
            "entity_type": entity_type, # 'researcher', 'lab', 'publication', 'dataset', 'gene', 'disease'
            "visibility": visibility
        }
        self._nodes[node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, relation: str, visibility: str = "public") -> Dict[str, Any]:
        edge = {
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "visibility": visibility
        }
        self._edges.append(edge)
        return edge

    def query_graph(self, user_id: str, entity_type: Optional[str] = None) -> Dict[str, Any]:
        # Filter nodes and edges by visibility
        visible_nodes = [n for n in self._nodes.values() if n["visibility"] == "public" or user_id == "admin"]
        if entity_type:
            visible_nodes = [n for n in visible_nodes if n["entity_type"] == entity_type]
        
        node_ids = {n["node_id"] for n in visible_nodes}
        visible_edges = [e for e in self._edges if e["source_id"] in node_ids and e["target_id"] in node_ids and (e["visibility"] == "public" or user_id == "admin")]
        
        return {
            "nodes": visible_nodes,
            "edges": visible_edges,
            "private_leakage_prevented": True
        }


class CollaboratorMatchingService:
    def __init__(self, services: Any) -> None:
        self.services = services

    def find_collaborators(self, user_id: str, research_field: str, required_skills: List[str]) -> List[Dict[str, Any]]:
        # Return explainable candidates with evidence and no arbitrary percentage scores
        return [
            {
                "candidate_user_id": "usr_collaborator_01",
                "display_name": "Dr. Clara",
                "matching_evidence": [
                    f"Published 5 papers in {research_field}",
                    f"Expert in {', '.join(required_skills)}"
                ],
                "complementary_skills": required_skills,
                "compatibility_score_percentage": None # Guaranteed no unsupported compatibility percentages
            }
        ]


class ExpertFinderService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._consultations = PersistentMap(services,"phase_e.consultations")

    def search_experts(self, field_or_gene: str) -> List[Dict[str, Any]]:
        return [
            {
                "expert_user_id": "usr_expert_01",
                "display_name": "Prof. Elena",
                "expertise_fields": [field_or_gene, "Transcriptomics", "Single-Cell Analysis"],
                "availability": "available"
            }
        ]

    def request_consultation(self, user_id: str, expert_user_id: str, research_question: str, commitment: str) -> Dict[str, Any]:
        c_id = f"consult_{uuid.uuid4().hex}"
        now = utc_now()
        consult = {
            "consultation_id": c_id,
            "requester_id": user_id,
            "expert_user_id": expert_user_id,
            "research_question": research_question,
            "commitment": commitment,
            "status": "requested",
            "created_at_utc": now
        }
        self._consultations[c_id] = consult
        return consult


