from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .models import canonical_json, new_id, utc_now

SCHEMA_VERSION = 220

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS platform_migrations(
    version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects(
    project_id TEXT PRIMARY KEY, title TEXT NOT NULL, research_question TEXT NOT NULL,
    scientific_objective TEXT NOT NULL, disease_context TEXT NOT NULL DEFAULT '',
    organism TEXT NOT NULL DEFAULT '', assay_types_json TEXT NOT NULL DEFAULT '[]',
    principal_investigator TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL,
    contributors_json TEXT NOT NULL DEFAULT '[]', reviewers_json TEXT NOT NULL DEFAULT '[]',
    start_date TEXT, target_date TEXT, current_stage TEXT NOT NULL,
    milestones_json TEXT NOT NULL DEFAULT '[]', dependencies_json TEXT NOT NULL DEFAULT '[]',
    risks_json TEXT NOT NULL DEFAULT '[]', blockers_json TEXT NOT NULL DEFAULT '[]',
    data_origin TEXT NOT NULL, is_synthetic INTEGER NOT NULL DEFAULT 0,
    legacy_project_id TEXT, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_stage_gates(
    gate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    stage TEXT NOT NULL, criteria_json TEXT NOT NULL, artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'Pending', reviewer TEXT NOT NULL DEFAULT '',
    decision_note TEXT NOT NULL DEFAULT '', decided_at_utc TEXT, updated_at_utc TEXT NOT NULL,
    UNIQUE(project_id, stage)
);
CREATE TABLE IF NOT EXISTS datasets(
    dataset_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', assay_type TEXT NOT NULL DEFAULT '',
    omics_type TEXT NOT NULL DEFAULT '', organism TEXT NOT NULL DEFAULT '', tissue TEXT NOT NULL DEFAULT '',
    disease TEXT NOT NULL DEFAULT '', cohort TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
    instrument TEXT NOT NULL DEFAULT '', reference_build TEXT NOT NULL DEFAULT '',
    annotation_release TEXT NOT NULL DEFAULT '', sample_count INTEGER NOT NULL DEFAULT 0,
    feature_count INTEGER NOT NULL DEFAULT 0, file_formats_json TEXT NOT NULL DEFAULT '[]',
    data_origin TEXT NOT NULL, consent_restrictions TEXT NOT NULL DEFAULT '',
    qc_status TEXT NOT NULL DEFAULT 'Not assessed', processing_status TEXT NOT NULL DEFAULT 'Registered',
    parent_dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    dataset_version TEXT NOT NULL DEFAULT '1.0', provenance_json TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0, created_at_utc TEXT NOT NULL, imported_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_files(
    file_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    original_name TEXT NOT NULL, stored_path TEXT NOT NULL, format TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, validation_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL,
    UNIQUE(dataset_id, sha256)
);
CREATE TABLE IF NOT EXISTS samples(
    sample_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL DEFAULT '', group_label TEXT NOT NULL DEFAULT '',
    condition_label TEXT NOT NULL DEFAULT '', treatment TEXT NOT NULL DEFAULT '',
    tissue TEXT NOT NULL DEFAULT '', timepoint TEXT NOT NULL DEFAULT '', batch TEXT NOT NULL DEFAULT '',
    plate TEXT NOT NULL DEFAULT '', lane TEXT NOT NULL DEFAULT '', biological_replicate TEXT NOT NULL DEFAULT '',
    technical_replicate TEXT NOT NULL DEFAULT '', sex TEXT NOT NULL DEFAULT '', age_group TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '', qc_status TEXT NOT NULL DEFAULT 'Not assessed',
    inclusion_status TEXT NOT NULL DEFAULT 'Included', exclusion_reason TEXT NOT NULL DEFAULT '',
    missing_metadata_json TEXT NOT NULL DEFAULT '[]', file_links_json TEXT NOT NULL DEFAULT '[]',
    derived_data_links_json TEXT NOT NULL DEFAULT '[]', lineage_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows(
    workflow_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL, template_key TEXT NOT NULL DEFAULT '', active_version_id TEXT,
    status TEXT NOT NULL DEFAULT 'Draft', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_versions(
    workflow_version_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,
    version TEXT NOT NULL, definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at_utc TEXT NOT NULL, UNIQUE(workflow_id, version)
);
CREATE TABLE IF NOT EXISTS workflow_nodes(
    node_id TEXT PRIMARY KEY, workflow_version_id TEXT NOT NULL REFERENCES workflow_versions(workflow_version_id) ON DELETE CASCADE,
    node_key TEXT NOT NULL, title TEXT NOT NULL, node_type TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}', retry_limit INTEGER NOT NULL DEFAULT 0,
    timeout_seconds INTEGER NOT NULL DEFAULT 3600, cache_enabled INTEGER NOT NULL DEFAULT 1,
    condition_json TEXT NOT NULL DEFAULT '{}', UNIQUE(workflow_version_id, node_key)
);
CREATE TABLE IF NOT EXISTS workflow_edges(
    edge_id TEXT PRIMARY KEY, workflow_version_id TEXT NOT NULL REFERENCES workflow_versions(workflow_version_id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL REFERENCES workflow_nodes(node_id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES workflow_nodes(node_id) ON DELETE CASCADE,
    condition_json TEXT NOT NULL DEFAULT '{}', UNIQUE(workflow_version_id, source_node_id, target_node_id)
);
CREATE TABLE IF NOT EXISTS runs(
    run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    workflow_version_id TEXT REFERENCES workflow_versions(workflow_version_id) ON DELETE SET NULL,
    module_id TEXT NOT NULL DEFAULT '', tool TEXT NOT NULL DEFAULT '', tool_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL, parameters_json TEXT NOT NULL DEFAULT '{}', input_hashes_json TEXT NOT NULL DEFAULT '{}',
    output_hashes_json TEXT NOT NULL DEFAULT '{}', started_at_utc TEXT NOT NULL, ended_at_utc TEXT,
    logs_path TEXT NOT NULL DEFAULT '', warnings_json TEXT NOT NULL DEFAULT '[]', errors_json TEXT NOT NULL DEFAULT '[]',
    resource_usage_json TEXT NOT NULL DEFAULT '{}', environment_json TEXT NOT NULL DEFAULT '{}',
    random_seed INTEGER, provenance_json TEXT NOT NULL, frozen INTEGER NOT NULL DEFAULT 0,
    parent_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS run_steps(
    step_run_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    node_id TEXT REFERENCES workflow_nodes(node_id) ON DELETE SET NULL, status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1, started_at_utc TEXT, ended_at_utc TEXT,
    stdout_path TEXT NOT NULL DEFAULT '', stderr_path TEXT NOT NULL DEFAULT '',
    checkpoint_json TEXT NOT NULL DEFAULT '{}', error_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(run_id, node_id, attempt)
);
CREATE TABLE IF NOT EXISTS artifacts(
    artifact_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL, artifact_type TEXT NOT NULL,
    name TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'application/octet-stream', provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates(
    candidate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    candidate_type TEXT NOT NULL, identity TEXT NOT NULL, synonyms_json TEXT NOT NULL DEFAULT '[]',
    data_source TEXT NOT NULL, discovery_run_ids_json TEXT NOT NULL DEFAULT '[]',
    scores_json TEXT NOT NULL DEFAULT '{}', confidence REAL, qc_json TEXT NOT NULL DEFAULT '{}',
    supporting_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    contradictory_evidence_ids_json TEXT NOT NULL DEFAULT '[]', cross_module_support_json TEXT NOT NULL DEFAULT '{}',
    risks_json TEXT NOT NULL DEFAULT '[]', limitations_json TEXT NOT NULL DEFAULT '[]',
    validation_status TEXT NOT NULL DEFAULT 'Not planned', action_plan_json TEXT NOT NULL DEFAULT '{}',
    timeline_json TEXT NOT NULL DEFAULT '{}', lifecycle_state TEXT NOT NULL DEFAULT 'Detected',
    owner TEXT NOT NULL DEFAULT '', review_status TEXT NOT NULL DEFAULT 'Pending',
    provenance_json TEXT NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
    UNIQUE(project_id, candidate_type, identity)
);
CREATE TABLE IF NOT EXISTS evidence(
    evidence_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source TEXT NOT NULL, identifier TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
    study_type TEXT NOT NULL DEFAULT '', evidence_type TEXT NOT NULL, direction TEXT NOT NULL DEFAULT 'Neutral',
    strength TEXT NOT NULL DEFAULT 'Unrated', independence TEXT NOT NULL DEFAULT 'Unknown',
    pmid TEXT NOT NULL DEFAULT '', doi TEXT NOT NULL DEFAULT '', database_name TEXT NOT NULL DEFAULT '',
    database_version TEXT NOT NULL DEFAULT '', cohort TEXT NOT NULL DEFAULT '', sample_size INTEGER,
    species TEXT NOT NULL DEFAULT '', tissue TEXT NOT NULL DEFAULT '', quality TEXT NOT NULL DEFAULT 'Unrated',
    risk_of_bias TEXT NOT NULL DEFAULT 'Not assessed', retraction_state TEXT NOT NULL DEFAULT 'Not checked',
    correction_state TEXT NOT NULL DEFAULT 'Not checked', verification_state TEXT NOT NULL DEFAULT 'Unverified',
    limitations_json TEXT NOT NULL DEFAULT '[]', linked_candidates_json TEXT NOT NULL DEFAULT '[]',
    linked_recommendations_json TEXT NOT NULL DEFAULT '[]', linked_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    linked_experiments_json TEXT NOT NULL DEFAULT '[]', provenance_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_identifier ON evidence(project_id, source, identifier) WHERE identifier != '';
CREATE TABLE IF NOT EXISTS hypotheses(
    hypothesis_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    statement TEXT NOT NULL, biological_mechanism TEXT NOT NULL DEFAULT '',
    supporting_observations_json TEXT NOT NULL DEFAULT '[]',
    contradictory_observations_json TEXT NOT NULL DEFAULT '[]',
    competing_hypotheses_json TEXT NOT NULL DEFAULT '[]', null_hypothesis TEXT NOT NULL,
    causal_dag_json TEXT NOT NULL DEFAULT '{}', predictions_json TEXT NOT NULL DEFAULT '[]',
    falsification_criteria_json TEXT NOT NULL DEFAULT '[]', evidence_gaps_json TEXT NOT NULL DEFAULT '[]',
    candidate_links_json TEXT NOT NULL DEFAULT '[]', experiment_links_json TEXT NOT NULL DEFAULT '[]',
    expected_outcomes_json TEXT NOT NULL DEFAULT '[]', failure_interpretation TEXT NOT NULL DEFAULT '',
    confidence REAL, novelty TEXT NOT NULL DEFAULT 'Unassessed', status TEXT NOT NULL DEFAULT 'Draft',
    review_history_json TEXT NOT NULL DEFAULT '[]', provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments(
    experiment_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    recommendation_id TEXT, candidate_id TEXT REFERENCES candidates(candidate_id) ON DELETE SET NULL,
    hypothesis_id TEXT REFERENCES hypotheses(hypothesis_id) ON DELETE SET NULL,
    validation_plan_json TEXT NOT NULL, protocol TEXT NOT NULL DEFAULT '', sop TEXT NOT NULL DEFAULT '',
    assay TEXT NOT NULL, samples_json TEXT NOT NULL DEFAULT '[]', controls_json TEXT NOT NULL DEFAULT '[]',
    replicates_json TEXT NOT NULL DEFAULT '{}', randomization TEXT NOT NULL DEFAULT '',
    blinding TEXT NOT NULL DEFAULT '', reagents_json TEXT NOT NULL DEFAULT '[]',
    instruments_json TEXT NOT NULL DEFAULT '[]', plate_layout_json TEXT NOT NULL DEFAULT '{}',
    operator TEXT NOT NULL DEFAULT '', start_date TEXT, completion_date TEXT,
    expected_result TEXT NOT NULL DEFAULT '', acceptance_criteria_json TEXT NOT NULL,
    failure_criteria_json TEXT NOT NULL, observed_result TEXT NOT NULL DEFAULT '',
    deviations_json TEXT NOT NULL DEFAULT '[]', qc_json TEXT NOT NULL DEFAULT '{}',
    attachments_json TEXT NOT NULL DEFAULT '[]', interpretation TEXT NOT NULL DEFAULT '',
    final_status TEXT NOT NULL DEFAULT 'Planned', provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_results(
    validation_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    recommendation_id TEXT, candidate_id TEXT REFERENCES candidates(candidate_id) ON DELETE SET NULL,
    outcome TEXT NOT NULL, observed_result TEXT NOT NULL, acceptance_met INTEGER NOT NULL,
    qc_status TEXT NOT NULL, evidence_id TEXT REFERENCES evidence(evidence_id) ON DELETE SET NULL,
    confidence_before REAL, confidence_after REAL, interpretation TEXT NOT NULL,
    provenance_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendations(
    recommendation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    candidate_id TEXT REFERENCES candidates(candidate_id) ON DELETE SET NULL,
    hypothesis_id TEXT REFERENCES hypotheses(hypothesis_id) ON DELETE SET NULL,
    state TEXT NOT NULL, recommendation_json TEXT NOT NULL, engine_implementation REAL,
    runtime_execution REAL, input_completeness REAL, qc_completion REAL, evidence_coverage REAL,
    external_validation REAL, scientific_validation REAL, provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_nodes(
    node_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, label TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}', provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, UNIQUE(project_id, entity_type, entity_id)
);
CREATE TABLE IF NOT EXISTS graph_edges(
    edge_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL, direction TEXT NOT NULL DEFAULT 'directed',
    strength REAL, evidence_ids_json TEXT NOT NULL DEFAULT '[]', confidence REAL,
    source TEXT NOT NULL, version TEXT NOT NULL DEFAULT '', provenance_json TEXT NOT NULL,
    contradiction_state TEXT NOT NULL DEFAULT 'None', created_at_utc TEXT NOT NULL,
    UNIQUE(project_id, source_node_id, target_node_id, relationship_type, source)
);
CREATE TABLE IF NOT EXISTS models(
    model_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL, version TEXT NOT NULL, task TEXT NOT NULL, owner TEXT NOT NULL,
    training_dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    validation_dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    feature_set_json TEXT NOT NULL DEFAULT '[]', preprocessing_json TEXT NOT NULL DEFAULT '{}',
    hyperparameters_json TEXT NOT NULL DEFAULT '{}', random_seed INTEGER,
    performance_json TEXT NOT NULL DEFAULT '{}', calibration_json TEXT NOT NULL DEFAULT '{}',
    subgroup_performance_json TEXT NOT NULL DEFAULT '{}', bias_analysis_json TEXT NOT NULL DEFAULT '{}',
    ood_checks_json TEXT NOT NULL DEFAULT '{}', drift_status TEXT NOT NULL DEFAULT 'Not assessed',
    explainability_json TEXT NOT NULL DEFAULT '{}', limitations_json TEXT NOT NULL DEFAULT '[]',
    approval_status TEXT NOT NULL DEFAULT 'Experimental', deployment_status TEXT NOT NULL DEFAULT 'Not deployed',
    deprecation_status TEXT NOT NULL DEFAULT 'Active', artifact_paths_json TEXT NOT NULL DEFAULT '[]',
    model_hash TEXT NOT NULL, environment_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, UNIQUE(name, version, model_hash)
);
CREATE TABLE IF NOT EXISTS notebooks(
    notebook_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL, tags_json TEXT NOT NULL DEFAULT '[]', created_by TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notebook_versions(
    version_id TEXT PRIMARY KEY, notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
    content_markdown TEXT NOT NULL, links_json TEXT NOT NULL DEFAULT '{}',
    attachments_json TEXT NOT NULL DEFAULT '[]', content_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports(
    report_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL, sections_json TEXT NOT NULL, review_required INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'Draft', artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments(
    comment_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, body TEXT NOT NULL,
    mentions_json TEXT NOT NULL DEFAULT '[]', author TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_actions(
    review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL,
    actor TEXT NOT NULL, role TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
    due_date TEXT, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments(
    attachment_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, name TEXT NOT NULL,
    path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL, created_by TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs(
    job_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    job_type TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 50, status TEXT NOT NULL DEFAULT 'Queued',
    payload_json TEXT NOT NULL DEFAULT '{}', progress REAL NOT NULL DEFAULT 0,
    cancellation_requested INTEGER NOT NULL DEFAULT 0, checkpoint_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dependency_checks(
    dependency_id TEXT PRIMARY KEY, tool_name TEXT NOT NULL, installed INTEGER NOT NULL,
    version TEXT NOT NULL DEFAULT '', executable_path TEXT NOT NULL DEFAULT '',
    health_status TEXT NOT NULL, compatible_modules_json TEXT NOT NULL DEFAULT '[]',
    required INTEGER NOT NULL DEFAULT 0, setup_instructions TEXT NOT NULL DEFAULT '',
    offline_instructions TEXT NOT NULL DEFAULT '', validation_json TEXT NOT NULL DEFAULT '{}',
    checked_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events(
    event_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
    actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL, previous_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL UNIQUE, occurred_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_permissions(
    permission_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    principal TEXT NOT NULL, role TEXT NOT NULL, granted_by TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, UNIQUE(project_id, principal)
);
CREATE TABLE IF NOT EXISTS dataset_permissions(
    permission_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    principal TEXT NOT NULL, role TEXT NOT NULL, granted_by TEXT NOT NULL,
    created_at_utc TEXT NOT NULL, UNIQUE(dataset_id, principal)
);
CREATE TABLE IF NOT EXISTS local_users(
    user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, role TEXT NOT NULL,
    password_hash TEXT NOT NULL, salt TEXT NOT NULL, iterations INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1, failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until_utc TEXT, last_login_utc TEXT,
    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_sessions(
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE, created_at_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL, expires_at_utc TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0, client_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS export_controls(
    control_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    sensitive INTEGER NOT NULL DEFAULT 0, allowed_roles_json TEXT NOT NULL DEFAULT '[]',
    require_review INTEGER NOT NULL DEFAULT 0, maximum_rows INTEGER,
    destination_policy TEXT NOT NULL DEFAULT 'local_only',
    updated_by TEXT NOT NULL, updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retention_policies(
    policy_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL, retention_days INTEGER,
    disposition TEXT NOT NULL DEFAULT 'review', legal_hold INTEGER NOT NULL DEFAULT 0,
    updated_by TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
    UNIQUE(project_id, entity_type)
);
CREATE TABLE IF NOT EXISTS instruments(
    instrument_id TEXT PRIMARY KEY, name TEXT NOT NULL, instrument_type TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Available', owner TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synthetic_manifests(
    manifest_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id TEXT REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    generator TEXT NOT NULL, generator_version TEXT NOT NULL,
    random_seed INTEGER NOT NULL, parameters_json TEXT NOT NULL,
    output_hashes_json TEXT NOT NULL, notice TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_permissions ON dataset_permissions(dataset_id, principal);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON local_sessions(user_id, expires_at_utc);
CREATE INDEX IF NOT EXISTS idx_synthetic_manifest ON synthetic_manifests(project_id, dataset_id);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(current_stage, updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_datasets_project ON datasets(project_id, imported_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_files_hash ON dataset_files(sha256);
CREATE INDEX IF NOT EXISTS idx_samples_dataset ON samples(dataset_id, qc_status, inclusion_status);
CREATE INDEX IF NOT EXISTS idx_samples_subject ON samples(subject_id, dataset_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, started_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, started_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_project ON candidates(project_id, lifecycle_state, candidate_type);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id, evidence_type, verification_state);
CREATE INDEX IF NOT EXISTS idx_hypotheses_project ON hypotheses(project_id, status);
CREATE INDEX IF NOT EXISTS idx_experiments_project ON experiments(project_id, final_status);
CREATE INDEX IF NOT EXISTS idx_validation_project ON validation_results(project_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_project ON recommendations(project_id, state);
CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(project_id, source_node_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(project_id, target_node_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id, occurred_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at_utc);
"""

TABLES = frozenset(
    {
        "projects", "project_stage_gates", "datasets", "dataset_files", "samples",
        "workflows", "workflow_versions", "workflow_nodes", "workflow_edges", "runs",
        "run_steps", "artifacts", "candidates", "evidence", "hypotheses", "experiments",
        "validation_results", "recommendations", "graph_nodes", "graph_edges", "models",
        "notebooks", "notebook_versions", "reports", "comments", "review_actions",
        "attachments", "jobs", "dependency_checks", "audit_events", "project_permissions",
        "dataset_permissions", "local_users", "local_sessions", "export_controls",
        "retention_policies", "instruments", "synthetic_manifests",
    }
)


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value


def _decode_row(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    for key in list(output):
        if key.endswith("_json"):
            raw = output.pop(key)
            try:
                output[key[:-5]] = json.loads(raw or "null")
            except (TypeError, json.JSONDecodeError):
                output[key[:-5]] = raw
    for key in (
        "is_synthetic", "frozen", "installed", "required", "acceptance_met", "resolved",
        "active", "revoked", "sensitive", "require_review", "legal_hold",
    ):
        if key in output and output[key] is not None:
            output[key] = bool(output[key])
    return output


class DiscoveryPlatformStore:
    """Versioned local-first persistence with foreign keys and a chained audit ledger."""

    def __init__(self, database_path: str | Path, artifact_root: str | Path | None = None):
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root = Path(
            artifact_root or self.database_path.parent / "discovery_platform_artifacts"
        ).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.backup_root = (self.database_path.parent / "migration_backups").resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _raw_connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _migration_backup(self, current_version: int) -> Path | None:
        if not self.database_path.is_file() or self.database_path.stat().st_size == 0:
            return None
        target = self.backup_root / (
            f"{self.database_path.stem}-before-v{SCHEMA_VERSION}-from-v{current_version}.sqlite3"
        )
        suffix = 1
        while target.exists():
            target = target.with_name(f"{target.stem}-{suffix}{target.suffix}")
            suffix += 1
        source = sqlite3.connect(self.database_path)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return target

    def _migrate(self) -> None:
        current = 0
        if self.database_path.exists() and self.database_path.stat().st_size:
            probe = sqlite3.connect(self.database_path)
            try:
                current = int(probe.execute("PRAGMA user_version").fetchone()[0])
            finally:
                probe.close()
        if current >= SCHEMA_VERSION:
            with closing(self._raw_connect()) as connection:
                connection.executescript(SCHEMA)
            return
        backup = self._migration_backup(current)
        try:
            with closing(self._raw_connect()) as connection:
                connection.executescript(SCHEMA)
                connection.execute(
                    "INSERT OR REPLACE INTO platform_migrations(version,name,applied_at_utc) VALUES(?,?,?)",
                    (SCHEMA_VERSION, "Step220 discovery platform schema", utc_now()),
                )
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                connection.commit()
        except Exception:
            if backup is not None and backup.exists():
                shutil.copy2(backup, self.database_path)
            raise

    @contextmanager
    def connect(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        if read_only:
            uri = self.database_path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA query_only=ON")
        else:
            connection = self._raw_connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str = "",
        *,
        project_id: str | None = None,
        actor: str = "local_user",
        role: str = "Administrator",
        detail: Mapping[str, Any] | None = None,
    ) -> str:
        event_id = new_id("AUDIT")
        occurred = utc_now()
        with self.transaction() as connection:
            previous = connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            previous_hash = str(previous[0]) if previous else ""
            payload = {
                "event_id": event_id,
                "project_id": project_id,
                "actor": actor,
                "role": role,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "detail": dict(detail or {}),
                "previous_hash": previous_hash,
                "occurred_at_utc": occurred,
            }
            event_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO audit_events(
                    event_id,project_id,actor,role,action,entity_type,entity_id,
                    detail_json,previous_hash,event_hash,occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_id, project_id, actor, role, action, entity_type, entity_id,
                    canonical_json(detail or {}), previous_hash, event_hash, occurred,
                ),
            )
        return event_id

    def insert(self, table: str, values: Mapping[str, Any]) -> None:
        if table not in TABLES:
            raise ValueError(f"Unsupported table: {table}")
        columns = [_identifier(key) for key in values]
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})"
        prepared = [
            canonical_json(value) if key.endswith("_json") and not isinstance(value, str) else value
            for key, value in values.items()
        ]
        with self.transaction() as connection:
            connection.execute(sql, prepared)

    def update(
        self,
        table: str,
        entity_column: str,
        entity_id: str,
        changes: Mapping[str, Any],
    ) -> bool:
        if table not in TABLES:
            raise ValueError(f"Unsupported table: {table}")
        entity_column = _identifier(entity_column)
        columns = [_identifier(key) for key in changes]
        if not columns:
            return False
        prepared = [
            canonical_json(value) if key.endswith("_json") and not isinstance(value, str) else value
            for key, value in changes.items()
        ]
        sql = f"UPDATE {table} SET {','.join(key + '=?' for key in columns)} WHERE {entity_column}=?"
        with self.transaction() as connection:
            cursor = connection.execute(sql, (*prepared, entity_id))
        return cursor.rowcount > 0

    def row(self, table: str, entity_column: str, entity_id: str) -> dict[str, Any] | None:
        if table not in TABLES:
            raise ValueError(f"Unsupported table: {table}")
        entity_column = _identifier(entity_column)
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {entity_column}=?", (entity_id,)
            ).fetchone()
        return _decode_row(row) if row else None

    def rows(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if table not in TABLES:
            raise ValueError(f"Unsupported table: {table}")
        where = []
        parameters: list[Any] = []
        for key, value in (filters or {}).items():
            where.append(f"{_identifier(key)}=?")
            parameters.append(value)
        sql = f"SELECT * FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if order_by:
            sql += f" ORDER BY {_identifier(order_by)} {'DESC' if descending else 'ASC'}"
        sql += " LIMIT ? OFFSET ?"
        parameters.extend((max(1, min(int(limit), 5000)), max(0, int(offset))))
        with self.connect(read_only=True) as connection:
            values = connection.execute(sql, parameters).fetchall()
        return [_decode_row(value) for value in values]

    def delete_project(self, project_id: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
        if cursor.rowcount:
            self.audit("project_deleted", "project", project_id, detail={"cascade": True})
        return cursor.rowcount > 0

    def table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.connect(read_only=True) as connection:
            for table in sorted(TABLES):
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return counts

    def integrity(self) -> dict[str, Any]:
        with self.connect(read_only=True) as connection:
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        return {
            "database": str(self.database_path),
            "schema_version": version,
            "quick_check": quick,
            "foreign_key_violations": foreign_keys,
            "healthy": quick == "ok" and not foreign_keys and version == SCHEMA_VERSION,
        }

    def backup(self, destination: str | Path) -> dict[str, Any]:
        target = Path(destination).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect(read_only=True) as source:
            output = sqlite3.connect(target)
            try:
                source.backup(output)
            finally:
                output.close()
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest = {
            "database": target.name,
            "sha256": digest,
            "size_bytes": target.stat().st_size,
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": utc_now(),
        }
        target.with_suffix(target.suffix + ".manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return manifest

    def verify_audit_chain(self) -> dict[str, Any]:
        rows = self.rows("audit_events", order_by="occurred_at_utc", descending=False, limit=5000)
        previous = ""
        failures: list[str] = []
        for row in rows:
            payload = {
                "event_id": row["event_id"],
                "project_id": row["project_id"],
                "actor": row["actor"],
                "role": row["role"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "detail": row.get("detail", {}),
                "previous_hash": row["previous_hash"],
                "occurred_at_utc": row["occurred_at_utc"],
            }
            expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                failures.append(row["event_id"])
            previous = row["event_hash"]
        return {"valid": not failures, "events": len(rows), "failures": failures}


__all__ = ["DiscoveryPlatformStore", "SCHEMA_VERSION", "TABLES"]
