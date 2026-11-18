from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.assets.research_assets import seed_asset_store
from biointel.data.evidence_registry import registry_summary, seed_standard_licenses
from biointel.data.scientific_registry import scientific_registry_summary
from biointel.database.migrations import optimize_existing_registries
from biointel.demo_workspace import seed_demo_workspace
from biointel.documents.history import history_summary, initialize_document_history
from biointel.intelligence.data_intelligence import all_database_health, optimize_all_databases
from biointel.intelligence.knowledge_warehouse import seed_knowledge_warehouse
from biointel.internet.download_registry import download_summary, initialize_download_registry
from biointel.observability.analytics_store import seed_analytics_store
from biointel.data.relationship_integrity import rebuild_relationship_registry
from biointel.training.demo_experiments import seed_bundled_demo_experiments
from biointel.runtime_paths import runtime_database_path, runtime_report_path


def main() -> None:
    initialize_download_registry(runtime_database_path(ROOT, "internet_downloads.sqlite3"))
    licenses = seed_standard_licenses(runtime_database_path(ROOT, "evidence.sqlite3"))
    initialize_document_history(runtime_database_path(ROOT, "document_history.sqlite3"))
    existing = optimize_existing_registries(ROOT)
    knowledge = seed_knowledge_warehouse(ROOT)
    analytics = seed_analytics_store(ROOT)
    assets = seed_asset_store(ROOT)
    demo_workspace = seed_demo_workspace(ROOT)
    demo_experiments = seed_bundled_demo_experiments(ROOT)
    relationships = rebuild_relationship_registry(ROOT)
    optimization = optimize_all_databases(ROOT)
    health = all_database_health(ROOT)
    payload = {
        "milestone": "Step 30 Scientific Data Foundation",
        "existing_registry_optimization": existing,
        "knowledge": knowledge.__dict__,
        "analytics": analytics.__dict__,
        "assets": assets.__dict__,
        "demo_workspace": demo_workspace,
        "demo_experiments": demo_experiments,
        "relationships": relationships.__dict__,
        "downloads": download_summary(runtime_database_path(ROOT, "internet_downloads.sqlite3")),
        "evidence": registry_summary(runtime_database_path(ROOT, "evidence.sqlite3")),
        "documents": history_summary(runtime_database_path(ROOT, "document_history.sqlite3")),
        "standard_licenses": [license.license_id for license in licenses],
        "scientific_registry": scientific_registry_summary(ROOT),
        "optimization": optimization,
        "health": health,
    }
    output = runtime_report_path(ROOT, "generated")
    output.mkdir(parents=True, exist_ok=True)
    for filename in (
        "step28_populated_workspace_summary.json",
        "step27_document_knowledge_databases_summary.json",
        "step26_document_intelligence_databases_summary.json",
        "step25_real_evidence_databases_summary.json",
        "step22_connected_databases_summary.json",
    ):
        (output / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
