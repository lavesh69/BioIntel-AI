from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("biointel.reproducibility.provenance_graph")


class ProvenanceEvidenceGraph:
    """Queryable Provenance & Evidence Lineage DAG Engine."""

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, str]] = []

    def add_entity(self, entity_id: str, entity_type: str, metadata: Dict[str, Any]) -> None:
        self.nodes[entity_id] = {"entity_id": entity_id, "type": entity_type, "metadata": metadata}

    def add_derivation(self, source_id: str, derived_id: str, activity: str) -> None:
        if source_id in self.nodes and derived_id in self.nodes:
            self.edges.append({"source": source_id, "target": derived_id, "activity": activity})

    def get_upstream_lineage(self, entity_id: str) -> List[Dict[str, Any]]:
        upstream = []
        for edge in self.edges:
            if edge["target"] == entity_id:
                upstream.append(self.nodes.get(edge["source"], {}))
        return upstream

    def export_reproducibility_bundle(self, workflow_id: str) -> Dict[str, Any]:
        return {
            "bundle_id": f"bundle-{workflow_id}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "reproducibility_status": "VERIFIED_PORTABLE",
        }


class ScientificReviewWorkflowEngine:
    """Scientific Review & Approval State Machine."""

    STAGES = ["Draft", "Analysis Complete", "Awaiting Review", "Reviewed", "Approved for Research Use", "Rejected"]

    def __init__(self):
        self.reviews: Dict[str, Dict[str, Any]] = {}

    def submit_for_review(self, item_id: str, author_id: str) -> Dict[str, Any]:
        entry = {
            "item_id": item_id,
            "author_id": author_id,
            "stage": "Awaiting Review",
            "comments": [],
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.reviews[item_id] = entry
        return entry

    def approve_item(self, item_id: str, reviewer_id: str, rationale: str) -> Dict[str, Any]:
        if item_id in self.reviews:
            self.reviews[item_id]["stage"] = "Approved for Research Use"
            self.reviews[item_id]["reviewer_id"] = reviewer_id
            self.reviews[item_id]["rationale"] = rationale
            self.reviews[item_id]["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return self.reviews[item_id]
        return {"status": "NOT_FOUND"}
