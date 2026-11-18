from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.assets.research_assets import seed_asset_store
from biointel.data.readiness import initialize_readiness_schema, platform_readiness_summary
from biointel.data.scientific_registry import (
    initialize_scientific_registries,
    register_dataset_file,
    sha256_file,
)
from biointel.database.core import transaction
from biointel.dti.feature_cache import _restore
from biointel.intelligence.knowledge_warehouse import (
    _upsert_entity,
    initialize_knowledge_warehouse,
)

VERSION = "3.1.0"


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


NOW = now_utc


def stable_id(*parts: str, length: int = 32) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:length]


def load_json(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def find_file(filename: str) -> Path | None:
    if not filename:
        return None
    candidates = [p for p in (ROOT / "data").rglob(filename) if p.is_file()]
    return sorted(candidates, key=lambda p: (len(p.parts), str(p)))[0] if candidates else None


def source_file_for_dataset(name: str, metadata: dict[str, Any]) -> Path | None:
    source_file = (
        metadata.get("source_file") or metadata.get("relative_path") or metadata.get("path")
    )
    if source_file:
        candidate = ROOT / str(source_file)
        if candidate.is_file():
            return candidate
    filename = str(metadata.get("filename") or "")
    candidate = find_file(filename)
    if candidate:
        return candidate
    mapping = {
        "BioIntel Synthetic 5X DTI": "data/packs/synthetic_5x_ultra_dti_v5.csv",
        "BioIntel Synthetic Double DTI": "data/packs/synthetic_double_ultra_dti_v4.csv",
        "BioIntel Synthetic Ultra DTI": "data/packs/synthetic_ultra_dti_v3.csv",
        "BioIntel Synthetic Extended DTI": "data/packs/synthetic_extended_dti_v2.csv",
        "BioIntel Synthetic Foundation DTI": "data/packs/synthetic_foundation_dti_v2.csv",
        "BioIntel Preloaded Demonstration Evidence": "data/examples/demo_workspace/BioIntel_Demo_Activity_Data.csv",
    }
    for prefix, relative in mapping.items():
        if name.startswith(prefix):
            path = ROOT / relative
            return path if path.is_file() else None
    if name.startswith("BioIntel Demo Dataset Pack"):
        path = ROOT / "data/examples/demo_workspace/BioIntel_Demo_Activity_Data.csv"
        return path if path.is_file() else None
    return None


def semantic_role(column: str) -> tuple[str, str | None]:
    key = column.strip().lower()
    if key in {
        "id",
        "dataset_id",
        "compound_id",
        "protein_id",
        "gene",
        "gene_id",
        "read_id",
        "sample",
        "sample_id",
        "taxon",
        "contig_id",
    } or key.endswith("_id"):
        return "identifier", None
    if "smiles" in key:
        return "chemical_structure", None
    if "sequence" in key:
        return "biological_sequence", None
    if key in {"label", "active", "activity_class", "class"}:
        return "label", None
    if key in {"value_nm", "activity_nm", "ic50", "ec50", "ki", "kd"}:
        return "measurement", "nM"
    if "quality" in key or key in {"qual", "filter", "depth", "dp"}:
        return "quality_metric", None
    if key in {"condition", "group", "treatment"}:
        return "group", None
    if "batch" in key:
        return "batch", None
    if "time" in key:
        return "timepoint", None
    if key in {"chrom", "pos", "ref", "alt", "start", "end", "strand", "feature_type"}:
        return "genomic_annotation", None
    return "feature", None


def infer_columns_from_file(path: Path, fallback: list[str]) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    columns: list[str] = []
    dtypes: dict[str, str] = {}
    nullable: dict[str, bool] = {}
    try:
        if suffix in {".csv", ".tsv"}:
            frame = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",", nrows=500)
            columns = [str(x) for x in frame.columns]
            dtypes = {str(c): str(frame[c].dtype) for c in frame.columns}
            nullable = {str(c): bool(frame[c].isna().any()) for c in frame.columns}
        elif suffix in {".fasta", ".fa", ".faa", ".fna"}:
            columns = ["record_id", "description", "sequence", "sequence_length"]
        elif suffix in {".fastq", ".fq"}:
            columns = ["read_id", "sequence", "quality", "read_length", "mean_quality"]
        elif suffix in {".vcf"}:
            columns = [
                "chrom",
                "pos",
                "id",
                "ref",
                "alt",
                "qual",
                "filter",
                "info",
                "format",
                "samples",
            ]
        elif suffix in {".gff", ".gff3", ".gtf"}:
            columns = [
                "seqid",
                "source",
                "feature_type",
                "start",
                "end",
                "score",
                "strand",
                "phase",
                "attributes",
            ]
        elif suffix in {".pdb", ".cif", ".mmcif"}:
            columns = [
                "record_type",
                "atom_id",
                "atom_name",
                "residue",
                "chain",
                "residue_number",
                "x",
                "y",
                "z",
                "element",
            ]
    except Exception:
        columns = []
    if not columns:
        columns = fallback or ["record"]
    result = []
    for index, column in enumerate(columns, 1):
        role, unit = semantic_role(column)
        result.append(
            {
                "column_name": column,
                "ordinal_position": index,
                "data_type": dtypes.get(column, "string"),
                "semantic_role": role,
                "unit": unit,
                "description": f"Registered field for {column}.",
                "nullable": int(nullable.get(column, True)),
                "metadata_json": json.dumps(
                    {"inferred_by": "Step31 registry completion"}, sort_keys=True
                ),
            }
        )
    return result


def manifest_for_dataset(row: sqlite3.Row, primary: Path | None) -> Path:
    manifest_dir = ROOT / "data" / "dataset_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    metadata = load_json(row["metadata_json"], {})
    payload = {
        "schema": "biointel.dataset-manifest.v3.1",
        "dataset_sha256": row["dataset_sha256"],
        "dataset_name": row["dataset_name"],
        "dataset_version": row["dataset_version"],
        "task_type": row["task_type"],
        "row_count": row["row_count"],
        "source_description": row["source_description"],
        "activity_type": row["activity_type"],
        "parent_sha256": row["parent_sha256"],
        "column_names": load_json(row["column_names_json"], []),
        "primary_file": primary.relative_to(ROOT).as_posix() if primary else None,
        "primary_file_exists": bool(primary and primary.is_file()),
        "scientific_release_eligible": bool(metadata.get("scientific_release_eligible", False)),
        "synthetic": bool(metadata.get("synthetic", "Synthetic" in row["dataset_name"])),
        "demo_only": bool(metadata.get("demo_only", metadata.get("preloaded_demo", False))),
        "metadata": metadata,
        "generated_by": "BioIntel Step 31 registry completion",
    }
    path = manifest_dir / f"{row['dataset_sha256']}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def seed_dataset_registry() -> dict[str, int]:
    database = ROOT / "reports" / "datasets.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        datasets = connection.execute(
            "SELECT * FROM datasets ORDER BY created_at_utc,dataset_name"
        ).fetchall()

    for row in datasets:
        metadata = load_json(row["metadata_json"], {})
        primary = source_file_for_dataset(row["dataset_name"], metadata)
        manifest = manifest_for_dataset(row, primary)
        register_dataset_file(
            ROOT,
            dataset_sha256=row["dataset_sha256"],
            relative_path=manifest.relative_to(ROOT).as_posix(),
            role="registry_manifest",
            metadata={"schema": "v3.1"},
        )
        if primary:
            register_dataset_file(
                ROOT,
                dataset_sha256=row["dataset_sha256"],
                relative_path=primary.relative_to(ROOT).as_posix(),
                role="primary_data",
                metadata={"verified_by": "Step31"},
            )

        fallback = [str(x) for x in load_json(row["column_names_json"], [])]
        with sqlite3.connect(database) as connection:
            current_columns = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_columns WHERE dataset_sha256=?",
                    (row["dataset_sha256"],),
                ).fetchone()[0]
            )
        if current_columns == 0:
            inferred = infer_columns_from_file(primary or manifest, fallback)
            with transaction(database) as connection:
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO dataset_columns(
                        dataset_sha256,column_name,ordinal_position,data_type,semantic_role,unit,
                        description,nullable,metadata_json
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            row["dataset_sha256"],
                            item["column_name"],
                            item["ordinal_position"],
                            item["data_type"],
                            item["semantic_role"],
                            item["unit"],
                            item["description"],
                            item["nullable"],
                            item["metadata_json"],
                        )
                        for item in inferred
                    ],
                )

        with sqlite3.connect(database) as connection:
            file_rows = connection.execute(
                "SELECT role,relative_path,sha256,size_bytes FROM dataset_files WHERE dataset_sha256=?",
                (row["dataset_sha256"],),
            ).fetchall()
            column_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_columns WHERE dataset_sha256=?",
                    (row["dataset_sha256"],),
                ).fetchone()[0]
            )
        primary_rows = [item for item in file_rows if item[0] == "primary_data"]
        integrity = "verified" if primary_rows else "manifest_only"
        standard_qc = [
            ("registered_row_count", float(row["row_count"]), None, "rows", "pass"),
            (
                "registered_column_count",
                float(column_count),
                None,
                "columns",
                "pass" if column_count else "fail",
            ),
            (
                "registered_file_count",
                float(len(file_rows)),
                None,
                "files",
                "pass" if file_rows else "fail",
            ),
            (
                "primary_file_integrity",
                None,
                integrity,
                None,
                "pass" if primary_rows else "warning",
            ),
            (
                "scientific_release_eligible",
                1.0 if metadata.get("scientific_release_eligible") else 0.0,
                None,
                "boolean",
                "warning" if not metadata.get("scientific_release_eligible") else "pass",
            ),
        ]
        with transaction(database) as connection:
            for metric_name, metric_value, metric_text, unit, status in standard_qc:
                qc_id = stable_id(row["dataset_sha256"], metric_name, "dataset", "")
                connection.execute(
                    """
                    INSERT OR REPLACE INTO dataset_qc_metrics(
                        qc_id,dataset_sha256,metric_name,metric_value,metric_text,unit,scope,scope_id,status,threshold_json,created_at_utc
                    ) VALUES (?,?,?,?,?,?, 'dataset',NULL,?,'{}',?)
                    """,
                    (
                        qc_id,
                        row["dataset_sha256"],
                        metric_name,
                        metric_value,
                        metric_text,
                        unit,
                        status,
                        NOW(),
                    ),
                )
            source_type = (
                "synthetic_reference"
                if metadata.get("synthetic", "Synthetic" in row["dataset_name"])
                else "local_reference"
            )
            provider = "BioIntel"
            provenance_id = stable_id(row["dataset_sha256"], source_type, provider)
            connection.execute(
                """
                INSERT OR REPLACE INTO dataset_provenance(
                    provenance_id,dataset_sha256,source_type,provider,release_label,licence_id,external_id,
                    access_method,status,retrieved_at_utc,metadata_json,created_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    provenance_id,
                    row["dataset_sha256"],
                    source_type,
                    provider,
                    row["dataset_version"],
                    "LOCAL_USER_SUPPLIED",
                    None,
                    "local_file",
                    "registered",
                    row["created_at_utc"],
                    json.dumps(
                        {
                            "source_description": row["source_description"],
                            "primary_file": primary.relative_to(ROOT).as_posix()
                            if primary
                            else None,
                        },
                        sort_keys=True,
                    ),
                    NOW(),
                ),
            )

    # Parent links and useful domain links.
    with transaction(database) as connection:
        rows = connection.execute(
            "SELECT dataset_sha256,dataset_name,parent_sha256,metadata_json FROM datasets"
        ).fetchall()
        for dataset_sha, name, parent_sha, metadata_json in rows:
            if parent_sha:
                connection.execute(
                    "INSERT OR IGNORE INTO dataset_links VALUES (?,?,?,?,?,?,?)",
                    (
                        stable_id(parent_sha, dataset_sha, "derived_from"),
                        parent_sha,
                        dataset_sha,
                        "parent_of",
                        f"Registered parent lineage for {name}",
                        "{}",
                        NOW(),
                    ),
                )
        named = {name: sha for sha, name, _, _ in rows}
        pairs = [
            ("Step30 omics sample metadata", "Step30 RNA-seq count matrix", "describes_samples"),
            (
                "Step30 omics sample metadata",
                "Step30 normalized transcriptomics matrix",
                "describes_samples",
            ),
            (
                "Step30 omics sample metadata",
                "Step30 proteomics abundance matrix",
                "describes_samples",
            ),
            ("Step30 gene annotation table", "Step30 RNA-seq count matrix", "annotates_features"),
            (
                "Step30 protein annotation table",
                "Step30 proteomics abundance matrix",
                "annotates_features",
            ),
            (
                "Step30 microbiome sample metadata",
                "Step30 microbiome abundance matrix",
                "describes_samples",
            ),
            (
                "Step30 protein family panel",
                "Step30 protein-ligand structure panel",
                "provides_sequences_for",
            ),
        ]
        for source_name, target_name, relation in pairs:
            if source_name in named and target_name in named:
                source, target = named[source_name], named[target_name]
                connection.execute(
                    "INSERT OR IGNORE INTO dataset_links VALUES (?,?,?,?,?,?,?)",
                    (
                        stable_id(source, target, relation),
                        source,
                        target,
                        relation,
                        "Step 31 scientific lineage completion",
                        json.dumps({"step": 31}),
                        NOW(),
                    ),
                )

    # VCF and wet-lab sample metadata where the concept is applicable.
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        lookup = {
            r["dataset_name"]: r["dataset_sha256"]
            for r in connection.execute("SELECT dataset_name,dataset_sha256 FROM datasets")
        }
    sample_sets: dict[str, list[dict[str, Any]]] = {}
    if "Step30 variant cohort" in lookup:
        sample_sets[lookup["Step30 variant cohort"]] = [
            {
                "sample_id": f"SAMPLE_{i:02d}",
                "sample_name": f"SAMPLE_{i:02d}",
                "organism": "Homo sapiens",
                "tissue_or_matrix": "reference germline DNA",
                "condition_name": "reference cohort",
                "batch_name": f"VCF_BATCH_{1 + (i - 1) % 2}",
                "replicate_type": "biological",
                "replicate_number": i,
                "subject_id": f"SUBJECT_{i:02d}",
            }
            for i in range(1, 9)
        ]
    for dataset_name, file_name, sample_col, condition_col in [
        ("Step30 qPCR 96-well study", "demo_qpcr.csv", "sample", "condition"),
        ("Step30 ELISA plate study", "demo_elisa.csv", "name", "type"),
        (
            "Step30 enzyme kinetics replicates",
            "demo_enzyme_kinetics.csv",
            None,
            "inhibitor_condition",
        ),
        ("Step30 bioprocess sensor time series", "demo_bioprocess.csv", None, None),
    ]:
        sha = lookup.get(dataset_name)
        path = ROOT / "data/bioinformatics_demo" / file_name
        if not sha or not path.is_file():
            continue
        frame = pd.read_csv(path)
        records = []
        if sample_col and sample_col in frame.columns:
            unique = frame.drop_duplicates(sample_col)
            for idx, (_, r) in enumerate(unique.iterrows(), 1):
                records.append(
                    {
                        "sample_id": str(r[sample_col]),
                        "sample_name": str(r[sample_col]),
                        "organism": "reference biological system",
                        "tissue_or_matrix": dataset_name.replace("Step30 ", ""),
                        "condition_name": str(r.get(condition_col, "reference")),
                        "batch_name": "STEP31_REFERENCE",
                        "replicate_type": "technical"
                        if dataset_name.startswith("Step30 ELISA")
                        else "biological",
                        "replicate_number": idx,
                    }
                )
        else:
            conditions = (
                sorted(frame[condition_col].astype(str).unique())
                if condition_col and condition_col in frame.columns
                else ["reference_run"]
            )
            for idx, condition in enumerate(conditions, 1):
                records.append(
                    {
                        "sample_id": f"{stable_id(dataset_name, condition, length=12)}",
                        "sample_name": condition,
                        "organism": "reference biological system",
                        "tissue_or_matrix": dataset_name.replace("Step30 ", ""),
                        "condition_name": condition,
                        "batch_name": "STEP31_REFERENCE",
                        "replicate_type": "experimental_run",
                        "replicate_number": idx,
                    }
                )
        sample_sets[sha] = records
    for dataset_name, file_name in [
        ("Step30 omics sample metadata", "demo_sample_metadata.csv"),
        ("Step30 microbiome sample metadata", "demo_microbiome_metadata.csv"),
    ]:
        sha = lookup.get(dataset_name)
        path = ROOT / "data/bioinformatics_demo" / file_name
        if sha and path.is_file():
            frame = pd.read_csv(path)
            sample_col = "sample" if "sample" in frame.columns else frame.columns[0]
            records = []
            for idx, (_, r) in enumerate(frame.iterrows(), 1):
                records.append(
                    {
                        "sample_id": str(r[sample_col]),
                        "sample_name": str(r[sample_col]),
                        "organism": str(r.get("organism", "reference biological system")),
                        "tissue_or_matrix": str(
                            r.get("tissue", r.get("body_site", dataset_name.replace("Step30 ", "")))
                        ),
                        "condition_name": str(r.get("condition", "reference")),
                        "batch_name": str(r.get("batch", "STEP31_REFERENCE")),
                        "replicate_type": "biological",
                        "replicate_number": int(r.get("biological_replicate", idx)),
                        "subject_id": str(r.get("subject_id", f"SUBJECT_{idx:03d}")),
                        "timepoint": str(r.get("timepoint_hours", "")),
                    }
                )
            sample_sets[sha] = records

    with transaction(database) as connection:
        for sha, records in sample_sets.items():
            connection.execute("DELETE FROM dataset_samples WHERE dataset_sha256=?", (sha,))
            connection.executemany(
                """INSERT INTO dataset_samples(sample_id,dataset_sha256,sample_name,organism,tissue_or_matrix,condition_name,batch_name,replicate_type,replicate_number,subject_id,timepoint,metadata_json,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r["sample_id"],
                        sha,
                        r["sample_name"],
                        r.get("organism"),
                        r.get("tissue_or_matrix"),
                        r.get("condition_name"),
                        r.get("batch_name"),
                        r.get("replicate_type"),
                        r.get("replicate_number"),
                        r.get("subject_id"),
                        r.get("timepoint"),
                        json.dumps({"seeded_by": "Step31"}),
                        NOW(),
                    )
                    for r in records
                ],
            )

    calculate_dataset_readiness()
    with sqlite3.connect(database) as connection:
        return {
            "datasets": int(connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]),
            "files": int(connection.execute("SELECT COUNT(*) FROM dataset_files").fetchone()[0]),
            "columns": int(
                connection.execute("SELECT COUNT(*) FROM dataset_columns").fetchone()[0]
            ),
            "samples": int(
                connection.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
            ),
            "qc": int(connection.execute("SELECT COUNT(*) FROM dataset_qc_metrics").fetchone()[0]),
            "links": int(connection.execute("SELECT COUNT(*) FROM dataset_links").fetchone()[0]),
            "provenance": int(
                connection.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0]
            ),
        }


def calculate_dataset_readiness() -> None:
    database = ROOT / "reports/datasets.sqlite3"
    applicable_terms = (
        "fastq",
        "variant",
        "rna-seq",
        "transcriptomics",
        "proteomics",
        "microbiome",
        "qpcr",
        "elisa",
        "enzyme kinetics",
        "bioprocess",
        "sample metadata",
    )
    with transaction(database) as connection:
        connection.execute("DELETE FROM dataset_readiness")
        connection.execute("DELETE FROM dataset_validation_issues")
        connection.row_factory = sqlite3.Row
        datasets = connection.execute("SELECT * FROM datasets").fetchall()
        for row in datasets:
            sha = row["dataset_sha256"]
            name = row["dataset_name"]
            metadata = load_json(row["metadata_json"], {})
            counts = {
                table: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE dataset_sha256=?", (sha,)
                    ).fetchone()[0]
                )
                for table in (
                    "dataset_files",
                    "dataset_columns",
                    "dataset_samples",
                    "dataset_qc_metrics",
                    "dataset_provenance",
                )
            }
            lineage = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_links WHERE source_dataset_sha256=? OR target_dataset_sha256=?",
                    (sha, sha),
                ).fetchone()[0]
            )
            primary = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_files WHERE dataset_sha256=? AND role='primary_data'",
                    (sha,),
                ).fetchone()[0]
            )
            applicable = int(any(term in name.lower() for term in applicable_terms))
            required_metadata = [
                row["dataset_name"],
                row["dataset_version"],
                row["task_type"],
                row["source_description"],
                row["column_names_json"],
                row["metadata_json"],
            ]
            completeness = 100.0 * sum(bool(x) for x in required_metadata) / len(required_metadata)
            blockers = []
            warnings = []
            if counts["dataset_columns"] == 0:
                blockers.append("Column dictionary is missing")
            if counts["dataset_files"] == 0:
                blockers.append("No registered file or manifest")
            if primary == 0:
                warnings.append("No primary data file; registry manifest only")
            if applicable and counts["dataset_samples"] == 0:
                warnings.append("Sample-level metadata is expected but missing")
            if counts["dataset_qc_metrics"] < 3:
                warnings.append("QC coverage is limited")
            synthetic = bool(
                metadata.get(
                    "synthetic",
                    "Synthetic" in name
                    or metadata.get("demo_only")
                    or metadata.get("preloaded_demo"),
                )
            )
            release = bool(metadata.get("scientific_release_eligible", False)) and not synthetic
            scientific_status = (
                "release_eligible"
                if release
                else ("reference_only" if synthetic else "needs_evidence_review")
            )
            score = 0.0
            score += 20 if counts["dataset_files"] else 0
            score += 15 if primary else 7
            score += 20 if counts["dataset_columns"] else 0
            score += (
                15
                if counts["dataset_qc_metrics"] >= 3
                else min(counts["dataset_qc_metrics"] * 4, 12)
            )
            score += 10 if counts["dataset_provenance"] else 0
            score += 8 if lineage or not row["parent_sha256"] else 0
            score += 7 if (not applicable or counts["dataset_samples"] > 0) else 0
            score += 5 * completeness / 100
            score = min(100.0, round(score, 2))
            integrity = "verified" if primary else "manifest_only"
            connection.execute(
                """INSERT INTO dataset_readiness VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sha,
                    counts["dataset_files"],
                    counts["dataset_columns"],
                    counts["dataset_samples"],
                    counts["dataset_qc_metrics"],
                    lineage,
                    counts["dataset_provenance"],
                    applicable,
                    round(completeness, 2),
                    integrity,
                    scientific_status,
                    score,
                    json.dumps(blockers),
                    json.dumps(warnings),
                    NOW(),
                ),
            )
            for severity, category, messages in (
                ("blocker", "completeness", blockers),
                ("warning", "coverage", warnings),
            ):
                for message in messages:
                    connection.execute(
                        "INSERT INTO dataset_validation_issues VALUES (?,?,?,?,?,'open','{}',?,NULL)",
                        (
                            stable_id(sha, severity, category, message),
                            sha,
                            severity,
                            category,
                            message,
                            NOW(),
                        ),
                    )


def seed_experiment_registry() -> dict[str, int]:
    db = ROOT / "reports/experiments.sqlite3"
    dataset_db = ROOT / "reports/datasets.sqlite3"

    with sqlite3.connect(dataset_db) as con:
        con.row_factory = sqlite3.Row
        dataset_rows = [
            dict(row)
            for row in con.execute(
                "SELECT dataset_name,dataset_version,task_type,dataset_sha256,metadata_json FROM datasets"
            )
        ]
        datasets = {row["dataset_sha256"] for row in dataset_rows}
        external = {
            row["task_type"]: row["dataset_sha256"]
            for row in dataset_rows
            if row["dataset_name"].startswith("BioIntel External Validation ")
        }

    def canonical_dataset(metadata: dict[str, Any], task_type: str) -> str | None:
        source_name = str(metadata.get("dataset_name") or "").lower()
        candidates: list[dict[str, Any]] = []
        for row in dataset_rows:
            if row["task_type"] != task_type:
                continue
            name = row["dataset_name"].lower()
            if "synthetic_5x" in source_name and "synthetic 5x dti" in name:
                candidates.append(row)
            elif "double" in source_name and "synthetic double dti" in name:
                candidates.append(row)
            elif "foundation" in source_name and "synthetic foundation dti" in name:
                candidates.append(row)
            elif "extended" in source_name and "synthetic extended dti" in name:
                candidates.append(row)
            elif (
                "ultra" in source_name
                and "double" not in source_name
                and "5x" not in source_name
                and "synthetic ultra dti" in name
            ):
                candidates.append(row)
            elif source_name == "synthetic_dti_demo" and name.startswith(
                "biointel demo dataset pack"
            ):
                # Preserve the historical demo hash while resolving each task to a
                # task-compatible retained demonstration dataset.
                pack_number = "01" if task_type == "classification" else "02"
                if f"pack {pack_number}" in name:
                    candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda row: (row["dataset_version"], row["dataset_name"]), reverse=True)
        return str(candidates[0]["dataset_sha256"])

    # Preserve historical hashes and add explicit, task-aware registry aliases.
    with sqlite3.connect(db) as exp_con:
        exp_con.row_factory = sqlite3.Row
        experiment_sources = [
            dict(row)
            for row in exp_con.execute(
                "SELECT DISTINCT dataset_sha256,task_type,metadata_json FROM experiments"
            )
        ]
    aliases: dict[tuple[str, str], str] = {}
    with transaction(dataset_db) as con:
        con.execute("DELETE FROM dataset_aliases WHERE alias_type='historical_experiment_dataset'")
        for item in experiment_sources:
            alias_sha = str(item["dataset_sha256"])
            task_type = str(item["task_type"])
            if alias_sha in datasets:
                continue
            metadata = load_json(item.get("metadata_json"), {})
            canonical = canonical_dataset(metadata, task_type)
            if not canonical:
                continue
            aliases[(alias_sha, task_type)] = canonical
            con.execute(
                """INSERT OR REPLACE INTO dataset_aliases(
                       alias_sha256,task_type,canonical_dataset_sha256,alias_type,
                       reason,metadata_json,created_at_utc
                   ) VALUES (?,?,?,?,?,?,?)""",
                (
                    alias_sha,
                    task_type,
                    canonical,
                    "historical_experiment_dataset",
                    "Historical training hash resolves to the retained task-compatible synthetic dataset family; the original experiment hash is preserved.",
                    json.dumps(
                        {
                            "source_dataset_name": metadata.get("dataset_name"),
                            "source_dataset_version": metadata.get("dataset_version"),
                            "scientific_release_eligible": False,
                            "resolved_by": "Step31",
                        },
                        sort_keys=True,
                    ),
                    NOW(),
                ),
            )

    with transaction(db) as con:
        # Repair a historical filename alias whose metadata exactly matches the retained artifact.
        con.execute(
            "UPDATE experiments SET model_file='packv3_regression_extra_trees_foundation.joblib' "
            "WHERE model_file='packv3_regression_extra_trees_extended.joblib'"
        )
        con.execute("DELETE FROM experiment_dataset_bindings")
        con.execute("DELETE FROM experiment_artifacts")
        con.execute("DELETE FROM experiment_validation_requirements")
        con.row_factory = sqlite3.Row
        experiments = con.execute("SELECT * FROM experiments ORDER BY trained_at_utc").fetchall()
        for exp in experiments:
            dataset_sha = str(exp["dataset_sha256"])
            task_type = str(exp["task_type"])
            resolved_sha = (
                dataset_sha if dataset_sha in datasets else aliases.get((dataset_sha, task_type))
            )
            verified = int(bool(resolved_sha))
            resolution_type = (
                "direct"
                if dataset_sha in datasets
                else ("historical_alias" if resolved_sha else "unresolved")
            )
            message = (
                "Dataset hash is directly registered"
                if resolution_type == "direct"
                else (
                    "Historical dataset hash resolves through a task-aware registry alias; original experiment hash is preserved"
                    if resolution_type == "historical_alias"
                    else "Training dataset hash is missing from the registry and has no verified alias"
                )
            )
            con.execute(
                """INSERT OR REPLACE INTO experiment_dataset_bindings(
                       experiment_id,dataset_sha256,binding_role,verified,
                       verification_message,created_at_utc,resolved_dataset_sha256,resolution_type
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    exp["experiment_id"],
                    dataset_sha,
                    "training",
                    verified,
                    message,
                    NOW(),
                    resolved_sha,
                    resolution_type,
                ),
            )
            ext = external.get(task_type)
            if ext:
                con.execute(
                    """INSERT OR REPLACE INTO experiment_dataset_bindings(
                           experiment_id,dataset_sha256,binding_role,verified,
                           verification_message,created_at_utc,resolved_dataset_sha256,resolution_type
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        exp["experiment_id"],
                        ext,
                        "external_validation_reference",
                        1,
                        "Reference external-validation dataset is registered but remains synthetic",
                        NOW(),
                        ext,
                        "direct",
                    ),
                )
            model_path = ROOT / "models" / str(exp["model_file"])
            candidates = [
                model_path,
                model_path.with_suffix(".json"),
                model_path.with_suffix(".model_card.md"),
            ]
            for path in candidates:
                relative = (
                    path.relative_to(ROOT).as_posix()
                    if path.is_absolute() and ROOT in path.parents
                    else str(path)
                )
                exists = path.is_file()
                con.execute(
                    "INSERT OR REPLACE INTO experiment_artifacts VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        stable_id(exp["experiment_id"], relative),
                        exp["experiment_id"],
                        "model"
                        if path.suffix == ".joblib"
                        else ("model_card" if path.name.endswith("model_card.md") else "metadata"),
                        relative,
                        sha256_file(path) if exists else None,
                        path.stat().st_size if exists else 0,
                        "available" if exists else "missing",
                        json.dumps({"verified_by": "Step31"}),
                        NOW(),
                    ),
                )
            requirements = [
                (
                    "artifact_integrity",
                    "Model artifact integrity",
                    "passed" if model_path.is_file() else "blocked",
                    "Model artifact is available and checksummed"
                    if model_path.is_file()
                    else "Model artifact is missing",
                ),
                (
                    "registered_dataset",
                    "Registered training dataset",
                    "passed" if verified else "blocked",
                    message,
                ),
                (
                    "real_experimental_training",
                    "Real experimental training data",
                    "blocked" if exp["synthetic_demo"] else "passed",
                    "Synthetic/demo training is not scientific release evidence"
                    if exp["synthetic_demo"]
                    else "Training data is marked non-synthetic",
                ),
                (
                    "independent_external_validation",
                    "Independent external validation",
                    "blocked" if exp["synthetic_demo"] else "review",
                    "Bundled validation is synthetic/reference only"
                    if exp["synthetic_demo"]
                    else "Independent validation requires review",
                ),
                (
                    "prospective_validation",
                    "Prospective wet-lab validation",
                    "blocked",
                    "No prospective wet-lab validation is registered",
                ),
            ]
            for key, label, status, requirement_message in requirements:
                evidence_ref = (
                    resolved_sha if key == "registered_dataset" and resolved_sha else None
                )
                con.execute(
                    "INSERT OR REPLACE INTO experiment_validation_requirements VALUES (?,?,?,?,?,?,?)",
                    (
                        exp["experiment_id"],
                        key,
                        label,
                        status,
                        requirement_message,
                        evidence_ref,
                        NOW(),
                    ),
                )
        return {
            "experiments": len(experiments),
            "bindings": int(
                con.execute("SELECT COUNT(*) FROM experiment_dataset_bindings").fetchone()[0]
            ),
            "verified_bindings": int(
                con.execute(
                    "SELECT COUNT(*) FROM experiment_dataset_bindings WHERE verified=1"
                ).fetchone()[0]
            ),
            "historical_aliases": len(aliases),
            "artifacts": int(
                con.execute("SELECT COUNT(*) FROM experiment_artifacts").fetchone()[0]
            ),
            "requirements": int(
                con.execute("SELECT COUNT(*) FROM experiment_validation_requirements").fetchone()[0]
            ),
        }


def seed_source_catalog() -> dict[str, int]:
    internet = ROOT / "reports/internet_downloads.sqlite3"
    evidence = ROOT / "reports/evidence.sqlite3"
    catalog_file = ROOT / "data/real_evidence/SCIENTIFIC_SOURCE_IMPORT_CATALOG.csv"
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(internet) as con:
        con.row_factory = sqlite3.Row
        profiles = con.execute(
            "SELECT * FROM scientific_source_catalog ORDER BY provider"
        ).fetchall()
    with transaction(evidence) as con:
        # Replace stale profile-only rows from earlier milestones while preserving
        # any future release that actually contains imported local records.
        con.execute(
            "DELETE FROM evidence_source_releases WHERE local_record_count=0 AND release_label LIKE 'connector-%'"
        )
        for p in profiles:
            con.execute(
                """INSERT OR REPLACE INTO evidence_source_releases(release_id,provider,release_label,release_date,connector_status,local_record_count,checksum,licence_id,refresh_cadence,notes,metadata_json,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"PROFILE-{p['source_key'].upper()}",
                    p["provider"],
                    "connector-profile",
                    None,
                    p["local_status"],
                    0,
                    None,
                    p["licence_profile"],
                    p["refresh_cadence"],
                    "Connector profile only; no remote scientific records are bundled.",
                    json.dumps(
                        {
                            "source_key": p["source_key"],
                            "official_host": p["official_host"],
                            "step": 31,
                            "real_records_imported": False,
                        },
                        sort_keys=True,
                    ),
                    NOW(),
                ),
            )
    with transaction(internet) as con:
        for p in profiles:
            con.execute(
                "UPDATE scientific_source_catalog SET last_checked_at_utc=?,records_available=COALESCE(records_available,0),metadata_json=? WHERE source_key=?",
                (
                    NOW(),
                    json.dumps(
                        {
                            **load_json(p["metadata_json"], {}),
                            "step": 31,
                            "catalog_synchronized": True,
                            "real_records_imported": False,
                        },
                        sort_keys=True,
                    ),
                    p["source_key"],
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO source_sync_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    stable_id(p["source_key"], "profile_check", VERSION),
                    p["source_key"],
                    "profile_check",
                    "ready",
                    "Official source profile validated locally; remote records remain pending explicit user import.",
                    0,
                    0,
                    None,
                    json.dumps({"host": p["official_host"], "access_method": p["access_method"]}),
                    NOW(),
                ),
            )
    with catalog_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "source_key",
                "provider",
                "resource_type",
                "official_host",
                "access_method",
                "licence_profile",
                "refresh_cadence",
                "local_status",
                "real_records_imported",
                "next_action",
            ]
        )
        for p in profiles:
            writer.writerow(
                [
                    p["source_key"],
                    p["provider"],
                    p["resource_type"],
                    p["official_host"],
                    p["access_method"],
                    p["licence_profile"],
                    p["refresh_cadence"],
                    p["local_status"],
                    "No",
                    "Use Internet Research Hub or provider-specific importer after reviewing licence terms",
                ]
            )
    checklist = ROOT / "data/real_evidence/REAL_DATA_IMPORT_CHECKLIST.md"
    checklist.write_text(
        """# Real Scientific Data Import Checklist\n\nThis directory intentionally contains no fabricated experimental data. Before importing a real source:\n\n1. Record the official release/version and retrieval date.\n2. Review licence, redistribution and attribution terms.\n3. Preserve the original file checksum.\n4. Curate units, assay relations, compound structures and target identifiers.\n5. Register rejected rows and reasons.\n6. Run leakage, duplicate and conflict audits.\n7. Require reviewer sign-off before scientific release.\n\nUse `IMPORT_REAL_EVIDENCE_WINDOWS.bat` for supported activity tables.\n""",
        encoding="utf-8",
    )
    return {
        "providers": len(profiles),
        "source_releases": len(profiles),
        "sync_events": len(profiles),
    }


def seed_feature_cache_metadata() -> dict[str, int]:
    db = ROOT / "reports/feature_cache.sqlite3"
    with transaction(db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT cache_key,feature_kind,payload FROM feature_cache").fetchall()
        counts = {"drug": 0, "protein": 0, "invalid": 0}
        for row in rows:
            try:
                _, _, metadata = _restore(row["payload"])
                kind = row["feature_kind"]
                schema = (
                    "drug-descriptors-morgan-v2"
                    if kind == "drug"
                    else "protein-composition-protparam-v2"
                )
                library = "RDKit" if kind == "drug" else "Biopython"
                params = {
                    k: v
                    for k, v in metadata.items()
                    if k not in {"canonical_smiles", "sequence_length"}
                }
                entity = str(metadata.get("canonical_smiles") or f"protein:{row['cache_key'][:20]}")
                con.execute(
                    "UPDATE feature_cache SET schema_version=?,library_version=?,parameters_json=?,entity_id=?,validation_status='valid',error_message=NULL WHERE cache_key=?",
                    (schema, library, json.dumps(params, sort_keys=True), entity, row["cache_key"]),
                )
                counts[kind] = counts.get(kind, 0) + 1
            except Exception as exc:
                con.execute(
                    "UPDATE feature_cache SET validation_status='invalid',error_message=? WHERE cache_key=?",
                    (str(exc)[:500], row["cache_key"]),
                )
                counts["invalid"] += 1
        for kind, schema, library, params in [
            (
                "drug",
                "drug-descriptors-morgan-v2",
                "RDKit",
                {"radius": 2, "n_bits": 256, "use_chirality": True},
            ),
            (
                "protein",
                "protein-composition-protparam-v2",
                "Biopython",
                {"include_dipeptides": False},
            ),
        ]:
            entry_count = int(
                con.execute(
                    "SELECT COUNT(*) FROM feature_cache WHERE feature_kind=?", (kind,)
                ).fetchone()[0]
            )
            valid = int(
                con.execute(
                    "SELECT COUNT(*) FROM feature_cache WHERE feature_kind=? AND validation_status='valid'",
                    (kind,),
                ).fetchone()[0]
            )
            con.execute(
                "INSERT OR REPLACE INTO feature_cache_profiles VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    kind,
                    kind,
                    schema,
                    library,
                    "bundled-runtime",
                    json.dumps(params, sort_keys=True),
                    entry_count,
                    valid,
                    entry_count - valid,
                    NOW(),
                ),
            )
        counts["entries"] = len(rows)
        return counts


def seed_projects_and_documents() -> dict[str, int]:
    project_db = ROOT / "reports/projects.sqlite3"
    dataset_db = ROOT / "reports/datasets.sqlite3"
    document_db = ROOT / "reports/document_history.sqlite3"
    evidence_db = ROOT / "reports/evidence.sqlite3"
    with sqlite3.connect(dataset_db) as con:
        datasets = [
            r[0] for r in con.execute("SELECT dataset_sha256 FROM datasets ORDER BY dataset_name")
        ]
    models = sorted(p.name for p in (ROOT / "models").glob("*.joblib"))
    with sqlite3.connect(document_db) as con:
        runs = [
            r[0]
            for r in con.execute(
                "SELECT run_id FROM document_extraction_runs ORDER BY started_at_utc"
            )
        ]
    with sqlite3.connect(evidence_db) as con:
        sources = [
            r[0] for r in con.execute("SELECT source_id FROM evidence_sources ORDER BY source_id")
        ]
    with transaction(project_db) as con:
        con.execute("DELETE FROM project_resources")
        con.row_factory = sqlite3.Row
        projects = con.execute("SELECT * FROM projects ORDER BY project_code").fetchall()
        for idx, p in enumerate(projects):
            dataset = p["dataset_sha256"] or datasets[idx % len(datasets)]
            model = p["model_filename"] or models[idx % len(models)]
            con.execute(
                "UPDATE projects SET dataset_sha256=?,model_filename=?,updated_at_utc=? WHERE project_id=?",
                (dataset, model, NOW(), p["project_id"]),
            )
            resources = [
                ("dataset", dataset, "uses", "linked"),
                ("model", model, "evaluates", "linked"),
            ]
            if runs:
                resources.append(("document_run", runs[idx % len(runs)], "documented_by", "linked"))
            if sources:
                resources.append(
                    ("evidence_source", sources[idx % len(sources)], "references", "demo_only")
                )
            for resource_type, resource_id, relation, status in resources:
                con.execute(
                    "INSERT OR IGNORE INTO project_resources VALUES (?,?,?,?,?,?,?,?)",
                    (
                        stable_id(p["project_id"], resource_type, resource_id, relation),
                        p["project_id"],
                        resource_type,
                        resource_id,
                        relation,
                        status,
                        "Step 31 lineage completion; demonstration project links remain non-release evidence.",
                        NOW(),
                    ),
                )
        result = {
            "projects": len(projects),
            "resource_links": int(
                con.execute("SELECT COUNT(*) FROM project_resources").fetchone()[0]
            ),
        }
    with transaction(document_db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT run_id,engine_version,metadata_json FROM document_extraction_runs"
        ).fetchall()
        for row in rows:
            integrity = con.execute(
                "SELECT COUNT(*),SUM(CASE WHEN integrity_status='verified' THEN 1 ELSE 0 END) FROM document_extraction_outputs WHERE run_id=?",
                (row["run_id"],),
            ).fetchone()
            status = (
                "verified" if integrity[0] and integrity[0] == (integrity[1] or 0) else "review"
            )
            con.execute(
                "INSERT OR REPLACE INTO document_registry_versions VALUES (?,?,?,?,?,?)",
                (
                    row["run_id"],
                    VERSION,
                    row["engine_version"],
                    NOW(),
                    status,
                    json.dumps({"engine_version_preserved": True, "registry_migrated": True}),
                ),
            )
            metadata = load_json(row["metadata_json"], {})
            metadata.update({"registry_version": VERSION, "registry_verified_at_utc": NOW()})
            con.execute(
                "UPDATE document_extraction_runs SET metadata_json=? WHERE run_id=?",
                (json.dumps(metadata, sort_keys=True, default=str), row["run_id"]),
            )
        result["document_registry_versions"] = len(rows)
    return result


def seed_knowledge_and_assets() -> dict[str, int]:
    knowledge = ROOT / "reports/knowledge.sqlite3"
    initialize_knowledge_warehouse(knowledge)
    with sqlite3.connect(ROOT / "reports/internet_downloads.sqlite3") as con:
        con.row_factory = sqlite3.Row
        sources = con.execute("SELECT * FROM scientific_source_catalog").fetchall()
    with sqlite3.connect(ROOT / "reports/datasets.sqlite3") as con:
        con.row_factory = sqlite3.Row
        readiness = {
            r["dataset_sha256"]: dict(r) for r in con.execute("SELECT * FROM dataset_readiness")
        }
    with transaction(knowledge) as con:
        con.execute(
            "DELETE FROM knowledge_relations WHERE evidence='Step31 source readiness catalogue'"
        )
        con.execute(
            "DELETE FROM knowledge_entities WHERE source='BioIntel Step31 source readiness catalogue'"
        )
        for p in sources:
            entity_id = f"step31:source:{p['source_key']}"
            _upsert_entity(
                con,
                entity_id=entity_id,
                entity_type="scientific_source",
                name=p["provider"],
                summary=f"{p['resource_type']} provider profile. Local status: {p['local_status']}. No remote records are claimed unless explicitly imported.",
                source="BioIntel Step31 source readiness catalogue",
                external_id=p["official_host"],
                confidence=0.95,
                tags=f"source,{p['resource_type']},{p['local_status']}",
                metadata={
                    "source_key": p["source_key"],
                    "access_method": p["access_method"],
                    "licence_profile": p["licence_profile"],
                    "real_records_imported": False,
                },
            )
        for sha, r in readiness.items():
            entity_id = f"dataset:{sha}"
            row = con.execute(
                "SELECT metadata_json FROM knowledge_entities WHERE entity_id=?", (entity_id,)
            ).fetchone()
            if row:
                metadata = load_json(row[0], {})
                metadata.update(
                    {
                        "readiness_score": r["readiness_score"],
                        "scientific_status": r["scientific_status"],
                        "integrity_status": r["integrity_status"],
                        "registry_version": VERSION,
                    }
                )
                con.execute(
                    "UPDATE knowledge_entities SET metadata_json=?,updated_at_utc=? WHERE entity_id=?",
                    (json.dumps(metadata, sort_keys=True), NOW(), entity_id),
                )
    seed_asset_store(ROOT, replace_demo=False)
    asset_db = ROOT / "reports/assets.sqlite3"
    with transaction(asset_db) as connection:
        now = NOW()
        connection.execute(
            """INSERT OR REPLACE INTO research_assets(asset_id,asset_type,title,path,source,sha256,size_bytes,mime_type,status,description,metadata_json,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "database:self:assets",
                "database",
                "assets.sqlite3",
                "reports/assets.sqlite3",
                "BioIntel primary database registry",
                None,
                asset_db.stat().st_size,
                "application/vnd.sqlite3",
                "available",
                "Research Assets database (self-reference; hash intentionally omitted while database is active).",
                json.dumps({"self_reference": True, "registry_version": VERSION}),
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO collection_assets(collection_id,asset_id,position,added_at_utc) VALUES ('COLL-DATABASES','database:self:assets',9999,?)",
            (now,),
        )
        connection.execute(
            "INSERT OR IGNORE INTO asset_tags(asset_id,tag) VALUES ('database:self:assets','database')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO asset_tags(asset_id,tag) VALUES ('database:self:assets','registry')"
        )
        asset_count = int(connection.execute("SELECT COUNT(*) FROM research_assets").fetchone()[0])
        database_assets = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'"
            ).fetchone()[0]
        )
        modules = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_assets WHERE asset_type='module'"
            ).fetchone()[0]
        )
    return {
        "scientific_sources": len(sources),
        "assets": asset_count,
        "database_assets": database_assets,
        "modules": modules,
    }


def write_reports(results: dict[str, Any]) -> None:
    report_dir = ROOT / "reports/generated"
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "version": VERSION,
        "milestone": "Step 31 Scientific Data & UI Overhaul",
        "generated_at_utc": NOW(),
        "results": results,
        "readiness": platform_readiness_summary(ROOT),
        "scientific_boundary": "Bundled data remains reference/simulation data. Real external records require explicit licensed import and review.",
    }
    (report_dir / "step31_readiness_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    rows = []
    with sqlite3.connect(ROOT / "reports/datasets.sqlite3") as con:
        con.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in con.execute(
                "SELECT d.dataset_name,d.dataset_version,d.task_type,d.row_count,r.* FROM datasets d JOIN dataset_readiness r USING(dataset_sha256) ORDER BY readiness_score,d.dataset_name"
            )
        ]
    pd.DataFrame(rows).to_csv(report_dir / "step31_dataset_readiness.csv", index=False)


def main() -> None:
    initialize_scientific_registries(ROOT)
    initialize_readiness_schema(ROOT)
    results = {}
    results["datasets"] = seed_dataset_registry()
    results["experiments"] = seed_experiment_registry()
    results["sources"] = seed_source_catalog()
    results["feature_cache"] = seed_feature_cache_metadata()
    results["projects_documents"] = seed_projects_and_documents()
    results["knowledge_assets"] = seed_knowledge_and_assets()
    write_reports(results)
    print(
        json.dumps(
            {"version": VERSION, **results, "readiness": platform_readiness_summary(ROOT)},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
