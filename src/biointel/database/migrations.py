from __future__ import annotations

from biointel.runtime_paths import runtime_database_directory

from dataclasses import asdict
from pathlib import Path

from biointel.database.core import connect, database_health, transaction

# Phase-2 performance indexes.  All statements are idempotent so the optimizer can
# be run safely on existing workspaces after upgrades.
INDEX_SCRIPTS = {
    "datasets.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_datasets_name_version ON datasets(dataset_name, dataset_version);
        CREATE INDEX IF NOT EXISTS idx_datasets_task_created ON datasets(task_type, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_datasets_parent ON datasets(parent_sha256);
        CREATE INDEX IF NOT EXISTS idx_datasets_activity ON datasets(activity_type);
    """,
    "experiments.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_experiments_trained ON experiments(trained_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_experiments_model ON experiments(model_name, model_version);
        CREATE INDEX IF NOT EXISTS idx_experiments_task_trained ON experiments(task_type, trained_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_experiments_dataset ON experiments(dataset_sha256);
        CREATE INDEX IF NOT EXISTS idx_experiments_split ON experiments(split_strategy);
        CREATE INDEX IF NOT EXISTS idx_experiments_demo ON experiments(synthetic_demo);
    """,
    "projects.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_projects_status_priority ON projects(status, priority);
        CREATE INDEX IF NOT EXISTS idx_projects_target_date ON projects(target_date);
        CREATE INDEX IF NOT EXISTS idx_projects_dataset ON projects(dataset_sha256);
        CREATE INDEX IF NOT EXISTS idx_projects_model ON projects(model_filename);
        CREATE INDEX IF NOT EXISTS idx_project_events_project_time ON project_events(project_id, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_project_events_type_time ON project_events(event_type, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_milestones_project_status ON project_milestones(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_milestones_due ON project_milestones(due_date);
        CREATE INDEX IF NOT EXISTS idx_decisions_project_status ON project_decisions(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_decisions_date ON project_decisions(decision_date);
        CREATE INDEX IF NOT EXISTS idx_gates_project_status ON project_gates(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_gates_name ON project_gates(gate_name);
    """,
    "analytics.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_run_events_time ON analytics_run_events(occurred_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_run_events_module_status ON analytics_run_events(module_key, status);
        CREATE INDEX IF NOT EXISTS idx_run_events_project ON analytics_run_events(project_code);
        CREATE INDEX IF NOT EXISTS idx_alerts_resolved_severity ON analytics_alerts(resolved, severity);
        CREATE INDEX IF NOT EXISTS idx_alerts_time ON analytics_alerts(occurred_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_metric_name_date ON analytics_daily_metrics(metric_name, metric_date DESC);
        CREATE INDEX IF NOT EXISTS idx_quality_dataset_time ON analytics_quality_snapshots(dataset_name, captured_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_system_samples_time ON analytics_system_samples(captured_at_utc DESC);
    """,
    "assets.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_assets_type_status_updated ON research_assets(asset_type, status, updated_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_assets_source ON research_assets(source);
        CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON research_assets(sha256);
        CREATE INDEX IF NOT EXISTS idx_asset_tags_tag ON asset_tags(tag, asset_id);
        CREATE INDEX IF NOT EXISTS idx_collection_assets_collection_pos ON collection_assets(collection_id, position);
        CREATE INDEX IF NOT EXISTS idx_asset_notes_asset_time ON asset_notes(asset_id, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_collections_pinned_updated ON asset_collections(pinned, updated_at_utc DESC);
    """,
    "knowledge.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_entities_type_status_updated ON knowledge_entities(entity_type, status, updated_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_entities_external ON knowledge_entities(source, external_id);
        CREATE INDEX IF NOT EXISTS idx_entities_confidence ON knowledge_entities(confidence DESC);
        CREATE INDEX IF NOT EXISTS idx_relations_source_type ON knowledge_relations(source_entity_id, relation_type);
        CREATE INDEX IF NOT EXISTS idx_relations_target_type ON knowledge_relations(target_entity_id, relation_type);
        CREATE INDEX IF NOT EXISTS idx_protocols_category_risk ON knowledge_protocols(category, risk_level);
        CREATE INDEX IF NOT EXISTS idx_saved_queries_scope_pinned ON knowledge_saved_queries(scope, pinned);
    """,
    "internet_downloads.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_downloads_provider_resource ON internet_downloads(provider, resource_id);
        CREATE INDEX IF NOT EXISTS idx_downloads_status_time ON internet_downloads(status, downloaded_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_downloads_sha256 ON internet_downloads(sha256);
        CREATE INDEX IF NOT EXISTS idx_downloads_path ON internet_downloads(relative_path);
    """,
    "evidence.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_evidence_sources_name_release ON evidence_sources(source_name, source_release);
        CREATE INDEX IF NOT EXISTS idx_evidence_links_dataset_status ON dataset_evidence_links(dataset_sha256, review_status);
        CREATE INDEX IF NOT EXISTS idx_evidence_links_source ON dataset_evidence_links(source_id, source_record_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_links_publication ON dataset_evidence_links(publication_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_dataset_decision ON evidence_reviews(dataset_sha256, decision);
        CREATE INDEX IF NOT EXISTS idx_import_runs_provider_time ON evidence_import_runs(provider, started_at_utc DESC);
    """,
    "document_history.sqlite3": """
        CREATE INDEX IF NOT EXISTS idx_document_runs_time ON document_extraction_runs(started_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_document_runs_type_status ON document_extraction_runs(file_type, status);
        CREATE INDEX IF NOT EXISTS idx_document_runs_sha256 ON document_extraction_runs(source_sha256);
        CREATE INDEX IF NOT EXISTS idx_document_runs_name ON document_extraction_runs(source_name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_document_outputs_run ON document_extraction_outputs(run_id, format);
        CREATE INDEX IF NOT EXISTS idx_document_events_run_time ON document_extraction_events(run_id, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_document_runs_project ON document_extraction_runs(project_code, started_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_document_runs_deleted ON document_extraction_runs(deleted_at_utc, started_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_document_content_run ON document_content(run_id, content_type);
        CREATE INDEX IF NOT EXISTS idx_document_entities_run_type ON document_entities(run_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_document_entities_normalized ON document_entities(normalized COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_ocr_corrections_run ON document_ocr_corrections(run_id, created_at_utc DESC);
    """,
}


def optimize_existing_registries(root: str | Path) -> dict[str, object]:
    project_root = Path(root).resolve()
    reports = runtime_database_directory(project_root)
    results: dict[str, object] = {}
    for filename, script in INDEX_SCRIPTS.items():
        path = reports / filename
        if not path.is_file():
            continue
        with transaction(path) as connection:
            connection.executescript(script)
            connection.execute("PRAGMA analysis_limit = 1000")
            connection.execute("PRAGMA optimize")
        results[filename] = asdict(database_health(path, name=filename.removesuffix(".sqlite3")))
    return results


def query_plan(path: str | Path, sql: str, parameters: tuple[object, ...] = ()) -> list[str]:
    with connect(path, read_only=True) as connection:
        rows = connection.execute("EXPLAIN QUERY PLAN " + sql, parameters).fetchall()
    return [" | ".join(str(value) for value in row) for row in rows]
