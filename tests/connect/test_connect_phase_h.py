from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from biointel.connect.services import build_connect_services
from biointel.connect.phase_h import NetworkAnalyticsService,ScientificTrendService,DigitalPreservationService
class ConnectPhaseHTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=self.root/'db.sqlite3'; self.media=self.root/'media'; self.services=build_connect_services(database_path=self.db,storage_root=self.media); self.alpha=self.services.ensure_identity('alpha','Alpha'); self.analytics_svc=NetworkAnalyticsService(self.services); self.trend_svc=ScientificTrendService(self.services); self.preserve_svc=DigitalPreservationService(self.services)
    def tearDown(self): self.temp.cleanup()
    def test_1_network_analytics(self):
        self.services.content.create_post(self.alpha['user_id'],body='Update #singlecell'); metrics=self.analytics_svc.get_user_analytics(self.alpha['user_id']); self.assertEqual(metrics['posts_published'],1); self.assertIsNone(metrics['profile_views']); self.assertEqual(metrics['metric_source'],'persisted_connect_tables')
    def test_2_explainable_scientific_trends(self):
        self.services.content.create_post(self.alpha['user_id'],body='Result #singlecell'); trends=self.trend_svc.discover_trends(); self.assertEqual(trends[0]['topic'],'singlecell'); self.assertIn('Popularity only',trends[0]['scientific_validity_note'])
    def test_3_digital_preservation_and_reproducibility(self):
        bundle=self.preserve_svc.create_reproducibility_bundle(self.alpha['user_id'],'Bundle',['ds_01'],['wf_01']); self.assertEqual(bundle['preservation_status'],'local_package_created'); self.assertFalse(bundle['permanent_archive']); self.assertEqual(len(bundle['sha256_checksum']),64); self.assertTrue(Path(bundle['archive_path']).is_file()); self.assertTrue(self.preserve_svc.verify_bundle(self.alpha['user_id'],bundle['bundle_id'])['checksum_matches']); restarted=build_connect_services(database_path=self.db,storage_root=self.media); self.assertTrue(DigitalPreservationService(restarted).verify_bundle(self.alpha['user_id'],bundle['bundle_id'])['checksum_matches'])
if __name__=='__main__': unittest.main()

