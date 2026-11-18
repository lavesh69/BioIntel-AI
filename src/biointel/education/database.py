from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATION_ID = "education_science_academy_v2_integrity"
SCHEMA = r'''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS education_migrations(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS institutions(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,timezone TEXT NOT NULL DEFAULT 'UTC',state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),user_id TEXT NOT NULL,role TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,user_id,role));
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id,institution_id,state);
CREATE TABLE IF NOT EXISTS academic_units(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),parent_id TEXT REFERENCES academic_units(id),unit_type TEXT NOT NULL,name TEXT NOT NULL,academic_year TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_units_tenant ON academic_units(institution_id,unit_type);
CREATE TABLE IF NOT EXISTS subjects(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),unit_id TEXT REFERENCES academic_units(id),code TEXT NOT NULL,name TEXT NOT NULL,syllabus TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,code));
CREATE TABLE IF NOT EXISTS enrollments(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),student_id TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(subject_id,student_id));
CREATE TABLE IF NOT EXISTS teacher_assignments(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),teacher_id TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(subject_id,teacher_id));
CREATE TABLE IF NOT EXISTS guardian_links(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),guardian_id TEXT NOT NULL,student_id TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,student_consent INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',requested_by TEXT NOT NULL DEFAULT '',consented_at TEXT,revoked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,guardian_id,student_id));
CREATE TABLE IF NOT EXISTS timetable_entries(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT REFERENCES subjects(id),teacher_id TEXT NOT NULL DEFAULT '',student_group TEXT NOT NULL DEFAULT '',room TEXT NOT NULL DEFAULT '',starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,meeting_id TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'scheduled',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_timetable_time ON timetable_entries(institution_id,starts_at,ends_at);
CREATE TABLE IF NOT EXISTS attendance_sessions(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),teacher_id TEXT NOT NULL,session_date TEXT NOT NULL,period TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(subject_id,session_date,period));
CREATE TABLE IF NOT EXISTS attendance_records(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),session_id TEXT NOT NULL REFERENCES attendance_sessions(id),student_id TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',marked_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(session_id,student_id));
CREATE TABLE IF NOT EXISTS attendance_corrections(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),record_id TEXT NOT NULL REFERENCES attendance_records(id),requester_id TEXT NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',decision_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),owner_id TEXT NOT NULL,title TEXT NOT NULL,file_name TEXT NOT NULL,mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,storage_path TEXT NOT NULL,download_allowed INTEGER NOT NULL DEFAULT 1,state TEXT NOT NULL DEFAULT 'published',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assignments(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),creator_id TEXT NOT NULL,title TEXT NOT NULL,instructions TEXT NOT NULL,due_at TEXT NOT NULL,max_marks REAL NOT NULL,allowed_types TEXT NOT NULL DEFAULT '[]',late_policy TEXT NOT NULL DEFAULT 'reject',state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),assignment_id TEXT NOT NULL REFERENCES assignments(id),student_id TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',file_path TEXT NOT NULL DEFAULT '',submitted_at TEXT,state TEXT NOT NULL DEFAULT 'draft',late INTEGER NOT NULL DEFAULT 0,late_seconds INTEGER NOT NULL DEFAULT 0,penalty_percent REAL NOT NULL DEFAULT 0,file_name TEXT NOT NULL DEFAULT '',mime_type TEXT NOT NULL DEFAULT '',size_bytes INTEGER NOT NULL DEFAULT 0,sha256 TEXT NOT NULL DEFAULT '',final_version INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(assignment_id,student_id));
CREATE TABLE IF NOT EXISTS submission_versions(id TEXT PRIMARY KEY,submission_id TEXT NOT NULL REFERENCES submissions(id),version INTEGER NOT NULL,actor_id TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',file_path TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL DEFAULT '',state TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(submission_id,version));
CREATE TABLE IF NOT EXISTS grades(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),submission_id TEXT NOT NULL REFERENCES submissions(id),grader_id TEXT NOT NULL,marks REAL NOT NULL,feedback TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'released',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(submission_id));
CREATE TABLE IF NOT EXISTS grade_revisions(id TEXT PRIMARY KEY,grade_id TEXT NOT NULL REFERENCES grades(id),submission_id TEXT NOT NULL,changed_by TEXT NOT NULL,old_marks REAL NOT NULL,new_marks REAL NOT NULL,old_feedback TEXT NOT NULL DEFAULT '',new_feedback TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS examinations(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),subject_id TEXT NOT NULL REFERENCES subjects(id),creator_id TEXT NOT NULL,title TEXT NOT NULL,max_marks REAL NOT NULL,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),examination_id TEXT NOT NULL REFERENCES examinations(id),student_id TEXT NOT NULL,marks REAL NOT NULL,grade TEXT NOT NULL DEFAULT '',published INTEGER NOT NULL DEFAULT 0,locked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(examination_id,student_id));
CREATE TABLE IF NOT EXISTS result_revisions(id TEXT PRIMARY KEY,result_id TEXT NOT NULL REFERENCES results(id),changed_by TEXT NOT NULL,old_marks REAL NOT NULL,new_marks REAL NOT NULL,old_grade TEXT NOT NULL DEFAULT '',new_grade TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS circulars(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),creator_id TEXT NOT NULL,circular_number TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,audience_json TEXT NOT NULL,priority TEXT NOT NULL DEFAULT 'normal',state TEXT NOT NULL DEFAULT 'draft',approved_by TEXT NOT NULL DEFAULT '',published_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,circular_number));
CREATE TABLE IF NOT EXISTS circular_acknowledgements(id TEXT PRIMARY KEY,circular_id TEXT NOT NULL REFERENCES circulars(id),user_id TEXT NOT NULL,acknowledged_at TEXT NOT NULL,UNIQUE(circular_id,user_id));
CREATE TABLE IF NOT EXISTS academic_events(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),title TEXT NOT NULL,event_type TEXT NOT NULL,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'scheduled',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_sources(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL DEFAULT '',name TEXT NOT NULL,source_type TEXT NOT NULL,base_url TEXT NOT NULL,configured INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_pulse_sources_tenant ON pulse_sources(institution_id,state);
CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY,source_id TEXT REFERENCES pulse_sources(id),doi TEXT NOT NULL DEFAULT '',pmid TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,abstract_excerpt TEXT NOT NULL DEFAULT '',authors_json TEXT NOT NULL DEFAULT '[]',source_url TEXT NOT NULL,published_at TEXT NOT NULL DEFAULT '',record_type TEXT NOT NULL DEFAULT 'journal',retraction_state TEXT NOT NULL DEFAULT 'none',metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pub_doi ON publications(doi) WHERE doi<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_pub_pmid ON publications(pmid) WHERE pmid<>'';
CREATE TABLE IF NOT EXISTS news_items(id TEXT PRIMARY KEY,source_id TEXT REFERENCES pulse_sources(id),external_id TEXT NOT NULL,title TEXT NOT NULL,summary_excerpt TEXT NOT NULL DEFAULT '',source_url TEXT NOT NULL,published_at TEXT NOT NULL,topics_json TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(source_id,external_id));
CREATE TABLE IF NOT EXISTS saved_research(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,resource_type,resource_id));
CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,query TEXT NOT NULL,resource_type TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_deliveries(id TEXT PRIMARY KEY,alert_id TEXT NOT NULL REFERENCES alerts(id),resource_id TEXT NOT NULL,delivered_at TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'delivered',UNIQUE(alert_id,resource_id));
CREATE TABLE IF NOT EXISTS ai_summaries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,summary TEXT NOT NULL,citations_json TEXT NOT NULL,label TEXT NOT NULL DEFAULT 'AI-generated',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_sync_jobs(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES pulse_sources(id),state TEXT NOT NULL,items_received INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS educator_profiles(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),user_id TEXT NOT NULL,bio TEXT NOT NULL DEFAULT '',verified INTEGER NOT NULL DEFAULT 0,verification_state TEXT NOT NULL DEFAULT 'unverified',verified_by TEXT NOT NULL DEFAULT '',verified_at TEXT,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,user_id));
CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),educator_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',difficulty TEXT NOT NULL DEFAULT 'beginner',passing_score REAL NOT NULL DEFAULT 60,minimum_watch_ratio REAL NOT NULL DEFAULT 0.85,require_all_quizzes INTEGER NOT NULL DEFAULT 1,state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS course_sections(id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id),parent_id TEXT REFERENCES course_sections(id),section_type TEXT NOT NULL,title TEXT NOT NULL,position INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lectures(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),course_id TEXT NOT NULL REFERENCES courses(id),educator_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',video_path TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL DEFAULT '',size_bytes INTEGER NOT NULL DEFAULT 0,mime_type TEXT NOT NULL DEFAULT '',duration_seconds REAL NOT NULL DEFAULT 0,processing_state TEXT NOT NULL DEFAULT 'not_uploaded',rights_id TEXT,state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS content_rights(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),owner_name TEXT NOT NULL,educator_id TEXT NOT NULL,license TEXT NOT NULL,rights_confirmed INTEGER NOT NULL,third_party_declaration TEXT NOT NULL DEFAULT '',download_allowed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS academy_enrollments(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),course_id TEXT NOT NULL REFERENCES courses(id),student_id TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(course_id,student_id));
CREATE TABLE IF NOT EXISTS watch_progress(id TEXT PRIMARY KEY,lecture_id TEXT NOT NULL REFERENCES lectures(id),user_id TEXT NOT NULL,seconds REAL NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,UNIQUE(lecture_id,user_id));
CREATE TABLE IF NOT EXISTS watch_events(id TEXT PRIMARY KEY,lecture_id TEXT NOT NULL REFERENCES lectures(id),user_id TEXT NOT NULL,event_type TEXT NOT NULL,position_seconds REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quizzes(id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id),creator_id TEXT NOT NULL,title TEXT NOT NULL,questions_json TEXT NOT NULL,passing_score REAL NOT NULL DEFAULT 60,state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quiz_attempts(id TEXT PRIMARY KEY,quiz_id TEXT NOT NULL REFERENCES quizzes(id),student_id TEXT NOT NULL,answers_json TEXT NOT NULL,score REAL NOT NULL,passed INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS certificates(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL REFERENCES institutions(id),course_id TEXT NOT NULL REFERENCES courses(id),student_id TEXT NOT NULL,issued_at TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,verification_code TEXT NOT NULL UNIQUE,evidence_json TEXT NOT NULL DEFAULT '{}',evidence_sha256 TEXT NOT NULL DEFAULT '',signature TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(course_id,student_id));
CREATE TABLE IF NOT EXISTS content_reports(id TEXT PRIMARY KEY,reporter_id TEXT NOT NULL,target_type TEXT NOT NULL,target_id TEXT NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS education_audit_events(id TEXT PRIMARY KEY,institution_id TEXT NOT NULL DEFAULT '',actor_id TEXT NOT NULL,action TEXT NOT NULL,target_type TEXT NOT NULL,target_id TEXT NOT NULL,detail_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON education_audit_events(institution_id,created_at);
'''

ALTERATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "guardian_links": (("requested_by", "TEXT NOT NULL DEFAULT ''"), ("consented_at", "TEXT"), ("revoked_at", "TEXT")),
    "submissions": (("late", "INTEGER NOT NULL DEFAULT 0"), ("late_seconds", "INTEGER NOT NULL DEFAULT 0"), ("penalty_percent", "REAL NOT NULL DEFAULT 0"), ("file_name", "TEXT NOT NULL DEFAULT ''"), ("mime_type", "TEXT NOT NULL DEFAULT ''"), ("size_bytes", "INTEGER NOT NULL DEFAULT 0"), ("sha256", "TEXT NOT NULL DEFAULT ''"), ("final_version", "INTEGER NOT NULL DEFAULT 0")),
    "pulse_sources": (("institution_id", "TEXT NOT NULL DEFAULT ''"),),
    "educator_profiles": (("verification_state", "TEXT NOT NULL DEFAULT 'unverified'"), ("verified_by", "TEXT NOT NULL DEFAULT ''"), ("verified_at", "TEXT")),
    "courses": (("passing_score", "REAL NOT NULL DEFAULT 60"), ("minimum_watch_ratio", "REAL NOT NULL DEFAULT 0.85"), ("require_all_quizzes", "INTEGER NOT NULL DEFAULT 1")),
    "lectures": (("duration_seconds", "REAL NOT NULL DEFAULT 0"),),
    "quizzes": (("passing_score", "REAL NOT NULL DEFAULT 60"),),
    "certificates": (("evidence_json", "TEXT NOT NULL DEFAULT '{}'"), ("evidence_sha256", "TEXT NOT NULL DEFAULT ''"), ("signature", "TEXT NOT NULL DEFAULT ''")),
}

class EducationDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)

    @staticmethod
    def _columns(db: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})").fetchall()}

    def migrate(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(SCHEMA)
            for table, columns in ALTERATIONS.items():
                existing = self._columns(db, table)
                for name, definition in columns:
                    if name not in existing:
                        try:
                            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                            existing.add(name)
                        except sqlite3.OperationalError as exc:
                            if "duplicate column name" not in str(exc).casefold():
                                raise
            try:
                db.execute("CREATE INDEX IF NOT EXISTS idx_pulse_sources_tenant ON pulse_sources(institution_id,state)")
            except sqlite3.OperationalError as exc:
                if "no such column" not in str(exc).casefold():
                    raise
            db.execute("INSERT OR IGNORE INTO education_migrations VALUES(?,datetime('now'))", (MIGRATION_ID,))
        return MIGRATION_ID

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def quick_check(self) -> bool:
        with self.connection() as db:
            return db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
