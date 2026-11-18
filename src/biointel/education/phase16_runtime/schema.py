from __future__ import annotations

MIGRATION_ID = "education_phase16_completion_v2"

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS education_event_consumers_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 actor_id TEXT NOT NULL,
 consumer_key TEXT NOT NULL,
 last_sequence INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'active',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 heartbeat_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,actor_id,consumer_key)
);
CREATE INDEX IF NOT EXISTS idx_phase16_consumers ON education_event_consumers_v16(institution_id,state,heartbeat_at);

CREATE TABLE IF NOT EXISTS education_rag_eval_cases_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 query_text TEXT NOT NULL,
 expected_document_ids_json TEXT NOT NULL DEFAULT '[]',
 expected_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_rag_eval_runs_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 top_k INTEGER NOT NULL,
 case_count INTEGER NOT NULL,
 recall_at_k REAL NOT NULL,
 mean_reciprocal_rank REAL NOT NULL,
 grounded_rate REAL NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '[]',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_pulse_alert_rules_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 query_terms_json TEXT NOT NULL DEFAULT '[]',
 providers_json TEXT NOT NULL DEFAULT '[]',
 record_types_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_pulse_alert_hits_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 rule_id TEXT NOT NULL REFERENCES education_pulse_alert_rules_v16(id) ON DELETE CASCADE,
 record_id TEXT NOT NULL REFERENCES education_pulse_external_records(id) ON DELETE CASCADE,
 matched_terms_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'unread',
 created_at TEXT NOT NULL,
 read_at TEXT,
 UNIQUE(rule_id,record_id)
);

CREATE TABLE IF NOT EXISTS education_scientific_datasets_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 source_name TEXT NOT NULL,
 stored_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 format TEXT NOT NULL,
 record_count INTEGER NOT NULL DEFAULT 0,
 size_bytes INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'ready',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(institution_id,sha256)
);
CREATE TABLE IF NOT EXISTS education_scientific_runs_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 dataset_id TEXT NOT NULL REFERENCES education_scientific_datasets_v16(id) ON DELETE CASCADE,
 analysis_type TEXT NOT NULL,
 parameters_json TEXT NOT NULL DEFAULT '{}',
 result_json TEXT NOT NULL DEFAULT '{}',
 artifact_path TEXT NOT NULL DEFAULT '',
 artifact_sha256 TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'completed',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_media_processing_jobs_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 asset_id TEXT NOT NULL REFERENCES education_media_assets_v15(id) ON DELETE CASCADE,
 profile TEXT NOT NULL,
 output_dir TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'planned',
 progress INTEGER NOT NULL DEFAULT 0,
 command_json TEXT NOT NULL DEFAULT '[]',
 evidence_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_transcription_jobs_v16(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
 asset_id TEXT NOT NULL REFERENCES education_media_assets_v15(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 model_path TEXT NOT NULL,
 requested_language TEXT NOT NULL DEFAULT 'auto',
 detected_language TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'planned',
 progress INTEGER NOT NULL DEFAULT 0,
 transcript_id TEXT NOT NULL DEFAULT '',
 evidence_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phase16_transcription_jobs
 ON education_transcription_jobs_v16(institution_id,lecture_id,state,updated_at);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase16_completion_v1',datetime('now'));
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase16_completion_v2',datetime('now'));
'''
