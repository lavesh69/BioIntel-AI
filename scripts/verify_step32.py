from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.readiness import platform_readiness_summary, provider_readiness_rows
from biointel.data.relationship_integrity import relationship_summary
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import CATEGORIES, PAGE_CATALOG, search_pages


def scalar(connection: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    return int(connection.execute(query, params).fetchone()[0])


def main() -> None:
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    assert len({page.key for page in PAGE_CATALOG}) >= 71
    assert len({page.path for page in PAGE_CATALOG}) >= 71
    assert len([page for page in PAGE_CATALOG if page.featured]) == 12
    assert "Modelling" not in CATEGORIES
    assert "Modeling" in CATEGORIES
    assert len(CATEGORIES) == 14
    assert search_pages("rnaseq")[0].key == "transcriptomics_expression"
    assert any(
        page.key == "scientific_data_readiness" for page in search_pages("scientific validation")
    )

    health = all_database_health(ROOT)
    assert health["database_count"] >= 13
    assert health["healthy_count"] == health["database_count"]

    relationships = relationship_summary(ROOT)
    assert relationships["node_count"] >= 860
    assert relationships["edge_count"] >= 1_400
    assert relationships["broken_edges"] == 0
    assert relationships["orphan_findings"] == 0

    readiness = platform_readiness_summary(ROOT)
    assert readiness["datasets"]["datasets"] == 52
    assert readiness["datasets"]["with_files"] == 52
    assert readiness["datasets"]["with_columns"] == 52
    assert readiness["datasets"]["with_qc"] == 52
    assert readiness["datasets"]["with_provenance"] == 52
    assert readiness["datasets"]["release_eligible"] == 0
    assert readiness["open_dataset_issues"] == 52

    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM physical_data_assets") >= 80
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_asset_bindings") >= 100
        assert (
            scalar(connection, "SELECT COUNT(*) FROM dataset_asset_bindings WHERE is_shared=1")
            >= 20
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM dataset_validation_issues WHERE category='scientific_scope' AND resolution_status='open'",
            )
            == 52
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM datasets WHERE json_extract(metadata_json,'$.public_reference')=1",
            )
            == 1
        )
        public_rows = scalar(
            connection,
            "SELECT SUM(row_count) FROM datasets WHERE json_extract(metadata_json,'$.public_reference')=1",
        )
        assert public_rows == 569
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM dataset_samples WHERE dataset_sha256 IN (SELECT dataset_sha256 FROM datasets WHERE json_extract(metadata_json,'$.public_reference')=1)",
            )
            == 569
        )

    public_catalog = ROOT / "data" / "public_reference" / "verified_public_reference_catalog.csv"
    public_dataset = (
        ROOT / "data" / "public_reference" / "uci_breast_cancer_wisconsin_diagnostic.csv"
    )
    attribution = ROOT / "data" / "public_reference" / "UCI_WDBC_ATTRIBUTION.md"
    assert public_catalog.is_file()
    assert public_dataset.is_file()
    assert attribution.is_file()
    assert sum(1 for _ in public_catalog.open(encoding="utf-8")) == 61
    assert sum(1 for _ in public_dataset.open(encoding="utf-8")) == 570

    providers = provider_readiness_rows(ROOT)
    assert len(providers) == 16
    uci = next(row for row in providers if row["provider"] == "UCI Machine Learning Repository")
    assert int(uci["records_available"]) == 569
    assert uci["local_status"] == "imported_reference"
    assert uci["data_scope"] == "public_reference_dataset"

    with sqlite3.connect(ROOT / "reports" / "assets.sqlite3") as connection:
        assert (
            scalar(connection, "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'")
            == 12
        )
        assert (
            scalar(
                connection,
                "SELECT COUNT(*) FROM research_assets WHERE source='BioIntel Step 32 foundation'",
            )
            >= 4
        )

    models = sorted((ROOT / "models").glob("*.joblib"))
    assert len(models) == 23
    for path in models:
        load_model_artifact(path, trusted_root=ROOT / "models")

    for page in PAGE_CATALOG:
        path = ROOT / page.path
        assert path.is_file(), page.path
        source = path.read_text(encoding="utf-8")
        assert "st.set_page_config" in source
        assert "apply_theme()" in source
        assert source.index("st.set_page_config") < source.index("apply_theme()")
        compile(source, str(path), "exec")

    required = [
        ROOT / "BUILD_STEP32_FOUNDATION_WINDOWS.bat",
        ROOT / "VERIFY_STEP32_WINDOWS.bat",
        ROOT / "docs" / "STEP32_SCIENTIFIC_UX_PERFORMANCE.md",
        ROOT / "src" / "biointel" / "ui" / "performance.py",
        ROOT / "src" / "biointel" / "ui" / "components.py",
        ROOT / "src" / "biointel" / "data" / "relationship_integrity.py",
        ROOT / "src" / "biointel" / "data" / "public_reference.py",
    ]
    assert all(path.is_file() for path in required)

    payload = {
        "version": __version__,
        "milestone": "Step 32 Scientific UX & Performance",
        "screens": len(PAGE_CATALOG),
        "featured_screens": len([p for p in PAGE_CATALOG if p.featured]),
        "categories": len(CATEGORIES),
        "databases": health["database_count"],
        "database_rows": health["total_rows"],
        "relationship_nodes": relationships["node_count"],
        "relationship_edges": relationships["edge_count"],
        "registered_datasets": readiness["datasets"]["datasets"],
        "public_reference_dataset_rows": 569,
        "public_identifier_references": 60,
        "provider_profiles": len(providers),
        "models_loaded": len(models),
        "scientific_release_eligible_datasets": readiness["datasets"]["release_eligible"],
        "scientific_boundary": "Public reference data is real and licensed, but bundled DTI models remain synthetic and release-blocked.",
    }
    output = ROOT / "reports" / "generated" / "step32_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
