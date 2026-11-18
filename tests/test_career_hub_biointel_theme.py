from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import biointel.education.career_hub_ui as hub
from biointel.ui.navigation import PAGE_BY_KEY


class TestCareerHubBioIntelTheme(unittest.TestCase):
    def test_canonical_and_compatibility_routes_apply_global_theme(self) -> None:
        for relative in (
            "pages/355_BioIntel_Career_Internship_Scholarship_Hub.py",
            "pages/168_Career_Internship_Scholarship_Hub.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("from biointel.ui.theme import apply_theme", text)
            self.assertIn("render_career_hub_page()", text)
            self.assertLess(text.index("apply_theme()"), text.index("render_career_hub_page()"))

    def test_navigation_points_to_canonical_biointel_page(self) -> None:
        page = PAGE_BY_KEY["career_hub"]
        self.assertEqual(page.path, "pages/355_BioIntel_Career_Internship_Scholarship_Hub.py")
        self.assertEqual(page.category, "Education")
        self.assertTrue(page.featured)

    def test_theme_aware_ui_and_preserved_workspace_features(self) -> None:
        text = (ROOT / "src/biointel/education/career_hub_ui.py").read_text(encoding="utf-8")
        for token in (
            "var(--bio-primary)",
            "BioIntel Education · Student Growth",
            "Connected BioIntel education ecosystem",
            "Career workspace records",
            "Application preparation workspace",
            "Opportunity information requires source confirmation",
        ):
            self.assertIn(token, text)

    def test_checklist_and_pending_review_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = pathlib.Path(temp_dir) / "career.sqlite3"
            with patch.object(hub, "CAREER_DB_PATH", database):
                hub.init_career_db()
                checklist = hub.get_preparation_checklist("learner")
                self.assertEqual(set(checklist), {item[0] for item in hub.PREPARATION_ITEMS})
                self.assertFalse(any(checklist.values()))

                hub.set_preparation_item("learner", "cv", True)
                self.assertTrue(hub.get_preparation_checklist("learner")["cv"])
                self.assertGreater(hub.application_progress("learner"), 0)

                opportunity_id = hub.add_new_opportunity(
                    "Research placement",
                    "Example Institute",
                    "Internship",
                    "Bioinformatics",
                    "Not specified",
                    "Undergraduate learner",
                    "2027-01-31",
                    "Remote",
                    "https://example.org/opportunity",
                    "Research training placement.",
                )
                with sqlite3.connect(database) as conn:
                    row = conn.execute(
                        "SELECT verification_status, verified_by FROM opportunities WHERE id = ?",
                        (opportunity_id,),
                    ).fetchone()
                self.assertEqual(row, ("Pending source review", "Pending reviewer"))

    def test_deadline_labels_are_deterministic(self) -> None:
        today = hub.dt.date(2026, 8, 6)
        self.assertEqual(hub.deadline_label("2026-08-06", today), ("Deadline today", "danger"))
        self.assertEqual(hub.deadline_label("2026-08-12", today), ("6 day(s) left", "warning"))
        self.assertEqual(hub.deadline_label("2026-09-01", today), ("26 day(s) left", "success"))
        self.assertEqual(hub.deadline_label("invalid", today), ("Deadline not normalized", "warning"))


if __name__ == "__main__":
    unittest.main()
