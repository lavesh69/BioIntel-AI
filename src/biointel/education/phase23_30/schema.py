from __future__ import annotations

MIGRATION_ID = "education_phase23_to_30_enterprise_platform_v1"

SCHEMA = r"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS education_p30_pilots(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 status TEXT NOT NULL,
 starts_on TEXT NOT NULL DEFAULT '',
 ends_on TEXT NOT NULL DEFAULT '',
 goals_json TEXT NOT NULL DEFAULT '[]',
 administrator_ids_json TEXT NOT NULL DEFAULT '[]',
 departments_json TEXT NOT NULL DEFAULT '[]',
 user_limit INTEGER NOT NULL DEFAULT 0,
 feature_flags_json TEXT NOT NULL DEFAULT '{}',
 terms_version TEXT NOT NULL DEFAULT '',
 consent_state TEXT NOT NULL DEFAULT 'pending',
 consented_by TEXT NOT NULL DEFAULT '',
 consented_at TEXT,
 support_contact TEXT NOT NULL DEFAULT '',
 onboarding_percent REAL NOT NULL DEFAULT 0,
 health_score REAL NOT NULL DEFAULT 0,
 blocker_count INTEGER NOT NULL DEFAULT 0,
 signoff_state TEXT NOT NULL DEFAULT 'pending',
 readiness_decision TEXT NOT NULL DEFAULT '',
 archived_at TEXT,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE INDEX IF NOT EXISTS idx_p30_pilots_tenant_status
 ON education_p30_pilots(institution_id,status,updated_at);

CREATE TABLE IF NOT EXISTS education_p30_pilot_transitions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 pilot_id TEXT NOT NULL REFERENCES education_p30_pilots(id),
 from_status TEXT NOT NULL,
 to_status TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',
 blocker_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_pilot_transition
 ON education_p30_pilot_transitions(pilot_id,created_at);

CREATE TABLE IF NOT EXISTS education_p30_onboarding(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 pilot_id TEXT NOT NULL REFERENCES education_p30_pilots(id),
 user_id TEXT NOT NULL,
 role TEXT NOT NULL,
 checklist_json TEXT NOT NULL DEFAULT '[]',
 tutorial_state_json TEXT NOT NULL DEFAULT '{}',
 configuration_json TEXT NOT NULL DEFAULT '{}',
 data_mode TEXT NOT NULL DEFAULT 'none',
 validation_errors_json TEXT NOT NULL DEFAULT '[]',
 progress_percent REAL NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'in_progress',
 approved_by TEXT NOT NULL DEFAULT '',
 approved_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(pilot_id,user_id,role)
);
CREATE INDEX IF NOT EXISTS idx_p30_onboarding_user
 ON education_p30_onboarding(institution_id,user_id,state);

CREATE TABLE IF NOT EXISTS education_p30_import_jobs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 pilot_id TEXT REFERENCES education_p30_pilots(id),
 entity_type TEXT NOT NULL,
 source_name TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 source_encoding TEXT NOT NULL DEFAULT 'utf-8-sig',
 dry_run INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL,
 confirmation_digest TEXT NOT NULL DEFAULT '',
 row_count INTEGER NOT NULL DEFAULT 0,
 valid_count INTEGER NOT NULL DEFAULT 0,
 invalid_count INTEGER NOT NULL DEFAULT 0,
 duplicate_count INTEGER NOT NULL DEFAULT 0,
 error_report_path TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 committed_by TEXT NOT NULL DEFAULT '',
 committed_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_import_jobs
 ON education_p30_import_jobs(institution_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_p30_import_rows(
 id TEXT PRIMARY KEY,
 job_id TEXT NOT NULL REFERENCES education_p30_import_jobs(id) ON DELETE CASCADE,
 row_number INTEGER NOT NULL,
 external_key TEXT NOT NULL DEFAULT '',
 payload_json TEXT NOT NULL,
 validation_errors_json TEXT NOT NULL DEFAULT '[]',
 duplicate_of TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(job_id,row_number)
);
CREATE INDEX IF NOT EXISTS idx_p30_import_rows_state
 ON education_p30_import_rows(job_id,state,row_number);

CREATE TABLE IF NOT EXISTS education_p30_pilot_records(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 entity_type TEXT NOT NULL,
 external_key TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 source_job_id TEXT NOT NULL REFERENCES education_p30_import_jobs(id),
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,entity_type,external_key)
);
CREATE INDEX IF NOT EXISTS idx_p30_pilot_records
 ON education_p30_pilot_records(institution_id,entity_type,state);

CREATE TABLE IF NOT EXISTS education_p30_health_samples(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 module TEXT NOT NULL,
 component TEXT NOT NULL,
 status TEXT NOT NULL,
 latency_ms REAL NOT NULL DEFAULT 0,
 failure_rate REAL NOT NULL DEFAULT 0,
 retry_count INTEGER NOT NULL DEFAULT 0,
 metrics_json TEXT NOT NULL DEFAULT '{}',
 sensitive_content_collected INTEGER NOT NULL DEFAULT 0,
 recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_health_samples
 ON education_p30_health_samples(institution_id,module,recorded_at);

CREATE TABLE IF NOT EXISTS education_p30_support_tickets(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 pilot_id TEXT REFERENCES education_p30_pilots(id),
 reporter_id TEXT NOT NULL,
 module TEXT NOT NULL,
 severity TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL,
 screenshot_path TEXT NOT NULL DEFAULT '',
 diagnostic_path TEXT NOT NULL DEFAULT '',
 consent INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'open',
 assigned_to TEXT NOT NULL DEFAULT '',
 resolution TEXT NOT NULL DEFAULT '',
 reopened_count INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_support_tickets
 ON education_p30_support_tickets(institution_id,state,severity,updated_at);

CREATE TABLE IF NOT EXISTS education_p30_support_comments(
 id TEXT PRIMARY KEY,
 ticket_id TEXT NOT NULL REFERENCES education_p30_support_tickets(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL,
 body TEXT NOT NULL,
 internal_only INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_agent_definitions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 key TEXT NOT NULL,
 name TEXT NOT NULL,
 description TEXT NOT NULL,
 allowed_tools_json TEXT NOT NULL DEFAULT '[]',
 prohibited_actions_json TEXT NOT NULL DEFAULT '[]',
 output_schema_json TEXT NOT NULL DEFAULT '{}',
 provider_policy_json TEXT NOT NULL DEFAULT '{}',
 memory_policy_json TEXT NOT NULL DEFAULT '{}',
 version TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,key,version)
);

CREATE TABLE IF NOT EXISTS education_p30_agent_tools(
 id TEXT PRIMARY KEY,
 key TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 description TEXT NOT NULL,
 permission TEXT NOT NULL,
 write_operation INTEGER NOT NULL DEFAULT 0,
 human_approval_required INTEGER NOT NULL DEFAULT 0,
 timeout_seconds INTEGER NOT NULL DEFAULT 60,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_agent_tasks(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 agent_key TEXT NOT NULL,
 parent_task_id TEXT REFERENCES education_p30_agent_tasks(id),
 root_task_id TEXT NOT NULL,
 depth INTEGER NOT NULL DEFAULT 0,
 requested_by TEXT NOT NULL,
 subject_user_id TEXT NOT NULL DEFAULT '',
 input_json TEXT NOT NULL,
 plan_json TEXT NOT NULL DEFAULT '[]',
 requested_tools_json TEXT NOT NULL DEFAULT '[]',
 provider TEXT NOT NULL DEFAULT 'local',
 provider_model TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL,
 approval_required INTEGER NOT NULL DEFAULT 0,
 approval_state TEXT NOT NULL DEFAULT 'not_required',
 output_json TEXT NOT NULL DEFAULT '{}',
 validation_json TEXT NOT NULL DEFAULT '{}',
 error TEXT NOT NULL DEFAULT '',
 token_count INTEGER NOT NULL DEFAULT 0,
 resource_seconds REAL NOT NULL DEFAULT 0,
 retry_count INTEGER NOT NULL DEFAULT 0,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 timeout_seconds INTEGER NOT NULL DEFAULT 120,
 idempotency_key TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_p30_agent_tasks
 ON education_p30_agent_tasks(institution_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_p30_agent_steps(
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES education_p30_agent_tasks(id) ON DELETE CASCADE,
 sequence INTEGER NOT NULL,
 tool_key TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL,
 input_json TEXT NOT NULL DEFAULT '{}',
 output_json TEXT NOT NULL DEFAULT '{}',
 error TEXT NOT NULL DEFAULT '',
 started_at TEXT,
 completed_at TEXT,
 UNIQUE(task_id,sequence)
);

CREATE TABLE IF NOT EXISTS education_p30_agent_evidence(
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES education_p30_agent_tasks(id) ON DELETE CASCADE,
 source_type TEXT NOT NULL,
 source_id TEXT NOT NULL,
 citation TEXT NOT NULL,
 claim TEXT NOT NULL DEFAULT '',
 confidence REAL NOT NULL DEFAULT 0,
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_agent_approvals(
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES education_p30_agent_tasks(id) ON DELETE CASCADE,
 checkpoint TEXT NOT NULL,
 requested_by TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'pending',
 decided_by TEXT NOT NULL DEFAULT '',
 decision_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 decided_at TEXT,
 UNIQUE(task_id,checkpoint)
);

CREATE TABLE IF NOT EXISTS education_p30_lab_experiments(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 key TEXT NOT NULL,
 discipline TEXT NOT NULL,
 title TEXT NOT NULL,
 capability_class TEXT NOT NULL,
 learning_outcomes_json TEXT NOT NULL DEFAULT '[]',
 prerequisites_json TEXT NOT NULL DEFAULT '[]',
 theory TEXT NOT NULL,
 apparatus_json TEXT NOT NULL DEFAULT '[]',
 reagents_json TEXT NOT NULL DEFAULT '[]',
 safety_json TEXT NOT NULL DEFAULT '[]',
 hazard_json TEXT NOT NULL DEFAULT '[]',
 references_json TEXT NOT NULL DEFAULT '[]',
 current_version INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL DEFAULT 'system',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,key)
);

CREATE TABLE IF NOT EXISTS education_p30_lab_versions(
 id TEXT PRIMARY KEY,
 experiment_id TEXT NOT NULL REFERENCES education_p30_lab_experiments(id),
 version INTEGER NOT NULL,
 protocol_json TEXT NOT NULL,
 calculation_schema_json TEXT NOT NULL DEFAULT '{}',
 scenario_json TEXT NOT NULL DEFAULT '{}',
 content_sha256 TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(experiment_id,version)
);

CREATE TABLE IF NOT EXISTS education_p30_lab_attempts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 experiment_id TEXT NOT NULL REFERENCES education_p30_lab_experiments(id),
 experiment_version INTEGER NOT NULL,
 student_id TEXT NOT NULL,
 assigned_by TEXT NOT NULL DEFAULT '',
 scenario_seed INTEGER NOT NULL,
 state TEXT NOT NULL,
 current_step INTEGER NOT NULL DEFAULT 0,
 safety_violations INTEGER NOT NULL DEFAULT 0,
 invalid_actions INTEGER NOT NULL DEFAULT 0,
 measurements_json TEXT NOT NULL DEFAULT '{}',
 results_json TEXT NOT NULL DEFAULT '{}',
 signed_submission_sha256 TEXT NOT NULL DEFAULT '',
 submitted_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_lab_attempts
 ON education_p30_lab_attempts(institution_id,student_id,state,updated_at);

CREATE TABLE IF NOT EXISTS education_p30_lab_steps(
 id TEXT PRIMARY KEY,
 attempt_id TEXT NOT NULL REFERENCES education_p30_lab_attempts(id) ON DELETE CASCADE,
 sequence INTEGER NOT NULL,
 step_key TEXT NOT NULL,
 action TEXT NOT NULL,
 input_json TEXT NOT NULL DEFAULT '{}',
 output_json TEXT NOT NULL DEFAULT '{}',
 valid INTEGER NOT NULL,
 safety_violation INTEGER NOT NULL DEFAULT 0,
 feedback TEXT NOT NULL DEFAULT '',
 recorded_at TEXT NOT NULL,
 UNIQUE(attempt_id,sequence)
);

CREATE TABLE IF NOT EXISTS education_p30_lab_notebook_entries(
 id TEXT PRIMARY KEY,
 attempt_id TEXT NOT NULL REFERENCES education_p30_lab_attempts(id) ON DELETE CASCADE,
 author_id TEXT NOT NULL,
 entry_type TEXT NOT NULL,
 body TEXT NOT NULL DEFAULT '',
 data_json TEXT NOT NULL DEFAULT '{}',
 attachment_path TEXT NOT NULL DEFAULT '',
 attachment_sha256 TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL,
 protocol_deviation INTEGER NOT NULL DEFAULT 0,
 instructor_comment TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 UNIQUE(attempt_id,version)
);

CREATE TABLE IF NOT EXISTS education_p30_lab_assessments(
 id TEXT PRIMARY KEY,
 attempt_id TEXT NOT NULL REFERENCES education_p30_lab_attempts(id),
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 assessor_id TEXT NOT NULL,
 procedural_score REAL NOT NULL,
 calculation_score REAL NOT NULL,
 safety_score REAL NOT NULL,
 interpretation_score REAL NOT NULL,
 rubric_score REAL NOT NULL,
 viva_json TEXT NOT NULL DEFAULT '[]',
 feedback TEXT NOT NULL DEFAULT '',
 override_reason TEXT NOT NULL DEFAULT '',
 total_score REAL NOT NULL,
 state TEXT NOT NULL DEFAULT 'released',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(attempt_id)
);

CREATE TABLE IF NOT EXISTS education_p30_concepts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT NOT NULL DEFAULT '',
 key TEXT NOT NULL,
 name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 learning_outcomes_json TEXT NOT NULL DEFAULT '[]',
 skill_keys_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,key)
);
CREATE INDEX IF NOT EXISTS idx_p30_concepts_subject
 ON education_p30_concepts(institution_id,subject_id,state);

CREATE TABLE IF NOT EXISTS education_p30_concept_edges(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 source_concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 target_concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 relation TEXT NOT NULL,
 weight REAL NOT NULL DEFAULT 1,
 policy_version TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(source_concept_id,target_concept_id,relation,policy_version)
);

CREATE TABLE IF NOT EXISTS education_p30_concept_mappings(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 resource_type TEXT NOT NULL,
 resource_id TEXT NOT NULL,
 weight REAL NOT NULL DEFAULT 1,
 verified INTEGER NOT NULL DEFAULT 0,
 verified_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(concept_id,resource_type,resource_id)
);

CREATE TABLE IF NOT EXISTS education_p30_mastery_policies(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 algorithm TEXT NOT NULL,
 version TEXT NOT NULL,
 minimum_evidence INTEGER NOT NULL DEFAULT 3,
 configuration_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(institution_id,name,version)
);

CREATE TABLE IF NOT EXISTS education_p30_mastery_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 evidence_type TEXT NOT NULL,
 correctness REAL NOT NULL,
 confidence REAL NOT NULL DEFAULT 0,
 difficulty REAL NOT NULL DEFAULT 0.5,
 hint_use INTEGER NOT NULL DEFAULT 0,
 time_seconds REAL NOT NULL DEFAULT 0,
 practical_score REAL,
 examination_score REAL,
 self_assessment REAL,
 source_id TEXT NOT NULL DEFAULT '',
 occurred_at TEXT NOT NULL,
 created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_mastery_events
 ON education_p30_mastery_events(institution_id,student_id,concept_id,occurred_at);

CREATE TABLE IF NOT EXISTS education_p30_mastery_records(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 policy_id TEXT NOT NULL REFERENCES education_p30_mastery_policies(id),
 score REAL NOT NULL,
 state TEXT NOT NULL,
 evidence_count INTEGER NOT NULL,
 last_evidence_at TEXT NOT NULL,
 explanation_codes_json TEXT NOT NULL DEFAULT '[]',
 teacher_override TEXT NOT NULL DEFAULT '',
 student_feedback TEXT NOT NULL DEFAULT '',
 opted_out INTEGER NOT NULL DEFAULT 0,
 version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(student_id,concept_id,policy_id)
);

CREATE TABLE IF NOT EXISTS education_p30_adaptive_recommendations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 recommendation_type TEXT NOT NULL,
 resource_type TEXT NOT NULL DEFAULT '',
 resource_id TEXT NOT NULL DEFAULT '',
 explanation_codes_json TEXT NOT NULL,
 explanation TEXT NOT NULL,
 evidence_snapshot_json TEXT NOT NULL,
 policy_name TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 teacher_review_state TEXT NOT NULL DEFAULT 'pending',
 teacher_id TEXT NOT NULL DEFAULT '',
 student_feedback TEXT NOT NULL DEFAULT '',
 expires_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_recommendations
 ON education_p30_adaptive_recommendations(institution_id,student_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_p30_review_schedule(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_p30_concepts(id),
 algorithm TEXT NOT NULL,
 algorithm_version TEXT NOT NULL,
 interval_days INTEGER NOT NULL,
 easiness REAL NOT NULL,
 repetitions INTEGER NOT NULL,
 next_review_at TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'scheduled',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(student_id,concept_id,algorithm,algorithm_version)
);

CREATE TABLE IF NOT EXISTS education_p30_research_papers(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 doi TEXT NOT NULL DEFAULT '',
 pmid TEXT NOT NULL DEFAULT '',
 pmcid TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL,
 authors_json TEXT NOT NULL DEFAULT '[]',
 journal TEXT NOT NULL DEFAULT '',
 published_on TEXT NOT NULL DEFAULT '',
 abstract TEXT NOT NULL DEFAULT '',
 study_type TEXT NOT NULL DEFAULT '',
 population_sample TEXT NOT NULL DEFAULT '',
 methods TEXT NOT NULL DEFAULT '',
 findings TEXT NOT NULL DEFAULT '',
 limitations TEXT NOT NULL DEFAULT '',
 conflicts TEXT NOT NULL DEFAULT '',
 funding TEXT NOT NULL DEFAULT '',
 retraction_state TEXT NOT NULL DEFAULT 'unknown',
 correction_state TEXT NOT NULL DEFAULT 'unknown',
 evidence_confidence TEXT NOT NULL DEFAULT 'unrated',
 source_metadata_json TEXT NOT NULL DEFAULT '{}',
 uploaded_pdf_path TEXT NOT NULL DEFAULT '',
 uploaded_pdf_sha256 TEXT NOT NULL DEFAULT '',
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_p30_paper_doi
 ON education_p30_research_papers(institution_id,doi) WHERE doi<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_p30_paper_pmid
 ON education_p30_research_papers(institution_id,pmid) WHERE pmid<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_p30_paper_pmcid
 ON education_p30_research_papers(institution_id,pmcid) WHERE pmcid<>'';

CREATE TABLE IF NOT EXISTS education_p30_paper_claims(
 id TEXT PRIMARY KEY,
 paper_id TEXT NOT NULL REFERENCES education_p30_research_papers(id) ON DELETE CASCADE,
 claim TEXT NOT NULL,
 evidence_excerpt TEXT NOT NULL DEFAULT '',
 locator TEXT NOT NULL DEFAULT '',
 confidence REAL NOT NULL DEFAULT 0,
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 verified_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_research_assets(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 asset_type TEXT NOT NULL,
 title TEXT NOT NULL,
 source_paper_ids_json TEXT NOT NULL,
 source_claim_ids_json TEXT NOT NULL DEFAULT '[]',
 content_json TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 citation_json TEXT NOT NULL,
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 review_state TEXT NOT NULL DEFAULT 'draft',
 publishing_state TEXT NOT NULL DEFAULT 'draft',
 version INTEGER NOT NULL DEFAULT 1,
 created_by TEXT NOT NULL,
 published_target TEXT NOT NULL DEFAULT '',
 published_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_research_assets
 ON education_p30_research_assets(institution_id,review_state,publishing_state);

CREATE TABLE IF NOT EXISTS education_p30_asset_reviews(
 id TEXT PRIMARY KEY,
 asset_id TEXT NOT NULL REFERENCES education_p30_research_assets(id) ON DELETE CASCADE,
 reviewer_id TEXT NOT NULL,
 decision TEXT NOT NULL,
 comments TEXT NOT NULL DEFAULT '',
 evidence_check_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_research_projects(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 title TEXT NOT NULL,
 supervisor_id TEXT NOT NULL,
 team_json TEXT NOT NULL DEFAULT '[]',
 research_questions_json TEXT NOT NULL DEFAULT '[]',
 hypotheses_json TEXT NOT NULL DEFAULT '[]',
 literature_ids_json TEXT NOT NULL DEFAULT '[]',
 protocol_json TEXT NOT NULL DEFAULT '{}',
 milestones_json TEXT NOT NULL DEFAULT '[]',
 dataset_metadata_json TEXT NOT NULL DEFAULT '[]',
 analysis_records_json TEXT NOT NULL DEFAULT '[]',
 manuscript_json TEXT NOT NULL DEFAULT '{}',
 ethics_metadata_json TEXT NOT NULL DEFAULT '{}',
 ethics_approval_verified INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_portfolios(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,
 profile_json TEXT NOT NULL DEFAULT '{}',
 visibility TEXT NOT NULL DEFAULT 'private',
 minor_safe INTEGER NOT NULL DEFAULT 1,
 public_opt_in INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,owner_id)
);

CREATE TABLE IF NOT EXISTS education_p30_portfolio_items(
 id TEXT PRIMARY KEY,
 portfolio_id TEXT NOT NULL REFERENCES education_p30_portfolios(id) ON DELETE CASCADE,
 item_type TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 evidence_type TEXT NOT NULL,
 evidence_id TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 verified_by TEXT NOT NULL DEFAULT '',
 selected_for_showcase INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_skills(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 key TEXT NOT NULL,
 category TEXT NOT NULL,
 name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 reassessment_days INTEGER NOT NULL DEFAULT 365,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,key)
);

CREATE TABLE IF NOT EXISTS education_p30_skill_evidence(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,
 skill_id TEXT NOT NULL REFERENCES education_p30_skills(id),
 evidence_type TEXT NOT NULL,
 evidence_id TEXT NOT NULL,
 proficiency TEXT NOT NULL,
 demonstrated_at TEXT NOT NULL,
 verification_state TEXT NOT NULL DEFAULT 'unverified',
 reviewer_id TEXT NOT NULL DEFAULT '',
 expires_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(owner_id,skill_id,evidence_type,evidence_id)
);

CREATE TABLE IF NOT EXISTS education_p30_credentials(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,
 credential_type TEXT NOT NULL,
 title TEXT NOT NULL,
 criteria_json TEXT NOT NULL,
 evidence_json TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL,
 issuer_id TEXT NOT NULL,
 issued_at TEXT NOT NULL,
 expires_at TEXT,
 unique_code TEXT NOT NULL UNIQUE,
 signature TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 revocation_reason TEXT NOT NULL DEFAULT '',
 revoked_by TEXT NOT NULL DEFAULT '',
 revoked_at TEXT,
 certificate_path TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_credentials_owner
 ON education_p30_credentials(institution_id,owner_id,state);

CREATE TABLE IF NOT EXISTS education_p30_credential_events(
 id TEXT PRIMARY KEY,
 credential_id TEXT NOT NULL REFERENCES education_p30_credentials(id),
 actor_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_p30_portfolio_shares(
 id TEXT PRIMARY KEY,
 portfolio_id TEXT NOT NULL REFERENCES education_p30_portfolios(id) ON DELETE CASCADE,
 token_sha256 TEXT NOT NULL UNIQUE,
 audience TEXT NOT NULL,
 item_ids_json TEXT NOT NULL DEFAULT '[]',
 expires_at TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS education_p30_career_plans(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 owner_id TEXT NOT NULL,
 career_key TEXT NOT NULL,
 interest_json TEXT NOT NULL DEFAULT '{}',
 required_skills_json TEXT NOT NULL DEFAULT '[]',
 missing_skills_json TEXT NOT NULL DEFAULT '[]',
 roadmap_json TEXT NOT NULL DEFAULT '[]',
 internships_json TEXT NOT NULL DEFAULT '[]',
 applications_json TEXT NOT NULL DEFAULT '[]',
 mentor_notes TEXT NOT NULL DEFAULT '',
 guidance_disclaimer TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,owner_id,career_key)
);

CREATE TABLE IF NOT EXISTS education_p30_integrations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 adapter_type TEXT NOT NULL,
 name TEXT NOT NULL,
 configuration_json TEXT NOT NULL DEFAULT '{}',
 secret_reference TEXT NOT NULL DEFAULT '',
 capability_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'disabled',
 last_test_state TEXT NOT NULL DEFAULT 'not_tested',
 last_test_detail TEXT NOT NULL DEFAULT '',
 last_test_at TEXT,
 timeout_seconds INTEGER NOT NULL DEFAULT 30,
 max_retries INTEGER NOT NULL DEFAULT 3,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);

CREATE TABLE IF NOT EXISTS education_p30_sync_runs(
 id TEXT PRIMARY KEY,
 integration_id TEXT NOT NULL REFERENCES education_p30_integrations(id),
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 direction TEXT NOT NULL,
 dry_run INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL,
 cursor TEXT NOT NULL DEFAULT '',
 received_count INTEGER NOT NULL DEFAULT 0,
 applied_count INTEGER NOT NULL DEFAULT 0,
 conflict_count INTEGER NOT NULL DEFAULT 0,
 retry_count INTEGER NOT NULL DEFAULT 0,
 conflict_json TEXT NOT NULL DEFAULT '[]',
 error TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL,
 completed_at TEXT
);

CREATE TABLE IF NOT EXISTS education_p30_api_keys(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 key_prefix TEXT NOT NULL,
 key_sha256 TEXT NOT NULL UNIQUE,
 scopes_json TEXT NOT NULL,
 created_by TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 expires_at TEXT,
 last_used_at TEXT,
 revoked_at TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_api_keys
 ON education_p30_api_keys(institution_id,state,key_prefix);

CREATE TABLE IF NOT EXISTS education_p30_api_usage(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 api_key_id TEXT NOT NULL DEFAULT '',
 actor_id TEXT NOT NULL DEFAULT '',
 route TEXT NOT NULL,
 method TEXT NOT NULL,
 status_code INTEGER NOT NULL,
 latency_ms REAL NOT NULL,
 request_id TEXT NOT NULL,
 idempotency_key TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_api_usage
 ON education_p30_api_usage(institution_id,created_at);

CREATE TABLE IF NOT EXISTS education_p30_webhooks(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 target_url TEXT NOT NULL,
 event_types_json TEXT NOT NULL,
 signing_secret_encrypted TEXT NOT NULL,
 secret_version INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'active',
 failure_count INTEGER NOT NULL DEFAULT 0,
 disabled_reason TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);

CREATE TABLE IF NOT EXISTS education_p30_webhook_deliveries(
 id TEXT PRIMARY KEY,
 webhook_id TEXT NOT NULL REFERENCES education_p30_webhooks(id),
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 event_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 signature TEXT NOT NULL,
 nonce TEXT NOT NULL,
 state TEXT NOT NULL,
 attempt_count INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TEXT,
 response_code INTEGER,
 response_excerpt TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(webhook_id,event_id)
);

CREATE TABLE IF NOT EXISTS education_p30_plugins(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 key TEXT NOT NULL,
 name TEXT NOT NULL,
 version TEXT NOT NULL,
 compatibility TEXT NOT NULL,
 manifest_json TEXT NOT NULL,
 configuration_schema_json TEXT NOT NULL DEFAULT '{}',
 trusted_state TEXT NOT NULL DEFAULT 'untrusted',
 signature_state TEXT NOT NULL DEFAULT 'not_verified',
 development_mode INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'disabled',
 health_state TEXT NOT NULL DEFAULT 'not_run',
 last_error TEXT NOT NULL DEFAULT '',
 installed_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,key)
);

CREATE TABLE IF NOT EXISTS education_p30_plugin_permissions(
 id TEXT PRIMARY KEY,
 plugin_id TEXT NOT NULL REFERENCES education_p30_plugins(id) ON DELETE CASCADE,
 permission TEXT NOT NULL,
 granted INTEGER NOT NULL DEFAULT 0,
 granted_by TEXT NOT NULL DEFAULT '',
 granted_at TEXT,
 UNIQUE(plugin_id,permission)
);

CREATE TABLE IF NOT EXISTS education_p30_mcp_policies(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 principal_id TEXT NOT NULL,
 tool_key TEXT NOT NULL,
 allowed INTEGER NOT NULL DEFAULT 0,
 write_approval_required INTEGER NOT NULL DEFAULT 1,
 rate_limit_per_minute INTEGER NOT NULL DEFAULT 30,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,principal_id,tool_key)
);

CREATE TABLE IF NOT EXISTS education_p30_jobs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 queue TEXT NOT NULL,
 job_type TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 idempotency_key TEXT NOT NULL,
 state TEXT NOT NULL,
 priority INTEGER NOT NULL DEFAULT 100,
 progress REAL NOT NULL DEFAULT 0,
 result_json TEXT NOT NULL DEFAULT '{}',
 error TEXT NOT NULL DEFAULT '',
 retry_count INTEGER NOT NULL DEFAULT 0,
 max_retries INTEGER NOT NULL DEFAULT 3,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 available_at TEXT NOT NULL,
 locked_by TEXT NOT NULL DEFAULT '',
 locked_at TEXT,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,job_type,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_p30_jobs_claim
 ON education_p30_jobs(queue,state,available_at,priority,created_at);

CREATE TABLE IF NOT EXISTS education_p30_job_attempts(
 id TEXT PRIMARY KEY,
 job_id TEXT NOT NULL REFERENCES education_p30_jobs(id) ON DELETE CASCADE,
 worker_id TEXT NOT NULL,
 attempt INTEGER NOT NULL,
 state TEXT NOT NULL,
 error TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL,
 completed_at TEXT,
 UNIQUE(job_id,attempt)
);

CREATE TABLE IF NOT EXISTS education_p30_objects(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 storage_backend TEXT NOT NULL,
 tenant_key TEXT NOT NULL,
 original_name TEXT NOT NULL,
 content_type TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 storage_path TEXT NOT NULL,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 deleted_at TEXT,
 UNIQUE(institution_id,tenant_key)
);
CREATE INDEX IF NOT EXISTS idx_p30_objects_usage
 ON education_p30_objects(institution_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_p30_deployment_profiles(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 profile_type TEXT NOT NULL,
 configuration_json TEXT NOT NULL,
 validation_json TEXT NOT NULL DEFAULT '{}',
 validation_state TEXT NOT NULL DEFAULT 'not_validated',
 version TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,profile_type,version)
);

CREATE TABLE IF NOT EXISTS education_p30_recovery_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 recovery_type TEXT NOT NULL,
 source_reference TEXT NOT NULL,
 state TEXT NOT NULL,
 verification_json TEXT NOT NULL DEFAULT '{}',
 rpo_seconds INTEGER,
 rto_seconds INTEGER,
 error TEXT NOT NULL DEFAULT '',
 initiated_by TEXT NOT NULL,
 started_at TEXT NOT NULL,
 completed_at TEXT
);

CREATE TABLE IF NOT EXISTS education_p30_audit_chain(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 actor_id TEXT NOT NULL,
 action TEXT NOT NULL,
 target_type TEXT NOT NULL,
 target_id TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 previous_hash TEXT NOT NULL,
 event_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p30_audit_chain
 ON education_p30_audit_chain(institution_id,created_at);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
VALUES('education_phase23_to_30_enterprise_platform_v1',datetime('now'));
"""

