"""Build the versioned, deterministic Education demonstration workspace."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from ..paths import education_paths
from ..platform import EducationPlatform
from ..universe import EducationUniverse, MODULES
from .generators import synthetic_metadata
from .manifest import (
    COUNTED_TABLES,
    DEMO_BADGE,
    DEMO_SEED_VERSION,
    DEMO_TIMESTAMP,
    manifest,
)
from .reset import reset_demo, validate_demo_targets
from .scenarios import INSTITUTIONS, PERSONAS

_DEMO_SCHEMA = """
CREATE TABLE IF NOT EXISTS education_demo_entities(
 entity_table TEXT NOT NULL, entity_id TEXT NOT NULL,
 is_demo INTEGER NOT NULL CHECK(is_demo=1), data_origin TEXT NOT NULL,
 demo_scenario TEXT NOT NULL, seed_version TEXT NOT NULL,
 created_by_demo_seed INTEGER NOT NULL CHECK(created_by_demo_seed=1),
 demo_institution_id TEXT NOT NULL DEFAULT '', demo_persona_id TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(entity_table,entity_id));
CREATE INDEX IF NOT EXISTS idx_demo_entities_scenario
 ON education_demo_entities(demo_scenario,demo_institution_id,demo_persona_id);
CREATE TABLE IF NOT EXISTS education_demo_manifest(
 seed_version TEXT PRIMARY KEY, badge TEXT NOT NULL, manifest_json TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def _insert_many(db: Any, table: str, columns: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> None:
    values = tuple(rows)
    if not values:
        return
    placeholders = ",".join("?" for _ in columns)
    db.executemany(
        f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({placeholders})',
        values,
    )


def _seed_classroom(db: Any, media_path: Path) -> None:
    t = DEMO_TIMESTAMP
    _insert_many(db, "institutions", ("id", "name", "kind", "timezone", "state", "created_at", "updated_at"), ((i["id"], i["name"], i["kind"], i["timezone"], "active", t, t) for i in INSTITUTIONS))

    cohort_teachers = tuple(
        (f"demo-cohort-teacher-{n:02d}", "demo-inst-university" if n <= 6 else "demo-inst-school", "lecturer" if n <= 6 else "subject_teacher")
        for n in range(1, 11)
    )
    cohort_students = tuple(
        (f"demo-cohort-student-{n:02d}", "demo-inst-university" if n <= 30 else "demo-inst-school", "university_student" if n <= 30 else "school_student")
        for n in range(1, 51)
    )
    membership_rows = [
        (f"demo-membership-persona-{n:02d}", p[4], p[0], p[3], "active", t, t)
        for n, p in enumerate(PERSONAS, 1)
    ]
    membership_rows.extend((f"demo-membership-teacher-{n:02d}", inst, uid, role, "active", t, t) for n, (uid, inst, role) in enumerate(cohort_teachers, 1))
    membership_rows.extend((f"demo-membership-student-{n:02d}", inst, uid, role, "active", t, t) for n, (uid, inst, role) in enumerate(cohort_students, 1))
    _insert_many(db, "memberships", ("id", "institution_id", "user_id", "role", "state", "created_at", "updated_at"), membership_rows)

    units = (
        ("demo-unit-school-biotech", "demo-inst-university", None, "school", "School of Biotechnology"),
        ("demo-unit-bioinformatics", "demo-inst-university", "demo-unit-school-biotech", "department", "Department of Bioinformatics"),
        ("demo-unit-molecular", "demo-inst-university", "demo-unit-school-biotech", "department", "Department of Molecular Biology"),
        ("demo-unit-computational", "demo-inst-university", "demo-unit-school-biotech", "department", "Department of Computational Biology"),
        ("demo-unit-biomedical", "demo-inst-university", "demo-unit-school-biotech", "department", "Department of Biomedical Sciences"),
        ("demo-unit-research", "demo-inst-university", None, "cell", "Research and Innovation Cell"),
        ("demo-unit-library", "demo-inst-university", None, "library", "Central Scientific Library"),
        ("demo-unit-career", "demo-inst-university", None, "cell", "Career and Internship Cell"),
        ("demo-unit-class-9", "demo-inst-school", None, "class", "Class 9"),
        ("demo-unit-class-10", "demo-inst-school", None, "class", "Class 10"),
        ("demo-unit-class-11", "demo-inst-school", None, "class", "Class 11"),
        ("demo-unit-class-12", "demo-inst-school", None, "class", "Class 12"),
        ("demo-unit-school-biology", "demo-inst-school", None, "department", "Biology Department"),
        ("demo-unit-science-lab", "demo-inst-school", None, "laboratory", "Science Laboratory"),
        ("demo-unit-school-admin", "demo-inst-school", None, "administration", "Academic Administration"),
        ("demo-unit-student-support", "demo-inst-school", None, "support", "Student Support Office"),
        ("demo-unit-science-club", "demo-inst-school", None, "club", "Science Club"),
    )
    _insert_many(db, "academic_units", ("id", "institution_id", "parent_id", "unit_type", "name", "academic_year", "state", "created_at", "updated_at"), ((a, b, c, d, e, "2026-27", "active", t, t) for a, b, c, d, e in units))
    subjects = (
        ("demo-subject-biotech", "demo-inst-university", "demo-unit-school-biotech", "BIO-101", "Biotechnology Foundations"),
        ("demo-subject-bioinfo", "demo-inst-university", "demo-unit-bioinformatics", "BIN-210", "Bioinformatics Methods"),
        ("demo-subject-molecular", "demo-inst-university", "demo-unit-molecular", "MOL-220", "Molecular Biology"),
        ("demo-subject-computational", "demo-inst-university", "demo-unit-computational", "CBI-230", "Computational Biology"),
        ("demo-subject-biomedical", "demo-inst-university", "demo-unit-biomedical", "BMS-240", "Biomedical Data Literacy"),
        ("demo-subject-school-biology", "demo-inst-school", "demo-unit-class-9", "BIO-09", "Foundations of Biology"),
        ("demo-subject-school-cell", "demo-inst-school", "demo-unit-class-10", "BIO-10", "Cell Biology"),
        ("demo-subject-school-genetics", "demo-inst-school", "demo-unit-class-11", "BIO-11", "Genetics and Inheritance"),
    )
    _insert_many(db, "subjects", ("id", "institution_id", "unit_id", "code", "name", "syllabus", "state", "created_at", "updated_at"), ((a, b, c, d, e, "Synthetic demonstration syllabus with safe learning outcomes.", "active", t, t) for a, b, c, d, e in subjects))
    subject_ids = [row[0] for row in subjects]
    subject_institution = {row[0]: row[1] for row in subjects}
    teacher_by_subject = {
        "demo-subject-biotech": "demo-persona-professor", "demo-subject-bioinfo": "demo-persona-department-head",
        "demo-subject-molecular": "demo-persona-lab-instructor", "demo-subject-computational": "demo-persona-research-mentor",
        "demo-subject-biomedical": "demo-persona-professor", "demo-subject-school-biology": "demo-persona-teacher",
        "demo-subject-school-cell": "demo-persona-academic-coordinator", "demo-subject-school-genetics": "demo-persona-teacher",
    }
    teacher_assignments = [(f"demo-teacher-assignment-persona-{n:02d}", subject_institution[sid], sid, teacher, "active", t, t) for n, (sid, teacher) in enumerate(teacher_by_subject.items(), 1)]
    teacher_assignments.extend((f"demo-teacher-assignment-cohort-{n:02d}", inst, subject_ids[(n-1) % 5] if inst == "demo-inst-university" else subject_ids[5 + (n-7) % 3], uid, "active", t, t) for n, (uid, inst, _) in enumerate(cohort_teachers, 1))
    _insert_many(db, "teacher_assignments", ("id", "institution_id", "subject_id", "teacher_id", "state", "created_at", "updated_at"), teacher_assignments)

    subject_students: dict[str, list[str]] = {sid: ["demo-persona-university-student" if subject_institution[sid] == "demo-inst-university" else "demo-persona-school-student"] for sid in subject_ids}
    for n, (student_id, institution_id, _) in enumerate(cohort_students, 1):
        candidates = subject_ids[:5] if institution_id == "demo-inst-university" else subject_ids[5:]
        subject_students[candidates[(n-1) % len(candidates)]].append(student_id)
    enrollment_rows = []
    enrollment_number = 0
    for subject_id in subject_ids:
        for student_id in subject_students[subject_id]:
            enrollment_number += 1
            enrollment_rows.append((f"demo-enrollment-{enrollment_number:03d}", subject_institution[subject_id], subject_id, student_id, "active", t, t))
    _insert_many(db, "enrollments", ("id", "institution_id", "subject_id", "student_id", "state", "created_at", "updated_at"), enrollment_rows)
    _insert_many(db, "guardian_links", ("id", "institution_id", "guardian_id", "student_id", "verified", "student_consent", "state", "created_at", "updated_at"), (("demo-guardian-link-01", "demo-inst-school", "demo-persona-guardian", "demo-persona-school-student", 1, 1, "active", t, t),))

    for n, subject_id in enumerate(subject_ids, 1):
        institution_id = subject_institution[subject_id]
        teacher_id = teacher_by_subject[subject_id]
        _insert_many(db, "timetable_entries", ("id", "institution_id", "subject_id", "teacher_id", "student_group", "room", "starts_at", "ends_at", "meeting_id", "state", "created_at", "updated_at"), ((f"demo-timetable-{n:02d}", institution_id, subject_id, teacher_id, "Demo Cohort", f"Room {100+n}", f"2026-07-{14+n:02d}T09:00:00+05:30", f"2026-07-{14+n:02d}T10:00:00+05:30", "", "scheduled", t, t),))
    first_day = date(2026, 4, 1)
    for n in range(1, 91):
        subject_id = subject_ids[(n-1) % len(subject_ids)]
        institution_id = subject_institution[subject_id]
        student_pool = subject_students[subject_id]
        student_id = student_pool[((n-1) // len(subject_ids)) % len(student_pool)]
        teacher_id = teacher_by_subject[subject_id]
        session_date = (first_day + timedelta(days=n-1)).isoformat()
        _insert_many(db, "attendance_sessions", ("id", "institution_id", "subject_id", "teacher_id", "session_date", "period", "state", "created_at", "updated_at"), ((f"demo-attendance-session-{n:03d}", institution_id, subject_id, teacher_id, session_date, f"Period {(n-1) % 6 + 1}", "locked", t, t),))
        _insert_many(db, "attendance_records", ("id", "institution_id", "session_id", "student_id", "status", "note", "marked_by", "created_at", "updated_at"), ((f"demo-attendance-record-{n:03d}", institution_id, f"demo-attendance-session-{n:03d}", student_id, "late" if n % 13 == 0 else "present", "Synthetic attendance example.", teacher_id, t, t),))

    media_path.mkdir(parents=True, exist_ok=True)
    material_dir = media_path / "shared-materials"
    material_dir.mkdir(parents=True, exist_ok=True)
    for n, (subject_id, institution_id, _, code, name) in enumerate(subjects, 1):
        material_path = material_dir / f"demo-material-{n:02d}.txt"
        content = f"{DEMO_BADGE}\n{name}\nSafe synthetic learning notes for {code}.\n"
        material_path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _insert_many(db, "materials", ("id", "institution_id", "subject_id", "owner_id", "title", "file_name", "mime_type", "size_bytes", "sha256", "storage_path", "download_allowed", "state", "created_at", "updated_at"), ((f"demo-material-{n:02d}", institution_id, subject_id, teacher_by_subject[subject_id], f"{name} learning guide", material_path.name, "text/plain", material_path.stat().st_size, digest, str(material_path), 1, "published", t, t),))

    submission_number = 0
    for n in range(1, 16):
        subject_id = subject_ids[(n-1) % len(subject_ids)]
        institution_id = subject_institution[subject_id]
        teacher_id = teacher_by_subject[subject_id]
        title = next(row[4] for row in subjects if row[0] == subject_id)
        due_at = f"2026-08-{3+n:02d}T17:00:00+05:30"
        assignment_id = f"demo-assignment-{n:02d}"
        _insert_many(db, "assignments", ("id", "institution_id", "subject_id", "creator_id", "title", "instructions", "due_at", "max_marks", "allowed_types", "late_policy", "state", "created_at", "updated_at"), ((assignment_id, institution_id, subject_id, teacher_id, f"{title} evidence reflection {n}", "Use only the synthetic course evidence supplied in this workspace.", due_at, 100.0, '["text/plain"]', "accept_with_flag", "published", t, t),))
        for student_id in subject_students[subject_id]:
            submission_number += 1
            submission_id = f"demo-submission-{submission_number:03d}"
            _insert_many(db, "submissions", ("id", "institution_id", "assignment_id", "student_id", "body", "file_path", "submitted_at", "state", "created_at", "updated_at"), ((submission_id, institution_id, assignment_id, student_id, "Synthetic evidence reflection submitted for demonstration.", "", t, "submitted", t, t),))
            _insert_many(db, "grades", ("id", "institution_id", "submission_id", "grader_id", "marks", "feedback", "state", "created_at", "updated_at"), ((f"demo-grade-{submission_number:03d}", institution_id, submission_id, teacher_id, float(70 + submission_number % 26), "Evidence was clear; expand the method rationale.", "released", t, t),))

    for n in range(1, 7):
        subject_id = subject_ids[n-1]
        institution_id = subject_institution[subject_id]
        teacher_id = teacher_by_subject[subject_id]
        exam_id = f"demo-examination-{n:02d}"
        _insert_many(db, "examinations", ("id", "institution_id", "subject_id", "creator_id", "title", "max_marks", "starts_at", "ends_at", "state", "created_at", "updated_at"), ((exam_id, institution_id, subject_id, teacher_id, f"Demonstration assessment {n}", 100.0, f"2026-08-{10+n:02d}T09:00:00+05:30", f"2026-08-{10+n:02d}T11:00:00+05:30", "published", t, t),))
        for m, student_id in enumerate(subject_students[subject_id], 1):
            _insert_many(db, "results", ("id", "institution_id", "examination_id", "student_id", "marks", "grade", "published", "locked", "created_at", "updated_at"), ((f"demo-result-{n:02d}-{m:02d}", institution_id, exam_id, student_id, float(72 + (n+m) % 22), "A" if (n+m) % 3 else "B+", 1, 1, t, t),))

    circulars = (
        ("demo-circular-01", "demo-inst-university", "demo-persona-university-admin", "DEMO-U-001", "Research orientation week"),
        ("demo-circular-02", "demo-inst-university", "demo-persona-university-admin", "DEMO-U-002", "Library evidence workshop"),
        ("demo-circular-03", "demo-inst-school", "demo-persona-school-admin", "DEMO-S-001", "Science club showcase"),
        ("demo-circular-04", "demo-inst-school", "demo-persona-school-admin", "DEMO-S-002", "Guardian learning review"),
    )
    _insert_many(db, "circulars", ("id", "institution_id", "creator_id", "circular_number", "title", "content", "audience_json", "priority", "state", "approved_by", "published_at", "created_at", "updated_at"), ((a, b, c, d, e, f"{DEMO_BADGE} {e}.", '["all_members"]', "normal", "published", c, t, t, t) for a, b, c, d, e in circulars))
    _insert_many(db, "academic_events", ("id", "institution_id", "title", "event_type", "starts_at", "ends_at", "state", "created_at", "updated_at"), (
        ("demo-event-01", "demo-inst-university", "Synthetic research poster review", "research", "2026-08-21T10:00:00+05:30", "2026-08-21T13:00:00+05:30", "scheduled", t, t),
        ("demo-event-02", "demo-inst-university", "Bioinformatics learning clinic", "support", "2026-08-24T14:00:00+05:30", "2026-08-24T15:00:00+05:30", "scheduled", t, t),
        ("demo-event-03", "demo-inst-school", "Safe simulation showcase", "science_club", "2026-08-22T10:00:00+05:30", "2026-08-22T12:00:00+05:30", "scheduled", t, t),
        ("demo-event-04", "demo-inst-school", "Student support review", "support", "2026-08-25T11:00:00+05:30", "2026-08-25T12:00:00+05:30", "scheduled", t, t),
    ))

def _seed_academy(db: Any) -> None:
    t = DEMO_TIMESTAMP
    educators = (
        ("demo-educator-01", "demo-inst-university", "demo-persona-professor", "Molecular learning and evidence literacy."),
        ("demo-educator-02", "demo-inst-university", "demo-persona-department-head", "Explainable bioinformatics education."),
        ("demo-educator-03", "demo-inst-university", "demo-persona-lab-instructor", "Simulation-only laboratory learning."),
        ("demo-educator-04", "demo-inst-school", "demo-persona-teacher", "School biology and scientific reasoning."),
    )
    _insert_many(db, "educator_profiles", ("id", "institution_id", "user_id", "bio", "verified", "state", "created_at", "updated_at"), ((a, b, c, d, 1, "active", t, t) for a, b, c, d in educators))
    courses = (
        ("demo-course-01", "demo-inst-university", "demo-persona-professor", "Evidence-led Biotechnology", "intermediate"),
        ("demo-course-02", "demo-inst-university", "demo-persona-department-head", "Explainable Bioinformatics", "advanced"),
        ("demo-course-03", "demo-inst-university", "demo-persona-lab-instructor", "Safe Virtual Laboratory Practice", "beginner"),
        ("demo-course-04", "demo-inst-university", "demo-persona-research-mentor", "Research Evidence Foundations", "intermediate"),
        ("demo-course-05", "demo-inst-university", "demo-persona-professor", "Molecular Data Interpretation", "intermediate"),
        ("demo-course-06", "demo-inst-university", "demo-persona-department-head", "Reproducible Scientific Computing", "advanced"),
        ("demo-course-07", "demo-inst-school", "demo-persona-teacher", "Biology through Scientific Evidence", "beginner"),
        ("demo-course-08", "demo-inst-school", "demo-persona-academic-coordinator", "Genetics Learning Studio", "beginner"),
    )
    _insert_many(db, "courses", ("id", "institution_id", "educator_id", "title", "description", "difficulty", "state", "created_at", "updated_at"), ((a, b, c, d, f"{DEMO_BADGE} {d}.", e, "published", t, t) for a, b, c, d, e in courses))
    lecture_number = 0
    lecture_counts = (4, 4, 4, 4, 4, 4, 3, 3)
    for n, (course_id, institution_id, educator_id, title, _) in enumerate(courses, 1):
        _insert_many(db, "course_sections", ("id", "course_id", "parent_id", "section_type", "title", "position", "created_at", "updated_at"), ((f"demo-section-{n:02d}-01", course_id, None, "module", "Foundations", 1, t, t), (f"demo-section-{n:02d}-02", course_id, None, "module", "Evidence review", 2, t, t)))
        rights_id = f"demo-rights-{n:02d}"
        _insert_many(db, "content_rights", ("id", "institution_id", "owner_name", "educator_id", "license", "rights_confirmed", "third_party_declaration", "download_allowed", "created_at", "updated_at"), ((rights_id, institution_id, "BioIntel Synthetic Demo", educator_id, "CC0 synthetic demonstration metadata", 1, "No third-party media is included.", 0, t, t),))
        first_lecture_id = ""
        for position in range(1, lecture_counts[n-1] + 1):
            lecture_number += 1
            lecture_id = f"demo-lecture-{lecture_number:02d}"
            first_lecture_id = first_lecture_id or lecture_id
            _insert_many(db, "lectures", ("id", "institution_id", "course_id", "educator_id", "title", "description", "video_path", "sha256", "size_bytes", "mime_type", "processing_state", "rights_id", "state", "created_at", "updated_at"), ((lecture_id, institution_id, course_id, educator_id, f"{title}: lesson {position}", "Synthetic lecture metadata; no fake processed media or provider status.", "", "", 0, "", "configuration_required", rights_id, "draft", t, t),))
        cohort_start = 1 if institution_id == "demo-inst-university" else 31
        switch_student = "demo-persona-university-student" if institution_id == "demo-inst-university" else "demo-persona-school-student"
        students = [switch_student] + [f"demo-cohort-student-{cohort_start + offset:02d}" for offset in range(6)]
        for m, student_id in enumerate(students, 1):
            _insert_many(db, "academy_enrollments", ("id", "institution_id", "course_id", "student_id", "state", "created_at", "updated_at"), ((f"demo-academy-enrollment-{n:02d}-{m:02d}", institution_id, course_id, student_id, "active", t, t),))
            _insert_many(db, "watch_progress", ("id", "lecture_id", "user_id", "seconds", "completed", "updated_at"), ((f"demo-watch-{n:02d}-{m:02d}", first_lecture_id, student_id, float(120 + 30*m), 1 if m % 3 == 0 else 0, t),))
        questions = json.dumps([{"prompt": "Which claim is supported by the supplied evidence?", "options": ["A", "B", "C"], "answer": 1}], sort_keys=True)
        _insert_many(db, "quizzes", ("id", "course_id", "creator_id", "title", "questions_json", "state", "created_at", "updated_at"), ((f"demo-quiz-{n:02d}", course_id, educator_id, f"{title} evidence check", questions, "published", t, t),))
        _insert_many(db, "quiz_attempts", ("id", "quiz_id", "student_id", "answers_json", "score", "passed", "created_at"), ((f"demo-quiz-attempt-{n:02d}", f"demo-quiz-{n:02d}", switch_student, "[1]", 100.0, 1, t),))

def _seed_pulse(db: Any) -> None:
    t = DEMO_TIMESTAMP
    sources = (
        ("demo-pulse-source-publications", "BioIntel Synthetic Publication Catalogue", "publication_api", "https://example.invalid/biointel-demo/publications"),
        ("demo-pulse-source-news", "BioIntel Synthetic Biotechnology Bulletin", "rss", "https://example.invalid/biointel-demo/news"),
    )
    _insert_many(db, "pulse_sources", ("id", "name", "source_type", "base_url", "configured", "state", "created_at", "updated_at"), ((a, b, c, d, 0, "active", t, t) for a, b, c, d in sources))
    topics = ("genomics", "biotechnology", "bioinformatics", "molecular biology", "science education", "open science", "proteomics", "systems biology", "data literacy", "research integrity")
    for n in range(1, 41):
        topic = topics[(n-1) % len(topics)]
        metadata = {"is_demo": True, "data_origin": "synthetic_demo", "topic": topic, "source_verification": "synthetic_unverified", "seed_version": DEMO_SEED_VERSION}
        published = (date(2023, 1, 1) + timedelta(days=n*23)).isoformat()
        _insert_many(db, "publications", ("id", "source_id", "doi", "pmid", "title", "abstract_excerpt", "authors_json", "source_url", "published_at", "record_type", "retraction_state", "metadata_json", "created_at", "updated_at"), ((f"demo-publication-{n:02d}", "demo-pulse-source-publications", "", "", f"Synthetic evidence brief {n}: {topic}", f"Clearly labelled synthetic abstract metadata for a {topic} learning scenario.", '["BioIntel Demo Editorial Group"]', f"https://example.invalid/biointel-demo/publications/{n}", published, "synthetic_demo", "none", json.dumps(metadata, sort_keys=True), t, t),))
    for n in range(1, 26):
        topic = topics[(n+2) % len(topics)]
        published = (date(2026, 6, 1) + timedelta(days=n)).isoformat()
        _insert_many(db, "news_items", ("id", "source_id", "external_id", "title", "summary_excerpt", "source_url", "published_at", "topics_json", "created_at", "updated_at"), ((f"demo-news-{n:02d}", "demo-pulse-source-news", f"synthetic-news-{n:02d}", f"Synthetic biotechnology classroom briefing {n}: {topic}", "Synthetic demonstration news summary; not a live report.", f"https://example.invalid/biointel-demo/news/{n}", published, json.dumps([topic]), t, t),))
    for n in range(1, 11):
        user_id = "demo-persona-university-student" if n % 2 else "demo-persona-research-mentor"
        _insert_many(db, "alerts", ("id", "user_id", "query", "resource_type", "state", "created_at", "updated_at"), ((f"demo-alert-{n:02d}", user_id, topics[n-1], "publication" if n % 3 else "all", "active", t, t),))
        _insert_many(db, "saved_research", ("id", "user_id", "resource_type", "resource_id", "created_at"), ((f"demo-saved-research-{n:02d}", user_id, "publication", f"demo-publication-{n:02d}", t),))

def _universe_value(field: str, module_key: str) -> Any:
    values: dict[str, Any] = {
        "evidence": ["demo-attendance-record-01", "demo-assignment-01"],
        "rationale": "Recommendation is based only on synthetic classroom evidence.",
        "expected_outcome": "Learner reviews the evidence and chooses the next activity.",
        "dismissible": True,
        "objective": "Explore a safe scientific concept using a simulation.",
        "safety_briefing": "Simulation only; no physical procedure is supplied.",
        "simulation_only": True,
        "dataset_label": "Synthetic non-clinical learning dataset",
        "method": "Guided educational evidence review",
        "parameters": {"mode": "synthetic_demo", "random_seed": 1560},
        "resource_limit_seconds": 60,
        "request": "Explain the approved lesson evidence and cite it.",
        "ai_generated": True,
        "review_status": "human_review_required",
        "subject_user_id": "demo-persona-university-student",
        "academic_session": "2026-27",
        "source_url": f"https://example.invalid/biointel-demo/{module_key}",
        "license_or_access": "Synthetic metadata only; no copyrighted full text.",
        "academic_level": "undergraduate",
        "research_question": "How does evidence quality affect a classroom conclusion?",
        "ethics_consideration": "Uses fictional people and synthetic non-clinical data only.",
        "rules": "Synthetic judging rubric with transparent scoring.",
        "deadline": "2026-09-30T17:00:00+05:30",
        "eligibility": "Open only inside this synthetic demonstration workspace.",
        "responsible_staff": "demo-persona-lab-instructor",
        "subject": "Biotechnology",
        "learning_outcome": "Distinguish a claim from its supporting evidence.",
        "lecture_id": "demo-lecture-01",
        "processing_status": "configuration_required",
        "metric_definition": "Count of completed synthetic learning activities in the selected date range.",
        "date_range": {"from": "2026-07-01", "to": "2026-07-31"},
        "source_events": ["demo-attendance-record-01", "demo-quiz-attempt-01"],
        "partner_institution_id": "demo-inst-school",
        "terms": "Synthetic, read-only collaboration proposal for demonstration.",
        "provenance": ["demo-publication-01", "demo-assignment-01"],
        "license": "CC0 synthetic demonstration metadata",
        "device_scope": "this_demo_device_only",
        "reason": "Synthetic moderation case for human review training.",
        "review_period": "2026-Q3",
    }
    return values.get(field, f"Synthetic demonstration value for {field}")


def _seed_universe(db: Any, universe: EducationUniverse) -> None:
    t = DEMO_TIMESTAMP
    for n, definition in enumerate(MODULES, 1):
        payload = {field: _universe_value(field, definition.key) for field in definition.required_fields}
        payload.update(synthetic_metadata(
            "student-learning-lifecycle",
            "demo-inst-university",
            "demo-persona-university-admin",
        ))
        universe._validate(definition, definition.record_types[0], payload)
        record_id = f"demo-universe-{n:02d}-{definition.key}"
        visibility = "restricted" if definition.key in {"question_bank", "academic_erp", "safety_moderation"} else definition.default_visibility
        state = "open" if definition.key == "safety_moderation" else "draft"
        _insert_many(db, "education_universe_records", ("id", "module_key", "institution_id", "owner_id", "record_type", "title", "state", "visibility", "payload_json", "source_status", "version", "deleted_at", "created_at", "updated_at"), ((record_id, definition.key, "demo-inst-university", "demo-persona-university-admin", definition.record_types[0], f"Synthetic {definition.name} example", state, visibility, json.dumps(payload, sort_keys=True, separators=(",", ":")), "synthetic_demo", 1, None, t, t),))
        _insert_many(db, "education_universe_events", ("id", "institution_id", "record_id", "actor_id", "event_type", "from_state", "to_state", "detail_json", "created_at"), ((f"demo-universe-event-{n:02d}", "demo-inst-university", record_id, "demo-persona-university-admin", "created", "", state, json.dumps({"is_demo": True, "seed_version": DEMO_SEED_VERSION}, sort_keys=True), t),))


def _entity_context(db: Any, table: str, row: Any) -> tuple[str, str]:
    keys = set(row.keys())
    institution_id = str(row["institution_id"] or "") if "institution_id" in keys else ""
    persona_id = ""
    for column in ("user_id", "owner_id", "actor_id", "creator_id", "teacher_id", "educator_id", "student_id", "grader_id", "reporter_id", "requester_id"):
        if column in keys and str(row[column] or "").startswith("demo-persona-"):
            persona_id = str(row[column])
            break
    if not institution_id and table in {"course_sections", "quizzes"}:
        course_id = str(row["course_id"])
        found = db.execute("SELECT institution_id,educator_id FROM courses WHERE id=?", (course_id,)).fetchone()
        if found:
            institution_id = str(found[0]); persona_id = persona_id or str(found[1])
    if not institution_id and table == "quiz_attempts":
        found = db.execute("SELECT c.institution_id FROM quizzes q JOIN courses c ON c.id=q.course_id WHERE q.id=?", (row["quiz_id"],)).fetchone()
        institution_id = str(found[0]) if found else ""
    return institution_id, persona_id


def _scenario_for(table: str, row: Any) -> str:
    if table in {"pulse_sources", "publications", "news_items", "saved_research", "alerts"}:
        return "student-research-workflow"
    if table in {"educator_profiles", "courses", "course_sections", "lectures", "content_rights", "academy_enrollments", "watch_progress", "quizzes", "quiz_attempts"}:
        return "teacher-course-workflow"
    if table == "education_universe_records":
        module = str(row["module_key"])
        if module in {"digital_library", "research_hub", "open_science", "academic_portfolio"}:
            return "student-research-workflow"
        if module == "lecture_intelligence":
            return "live-lecture-workflow"
    return "student-learning-lifecycle"


def _seed_metadata(db: Any) -> None:
    t = DEMO_TIMESTAMP
    tables = COUNTED_TABLES + ("education_universe_events",)
    for table in tables:
        present = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not present:
            continue
        for row in db.execute(f'SELECT * FROM "{table}"').fetchall():
            institution_id, persona_id = _entity_context(db, table, row)
            db.execute(
                "INSERT INTO education_demo_entities VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (table, str(row["id"]), 1, "synthetic_demo", _scenario_for(table, row),
                 DEMO_SEED_VERSION, 1, institution_id, persona_id, t, t),
            )


def seed_demo(candidate_project_root: str | Path | None = None) -> dict[str, Any]:
    """Rebuild and return the exact versioned synthetic workspace."""
    database_path, media_path = education_paths(candidate_project_root, demo=True)
    database_path, media_path = validate_demo_targets(database_path, media_path)
    reset_demo(candidate_project_root)
    platform = EducationPlatform(database_path, media_path)
    universe = EducationUniverse(platform)
    with platform.db.connection() as db:
        db.executescript(_DEMO_SCHEMA)
        _seed_classroom(db, media_path)
        _seed_academy(db)
        _seed_pulse(db)
        _seed_universe(db, universe)
        _seed_metadata(db)
    result = manifest(candidate_project_root)
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO education_demo_manifest VALUES(?,?,?,?,?)",
            (DEMO_SEED_VERSION, DEMO_BADGE, json.dumps(result, sort_keys=True), DEMO_TIMESTAMP, DEMO_TIMESTAMP),
        )
    if not platform.db.quick_check():
        raise RuntimeError("Education demo database integrity check failed.")
    result["status"] = "seeded"
    result["integrity"] = "ok"
    return result







