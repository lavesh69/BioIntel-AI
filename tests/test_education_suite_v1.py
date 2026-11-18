from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from biointel.education.education_suite import EducationSuiteError, EducationSuiteService


class EducationSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = EducationSuiteService(root / "suite.sqlite3", root / "storage")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_interactive_lesson_scoring(self):
        lesson = self.service.create_lesson(
            "inst", "bio", "DNA basics", "Intro",
            [{"type": "mcq", "prompt": "DNA base?", "options": ["A", "U"], "answer": "A", "points": 2}],
            "teacher", True,
        )
        result = self.service.submit_lesson_attempt(lesson["id"], "student", {lesson["activities"][0]["id"]: "A"})
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["max_score"], 2)

    def test_versioned_notes_and_comments(self):
        note = self.service.save_note("inst", "bio", "Shared", "v1", "teacher")
        updated = self.service.save_note("inst", "bio", "Shared", "v2", "student", note["id"])
        self.service.add_note_comment(note["id"], "teacher", "reviewed")
        loaded = self.service.get_note(note["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(loaded["revisions"]), 2)
        self.assertEqual(len(loaded["comments"]), 1)

    def test_question_bank_and_assessment(self):
        question = self.service.create_question("inst", "bio", "numeric", "2+3", 5, "teacher", points=3)
        assessment = self.service.create_assessment("inst", "bio", "Quiz", [question["id"]], "teacher", publish=True)
        result = self.service.submit_assessment(assessment["id"], "student", {question["id"]: 5})
        self.assertEqual(result["score"], 3)

    def test_qa_acceptance(self):
        question = self.service.create_qa_question("inst", "bio", "Question", "Details", "student")
        answer = self.service.answer_qa_question(question["id"], "Answer", "teacher")
        accepted = self.service.accept_qa_answer(question["id"], answer["id"], "student")
        self.assertEqual(accepted["accepted_answer_id"], answer["id"])
        with self.assertRaises(EducationSuiteError):
            self.service.accept_qa_answer(question["id"], answer["id"], "other")

    def test_learning_records_export(self):
        self.service.track_event("inst", "student", "lesson_opened", "lesson", "l1", {"progress": 0.5})
        records = self.service.export_learning_records("inst")
        self.assertEqual(records[0]["actor"]["account"]["name"], "student")
        self.assertIn("lesson_opened", records[0]["verb"]["id"])

    def test_offline_resource_hash(self):
        resource = self.service.add_offline_resource("inst", "bio", "File", "", b"abc", "a.txt", "teacher", "text/plain")
        self.assertEqual(resource["sha256"], "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertTrue(Path(resource["path"]).is_file())

    def test_connector_configuration_is_biointel_named(self):
        item = self.service.configure_connector("inst", "live_class", "BioIntel Live Classroom", "http://127.0.0.1:9", "admin")
        self.assertEqual(item["display_name"], "BioIntel Live Classroom")
        self.assertEqual(item["connector_type"], "live_class")

    def test_local_python_runner(self):
        result = self.service.run_python("print(sum(map(int,input().split())))", "2 3\n")
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.strip(), "5")
        with self.assertRaises(EducationSuiteError):
            self.service.run_python("import os\nprint(os.getcwd())")

    def test_code_task_grading(self):
        task = self.service.create_code_task(
            "inst", "bio", "Add", "Add two integers",
            [{"stdin": "2 3\n", "expected_stdout": "5"}], "teacher",
        )
        result = self.service.submit_code(task["id"], "student", "print(sum(map(int,input().split())))")
        self.assertEqual(result["score"], 100)

    def test_notebook_grading(self):
        notebook = {"cells": [{"cell_type": "code", "source": ["print('BioIntel')"]}]}
        result = self.service.grade_notebook(json.dumps(notebook).encode(), [{"stdin": "", "expected_stdout": "BioIntel"}])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["code_cells"], 1)

    def test_similarity_is_review_indicator(self):
        result = self.service.code_similarity("x=1\nprint(x)", "y=2\nprint(y)")
        self.assertIn("not a plagiarism verdict", result["note"])
        self.assertGreaterEqual(result["similarity"], 0)

    def test_resume_and_application_documents(self):
        resume = self.service.save_resume("student", "A Student", "Biotechnology", {"skills": ["Python", "Genomics"]})
        self.assertIn("Genomics", self.service.resume_markdown(resume))
        document = self.service.save_application_document("student", "Statement of purpose", "Program", "Evidence")
        self.assertEqual(document["owner_id"], "student")

    def test_credentials(self):
        credential = self.service.issue_credential("inst", "student", "Genomics", "Skill badge", "report-1", "BioIntel Education")
        self.assertEqual(credential["recipient_id"], "student")
        self.assertEqual(len(self.service.list_credentials("inst", "student")), 1)

    def test_unified_search(self):
        self.service.create_lesson("inst", "bio", "Genome lesson", "Sequence analysis", [], "teacher", True)
        results = self.service.search("inst", "Genome")
        self.assertEqual(results[0]["kind"], "lesson")

    def test_roster_and_gradebook_interchange(self):
        rows = self.service.roster_from_csv(b"user_id,name,role\nu1,Student,student\n")
        self.assertEqual(rows[0]["user_id"], "u1")
        data = self.service.gradebook_csv([{"learner_id": "u1", "assessment_id": "a1", "score": 8, "max_score": 10, "submitted_at": "now"}])
        self.assertIn(b"learner_id", data)


class EducationSuiteIntegrationFilesTests(unittest.TestCase):
    def test_ui_and_routes_are_wired(self):
        root = Path(__file__).resolve().parents[1]
        classroom = (root / "src/biointel/education/classroom_ui.py").read_text(encoding="utf-8")
        career = (root / "src/biointel/education/career_hub_ui.py").read_text(encoding="utf-8")
        navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
        self.assertIn("render_classroom_suite", classroom)
        self.assertIn("Application studio", career)
        self.assertIn("pages/356_BioIntel_Education_Suite.py", navigation)
        self.assertTrue((root / "SETUP_BIOINTEL_EDUCATION_SERVICES_WINDOWS.bat").is_file())


if __name__ == "__main__":
    unittest.main()
