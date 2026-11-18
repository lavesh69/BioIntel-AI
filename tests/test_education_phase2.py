from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from biointel.education.demo import seed_demo
from biointel.education.paths import education_paths
from biointel.education.phase2 import DEFAULT_DASHBOARD_WIDGETS, EducationPhase2
from biointel.education.platform import Denied, EducationError, EducationPlatform
from biointel.education.components.charts import chart_text_alternative
from biointel.education.components.status import provider_status
from biointel.education.components.workflows import workflow_state


class EducationPhase2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="BioIntel Phase2 ", dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)
        self.previous_data_root = os.environ.get("BIOINTEL_USER_DATA_DIR")
        os.environ["BIOINTEL_USER_DATA_DIR"] = str(self.root / "UserData")
        seed_demo()
        database, media = education_paths(demo=True)
        self.platform = EducationPlatform(database, media)
        self.service = EducationPhase2(self.platform)
        self.admin = "demo-persona-university-admin"
        self.student = "demo-persona-university-student"
        self.institution = "demo-inst-university"

    def tearDown(self) -> None:
        if self.previous_data_root is None:
            os.environ.pop("BIOINTEL_USER_DATA_DIR", None)
        else:
            os.environ["BIOINTEL_USER_DATA_DIR"] = self.previous_data_root
        self.temp.cleanup()

    def test_preferences_are_user_scoped_persistent_and_resettable(self) -> None:
        initial = self.service.preferences(self.admin, self.institution)
        self.assertEqual(initial["widgets"], list(DEFAULT_DASHBOARD_WIDGETS))
        saved = self.service.save_preferences(self.admin, self.institution, "Research", ["pulse_alerts", "today_timeline", "pulse_alerts"], "expanded", "2026-27")
        self.assertEqual(saved["widgets"], ["pulse_alerts", "today_timeline"])
        self.assertEqual(saved["density"], "expanded")
        self.assertFalse(self.service.preferences(self.student, self.institution)["persisted"])
        self.assertFalse(self.service.reset_preferences(self.admin, self.institution, "Research")["persisted"])

    def test_branding_is_admin_only_and_logo_is_bounded(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"phase2"
        saved = self.service.save_branding(
            self.admin, self.institution, campus_name="BioIntel Campus", accent_color="#11AACC",
            certificate_footer="Verified by the institution", course_cover_style="molecular-lines",
            login_welcome_text="Welcome", footer_information="Synthetic demo", logo_name="logo.png",
            logo_mime="image/png", logo_bytes=png,
        )
        self.assertEqual(saved["accent_color"], "#11AACC")
        self.assertTrue(Path(self.service.logo_path(saved) or "").is_file())
        with self.assertRaises(Denied):
            self.service.save_branding(self.student, self.institution, campus_name="No", accent_color="#11AACC", certificate_footer="", course_cover_style="scientific-grid", login_welcome_text="", footer_information="")
        with self.assertRaises(EducationError):
            self.service.save_branding(self.admin, self.institution, campus_name="No", accent_color="blue", certificate_footer="", course_cover_style="scientific-grid", login_welcome_text="", footer_information="")

    def test_dashboard_and_activity_use_persisted_records(self) -> None:
        snapshot = self.service.dashboard_snapshot(self.admin, self.institution)
        self.assertEqual(snapshot["data_origin"], "persisted_education_records")
        self.assertGreater(len(snapshot["attendance"]), 0)
        self.assertGreater(len(snapshot["universe"]), 0)
        activity = self.service.activity_stream(self.admin, self.institution, limit=200)
        self.assertTrue(any(item["source"] == "timetable" for item in activity))
        self.assertTrue(all(str(item["page"]).startswith("pages/") for item in activity))

    def test_module_visual_records_reuse_universe_visibility_policy(self) -> None:
        with self.assertRaises(Denied):
            self.service.module_records(self.student, self.institution, "question_bank")
        staff_rows = self.service.module_records(self.admin, self.institution, "question_bank")
        self.assertGreater(len(staff_rows), 0)
        self.assertIn("payload", staff_rows[0])

    def test_reports_export_real_rows_and_never_claim_scheduling(self) -> None:
        rows = self.service.report_rows(self.admin, self.institution, "attendance")
        self.assertGreater(len(rows), 0)
        self.assertTrue(self.service.export_csv(rows).startswith(b"\xef\xbb\xbf"))
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(self.service.export_xlsx(rows, "Attendance"))))
        self.assertTrue(self.service.export_pdf(rows, "Attendance").startswith(b"%PDF"))
        saved = self.service.save_report(self.admin, self.institution, "attendance", "Weekly attendance", schedule={"frequency": "Weekly"})
        self.assertEqual(saved["schedule_state"], "configuration_required")
        with self.assertRaises(Denied):
            self.service.report_rows(self.student, self.institution, "attendance")

    def test_presentation_acknowledgement_and_owner_boundary(self) -> None:
        with self.assertRaises(EducationError):
            self.service.start_presentation(self.admin, self.institution, self.student, "student-learning-lifecycle", False)
        run = self.service.start_presentation(self.admin, self.institution, self.student, "student-learning-lifecycle", True)
        self.assertEqual(run["state"], "active")
        with self.assertRaises(Denied):
            self.service.finish_presentation(self.student, run["id"])
        self.assertEqual(self.service.finish_presentation(self.admin, run["id"])["state"], "completed")

    def test_student_visual_aggregates_do_not_leak_other_learners_or_question_bank(self) -> None:
        snapshot = self.service.dashboard_snapshot(self.student, self.institution)
        self.assertTrue(all(row.get("module_key") != "question_bank" for row in snapshot["universe"]))
        self.assertTrue(all(int(row.get("submissions") or 0) <= 1 for row in snapshot["assignments"]))
        self.assertTrue(all(int(row.get("enrollments") or 0) <= 1 for row in snapshot["courses"]))
        student_activity = self.service.activity_stream(self.student, self.institution, limit=200)
        titles = "\n".join(str(row.get("title")) for row in student_activity)
        self.assertNotIn("demo-cohort-student-", titles)
    def test_accessible_text_and_status_helpers_are_truthful(self) -> None:
        self.assertIn("highest Feb at 7", chart_text_alternative([{"Month": "Jan", "Records": 3}, {"Month": "Feb", "Records": 7}], "Month", "Records"))
        self.assertEqual(provider_status(False, False)["state"], "configuration_required")
        self.assertTrue(workflow_state(("Draft", "Review", "Published"), "Review")[1]["current"])


if __name__ == "__main__":
    unittest.main()