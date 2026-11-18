from __future__ import annotations

MIGRATION_ID = "education_phase31_to_35_research_platform_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_p35_migrations(
 id TEXT PRIMARY KEY,
 applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p32_sync_devices(
 device_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 device_name TEXT NOT NULL,
 device_type TEXT NOT NULL,
 operating_system TEXT NOT NULL,
 public_key_fingerprint TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL CHECK(state IN ('pending','trusted','untrusted','revoked','lost')),
 permissions_json TEXT NOT NULL,
 registered_at_utc TEXT NOT NULL,
 approved_at_utc TEXT,
 approved_by TEXT,
 revoked_at_utc TEXT,
 revoked_by TEXT,
 last_activity_at_utc TEXT,
 last_sync_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_p32_devices_tenant
 ON education_p32_sync_devices(tenant_id,owner_id,state);

CREATE TABLE IF NOT EXISTS education_p32_device_sessions(
 session_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 device_id TEXT NOT NULL REFERENCES education_p32_sync_devices(device_id),
 token_ciphertext TEXT NOT NULL,
 token_fingerprint TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 expires_at_utc TEXT NOT NULL,
 last_seen_at_utc TEXT,
 revoked_at_utc TEXT,
 revoked_by TEXT
);

CREATE TABLE IF NOT EXISTS education_p32_sync_policies(
 tenant_id TEXT PRIMARY KEY,
 allowed_categories_json TEXT NOT NULL,
 excluded_categories_json TEXT NOT NULL,
 data_residency TEXT NOT NULL DEFAULT 'local',
 retention_days INTEGER NOT NULL DEFAULT 365,
 allowed_device_types_json TEXT NOT NULL DEFAULT '[]',
 sync_windows_json TEXT NOT NULL DEFAULT '[]',
 bandwidth_limit_kib INTEGER NOT NULL DEFAULT 0,
 quota_bytes INTEGER NOT NULL DEFAULT 10737418240,
 metered_allowed INTEGER NOT NULL DEFAULT 0,
 low_bandwidth_default INTEGER NOT NULL DEFAULT 0,
 paused INTEGER NOT NULL DEFAULT 0,
 updated_at_utc TEXT NOT NULL,
 updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p32_sync_consents(
 consent_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 categories_json TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 granted INTEGER NOT NULL,
 recorded_at_utc TEXT NOT NULL,
 actor_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p32_sync_endpoints(
 endpoint_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 endpoint_kind TEXT NOT NULL,
 endpoint_url TEXT NOT NULL,
 certificate_pins_json TEXT NOT NULL DEFAULT '[]',
 encrypted_auth_config TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 UNIQUE(tenant_id,endpoint_url)
);

CREATE TABLE IF NOT EXISTS education_p32_key_versions(
 key_version INTEGER PRIMARY KEY,
 key_fingerprint TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('active','retired','revoked')),
 created_at_utc TEXT NOT NULL,
 rotated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p32_sync_journal(
 change_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 tenant_id TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 operation TEXT NOT NULL,
 entity_version INTEGER NOT NULL,
 device_id TEXT NOT NULL REFERENCES education_p32_sync_devices(device_id),
 actor_id TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 checksum TEXT NOT NULL,
 tombstone INTEGER NOT NULL DEFAULT 0,
 payload_ciphertext TEXT NOT NULL,
 key_version INTEGER NOT NULL,
 UNIQUE(tenant_id,entity_type,entity_id,device_id,entity_version,checksum)
);
CREATE INDEX IF NOT EXISTS idx_p32_journal_pending
 ON education_p32_sync_journal(tenant_id,device_id,created_at_utc);

CREATE TRIGGER IF NOT EXISTS trg_p32_journal_no_delete
BEFORE DELETE ON education_p32_sync_journal
BEGIN
 SELECT RAISE(ABORT,'sync journal is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_p32_journal_core_immutable
BEFORE UPDATE ON education_p32_sync_journal
WHEN OLD.idempotency_key != NEW.idempotency_key
 OR OLD.tenant_id != NEW.tenant_id
 OR OLD.entity_type != NEW.entity_type
 OR OLD.entity_id != NEW.entity_id
 OR OLD.operation != NEW.operation
 OR OLD.entity_version != NEW.entity_version
 OR OLD.device_id != NEW.device_id
 OR OLD.actor_id != NEW.actor_id
 OR OLD.created_at_utc != NEW.created_at_utc
 OR OLD.checksum != NEW.checksum
 OR OLD.tombstone != NEW.tombstone
 OR OLD.payload_ciphertext != NEW.payload_ciphertext
 OR OLD.key_version != NEW.key_version
BEGIN
 SELECT RAISE(ABORT,'sync journal core is immutable');
END;

CREATE TABLE IF NOT EXISTS education_p32_sync_delivery(
 change_id TEXT PRIMARY KEY REFERENCES education_p32_sync_journal(change_id),
 sync_status TEXT NOT NULL CHECK(sync_status IN ('pending','in_progress','acknowledged','failed','cancelled')),
 retry_count INTEGER NOT NULL DEFAULT 0,
 remote_acknowledgement TEXT NOT NULL DEFAULT '',
 last_attempt_at_utc TEXT,
 next_retry_at_utc TEXT,
 last_error_code TEXT NOT NULL DEFAULT '',
 support_reference TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS education_p32_entity_state(
 tenant_id TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 entity_version INTEGER NOT NULL,
 checksum TEXT NOT NULL,
 payload_ciphertext TEXT NOT NULL,
 key_version INTEGER NOT NULL,
 tombstone INTEGER NOT NULL DEFAULT 0,
 source_device_id TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 PRIMARY KEY(tenant_id,entity_type,entity_id)
);

CREATE TABLE IF NOT EXISTS education_p32_sync_conflicts(
 conflict_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 local_change_id TEXT,
 remote_change_id TEXT,
 strategy TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('open','resolved','rejected')),
 local_checksum TEXT NOT NULL,
 remote_checksum TEXT NOT NULL,
 resolution_reason TEXT NOT NULL DEFAULT '',
 resolved_payload_ciphertext TEXT NOT NULL DEFAULT '',
 detected_at_utc TEXT NOT NULL,
 resolved_at_utc TEXT,
 resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS education_p32_sync_files(
 file_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL,
 original_name TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 current_version INTEGER NOT NULL,
 local_path TEXT,
 remote_reference TEXT,
 availability TEXT NOT NULL CHECK(availability IN ('local','remote','both','unavailable')),
 local_only INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 UNIQUE(tenant_id,entity_type,entity_id,sha256)
);

CREATE TABLE IF NOT EXISTS education_p32_sync_file_versions(
 file_version_id TEXT PRIMARY KEY,
 file_id TEXT NOT NULL REFERENCES education_p32_sync_files(file_id),
 version_number INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 storage_path TEXT,
 remote_reference TEXT,
 created_at_utc TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 UNIQUE(file_id,version_number)
);

CREATE TABLE IF NOT EXISTS education_p32_sync_file_chunks(
 file_id TEXT NOT NULL REFERENCES education_p32_sync_files(file_id),
 direction TEXT NOT NULL CHECK(direction IN ('upload','download')),
 chunk_index INTEGER NOT NULL,
 byte_offset INTEGER NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','verified','failed')),
 updated_at_utc TEXT NOT NULL,
 PRIMARY KEY(file_id,direction,chunk_index)
);

CREATE TABLE IF NOT EXISTS education_p32_sync_incidents(
 incident_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 device_id TEXT,
 severity TEXT NOT NULL,
 code TEXT NOT NULL,
 safe_message TEXT NOT NULL,
 support_reference TEXT NOT NULL,
 details_json TEXT NOT NULL DEFAULT '{}',
 created_at_utc TEXT NOT NULL,
 resolved_at_utc TEXT,
 resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS education_p33_twin_projects(
 project_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 institution_id TEXT NOT NULL,
 title TEXT NOT NULL,
 purpose TEXT NOT NULL,
 classification TEXT NOT NULL,
 consent_status TEXT NOT NULL,
 deidentification_status TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 ethics_record_reference TEXT NOT NULL DEFAULT '',
 model_version TEXT NOT NULL DEFAULT '1.0.0',
 parameter_version TEXT NOT NULL DEFAULT '1.0.0',
 validation_status TEXT NOT NULL DEFAULT 'Not Validated',
 state TEXT NOT NULL CHECK(state IN ('active','archived','deleted')),
 retention_until_utc TEXT,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p33_projects_tenant
 ON education_p33_twin_projects(tenant_id,owner_id,state);

CREATE TABLE IF NOT EXISTS education_p33_twin_collaborators(
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 user_id TEXT NOT NULL,
 role TEXT NOT NULL,
 added_at_utc TEXT NOT NULL,
 added_by TEXT NOT NULL,
 PRIMARY KEY(project_id,user_id)
);

CREATE TABLE IF NOT EXISTS education_p33_twin_data_sources(
 source_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 source_type TEXT NOT NULL,
 source_label TEXT NOT NULL,
 source_reference TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 schema_version TEXT NOT NULL,
 units_json TEXT NOT NULL,
 reference_ranges_json TEXT NOT NULL,
 missing_data_status TEXT NOT NULL,
 deidentification_status TEXT NOT NULL,
 consent_status TEXT NOT NULL,
 quality_score REAL NOT NULL,
 content_sha256 TEXT NOT NULL,
 synthetic INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(project_id,content_sha256)
);

CREATE TABLE IF NOT EXISTS education_p33_twin_observations(
 observation_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 source_id TEXT REFERENCES education_p33_twin_data_sources(source_id),
 variable_class TEXT NOT NULL,
 variable_name TEXT NOT NULL,
 observed_at_utc TEXT NOT NULL,
 value_numeric REAL,
 value_text TEXT,
 unit TEXT NOT NULL,
 reference_low REAL,
 reference_high REAL,
 missing_status TEXT NOT NULL,
 quality_score REAL NOT NULL,
 provenance_json TEXT NOT NULL,
 synthetic INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p33_observations_project
 ON education_p33_twin_observations(project_id,variable_name,observed_at_utc);

CREATE TABLE IF NOT EXISTS education_p33_synthetic_generations(
 generation_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 seed INTEGER NOT NULL,
 generator_version TEXT NOT NULL,
 assumptions_json TEXT NOT NULL,
 distributions_json TEXT NOT NULL,
 constraints_json TEXT NOT NULL,
 generated_records INTEGER NOT NULL,
 output_sha256 TEXT NOT NULL,
 synthetic_label TEXT NOT NULL,
 non_clinical_status TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_models(
 model_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 model_key TEXT NOT NULL,
 model_name TEXT NOT NULL,
 model_type TEXT NOT NULL,
 model_version TEXT NOT NULL,
 definition_json TEXT NOT NULL,
 assumptions_json TEXT NOT NULL,
 boundaries_json TEXT NOT NULL,
 parameter_sources_json TEXT NOT NULL,
 uncertainty_json TEXT NOT NULL,
 evidence_references_json TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 executable INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(project_id,model_key,model_version)
);

CREATE TABLE IF NOT EXISTS education_p33_twin_parameters(
 parameter_id TEXT PRIMARY KEY,
 model_id TEXT NOT NULL REFERENCES education_p33_twin_models(model_id),
 parameter_version TEXT NOT NULL,
 name TEXT NOT NULL,
 value REAL NOT NULL,
 unit TEXT NOT NULL,
 lower_bound REAL,
 upper_bound REAL,
 source_reference TEXT NOT NULL,
 uncertainty REAL NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(model_id,parameter_version,name)
);

CREATE TABLE IF NOT EXISTS education_p33_twin_scenarios(
 scenario_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 model_id TEXT NOT NULL REFERENCES education_p33_twin_models(model_id),
 name TEXT NOT NULL,
 domain TEXT NOT NULL,
 baseline_json TEXT NOT NULL,
 time_steps INTEGER NOT NULL,
 step_size REAL NOT NULL,
 interventions_json TEXT NOT NULL,
 assumptions_json TEXT NOT NULL,
 seed INTEGER NOT NULL,
 acknowledgement INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_simulations(
 simulation_id TEXT PRIMARY KEY,
 scenario_id TEXT NOT NULL REFERENCES education_p33_twin_scenarios(scenario_id),
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 model_id TEXT NOT NULL REFERENCES education_p33_twin_models(model_id),
 model_version TEXT NOT NULL,
 parameter_version TEXT NOT NULL,
 seed INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('completed','failed','cancelled')),
 trajectory_json TEXT NOT NULL,
 uncertainty_json TEXT NOT NULL,
 sensitivity_json TEXT NOT NULL,
 output_sha256 TEXT NOT NULL,
 warnings_json TEXT NOT NULL,
 replay_of TEXT,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_validations(
 validation_id TEXT PRIMARY KEY,
 model_id TEXT NOT NULL REFERENCES education_p33_twin_models(model_id),
 category TEXT NOT NULL,
 benchmark_reference TEXT NOT NULL,
 expected_output_json TEXT NOT NULL,
 observed_output_json TEXT NOT NULL,
 calibration_json TEXT NOT NULL,
 sensitivity_json TEXT NOT NULL,
 uncertainty_json TEXT NOT NULL,
 reproducibility_seed INTEGER NOT NULL,
 limitations TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL,
 reviewer_id TEXT NOT NULL,
 approved INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_integrations(
 integration_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 target_module TEXT NOT NULL,
 target_object_id TEXT NOT NULL,
 purpose TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('linked','review_required','revoked')),
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_learning_activities(
 activity_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 simulation_id TEXT NOT NULL REFERENCES education_p33_twin_simulations(simulation_id),
 classroom_reference TEXT NOT NULL,
 teacher_id TEXT NOT NULL,
 interpretation_prompt TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('open','closed','archived')),
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p33_twin_learning_submissions(
 submission_id TEXT PRIMARY KEY,
 activity_id TEXT NOT NULL REFERENCES education_p33_twin_learning_activities(activity_id),
 student_id TEXT NOT NULL,
 interpretation_text TEXT NOT NULL,
 interpretation_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('submitted','reviewed','revision_requested')),
 score REAL,
 feedback TEXT NOT NULL,
 mastery_delta REAL NOT NULL DEFAULT 0,
 portfolio_record_json TEXT NOT NULL DEFAULT '{}',
 submitted_at_utc TEXT NOT NULL,
 reviewed_at_utc TEXT,
 reviewed_by TEXT,
 UNIQUE(activity_id,student_id)
);

CREATE TABLE IF NOT EXISTS education_p33_twin_audit(
 audit_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p33_twin_projects(project_id),
 actor_id TEXT NOT NULL,
 action TEXT NOT NULL,
 object_type TEXT NOT NULL,
 object_id TEXT NOT NULL,
 details_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_research_projects(
 project_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 institution_id TEXT NOT NULL,
 title TEXT NOT NULL,
 hypothesis TEXT NOT NULL,
 objectives_json TEXT NOT NULL,
 milestones_json TEXT NOT NULL,
 issues_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','archived','deleted')),
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_project_members(
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 user_id TEXT NOT NULL,
 role TEXT NOT NULL,
 added_at_utc TEXT NOT NULL,
 added_by TEXT NOT NULL,
 PRIMARY KEY(project_id,user_id)
);

CREATE TABLE IF NOT EXISTS education_p34_project_assets(
 asset_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 asset_type TEXT NOT NULL CHECK(asset_type IN (
  'sample_sheet','analysis','notebook','report','reference','approval',
  'publication','export','issue','milestone'
 )),
 title TEXT NOT NULL,
 version TEXT NOT NULL,
 content_json TEXT NOT NULL,
 source_run_id TEXT,
 archive_state TEXT NOT NULL CHECK(archive_state IN ('active','archived','deleted')),
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p34_assets_project
 ON education_p34_project_assets(project_id,asset_type,archive_state);

CREATE TABLE IF NOT EXISTS education_p34_datasets(
 dataset_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 tenant_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 institution_id TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL,
 source TEXT NOT NULL,
 licence TEXT NOT NULL,
 consent_status TEXT NOT NULL,
 access_level TEXT NOT NULL,
 format TEXT NOT NULL,
 sample_count INTEGER,
 metadata_schema_json TEXT NOT NULL,
 data_dictionary_json TEXT NOT NULL,
 version TEXT NOT NULL,
 lineage_json TEXT NOT NULL,
 quality_status TEXT NOT NULL,
 archive_state TEXT NOT NULL,
 storage_location TEXT NOT NULL,
 total_size_bytes INTEGER NOT NULL,
 manifest_sha256 TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p34_datasets_project
 ON education_p34_datasets(project_id,archive_state);

CREATE TABLE IF NOT EXISTS education_p34_dataset_files(
 dataset_file_id TEXT PRIMARY KEY,
 dataset_id TEXT NOT NULL REFERENCES education_p34_datasets(dataset_id),
 relative_path TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 format TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 validation_details_json TEXT NOT NULL,
 imported_bytes INTEGER NOT NULL,
 import_state TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 UNIQUE(dataset_id,relative_path,sha256)
);

CREATE TABLE IF NOT EXISTS education_p34_import_history(
 import_id TEXT PRIMARY KEY,
 dataset_id TEXT NOT NULL REFERENCES education_p34_datasets(dataset_id),
 source_path_hash TEXT NOT NULL,
 imported_bytes INTEGER NOT NULL,
 total_bytes INTEGER NOT NULL,
 state TEXT NOT NULL,
 support_reference TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 completed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS education_p34_dataset_import_sessions(
 session_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 tenant_id TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 encrypted_request TEXT NOT NULL,
 source_manifest_json TEXT NOT NULL,
 staging_location TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','copying','paused','completed','failed','cancelled')),
 imported_bytes INTEGER NOT NULL,
 total_bytes INTEGER NOT NULL,
 support_reference TEXT NOT NULL,
 dataset_id TEXT,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_tools(
 tool_id TEXT PRIMARY KEY,
 tool_name TEXT NOT NULL,
 tool_version TEXT NOT NULL,
 source TEXT NOT NULL,
 adapter_type TEXT NOT NULL,
 handler_key TEXT NOT NULL,
 executable_reference TEXT NOT NULL,
 container_reference TEXT NOT NULL,
 checksum TEXT NOT NULL,
 licence TEXT NOT NULL,
 parameters_schema_json TEXT NOT NULL,
 expected_inputs_json TEXT NOT NULL,
 expected_outputs_json TEXT NOT NULL,
 resource_requirements_json TEXT NOT NULL,
 permission_level TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 approved INTEGER NOT NULL DEFAULT 0,
 approved_by TEXT,
 approved_at_utc TEXT,
 state TEXT NOT NULL CHECK(state IN ('active','disabled','revoked')),
 UNIQUE(tool_name,tool_version)
);

CREATE TABLE IF NOT EXISTS education_p34_workflows(
 workflow_id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 name TEXT NOT NULL,
 domain TEXT NOT NULL,
 version TEXT NOT NULL,
 specification_json TEXT NOT NULL,
 specification_sha256 TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','approved','disabled','revoked')),
 approved_by TEXT,
 approved_at_utc TEXT,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(project_id,name,version)
);

CREATE TABLE IF NOT EXISTS education_p34_runs(
 run_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 workflow_id TEXT NOT NULL REFERENCES education_p34_workflows(workflow_id),
 dataset_id TEXT NOT NULL REFERENCES education_p34_datasets(dataset_id),
 tenant_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 institution_id TEXT NOT NULL,
 state TEXT NOT NULL,
 priority INTEGER NOT NULL,
 attempt INTEGER NOT NULL DEFAULT 0,
 max_retries INTEGER NOT NULL DEFAULT 0,
 timeout_seconds INTEGER NOT NULL,
 cpu_limit INTEGER NOT NULL,
 memory_limit_mb INTEGER NOT NULL,
 disk_limit_mb INTEGER NOT NULL,
 seed INTEGER NOT NULL,
 parameters_json TEXT NOT NULL,
 workflow_version TEXT NOT NULL,
 environment_json TEXT NOT NULL,
 started_at_utc TEXT,
 ended_at_utc TEXT,
 cancellation_requested INTEGER NOT NULL DEFAULT 0,
 failure_code TEXT NOT NULL DEFAULT '',
 safe_message TEXT NOT NULL DEFAULT '',
 support_reference TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p34_runs_queue
 ON education_p34_runs(tenant_id,state,priority,created_at_utc);

CREATE TABLE IF NOT EXISTS education_p34_compute_quotas(
 tenant_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 max_concurrent_runs INTEGER NOT NULL,
 max_queued_runs INTEGER NOT NULL,
 max_cpu INTEGER NOT NULL,
 max_memory_mb INTEGER NOT NULL,
 max_disk_mb INTEGER NOT NULL,
 max_gpu INTEGER NOT NULL DEFAULT 0,
 updated_at_utc TEXT NOT NULL,
 updated_by TEXT NOT NULL,
 PRIMARY KEY(tenant_id,user_id)
);

CREATE TABLE IF NOT EXISTS education_p34_run_steps(
 run_step_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_p34_runs(run_id),
 step_id TEXT NOT NULL,
 tool_id TEXT NOT NULL REFERENCES education_p34_tools(tool_id),
 state TEXT NOT NULL,
 attempt INTEGER NOT NULL DEFAULT 0,
 input_manifest_json TEXT NOT NULL,
 output_manifest_json TEXT NOT NULL DEFAULT '{}',
 checkpoint_json TEXT NOT NULL DEFAULT '{}',
 started_at_utc TEXT,
 ended_at_utc TEXT,
 log_text TEXT NOT NULL DEFAULT '',
 warning_text TEXT NOT NULL DEFAULT '',
 UNIQUE(run_id,step_id)
);

CREATE TABLE IF NOT EXISTS education_p34_run_artifacts(
 artifact_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_p34_runs(run_id),
 step_id TEXT NOT NULL,
 artifact_type TEXT NOT NULL,
 relative_path TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 media_type TEXT NOT NULL,
 partial INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 UNIQUE(run_id,relative_path)
);

CREATE TABLE IF NOT EXISTS education_p34_run_reviews(
 review_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_p34_runs(run_id),
 reviewer_id TEXT NOT NULL,
 decision TEXT NOT NULL,
 comments TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_result_notes(
 note_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_p34_runs(run_id),
 author_id TEXT NOT NULL,
 note_type TEXT NOT NULL CHECK(note_type IN ('annotation','comment','warning')),
 body TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_handoffs(
 handoff_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_p34_runs(run_id),
 destination TEXT NOT NULL CHECK(destination IN ('studio','shiro','discovery_agents')),
 payload_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('review_required','approved','cancelled')),
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 reviewed_at_utc TEXT,
 reviewed_by TEXT
);

CREATE TABLE IF NOT EXISTS education_p34_imported_run_bundles(
 imported_bundle_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 imported_by TEXT NOT NULL,
 source_run_id TEXT NOT NULL,
 bundle_sha256 TEXT NOT NULL UNIQUE,
 storage_location TEXT NOT NULL,
 manifest_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('reference_only','archived','deleted')),
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_remote_adapters(
 adapter_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 adapter_type TEXT NOT NULL,
 endpoint TEXT NOT NULL,
 allowed_hosts_json TEXT NOT NULL,
 command_templates_json TEXT NOT NULL,
 encrypted_credentials TEXT NOT NULL,
 resource_limits_json TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p34_compute_audit(
 audit_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 action TEXT NOT NULL,
 object_type TEXT NOT NULL,
 object_id TEXT NOT NULL,
 details_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_research_workspaces(
 workspace_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 research_project_id TEXT NOT NULL REFERENCES education_p34_research_projects(project_id),
 owner_id TEXT NOT NULL,
 institution_id TEXT NOT NULL,
 title TEXT NOT NULL,
 policy_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','archived','deleted')),
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL,
 UNIQUE(tenant_id,research_project_id)
);

CREATE TABLE IF NOT EXISTS education_p35_evidence_sources(
 source_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 tenant_id TEXT NOT NULL,
 source_type TEXT NOT NULL,
 title TEXT NOT NULL,
 citation TEXT NOT NULL,
 persistent_identifier TEXT NOT NULL,
 publication_date TEXT NOT NULL,
 abstract_text TEXT NOT NULL,
 methodology_text TEXT NOT NULL,
 limitations_text TEXT NOT NULL,
 claims_json TEXT NOT NULL,
 metadata_json TEXT NOT NULL,
 retraction_status TEXT NOT NULL,
 existence_status TEXT NOT NULL,
 content_sha256 TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(workspace_id,content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_p35_evidence_workspace
 ON education_p35_evidence_sources(workspace_id,retraction_status,existence_status);

CREATE TABLE IF NOT EXISTS education_p35_saved_searches(
 search_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 query_text TEXT NOT NULL,
 expanded_queries_json TEXT NOT NULL,
 filters_json TEXT NOT NULL,
 result_ids_json TEXT NOT NULL,
 citation_graph_json TEXT NOT NULL,
 databases_queried_json TEXT NOT NULL,
 search_date_utc TEXT NOT NULL,
 unresolved_uncertainty TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_agent_definitions(
 agent_key TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 purpose TEXT NOT NULL,
 permissions_json TEXT NOT NULL,
 prohibited_actions_json TEXT NOT NULL,
 output_schema_json TEXT NOT NULL,
 validation_status TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','disabled','revoked')),
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_agent_tasks(
 task_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 tenant_id TEXT NOT NULL,
 agent_key TEXT NOT NULL REFERENCES education_p35_agent_definitions(agent_key),
 phase24_parent_task_id TEXT,
 requested_by TEXT NOT NULL,
 input_json TEXT NOT NULL,
 evidence_ids_json TEXT NOT NULL,
 requested_permissions_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN (
  'planned','awaiting_approval','running','completed','refused','failed',
  'cancelled','revision_required'
 )),
 approval_state TEXT NOT NULL,
 output_json TEXT NOT NULL,
 uncertainty_json TEXT NOT NULL,
 novelty_status TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 safe_message TEXT NOT NULL,
 support_reference TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p35_tasks_workspace
 ON education_p35_agent_tasks(workspace_id,state,created_at_utc);

CREATE TABLE IF NOT EXISTS education_p35_agent_approvals(
 approval_id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES education_p35_agent_tasks(task_id),
 operation TEXT NOT NULL,
 requested_by TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('pending','approved','rejected')),
 decided_by TEXT,
 decision_note TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 decided_at_utc TEXT,
 UNIQUE(task_id,operation)
);

CREATE TABLE IF NOT EXISTS education_p35_hypotheses(
 hypothesis_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 tenant_id TEXT NOT NULL,
 statement TEXT NOT NULL,
 biological_context TEXT NOT NULL,
 supporting_evidence_json TEXT NOT NULL,
 contradictory_evidence_json TEXT NOT NULL,
 assumptions_json TEXT NOT NULL,
 predicted_observations_json TEXT NOT NULL,
 falsification_criteria_json TEXT NOT NULL,
 novelty_search_id TEXT,
 confidence REAL NOT NULL,
 uncertainty_json TEXT NOT NULL,
 creator_id TEXT NOT NULL,
 agent_task_id TEXT REFERENCES education_p35_agent_tasks(task_id),
 reviewer_id TEXT,
 approval_status TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN (
  'Draft','Evidence Collection','Human Review','Approved for Testing',
  'Experiment Planned','Testing','Supported','Not Supported','Inconclusive',
  'Revised','Rejected','Archived'
 )),
 linked_experiments_json TEXT NOT NULL,
 linked_datasets_json TEXT NOT NULL,
 linked_workflows_json TEXT NOT NULL,
 linked_twin_scenarios_json TEXT NOT NULL,
 results_json TEXT NOT NULL,
 outcome TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_experiments(
 experiment_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 hypothesis_id TEXT NOT NULL REFERENCES education_p35_hypotheses(hypothesis_id),
 objective TEXT NOT NULL,
 design_json TEXT NOT NULL,
 variables_json TEXT NOT NULL,
 controls_json TEXT NOT NULL,
 samples_json TEXT NOT NULL,
 replicates_json TEXT NOT NULL,
 randomization_json TEXT NOT NULL,
 blinding_json TEXT NOT NULL,
 inclusion_criteria_json TEXT NOT NULL,
 exclusion_criteria_json TEXT NOT NULL,
 endpoints_json TEXT NOT NULL,
 analysis_plan_json TEXT NOT NULL,
 resources_json TEXT NOT NULL,
 timeline_json TEXT NOT NULL,
 risks_json TEXT NOT NULL,
 ethics_status TEXT NOT NULL,
 ethics_record_asset_id TEXT,
 safety_status TEXT NOT NULL,
 specialist_review_json TEXT NOT NULL,
 protocol_version TEXT NOT NULL,
 approval_status TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','human_review','approved','active','completed','rejected','archived')),
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_novelty_searches(
 novelty_search_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 search_queries_json TEXT NOT NULL,
 search_date_utc TEXT NOT NULL,
 databases_queried_json TEXT NOT NULL,
 results_json TEXT NOT NULL,
 related_hypotheses_json TEXT NOT NULL,
 similar_methods_json TEXT NOT NULL,
 unresolved_uncertainty TEXT NOT NULL,
 legal_patent_assessment INTEGER NOT NULL DEFAULT 0,
 definitive_novelty_claim INTEGER NOT NULL DEFAULT 0,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_claim_nodes(
 node_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 node_type TEXT NOT NULL CHECK(node_type IN (
  'claim','source','dataset','analysis','figure','hypothesis','experiment',
  'model','digital_twin_result','reviewer','publication_asset'
 )),
 external_id TEXT NOT NULL,
 label TEXT NOT NULL,
 metadata_json TEXT NOT NULL,
 confidence REAL NOT NULL,
 unsupported INTEGER NOT NULL,
 provenance_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(workspace_id,node_type,external_id)
);

CREATE TABLE IF NOT EXISTS education_p35_claim_edges(
 edge_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 source_node_id TEXT NOT NULL REFERENCES education_p35_claim_nodes(node_id),
 target_node_id TEXT NOT NULL REFERENCES education_p35_claim_nodes(node_id),
 relation TEXT NOT NULL CHECK(relation IN (
  'direct_evidence','indirect_evidence','conflicting_evidence','derived_from',
  'generated_by','reviewed_by','supports','contradicts','references'
 )),
 confidence REAL NOT NULL,
 provenance_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 UNIQUE(workspace_id,source_node_id,target_node_id,relation)
);

CREATE TABLE IF NOT EXISTS education_p35_discovery_workflows(
 discovery_workflow_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 research_question TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','active','awaiting_human','completed','cancelled')),
 current_step INTEGER NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_discovery_steps(
 discovery_step_id TEXT PRIMARY KEY,
 discovery_workflow_id TEXT NOT NULL REFERENCES education_p35_discovery_workflows(discovery_workflow_id),
 sequence INTEGER NOT NULL,
 step_key TEXT NOT NULL,
 agent_key TEXT,
 human_checkpoint INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','ready','awaiting_human','completed','blocked','cancelled')),
 task_id TEXT,
 artifact_reference TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 completed_at_utc TEXT,
 UNIQUE(discovery_workflow_id,sequence)
);

CREATE TABLE IF NOT EXISTS education_p35_agent_evaluations(
 evaluation_id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES education_p35_research_workspaces(workspace_id),
 suite_version TEXT NOT NULL,
 fixture_manifest_sha256 TEXT NOT NULL,
 metrics_json TEXT NOT NULL,
 passed_count INTEGER NOT NULL,
 failed_count INTEGER NOT NULL,
 created_at_utc TEXT NOT NULL,
 created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p35_integrity_audit(
 audit_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 action TEXT NOT NULL,
 object_type TEXT NOT NULL,
 object_id TEXT NOT NULL,
 details_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL
);
"""
