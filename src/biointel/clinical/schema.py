from __future__ import annotations

import sqlite3
from collections.abc import Callable

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS validation_programs (
    program_id TEXT PRIMARY KEY, title TEXT NOT NULL, claim_profile TEXT NOT NULL,
    intended_use TEXT NOT NULL, decision_context TEXT NOT NULL, target_population TEXT NOT NULL,
    jurisdictions_json TEXT NOT NULL, risk_classification TEXT NOT NULL,
    prohibited_uses_json TEXT NOT NULL, owner TEXT NOT NULL, quality_owner TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_sites (
    site_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, site_name TEXT NOT NULL,
    organization TEXT NOT NULL, country TEXT NOT NULL, independent INTEGER NOT NULL,
    laboratory_accreditation TEXT, principal_investigator TEXT NOT NULL, qa_contact TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE TABLE IF NOT EXISTS protocols (
    protocol_version_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, protocol_id TEXT NOT NULL,
    version INTEGER NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
    primary_endpoint TEXT NOT NULL, success_criterion TEXT NOT NULL, sample_size INTEGER NOT NULL,
    statistical_plan TEXT NOT NULL, preregistration_reference TEXT, ethics_reference TEXT,
    data_management_plan TEXT NOT NULL, payload_json TEXT NOT NULL, protocol_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT,
    UNIQUE(program_id, protocol_id, version),
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE TABLE IF NOT EXISTS model_freezes (
    freeze_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, protocol_version_id TEXT NOT NULL,
    model_id TEXT NOT NULL, model_sha256 TEXT NOT NULL, dataset_sha256 TEXT NOT NULL,
    code_sha256 TEXT NOT NULL, environment_sha256 TEXT NOT NULL, feature_spec_sha256 TEXT NOT NULL,
    intended_use TEXT NOT NULL, locked_by TEXT NOT NULL, locked_at TEXT NOT NULL, status TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id),
    FOREIGN KEY(protocol_version_id) REFERENCES protocols(protocol_version_id)
);
CREATE TABLE IF NOT EXISTS prediction_batches (
    batch_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, freeze_id TEXT NOT NULL, site_id TEXT NOT NULL,
    batch_label TEXT NOT NULL, predictions_sha256 TEXT NOT NULL, sample_count INTEGER NOT NULL,
    blinded INTEGER NOT NULL, sample_code_scheme TEXT NOT NULL, locked_by TEXT NOT NULL,
    locked_at TEXT NOT NULL, status TEXT NOT NULL, UNIQUE(program_id, batch_label),
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id),
    FOREIGN KEY(freeze_id) REFERENCES model_freezes(freeze_id),
    FOREIGN KEY(site_id) REFERENCES validation_sites(site_id)
);
CREATE TABLE IF NOT EXISTS outcome_batches (
    outcome_batch_id TEXT PRIMARY KEY, program_id TEXT NOT NULL,
    prediction_batch_id TEXT NOT NULL UNIQUE, outcomes_sha256 TEXT NOT NULL,
    sample_count INTEGER NOT NULL, endpoint_name TEXT NOT NULL, adjudicated INTEGER NOT NULL,
    received_by TEXT NOT NULL, received_at TEXT NOT NULL, status TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id),
    FOREIGN KEY(prediction_batch_id) REFERENCES prediction_batches(batch_id)
);
CREATE TABLE IF NOT EXISTS analysis_results (
    analysis_result_id TEXT PRIMARY KEY, program_id TEXT NOT NULL,
    protocol_version_id TEXT NOT NULL, result_scope TEXT NOT NULL, site_id TEXT, subgroup TEXT,
    metric_name TEXT NOT NULL, metric_value REAL NOT NULL, lower_ci REAL, upper_ci REAL,
    success_criterion TEXT NOT NULL, passed INTEGER NOT NULL, analysis_sha256 TEXT NOT NULL,
    status TEXT NOT NULL, analyst TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id),
    FOREIGN KEY(protocol_version_id) REFERENCES protocols(protocol_version_id),
    FOREIGN KEY(site_id) REFERENCES validation_sites(site_id)
);
CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, category TEXT NOT NULL,
    evidence_type TEXT NOT NULL, reference TEXT NOT NULL, source_organization TEXT NOT NULL,
    independent INTEGER NOT NULL, evidence_sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL,
    status TEXT NOT NULL, owner TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE TABLE IF NOT EXISTS quality_events (
    quality_event_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, event_type TEXT NOT NULL,
    severity TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, root_cause TEXT,
    action_plan TEXT, owner TEXT NOT NULL, due_at TEXT, status TEXT NOT NULL,
    effectiveness_verified INTEGER NOT NULL, created_at TEXT NOT NULL, closed_at TEXT,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE TABLE IF NOT EXISTS training_records (
    training_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, person_id TEXT NOT NULL,
    role_name TEXT NOT NULL, curriculum_id TEXT NOT NULL, completed_at TEXT NOT NULL,
    expires_at TEXT, result TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE TABLE IF NOT EXISTS signatures (
    signature_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, object_type TEXT NOT NULL,
    object_id TEXT NOT NULL, object_sha256 TEXT NOT NULL, signer TEXT NOT NULL,
    meaning TEXT NOT NULL, reason TEXT NOT NULL, signed_at TEXT NOT NULL,
    signature_digest TEXT NOT NULL,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);

CREATE TABLE IF NOT EXISTS external_validation_artifacts (
    artifact_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, domain TEXT NOT NULL,
    title TEXT NOT NULL, source_organization TEXT NOT NULL, source_type TEXT NOT NULL,
    external_identifier TEXT NOT NULL, source_url TEXT, jurisdiction TEXT,
    independent INTEGER NOT NULL, artifact_sha256 TEXT NOT NULL, artifact_size INTEGER NOT NULL,
    artifact_path TEXT NOT NULL, original_filename TEXT NOT NULL, mime_type TEXT NOT NULL,
    issued_at TEXT NOT NULL, expires_at TEXT, metadata_json TEXT NOT NULL,
    test_fixture INTEGER NOT NULL, status TEXT NOT NULL, submitted_by TEXT NOT NULL,
    created_at TEXT NOT NULL, verified_by TEXT, verified_at TEXT,
    verification_method TEXT, verification_notes TEXT,
    FOREIGN KEY(program_id) REFERENCES validation_programs(program_id)
);
CREATE INDEX IF NOT EXISTS idx_external_artifacts_program
    ON external_validation_artifacts(program_id);
CREATE INDEX IF NOT EXISTS idx_external_artifacts_domain
    ON external_validation_artifacts(program_id, domain, status);

CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
    object_type TEXT NOT NULL, object_id TEXT NOT NULL, reason TEXT NOT NULL,
    payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sites_program ON validation_sites(program_id);
CREATE INDEX IF NOT EXISTS idx_protocols_program ON protocols(program_id);
CREATE INDEX IF NOT EXISTS idx_freezes_program ON model_freezes(program_id);
CREATE INDEX IF NOT EXISTS idx_predictions_program ON prediction_batches(program_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_program ON outcome_batches(program_id);
CREATE INDEX IF NOT EXISTS idx_analysis_program ON analysis_results(program_id);
CREATE INDEX IF NOT EXISTS idx_evidence_program ON evidence_items(program_id);
CREATE INDEX IF NOT EXISTS idx_quality_program ON quality_events(program_id);
CREATE INDEX IF NOT EXISTS idx_training_program ON training_records(program_id);
CREATE INDEX IF NOT EXISTS idx_signatures_program ON signatures(program_id);
"""


def initialize_schema(connect: Callable[[], sqlite3.Connection]) -> None:
    with connect() as connection:
        connection.executescript(SCHEMA_SQL)
