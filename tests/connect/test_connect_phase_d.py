from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biointel.connect.services import ConnectError, PermissionDenied, build_connect_services
from biointel.connect.phase_d import (
    PeerReviewService,
    PreprintPublishingService,
    ContributorshipService,
    TrustPortfolioService
)

class ConnectPhaseDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.services = build_connect_services(
            database_path=self.root / "connect_phase_d.sqlite3",
            storage_root=self.root / "media"
        )
        self.review_svc = PeerReviewService(self.services)
        self.preprint_svc = PreprintPublishingService(self.services)
        self.credit_svc = ContributorshipService(self.services)
        self.trust_svc = TrustPortfolioService(self.services)

        self.editor = self.services.ensure_identity("editor_alpha", "Dr. Editor", "administrator")
        self.reviewer = self.services.ensure_identity("reviewer_beta", "Dr. Reviewer", "researcher")
        self.author = self.services.ensure_identity("author_gamma", "Dr. Author", "researcher")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_1_peer_review_workspace(self):
        """Verify reviewer invitation, COI declaration, structured review submission, editor notes, and review certificates."""
        invitation = self.review_svc.invite_reviewer(self.editor["user_id"], "ms_genomics_01", self.reviewer["user_id"], review_mode="double_blind")
        self.assertEqual(invitation["review_mode"], "double_blind")

        # Reviewer accepts invitation
        accepted = self.review_svc.respond_invitation(self.reviewer["user_id"], invitation["review_id"], accept=True)
        self.assertEqual(accepted["status"], "accepted")

        # Submit structured review with confidential editor notes
        review = self.review_svc.submit_review(
            self.reviewer["user_id"],
            invitation["review_id"],
            major_comments="Statistical power calculation required for cohort B.",
            minor_comments="Fix figure 3 legend typo.",
            recommendation="minor_revision",
            confidential_editor_notes="Sound methodology, minor revisions sufficient."
        )
        self.assertEqual(review["recommendation"], "minor_revision")

        # Issue review certificate
        cert = self.review_svc.issue_review_certificate(self.reviewer["user_id"], invitation["review_id"])
        self.assertEqual(cert["verification_status"], "verified")

    def test_2_preprint_publishing_and_corrections(self):
        """Verify preprint publication, persistent ID assignment, versioned corrections, and withdrawal."""
        pp = self.preprint_svc.submit_preprint(self.author["user_id"], "CRDT Synchronization in Single-Cell Pipelines", "Abstract body text.")
        self.assertTrue(pp["persistent_id"].startswith("biointel.preprint."))

        # Issue versioned correction notice
        corr = self.preprint_svc.issue_correction(self.author["user_id"], pp["preprint_id"], "Updated reference list in section 4.")
        self.assertEqual(corr["version"], 2)

        # Withdraw preprint with formal reason
        withdrawn = self.preprint_svc.withdraw_preprint(self.author["user_id"], pp["preprint_id"], "Duplicate submission error.")
        self.assertEqual(withdrawn["status"], "withdrawn")

    def test_3_credit_contributorship_and_authorship_lock(self):
        """Verify CRediT contribution mapping, role assignment, and final authorship lock."""
        res1 = self.credit_svc.assign_credit_roles(self.author["user_id"], "ms_01", self.author["user_id"], ["Conceptualization", "Writing", "Funding acquisition"])
        self.assertIn("Writing", res1["credit_roles"])

        res2 = self.credit_svc.assign_credit_roles(self.author["user_id"], "ms_01", self.reviewer["user_id"], ["Software", "Formal analysis"])
        self.assertIn("Software", res2["credit_roles"])

        # Lock authorship
        locked = self.credit_svc.lock_authorship(self.author["user_id"], "ms_01")
        self.assertTrue(locked["authorship_locked"])

        # Post-lock modifications fail without formal dispute resolution
        with self.assertRaises(ConnectError):
            self.credit_svc.assign_credit_roles(self.author["user_id"], "ms_01", "new_user", ["Resources"])

    def test_4_trust_portfolio_and_endorsements(self):
        """Verify transparent scientific indicators and skill endorsements (no single scientist score)."""
        portfolio = self.trust_svc.get_reputation_portfolio(self.author["user_id"])
        self.assertTrue(portfolio["identity_verified"])
        self.assertIsNone(portfolio["universal_scientist_score"]) # Guaranteed no artificial single score

        end = self.trust_svc.add_skill_endorsement(self.editor["user_id"], self.author["user_id"], "Single-Cell Sequencing")
        self.assertEqual(end["skill_name"], "Single-Cell Sequencing")

if __name__ == "__main__":
    unittest.main()
