import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from biointel.connect.connect_service import ConnectService
from biointel.education.classroom_service import ClassroomService
from biointel.education.science_pulse_service import SciencePulseService
from biointel.education.academy_service import AcademyService
from biointel.education.examination_service import ExaminationService
from biointel.education.intelligence_hub_service import IntelligenceHubService
from biointel.education.universe_workspaces_service import UniverseWorkspacesService
from biointel.education.education_demo_seeder import seed_education_demo_data

class TestBioIntelMegaUpgrade(unittest.TestCase):
    def setUp(self):
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_01_connect_service(self):
        cs = ConnectService(self.root_dir)
        p = cs.create_or_update_profile("test_user_1", {"name": "Test Scientist", "orcid": "0000-0000-0000-0001"})
        self.assertIsNotNone(p)
        self.assertEqual(p["name"], "Test Scientist")

        post = cs.create_post("test_user_1", "Test Scientist", "publication", "Test publication content")
        self.assertIsNotNone(post)
        feed = cs.get_feed()
        self.assertTrue(len(feed) > 0)

    def test_02_classroom_service(self):
        cls = ClassroomService(self.root_dir)
        c = cls.add_class("Test Class", "2026", "Bio", "Dr. Test")
        self.assertIsNotNone(c)
        classes = cls.get_classes()
        self.assertTrue(len(classes) > 0)

    def test_03_science_pulse_service(self):
        sp = SciencePulseService(self.root_dir)
        art_id = sp.add_article({"article_id": "test_art_1", "title": "Test Paper", "source": "PubMed"})
        self.assertEqual(art_id, "test_art_1")
        articles = sp.list_articles()
        self.assertTrue(len(articles) > 0)

    def test_04_universe_workspaces_service(self):
        uv = UniverseWorkspacesService(self.root_dir)
        rec = uv.save_record("adaptive_learning", "Test Track", {"score": 100})
        self.assertIsNotNone(rec)
        records = uv.list_records("adaptive_learning")
        self.assertTrue(len(records) > 0)

    def test_05_education_demo_seeder(self):
        seed_education_demo_data(self.root_dir)
        cs = ConnectService(self.root_dir)
        p = cs.get_profile("user_demo_1")
        self.assertIsNotNone(p)
        self.assertEqual(p["name"], "Dr. Aarav Sharma")

if __name__ == "__main__":
    unittest.main()
