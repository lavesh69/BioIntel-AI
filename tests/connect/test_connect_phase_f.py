from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biointel.connect.services import ConnectError, PermissionDenied, build_connect_services
from biointel.connect.phase_f import (
    ServiceMarketplaceService,
    EquipmentBookingService,
    AdvancedEventService,
    MentorshipService
)

class ConnectPhaseFTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.services = build_connect_services(
            database_path=self.root / "connect_phase_f.sqlite3",
            storage_root=self.root / "media"
        )
        self.market_svc = ServiceMarketplaceService(self.services)
        self.eq_svc = EquipmentBookingService(self.services)
        self.event_svc = AdvancedEventService(self.services)
        self.mentor_svc = MentorshipService(self.services)

        self.alpha = self.services.ensure_identity("dr_alpha", "Dr. Alpha", "researcher")
        self.beta = self.services.ensure_identity("dr_beta", "Dr. Beta", "bioinformatician")
        self.provider = self.services.ensure_identity("provider_gamma", "Seq Lab", "organization")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_1_scientific_service_marketplace(self):
        """Verify service listing creation, quote requests, and zero payment processing default."""
        listing = self.market_svc.create_listing(self.provider["user_id"], "Illumina NovaSeq 6000 Sequencing", "sequencing", turnaround_days=7)
        self.assertEqual(listing["category"], "sequencing")
        self.assertFalse(listing["payment_gateway_required"])

        quote = self.market_svc.request_quote(self.alpha["user_id"], listing["listing_id"], sample_count=24, requirements="30x coverage WGS")
        self.assertEqual(quote["status"], "pending_quote")

    def test_2_equipment_booking_and_double_booking_lock(self):
        """Verify equipment registration, slot reservation, and transactional double-booking prevention."""
        eq = self.eq_svc.register_equipment(self.provider["user_id"], "Cryo-EM Microscope", "Room 102")
        self.assertEqual(eq["name"], "Cryo-EM Microscope")

        # Alpha books 10:00-12:00 slot
        book1 = self.eq_svc.book_slot(self.alpha["user_id"], eq["equipment_id"], "2026-08-01T10:00:00", "2026-08-01T12:00:00")
        self.assertTrue(book1["transaction_locked"])

        # Beta attempts to book exact same slot -> transactional double-booking prevention raises error
        with self.assertRaises(ConnectError):
            self.eq_svc.book_slot(self.beta["user_id"], eq["equipment_id"], "2026-08-01T10:00:00", "2026-08-01T12:00:00")

    def test_3_advanced_events_and_abstracts(self):
        """Verify conference creation, abstract submission, and non-accredited certificate issuance."""
        event = self.event_svc.create_conference(self.provider["user_id"], "International Genomics Summit 2026", "2026-09-15")
        self.assertTrue(event["multi_track"])

        abstract = self.event_svc.submit_abstract(self.alpha["user_id"], event["event_id"], "CRDT Synchronization in Omics Pipelines", "Abstract body text...")
        self.assertEqual(abstract["status"], "under_review")

        cert = self.event_svc.generate_certificate(self.alpha["user_id"], event["event_id"])
        self.assertFalse(cert["accredited"]) # Guaranteed non-accredited status explicitly declared

    def test_4_mentorship_network(self):
        """Verify mentorship request and mentor acceptance lifecycle."""
        req = self.mentor_svc.request_mentorship(self.beta["user_id"], self.alpha["user_id"], "Single-cell RNA-seq career guidance")
        self.assertEqual(req["status"], "requested")

        accepted = self.mentor_svc.accept_mentorship(self.alpha["user_id"], req["mentorship_id"])
        self.assertEqual(accepted["status"], "active")

        # Wrong user cannot accept mentorship
        with self.assertRaises(PermissionDenied):
            self.mentor_svc.accept_mentorship(self.beta["user_id"], req["mentorship_id"])

if __name__ == "__main__":
    unittest.main()
