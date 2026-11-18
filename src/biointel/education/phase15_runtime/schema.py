from __future__ import annotations

MIGRATION_ID = "education_phase15_runtime_intelligence_v1"

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS education_realtime_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 id TEXT NOT NULL UNIQUE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 channel TEXT NOT NULL,
 event_type TEXT NOT NULL,
 target_type TEXT NOT NULL DEFAULT '',
 target_id TEXT NOT NULL DEFAULT '',
 audience_json TEXT NOT NULL DEFAULT '{}',
 payload_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase15_events
 ON education_realtime_events(institution_id,sequence,channel,event_type);

CREATE TABLE IF NOT EXISTS education_rag_vector_indexes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 model_name TEXT NOT NULL,
 dimensions INTEGER NOT NULL,
 chunk_count INTEGER NOT NULL DEFAULT 0,
 index_sha256 TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'ready',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,project_id,model_name)
);
CREATE TABLE IF NOT EXISTS education_rag_chunk_embeddings(
 chunk_id TEXT NOT NULL REFERENCES education_rag_chunks(id) ON DELETE CASCADE,
 index_id TEXT NOT NULL REFERENCES education_rag_vector_indexes(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 vector_blob BLOB NOT NULL,
 vector_norm REAL NOT NULL,
 content_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL,
 PRIMARY KEY(chunk_id,index_id)
);
CREATE INDEX IF NOT EXISTS idx_phase15_embeddings
 ON education_rag_chunk_embeddings(institution_id,project_id,index_id);
CREATE TABLE IF NOT EXISTS education_rag_hybrid_search_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 query_text TEXT NOT NULL,
 lexical_weight REAL NOT NULL,
 vector_weight REAL NOT NULL,
 result_count INTEGER NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '[]',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_model_runtimes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 provider_type TEXT NOT NULL,
 endpoint TEXT NOT NULL DEFAULT '',
 model_name TEXT NOT NULL,
 secret_reference TEXT NOT NULL DEFAULT '',
 context_window INTEGER NOT NULL DEFAULT 4096,
 external_processing INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'configured',
 readiness_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_model_runtime_checks(
 id TEXT PRIMARY KEY,
 runtime_id TEXT NOT NULL REFERENCES education_model_runtimes(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 state TEXT NOT NULL,
 latency_ms REAL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 checked_by TEXT NOT NULL,
 checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_pulse_provider_configs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider TEXT NOT NULL,
 name TEXT NOT NULL,
 query_text TEXT NOT NULL DEFAULT '',
 cursor_text TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'active',
 config_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,provider,name)
);
CREATE TABLE IF NOT EXISTS education_pulse_provider_runs(
 id TEXT PRIMARY KEY,
 config_id TEXT NOT NULL REFERENCES education_pulse_provider_configs(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 state TEXT NOT NULL,
 received_count INTEGER NOT NULL DEFAULT 0,
 inserted_count INTEGER NOT NULL DEFAULT 0,
 cursor_text TEXT NOT NULL DEFAULT '',
 evidence_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE TABLE IF NOT EXISTS education_pulse_external_records(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider TEXT NOT NULL,
 external_id TEXT NOT NULL,
 doi TEXT NOT NULL DEFAULT '',
 pmid TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL,
 abstract_excerpt TEXT NOT NULL DEFAULT '',
 authors_json TEXT NOT NULL DEFAULT '[]',
 source_url TEXT NOT NULL,
 published_at TEXT NOT NULL DEFAULT '',
 record_type TEXT NOT NULL DEFAULT 'journal',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,provider,external_id)
);
CREATE INDEX IF NOT EXISTS idx_phase15_pulse_records
 ON education_pulse_external_records(institution_id,provider,published_at);

CREATE TABLE IF NOT EXISTS education_media_assets_v15(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 source_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 mime_type TEXT NOT NULL DEFAULT '',
 duration_seconds REAL NOT NULL DEFAULT 0,
 width INTEGER NOT NULL DEFAULT 0,
 height INTEGER NOT NULL DEFAULT 0,
 video_codec TEXT NOT NULL DEFAULT '',
 audio_codec TEXT NOT NULL DEFAULT '',
 probe_json TEXT NOT NULL DEFAULT '{}',
 processing_state TEXT NOT NULL DEFAULT 'registered',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(lecture_id,sha256)
);
CREATE TABLE IF NOT EXISTS education_media_playback_events_v15(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 user_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 position_seconds REAL NOT NULL DEFAULT 0,
 playback_rate REAL NOT NULL DEFAULT 1,
 session_id TEXT NOT NULL,
 client_event_id TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(lecture_id,user_id,client_event_id)
);
CREATE INDEX IF NOT EXISTS idx_phase15_media_events
 ON education_media_playback_events_v15(institution_id,lecture_id,user_id,created_at);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase15_runtime_intelligence_v1',datetime('now'));
'''
