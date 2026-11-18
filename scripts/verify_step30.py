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
from biointel.data.dataset_registry import list_datasets
from biointel.data.scientific_registry import scientific_registry_summary
from biointel.dti.feature_cache import FeatureCache
from biointel.genomics.annotations import annotation_summary, parse_gff
from biointel.genomics.fastq import fastq_qc, parse_fastq
from biointel.genomics.variants import parse_vcf, variant_summary
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG


def scalar(connection: sqlite3.Connection, sql: str) -> int:
    return int(connection.execute(sql).fetchone()[0])


def main() -> None:
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    demo = ROOT / "data" / "bioinformatics_demo"
    qc = fastq_qc(parse_fastq((demo / "demo_reads.fastq").read_text(encoding="utf-8")))
    assert qc.reads == 20_000
    variants = variant_summary(parse_vcf((demo / "demo_variants.vcf").read_text(encoding="utf-8")))
    assert variants.variants == 5_000
    annotations = annotation_summary(
        parse_gff((demo / "demo_annotations.gff3").read_text(encoding="utf-8"))
    )
    assert annotations.genes == 2_000
    expression_rows = (
        sum(1 for _ in (demo / "demo_expression_counts.csv").open(encoding="utf-8")) - 1
    )
    assert expression_rows == 5_000
    assert len(list((demo / "structures").glob("*.pdb"))) == 12

    datasets = list_datasets(ROOT / "reports" / "datasets.sqlite3", limit=5000)
    assert len(datasets) >= 51
    step30 = [record for record in datasets if record.metadata.get("step") == 30]
    assert len(step30) >= 19
    assert all(record.metadata.get("synthetic") is True for record in step30)
    assert all(record.metadata.get("scientific_release_eligible") is False for record in step30)

    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_files") >= 19
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_samples") >= 130
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_qc_metrics") >= 30
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_columns") >= 2_500
        assert scalar(connection, "SELECT COUNT(*) FROM dataset_links") >= 5
    with sqlite3.connect(ROOT / "reports" / "experiments.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM experiment_folds") == 115
        assert scalar(connection, "SELECT COUNT(*) FROM hyperparameter_trials") == 230
        assert scalar(connection, "SELECT COUNT(*) FROM experiment_runtime_metrics") == 69
        assert scalar(connection, "SELECT COUNT(*) FROM experiment_events") == 115
        assert scalar(connection, "SELECT COUNT(*) FROM experiments WHERE synthetic_demo=0") == 0
    with sqlite3.connect(ROOT / "reports" / "evidence.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM evidence_assay_context") == 660
        assert scalar(connection, "SELECT COUNT(*) FROM evidence_replicates") == 1_980
        assert scalar(connection, "SELECT COUNT(*) FROM evidence_source_releases") == 10
    with sqlite3.connect(ROOT / "reports" / "internet_downloads.sqlite3") as connection:
        assert scalar(connection, "SELECT COUNT(*) FROM scientific_source_catalog") == 16
    with sqlite3.connect(ROOT / "reports" / "knowledge.sqlite3") as connection:
        assert (
            scalar(connection, "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type='gene'")
            >= 100
        )
        assert (
            scalar(
                connection, "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type='disease'"
            )
            >= 30
        )
        assert (
            scalar(
                connection, "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type='pathway'"
            )
            >= 30
        )

    cache = FeatureCache(ROOT / "reports" / "feature_cache.sqlite3").stats()
    assert cache.entries >= 1_200
    assert cache.drug_entries >= 1_000
    assert cache.protein_entries >= 200

    models = sorted((ROOT / "models").glob("*.joblib"))
    assert len(models) >= 23
    for model in models:
        load_model_artifact(model, trusted_root=ROOT / "models")

    health = all_database_health(ROOT)
    assert health["healthy_count"] == health["database_count"]
    registry = scientific_registry_summary(ROOT)
    payload = {
        "version": __version__,
        "screens": len(PAGE_CATALOG),
        "models": len(models),
        "databases": health,
        "fastq_reads": qc.reads,
        "variants": variants.variants,
        "genes": annotations.genes,
        "expression_genes": expression_rows,
        "datasets": len(datasets),
        "step30_datasets": len(step30),
        "feature_cache": cache.__dict__,
        "scientific_registry": registry,
        "scientific_boundary": "Reference/simulation data only; real scientific release remains blocked.",
    }
    output = ROOT / "reports" / "generated" / "step30_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
