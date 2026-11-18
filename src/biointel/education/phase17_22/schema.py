from __future__ import annotations

MIGRATION_ID = "education_phase17_to_22_unified_os_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_os_migrations(
 migration_id TEXT PRIMARY KEY,
 applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_resource_registry(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 resource_type TEXT NOT NULL,
 external_id TEXT NOT NULL,
 parent_resource_id TEXT REFERENCES education_resource_registry(id),
 owner_id TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'active',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,resource_type,external_id)
);
CREATE INDEX IF NOT EXISTS idx_education_resource_tenant
 ON education_resource_registry(institution_id,resource_type,state,external_id);
CREATE INDEX IF NOT EXISTS idx_education_resource_parent
 ON education_resource_registry(parent_resource_id,state);

CREATE TABLE IF NOT EXISTS education_role_bindings(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 role TEXT NOT NULL,
 resource_type TEXT NOT NULL DEFAULT 'institution',
 resource_id TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'active',
 granted_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,role,resource_type,resource_id)
);
CREATE INDEX IF NOT EXISTS idx_education_role_binding_lookup
 ON education_role_bindings(institution_id,user_id,resource_type,resource_id,state);

CREATE TABLE IF NOT EXISTS education_workflow_instances(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 program_id TEXT NOT NULL DEFAULT '',
 course_id TEXT NOT NULL DEFAULT '',
 classroom_id TEXT NOT NULL DEFAULT '',
 teacher_id TEXT NOT NULL DEFAULT '',
 student_id TEXT NOT NULL DEFAULT '',
 stage TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 last_error TEXT NOT NULL DEFAULT '',
 detail_json TEXT NOT NULL DEFAULT '{}',
 version INTEGER NOT NULL DEFAULT 1,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_workflow_tenant
 ON education_workflow_instances(institution_id,state,stage,updated_at);

CREATE TABLE IF NOT EXISTS education_outbox(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 event_type TEXT NOT NULL,
 aggregate_type TEXT NOT NULL,
 aggregate_id TEXT NOT NULL,
 payload_json TEXT NOT NULL DEFAULT '{}',
 dedupe_key TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TEXT NOT NULL,
 last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 published_at TEXT,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_education_outbox_delivery
 ON education_outbox(state,next_attempt_at,created_at);

CREATE TABLE IF NOT EXISTS education_idempotency_keys(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 actor_id TEXT NOT NULL,
 operation TEXT NOT NULL,
 idempotency_key TEXT NOT NULL,
 request_sha256 TEXT NOT NULL,
 response_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'running',
 expires_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,actor_id,operation,idempotency_key)
);

CREATE TABLE IF NOT EXISTS education_shiro_scopes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 course_id TEXT NOT NULL,
 classroom_id TEXT NOT NULL DEFAULT '',
 project_id TEXT NOT NULL UNIQUE,
 collection_name TEXT NOT NULL,
 approved_only INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,course_id,classroom_id)
);
CREATE INDEX IF NOT EXISTS idx_education_shiro_scope_tenant
 ON education_shiro_scopes(institution_id,course_id,classroom_id,state);

CREATE TABLE IF NOT EXISTS education_shiro_scope_acl(
 id TEXT PRIMARY KEY,
 scope_id TEXT NOT NULL REFERENCES education_shiro_scopes(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 access_level TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 granted_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(scope_id,user_id)
);

CREATE TABLE IF NOT EXISTS education_shiro_documents(
 id TEXT PRIMARY KEY,
 scope_id TEXT NOT NULL REFERENCES education_shiro_scopes(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 material_id TEXT NOT NULL,
 shiro_source_id TEXT NOT NULL,
 approval_state TEXT NOT NULL DEFAULT 'approved',
 approved_by TEXT NOT NULL,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(scope_id,material_id)
);

CREATE TABLE IF NOT EXISTS education_shiro_generated_artifacts(
 id TEXT PRIMARY KEY,
 scope_id TEXT NOT NULL REFERENCES education_shiro_scopes(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 creator_id TEXT NOT NULL,
 artifact_type TEXT NOT NULL,
 title TEXT NOT NULL,
 content_json TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '[]',
 evidence_status TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'draft',
 reviewed_by TEXT NOT NULL DEFAULT '',
 reviewed_at TEXT,
 review_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_connect_identities(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 education_user_id TEXT NOT NULL,
 connect_user_id TEXT NOT NULL,
 connect_username TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,education_user_id),
 UNIQUE(connect_user_id)
);

CREATE TABLE IF NOT EXISTS education_channel_links(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 resource_type TEXT NOT NULL,
 resource_id TEXT NOT NULL,
 connect_target_type TEXT NOT NULL,
 connect_target_id TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,resource_type,resource_id,connect_target_type)
);

CREATE TABLE IF NOT EXISTS education_intervention_recommendations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 subject_id TEXT NOT NULL DEFAULT '',
 concept_id TEXT NOT NULL DEFAULT '',
 category TEXT NOT NULL,
 reason_code TEXT NOT NULL,
 rationale TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 confidence REAL NOT NULL,
 minimum_data_met INTEGER NOT NULL DEFAULT 0,
 model_kind TEXT NOT NULL,
 model_version TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending_review',
 human_review_required INTEGER NOT NULL DEFAULT 1,
 reviewed_by TEXT NOT NULL DEFAULT '',
 reviewed_at TEXT,
 review_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,student_id,subject_id,concept_id,reason_code)
);
CREATE INDEX IF NOT EXISTS idx_education_intervention_student
 ON education_intervention_recommendations(institution_id,student_id,state,updated_at);

CREATE TABLE IF NOT EXISTS education_studio_projects(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,
 title TEXT NOT NULL,
 project_type TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'draft',
 current_version INTEGER NOT NULL DEFAULT 0,
 collaboration_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_studio_projects
 ON education_studio_projects(institution_id,owner_id,state,updated_at);

CREATE TABLE IF NOT EXISTS education_studio_versions(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_studio_projects(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 version_number INTEGER NOT NULL,
 content_json TEXT NOT NULL,
 content_sha256 TEXT NOT NULL,
 change_note TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(project_id,version_number)
);

CREATE TABLE IF NOT EXISTS education_studio_assets(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_studio_projects(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 original_name TEXT NOT NULL,
 stored_path TEXT NOT NULL UNIQUE,
 mime_type TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(project_id,sha256)
);

CREATE TABLE IF NOT EXISTS education_studio_citations(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_studio_projects(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 title TEXT NOT NULL,
 doi TEXT NOT NULL DEFAULT '',
 pmid TEXT NOT NULL DEFAULT '',
 source_url TEXT NOT NULL DEFAULT '',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_studio_reviews(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_studio_projects(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 reviewer_id TEXT NOT NULL,
 decision TEXT NOT NULL,
 comment TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_studio_publications(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_studio_projects(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 version_id TEXT NOT NULL REFERENCES education_studio_versions(id),
 target_type TEXT NOT NULL,
 target_id TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued',
 external_reference TEXT NOT NULL DEFAULT '',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(project_id,version_id,target_type,target_id)
);

CREATE TABLE IF NOT EXISTS education_feature_flags_v22(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 flag_key TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 0,
 config_json TEXT NOT NULL DEFAULT '{}',
 changed_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,flag_key)
);

CREATE TABLE IF NOT EXISTS education_health_checks_v22(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 component TEXT NOT NULL,
 state TEXT NOT NULL,
 latency_ms REAL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 checked_by TEXT NOT NULL,
 checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_health_latest
 ON education_health_checks_v22(institution_id,component,checked_at DESC);

CREATE TABLE IF NOT EXISTS education_release_checks_v22(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 check_key TEXT NOT NULL,
 status TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 blocker TEXT NOT NULL DEFAULT '',
 verified_by TEXT NOT NULL,
 verified_at TEXT NOT NULL,
 UNIQUE(institution_id,check_key)
);

CREATE TABLE IF NOT EXISTS education_pulse_canonical_records(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 canonical_key TEXT NOT NULL,
 doi TEXT NOT NULL DEFAULT '',
 pmid TEXT NOT NULL DEFAULT '',
 normalized_title TEXT NOT NULL,
 preferred_record_id TEXT NOT NULL,
 correction_state TEXT NOT NULL DEFAULT 'none',
 source_count INTEGER NOT NULL DEFAULT 1,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,canonical_key)
);

CREATE TABLE IF NOT EXISTS education_pulse_canonical_links(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 canonical_id TEXT NOT NULL REFERENCES education_pulse_canonical_records(id) ON DELETE CASCADE,
 provider_record_id TEXT NOT NULL,
 similarity REAL NOT NULL DEFAULT 1.0,
 created_at TEXT NOT NULL,
 UNIQUE(institution_id,provider_record_id)
);

INSERT OR IGNORE INTO education_os_migrations(migration_id,applied_at)
 VALUES('education_phase17_to_22_unified_os_v1',datetime('now'));
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase17_to_22_unified_os_v1',datetime('now'));
"""
