from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biointel.connect.services import ConnectError, PermissionDenied, build_connect_services
from biointel.connect.phase_c import (
    GrantIntelligenceService,
    ConsortiumService,
    DataAccessCommitteeService,
    GovernancePolicyService
)

class ConnectPhaseCTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.services = build_connect_services(
            database_path=self.root / "connect_phase_c.sqlite3",
            storage_root=self.root / "media"
        )
        self.grant_svc = GrantIntelligenceService(self.services)
        self.consortium_svc = ConsortiumService(self.services)
        self.dac_svc = DataAccessCommitteeService(self.services)
        self.gov_svc = GovernancePolicyService(self.services)

        self.alpha = self.services.ensure_identity("dr_alpha", "Dr. Alpha", "researcher")
        self.beta = self.services.ensure_identity("dr_beta", "Dr. Beta", "bioinformatician")
        self.admin = self.services.ensure_identity("admin_user", "Admin User", "administrator")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_1_grant_intelligence_and_proposal_workspace(self):
        """Verify grant opportunity discovery, proposal workspace, team formation, and Shiro assistant."""
        opp = self.grant_svc.add_opportunity("NIH", "Genomics Research Grant 2026", 500000.0, "2026-12-31", ["Genomics", "Bioinformatics"])
        self.assertEqual(opp["sponsor"], "NIH")

        prop = self.grant_svc.create_proposal(self.alpha["user_id"], opp["grant_id"], "Single-Cell Expression Proposal", self.alpha["user_id"])
        self.assertEqual(prop["pi_user_id"], self.alpha["user_id"])

        updated_prop = self.grant_svc.add_co_investigator(self.alpha["user_id"], prop["proposal_id"], self.beta["user_id"])
        self.assertIn(self.beta["user_id"], updated_prop["co_investigators"])

        # Non-PI cannot add co-investigators
        with self.assertRaises(PermissionDenied):
            self.grant_svc.add_co_investigator(self.beta["user_id"], prop["proposal_id"], "fake_user")

        shiro_help = self.grant_svc.assist_grant_draft(self.alpha["user_id"], prop["proposal_id"], "Work Packages")
        self.assertTrue(shiro_help["requires_user_approval"])
        self.assertFalse(shiro_help["fabricated_citations"])

    def test_2_research_consortium_management_and_voting(self):
        """Verify consortium workspace, site management, decision voting, and quorum enforcement."""
        consortium = self.consortium_svc.create(self.alpha["user_id"], "Global Cancer Genomics Consortium", "Harvard Medical School")
        self.assertIn("Harvard Medical School", consortium["sites"])

        vote = self.consortium_svc.propose_decision_vote(self.alpha["user_id"], consortium["consortium_id"], "Approve Data Sharing Policy", quorum_required=2)
        self.assertEqual(vote["quorum_required"], 2)

        cast1 = self.consortium_svc.cast_vote(self.alpha["user_id"], consortium["consortium_id"], vote["vote_id"], "yes")
        self.assertFalse(cast1["quorum_met"])

        cast2 = self.consortium_svc.cast_vote(self.beta["user_id"], consortium["consortium_id"], vote["vote_id"], "yes")
        self.assertTrue(cast2["quorum_met"])

    def test_3_data_access_committee_workflow(self):
        """Verify DAC access request, voting quorum, approval, and explicit access revocation."""
        req = self.dac_svc.submit_request(self.beta["user_id"], "dataset_tcga_01", "Replicate BRCA expression signatures")
        self.assertEqual(req["status"], "pending_review")

        v1 = self.dac_svc.vote_request(self.alpha["user_id"], req["request_id"], "approve")
        self.assertEqual(v1["status"], "pending_review")

        v2 = self.dac_svc.vote_request(self.admin["user_id"], req["request_id"], "approve")
        self.assertEqual(v2["status"], "approved")

        revocation = self.dac_svc.revoke_access(self.admin["user_id"], req["request_id"], "Project embargo expired")
        self.assertEqual(revocation["status"], "revoked")
        self.assertEqual(revocation["revocation_reason"], "Project embargo expired")

    def test_4_scientific_policy_and_governance(self):
        """Verify governance policy creation, versioning, and user acknowledgements."""
        policy = self.gov_svc.create_policy(self.admin["user_id"], "Open Science Data Policy 2026", "All publication datasets must be shared upon acceptance.", scope="global")
        self.assertEqual(policy["version"], 1)

        ack = self.gov_svc.acknowledge_policy(self.beta["user_id"], policy["policy_id"])
        self.assertTrue(ack["acknowledged"])

if __name__ == "__main__":
    unittest.main()
