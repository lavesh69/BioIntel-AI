"""Demo-workspace manifest generated from the durable demo database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ..paths import education_paths
from .scenarios import INSTITUTIONS, SCENARIOS, persona_manifest

DEMO_SEED_VERSION = "education-demo-2026.07-v1"
DEMO_BADGE = "Synthetic demonstration workspace - not real institutional data."
DEMO_TIMESTAMP = "2026-07-15T09:00:00+00:00"
SYNTHETIC_FIELDS = (
    "is_demo", "data_origin", "demo_scenario", "seed_version",
    "created_by_demo_seed", "demo_institution_id", "demo_persona_id",
    "created_at", "updated_at",
)
COUNTED_TABLES = (
    "institutions", "memberships", "academic_units", "subjects", "enrollments",
    "teacher_assignments", "guardian_links", "timetable_entries",
    "attendance_sessions", "attendance_records", "materials", "assignments",
    "submissions", "grades", "examinations", "results", "circulars",
    "academic_events", "pulse_sources", "publications", "news_items",
    "saved_research", "alerts", "educator_profiles", "courses",
    "course_sections", "lectures", "content_rights", "academy_enrollments",
    "watch_progress", "quizzes", "quiz_attempts", "education_universe_records",
)


def _counts(database_path: Path) -> dict[str, int]:
    if not database_path.is_file():
        return {}
    with closing(sqlite3.connect(database_path)) as db:
        existing = {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            table: int(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in COUNTED_TABLES if table in existing
        }


def manifest(candidate_project_root: str | Path | None = None) -> dict[str, Any]:
    database_path, media_path = education_paths(candidate_project_root, demo=True)
    counts = _counts(database_path)
    return {
        "seed_version": DEMO_SEED_VERSION,
        "badge": DEMO_BADGE,
        "is_demo": True,
        "data_origin": "synthetic_demo",
        "created_by_demo_seed": True,
        "database_path": str(database_path),
        "media_path": str(media_path),
        "institutions": [dict(item) for item in INSTITUTIONS],
        "personas": persona_manifest(),
        "scenarios": [dict(item) for item in SCENARIOS],
        "synthetic_metadata_fields": list(SYNTHETIC_FIELDS),
        "counts": counts,
        "summary": {
            "institutions": len(INSTITUTIONS),
            "personas": len(persona_manifest()),
            "scenarios": len(SCENARIOS),
            "universe_modules": counts.get("education_universe_records", 0),
            "records": sum(counts.values()),
        },
    }

