from __future__ import annotations

from typing import Final

MIGRATION_ID: Final = "education_selective_mega_r9_v1"

SCHEMA: Final = r"""
CREATE TABLE IF NOT EXISTS education_entities(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,entity_type TEXT NOT NULL,name TEXT NOT NULL,
 code TEXT NOT NULL DEFAULT '',parent_id TEXT,data_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(institution_id,entity_type,code));
CREATE INDEX IF NOT EXISTS idx_education_entities_search ON education_entities(institution_id,entity_type,state,name);

CREATE TABLE IF NOT EXISTS education_workflows(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,workflow_type TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',
 requester_id TEXT NOT NULL,assignee_id TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'draft',
 payload_json TEXT NOT NULL DEFAULT '{}',decision_reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_education_workflows_queue ON education_workflows(institution_id,workflow_type,state,updated_at);

CREATE TABLE IF NOT EXISTS education_classes_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT,owner_id TEXT NOT NULL,name TEXT NOT NULL,
 class_code TEXT NOT NULL,section TEXT NOT NULL DEFAULT '',academic_session TEXT NOT NULL DEFAULT '',visibility TEXT NOT NULL DEFAULT 'institution',
 meeting_url TEXT NOT NULL DEFAULT '',settings_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,class_code));
CREATE INDEX IF NOT EXISTS idx_education_classes_r9 ON education_classes_r9(institution_id,state,name);

CREATE TABLE IF NOT EXISTS education_class_members_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,class_id TEXT NOT NULL,user_id TEXT NOT NULL,role TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'invited',joined_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(class_id,user_id,role));
CREATE INDEX IF NOT EXISTS idx_education_class_members_r9 ON education_class_members_r9(class_id,state,user_id);

CREATE TABLE IF NOT EXISTS education_stream_posts_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,class_id TEXT NOT NULL,author_id TEXT NOT NULL,post_type TEXT NOT NULL DEFAULT 'announcement',
 title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL,attachments_json TEXT NOT NULL DEFAULT '[]',audience_json TEXT NOT NULL DEFAULT '[]',
 scheduled_at TEXT,published_at TEXT,pinned INTEGER NOT NULL DEFAULT 0,edited INTEGER NOT NULL DEFAULT 0,
 moderation_state TEXT NOT NULL DEFAULT 'published',state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_education_stream_posts_r9 ON education_stream_posts_r9(class_id,state,pinned,created_at);

CREATE TABLE IF NOT EXISTS education_classwork_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,class_id TEXT NOT NULL,creator_id TEXT NOT NULL,item_type TEXT NOT NULL,
 title TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '',topic TEXT NOT NULL DEFAULT '',due_at TEXT,publish_at TEXT,
 max_marks REAL NOT NULL DEFAULT 0,settings_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'draft',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_education_classwork_r9 ON education_classwork_r9(class_id,state,due_at);

CREATE TABLE IF NOT EXISTS education_exam_registrations_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,student_id TEXT NOT NULL,
 subjects_json TEXT NOT NULL DEFAULT '[]',eligibility_json TEXT NOT NULL DEFAULT '{}',registration_number TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'submitted',decision_reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(examination_id,student_id));
CREATE INDEX IF NOT EXISTS idx_exam_registrations_r9 ON education_exam_registrations_r9(institution_id,state,student_id);

CREATE TABLE IF NOT EXISTS education_question_bank_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL,author_id TEXT NOT NULL,question_type TEXT NOT NULL,
 prompt TEXT NOT NULL,answer_json TEXT NOT NULL DEFAULT '{}',metadata_json TEXT NOT NULL DEFAULT '{}',fingerprint TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,reviewer_id TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'draft',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,fingerprint,version));
CREATE INDEX IF NOT EXISTS idx_question_bank_r9 ON education_question_bank_r9(institution_id,subject_id,state,question_type);

CREATE TABLE IF NOT EXISTS education_exam_schedules_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',
 room TEXT NOT NULL,capacity INTEGER NOT NULL,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,invigilators_json TEXT NOT NULL DEFAULT '[]',
 settings_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_exam_schedules_r9 ON education_exam_schedules_r9(institution_id,starts_at,ends_at,room);

CREATE TABLE IF NOT EXISTS education_exam_seats_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,schedule_id TEXT NOT NULL,student_id TEXT NOT NULL,seat_label TEXT NOT NULL,
 accessibility_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(schedule_id,student_id),UNIQUE(schedule_id,seat_label));

CREATE TABLE IF NOT EXISTS education_admit_cards_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,registration_id TEXT NOT NULL,reference_code TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'issued',issued_by TEXT NOT NULL,issued_at TEXT NOT NULL,
 cancelled_at TEXT,updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS education_evaluations_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,student_id TEXT NOT NULL,evaluator_id TEXT NOT NULL,
 marks_json TEXT NOT NULL DEFAULT '{}',total_marks REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'draft',
 flags_json TEXT NOT NULL DEFAULT '{}',locked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(examination_id,student_id,evaluator_id));

CREATE TABLE IF NOT EXISTS education_result_versions_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,student_id TEXT NOT NULL,version INTEGER NOT NULL,
 result_json TEXT NOT NULL,reason TEXT NOT NULL,created_by TEXT NOT NULL,published INTEGER NOT NULL DEFAULT 0,
 withdrawn INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(examination_id,student_id,version));
CREATE INDEX IF NOT EXISTS idx_result_versions_r9 ON education_result_versions_r9(institution_id,examination_id,student_id,version);

CREATE TABLE IF NOT EXISTS education_revaluation_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,student_id TEXT NOT NULL,subject_id TEXT NOT NULL,
 reason TEXT NOT NULL,evaluator_id TEXT NOT NULL DEFAULT '',outcome_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'requested',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS education_proctor_policies_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,examination_id TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,
 provider TEXT NOT NULL DEFAULT '',camera INTEGER NOT NULL DEFAULT 0,microphone INTEGER NOT NULL DEFAULT 0,
 retention_days INTEGER NOT NULL DEFAULT 0,consent_text TEXT NOT NULL DEFAULT '',updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(institution_id,examination_id));

CREATE TABLE IF NOT EXISTS education_official_sources_r9(
 id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,authority TEXT NOT NULL,url TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,
 adapter TEXT NOT NULL DEFAULT 'authorised_file',terms_note TEXT NOT NULL DEFAULT '',limitations TEXT NOT NULL DEFAULT '',
 last_success_at TEXT,last_checksum TEXT NOT NULL DEFAULT '',last_error TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS education_ingestion_runs_r9(
 id TEXT PRIMARY KEY,source_id TEXT NOT NULL,state TEXT NOT NULL,records_received INTEGER NOT NULL DEFAULT 0,
 records_imported INTEGER NOT NULL DEFAULT 0,records_rejected INTEGER NOT NULL DEFAULT 0,duplicate_merges INTEGER NOT NULL DEFAULT 0,
 checksum TEXT NOT NULL DEFAULT '',dataset_year TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',cancel_requested INTEGER NOT NULL DEFAULT 0,
 started_at TEXT NOT NULL,finished_at TEXT);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_r9 ON education_ingestion_runs_r9(source_id,started_at,state);

CREATE TABLE IF NOT EXISTS education_official_records_r9(
 id TEXT PRIMARY KEY,source_id TEXT NOT NULL,official_id TEXT NOT NULL,name TEXT NOT NULL,alternate_names_json TEXT NOT NULL DEFAULT '[]',
 institution_type TEXT NOT NULL DEFAULT '',management_type TEXT NOT NULL DEFAULT '',state_ut TEXT NOT NULL DEFAULT '',district TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '',pin_code TEXT NOT NULL DEFAULT '',board TEXT NOT NULL DEFAULT '',affiliation TEXT NOT NULL DEFAULT '',
 recognition_status TEXT NOT NULL DEFAULT '',programmes_json TEXT NOT NULL DEFAULT '[]',source_url TEXT NOT NULL,dataset_year TEXT NOT NULL DEFAULT '',
 retrieved_at TEXT NOT NULL,checksum TEXT NOT NULL,transformation_version TEXT NOT NULL,verification_status TEXT NOT NULL DEFAULT 'source_asserted_pending_review',
 freshness_status TEXT NOT NULL DEFAULT 'current',conflict_status TEXT NOT NULL DEFAULT 'none',raw_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(source_id,official_id));
CREATE INDEX IF NOT EXISTS idx_official_records_r9_search ON education_official_records_r9(source_id,state_ut,district,name);

CREATE TABLE IF NOT EXISTS education_import_conflicts_r9(
 id TEXT PRIMARY KEY,run_id TEXT NOT NULL,record_id TEXT NOT NULL,candidate_record_id TEXT NOT NULL DEFAULT '',
 conflict_type TEXT NOT NULL,detail_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'pending',
 resolved_by TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS education_notifications_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,user_id TEXT NOT NULL DEFAULT '',role TEXT NOT NULL DEFAULT '',
 event_type TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT 'normal',
 target_url TEXT NOT NULL DEFAULT '',read_at TEXT,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_notifications_r9 ON education_notifications_r9(institution_id,user_id,role,read_at,created_at);

CREATE TABLE IF NOT EXISTS education_saved_searches_r9(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,user_id TEXT NOT NULL,name TEXT NOT NULL,query_json TEXT NOT NULL,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,user_id,name));
"""


def migrate_selective_mega(database: object) -> str:
    """Apply the additive R9 schema inside one SQLite transaction."""
    with database.connection() as connection:  # type: ignore[attr-defined]
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO education_migrations(id,applied_at) VALUES(?,datetime('now'))",
            (MIGRATION_ID,),
        )
    return MIGRATION_ID
