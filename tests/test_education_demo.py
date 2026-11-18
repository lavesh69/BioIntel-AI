from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from biointel.education.demo import DEMO_BADGE, DEMO_SEED_VERSION, manifest, reset_demo, seed_demo
from biointel.education.demo.manifest import COUNTED_TABLES, SYNTHETIC_FIELDS
from biointel.education.demo.reset import validate_demo_targets
from biointel.education.paths import education_paths
from biointel.education.universe import MODULES


class EducationDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="BioIntel Demo With Spaces ", dir=Path(__file__).resolve().parent)
        self.previous_data_root = os.environ.get("BIOINTEL_USER_DATA_DIR")
        os.environ["BIOINTEL_USER_DATA_DIR"] = str(Path(self.temp.name) / "User Data With Spaces")

    def tearDown(self) -> None:
        reset_demo()
        if self.previous_data_root is None:
            os.environ.pop("BIOINTEL_USER_DATA_DIR", None)
        else:
            os.environ["BIOINTEL_USER_DATA_DIR"] = self.previous_data_root
        self.temp.cleanup()

    @staticmethod
    def database() -> Path:
        return education_paths(demo=True)[0]

    def scalar(self, sql: str, args: tuple[object, ...] = ()) -> int:
        with closing(sqlite3.connect(self.database())) as db:
            return int(db.execute(sql, args).fetchone()[0])

    def test_seed_builds_full_typed_demo_workspace(self) -> None:
        result = seed_demo()
        counts = result["counts"]
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(result["seed_version"], DEMO_SEED_VERSION)
        self.assertEqual(result["badge"], DEMO_BADGE)
        minima = {
            "institutions": 2, "subjects": 8, "memberships": 74,
            "attendance_sessions": 90, "attendance_records": 90,
            "assignments": 15, "submissions": 100, "examinations": 6,
            "courses": 8, "lectures": 30, "academy_enrollments": 50,
            "watch_progress": 50, "publications": 40, "news_items": 25,
            "alerts": 10, "education_universe_records": 20,
        }
        for table, minimum in minima.items():
            self.assertGreaterEqual(counts[table], minimum, table)
        self.assertEqual(counts["education_universe_records"], len(MODULES))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM memberships WHERE user_id LIKE 'demo-cohort-teacher-%'"), 10)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM memberships WHERE user_id LIKE 'demo-cohort-student-%'"), 50)
        self.assertEqual(self.scalar("SELECT COUNT(DISTINCT session_date) FROM attendance_sessions"), 90)

    def test_every_seeded_record_has_permanent_synthetic_metadata(self) -> None:
        seeded = seed_demo()
        with closing(sqlite3.connect(self.database())) as db:
            db.row_factory = sqlite3.Row
            for table, count in seeded["counts"].items():
                actual = db.execute("SELECT COUNT(*) FROM education_demo_entities WHERE entity_table=?", (table,)).fetchone()[0]
                self.assertEqual(actual, count, table)
            rows = db.execute("SELECT * FROM education_demo_entities").fetchall()
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(row["is_demo"], 1)
                self.assertEqual(row["data_origin"], "synthetic_demo")
                self.assertEqual(row["seed_version"], DEMO_SEED_VERSION)
                self.assertEqual(row["created_by_demo_seed"], 1)
                self.assertTrue(row["demo_scenario"])
                self.assertEqual(row["created_at"], row["updated_at"])
            payloads = db.execute("SELECT module_key,payload_json FROM education_universe_records").fetchall()
            self.assertEqual({row["module_key"] for row in payloads}, {module.key for module in MODULES})
            for row in payloads:
                payload = json.loads(row["payload_json"])
                self.assertTrue(all(field in payload for field in SYNTHETIC_FIELDS))
                self.assertIs(payload["is_demo"], True)
                self.assertEqual(payload["data_origin"], "synthetic_demo")

    def test_repeat_seed_is_idempotent_and_versioned(self) -> None:
        first = seed_demo()
        with closing(sqlite3.connect(self.database())) as db:
            first_ids = [row[0] for row in db.execute("SELECT id FROM submissions ORDER BY id")]
        second = seed_demo()
        with closing(sqlite3.connect(self.database())) as db:
            second_ids = [row[0] for row in db.execute("SELECT id FROM submissions ORDER BY id")]
            stored = json.loads(db.execute("SELECT manifest_json FROM education_demo_manifest WHERE seed_version=?", (DEMO_SEED_VERSION,)).fetchone()[0])
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(first_ids, second_ids)
        self.assertGreaterEqual(len(second_ids), 100)
        self.assertEqual(stored["counts"], second["counts"])

    def test_manifest_supports_institution_and_persona_switching(self) -> None:
        seed_demo()
        data = manifest()
        self.assertEqual([item["id"] for item in data["institutions"]], ["demo-inst-university", "demo-inst-school"])
        self.assertEqual(len(data["personas"]), 14)
        self.assertEqual(len({item["persona_type"] for item in data["personas"]}), 14)
        self.assertTrue(all(item["is_fictional"] is True and item["switch_label"] for item in data["personas"]))
        self.assertEqual({item["institution_id"] for item in data["personas"]}, {"demo-inst-university", "demo-inst-school"})
        for item in data["personas"]:
            self.assertGreaterEqual(self.scalar("SELECT COUNT(*) FROM memberships WHERE user_id=? AND institution_id=?", (item["id"], item["institution_id"])), 1)
        self.assertFalse(any(item["id"].startswith("demo-cohort-") for item in data["personas"]))
        self.assertEqual({scenario["institution_id"] for scenario in data["scenarios"]}, {"demo-inst-university", "demo-inst-school"})

    def test_manifest_counts_match_database(self) -> None:
        seed_demo()
        data = manifest()
        with closing(sqlite3.connect(self.database())) as db:
            for table in COUNTED_TABLES:
                actual = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                self.assertEqual(data["counts"][table], actual, table)
        self.assertEqual(data["summary"]["records"], sum(data["counts"].values()))
        self.assertEqual(data["summary"]["universe_modules"], 20)

    def test_reset_removes_only_demo_targets_and_preserves_production(self) -> None:
        production_db, production_media = education_paths(demo=False)
        production_db.parent.mkdir(parents=True, exist_ok=True)
        production_db.write_bytes(b"production-marker")
        production_media.mkdir(parents=True, exist_ok=True)
        production_file = production_media / "keep.txt"
        production_file.write_text("keep", encoding="utf-8")
        seeded = seed_demo()
        demo_db = Path(seeded["database_path"])
        demo_media = Path(seeded["media_path"])
        result = reset_demo()
        self.assertEqual(result["status"], "reset")
        self.assertFalse(demo_db.exists())
        self.assertFalse(demo_media.exists())
        self.assertEqual(production_db.read_bytes(), b"production-marker")
        self.assertEqual(production_file.read_text(encoding="utf-8"), "keep")
        self.assertEqual(reset_demo()["removed"], [])

    def test_demo_target_validation_rejects_unsafe_paths(self) -> None:
        education_root = Path(self.temp.name) / "User Data" / "education"
        good_db, good_media = validate_demo_targets(education_root / "education-demo.sqlite3", education_root / "demo-media")
        self.assertEqual(good_db.name, "education-demo.sqlite3")
        self.assertEqual(good_media.name, "demo-media")
        with self.assertRaises(ValueError):
            validate_demo_targets(education_root / "education.sqlite3", education_root / "demo-media")
        with self.assertRaises(ValueError):
            validate_demo_targets(education_root / "education-demo.sqlite3", education_root / "media")
        with self.assertRaises(ValueError):
            validate_demo_targets(education_root / "education-demo.sqlite3", Path(self.temp.name) / "other" / "demo-media")

    def test_seed_and_reset_cli_emit_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        seeded = subprocess.run([sys.executable, str(root / "scripts" / "seed_biointel_education_demo.py"), "--project-root", str(root)], check=True, capture_output=True, text=True, env=env)
        seed_result = json.loads(seeded.stdout)
        self.assertEqual(seed_result["status"], "seeded")
        self.assertEqual(seed_result["counts"]["education_universe_records"], 20)
        reset = subprocess.run([sys.executable, str(root / "scripts" / "reset_biointel_education_demo.py"), "--project-root", str(root)], check=True, capture_output=True, text=True, env=env)
        self.assertEqual(json.loads(reset.stdout)["status"], "reset")
        for name in ("SEED_EDUCATION_DEMO_WINDOWS.bat", "RESET_EDUCATION_DEMO_WINDOWS.bat"):
            text = (root / name).read_text(encoding="ascii")
            self.assertIn("%~dp0", text)
            self.assertIn('"%BIOINTEL_DEMO_PYTHON%"', text)


if __name__ == "__main__":
    unittest.main()

