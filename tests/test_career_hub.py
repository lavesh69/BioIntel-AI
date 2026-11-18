import unittest, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.career_hub_ui import (
    init_career_db,
    get_opportunities,
    get_user_applications,
    save_application_status,
    add_new_opportunity,
)


class TestCareerHub(unittest.TestCase):
    def setUp(self) -> None:
        init_career_db()

    def test_get_opportunities(self) -> None:
        opps = get_opportunities(opp_type="All")
        self.assertGreaterEqual(len(opps), 6)
        titles = [o["title"] for o in opps]
        self.assertTrue(any("ICMR" in t for t in titles))
        self.assertTrue(any("IISc" in t for t in titles))

    def test_filter_opportunities(self) -> None:
        scholarships = get_opportunities(opp_type="Scholarship")
        self.assertTrue(all(s["opp_type"] == "Scholarship" for s in scholarships))

    def test_search_opportunities(self) -> None:
        results = get_opportunities(search_query="Genomics")
        self.assertGreater(len(results), 0)

    def test_application_tracking(self) -> None:
        opps = get_opportunities("All")
        target_id = opps[0]["id"]
        save_application_status(target_id, applicant_id="test_user", status="Applied", notes="Submitted online")

        apps = get_user_applications(applicant_id="test_user")
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["id"], target_id)
        self.assertEqual(apps[0]["status"], "Applied")

    def test_add_new_opportunity(self) -> None:
        new_id = add_new_opportunity(
            title="Test Postdoc Fellowship",
            organization="Test University",
            opp_type="Research Fellowship",
            domain="Cancer Biology",
            stipend="$60,000/yr",
            eligibility="PhD in Biology",
            deadline="2026-12-31",
            location="Remote",
            url="https://test.edu/apply",
            description="Test description"
        )
        self.assertTrue(new_id.startswith("OPP-"))
        fetched = get_opportunities(search_query="Test Postdoc")
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["organization"], "Test University")


if __name__ == "__main__":
    unittest.main()
