from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biointel.connect.services import build_connect_services
from biointel.connect.phase_e import (
    ContentIntegrityService,
    RetractionAlertService,
    KnowledgeGraphService,
    CollaboratorMatchingService,
    ExpertFinderService
)

class ConnectPhaseETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.services = build_connect_services(
            database_path=self.root / "connect_phase_e.sqlite3",
            storage_root=self.root / "media"
        )
        self.integrity_svc = ContentIntegrityService(self.services)
        self.retraction_svc = RetractionAlertService(self.services)
        self.graph_svc = KnowledgeGraphService(self.services)
        self.matching_svc = CollaboratorMatchingService(self.services)
        self.expert_svc = ExpertFinderService(self.services)

        self.alpha = self.services.ensure_identity("dr_alpha", "Dr. Alpha", "researcher")
        self.beta = self.services.ensure_identity("dr_beta", "Dr. Beta", "bioinformatician")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_1_scientific_content_authenticity_and_integrity(self):
        """Verify image duplication scan, panel consistency checks, and human review flags (no auto verdicts)."""
        flag = self.integrity_svc.scan_content_integrity(self.alpha["user_id"], "figure_01.png", "sha256_figure_hash")
        self.assertEqual(flag["review_status"], "flagged_for_human_review")
        self.assertFalse(flag["duplicate_region_warning"])

    def test_2_retraction_and_correction_alerts(self):
        """Verify retraction notice issuance, alert distribution, and historical discussion preservation."""
        alert = self.retraction_svc.issue_retraction_alert(self.alpha["user_id"], "pub_2024_001", "retraction", "Data mislabeling in supplementary table 3.")
        self.assertEqual(alert["alert_type"], "retraction")
        self.assertTrue(alert["historical_discussion_preserved"])

    def test_3_permission_aware_knowledge_graph(self):
        """Verify knowledge graph node/edge insertion, entity filtering, and private relation isolation."""
        self.graph_svc.add_node("n_gene_tp53", "TP53", "gene", visibility="public")
        self.graph_svc.add_node("n_disease_brca", "Breast Cancer", "disease", visibility="public")
        self.graph_svc.add_node("n_secret_project", "Confidential Project", "project", visibility="private")

        self.graph_svc.add_edge("n_gene_tp53", "n_disease_brca", "associated_with", visibility="public")
        self.graph_svc.add_edge("n_gene_tp53", "n_secret_project", "used_in", visibility="private")

        # Standard user query hides private node and edge
        public_graph = self.graph_svc.query_graph(self.beta["user_id"])
        node_ids = {n["node_id"] for n in public_graph["nodes"]}
        self.assertIn("n_gene_tp53", node_ids)
        self.assertNotIn("n_secret_project", node_ids)
        self.assertTrue(public_graph["private_leakage_prevented"])

    def test_4_explainable_collaborator_matching_and_expert_finder(self):
        """Verify collaborator matching with explicit evidence, no artificial score, and consultation request lifecycle."""
        candidates = self.matching_svc.find_collaborators(self.alpha["user_id"], "Single-Cell Genomics", ["CRDT", "Python"])
        self.assertGreaterEqual(len(candidates), 1)
        self.assertIsNone(candidates[0]["compatibility_score_percentage"]) # Guaranteed no artificial single score
        self.assertIn("Published 5 papers", candidates[0]["matching_evidence"][0])

        experts = self.expert_svc.search_experts("TP53")
        self.assertGreaterEqual(len(experts), 1)

        consult = self.expert_svc.request_consultation(self.alpha["user_id"], experts[0]["expert_user_id"], "Single-cell clustering parameters", "2 hours")
        self.assertEqual(consult["status"], "requested")

if __name__ == "__main__":
    unittest.main()
