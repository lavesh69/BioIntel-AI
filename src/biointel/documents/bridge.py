from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.data.dataset_registry import register_dataset
from biointel.data.real_evidence import import_curated_evidence, result_dict
from biointel.documents.service import load_processed_document


def table_dataframe(project_root: str | Path, run_id: str, table_index: int) -> pd.DataFrame:
    extraction = load_processed_document(project_root, run_id).extraction
    if table_index < 0 or table_index >= len(extraction.tables):
        raise IndexError("Table index is outside the extracted table range.")
    table = extraction.tables[table_index]
    return pd.DataFrame(table.rows, columns=table.columns)


def register_table_as_dataset(
    project_root: str | Path,
    *,
    run_id: str,
    table_index: int,
    dataset_name: str,
    dataset_version: str,
    task_type: str = "unlabelled",
    activity_type: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    processed = load_processed_document(root, run_id)
    table = processed.extraction.tables[table_index]
    frame = pd.DataFrame(table.rows, columns=table.columns)
    record = register_dataset(
        runtime_database_path(root, "datasets.sqlite3"),
        frame,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        task_type=task_type,
        source_description=(
            f"Extracted from {processed.extraction.source_name}; run {run_id}; "
            f"source {table.source}; table {table.name}."
        ),
        activity_type=activity_type,
        notes=notes,
        metadata={
            "document_run_id": run_id,
            "document_sha256": processed.extraction.source_sha256,
            "document_source_name": processed.extraction.source_name,
            "table_index": table_index,
            "table_name": table.name,
            "table_source": table.source,
            "table_confidence": table.confidence,
            "page_cell_provenance": table.metadata,
            "step27_document_bridge": True,
        },
    )
    return asdict(record)


def import_table_as_evidence(
    project_root: str | Path,
    *,
    run_id: str,
    table_index: int,
    column_mapping: dict[str, str],
    provider: str = "document_extraction",
    source_release: str = "document_import",
    active_threshold: float = 6.0,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    processed = load_processed_document(root, run_id)
    table = processed.extraction.tables[table_index]
    frame = pd.DataFrame(table.rows, columns=table.columns)
    required = {
        "canonical_smiles",
        "protein_sequence",
        "standard_value",
        "standard_units",
    }
    missing = required - set(column_mapping)
    if missing:
        raise ValueError("Missing evidence mappings: " + ", ".join(sorted(missing)))
    renamed = pd.DataFrame()
    for target, source in column_mapping.items():
        if source and source in frame.columns:
            renamed[target] = frame[source]
    if "standard_relation" not in renamed:
        renamed["standard_relation"] = "="
    if "activity_type" not in renamed:
        renamed["activity_type"] = "unspecified"
    result = import_curated_evidence(
        renamed,
        provider=provider,
        source_release=source_release,
        registry_path=runtime_database_path(root, "evidence.sqlite3"),
        dataset_registry_path=runtime_database_path(root, "datasets.sqlite3"),
        output_directory=root / "data" / "real_evidence",
        source_sha256=processed.extraction.source_sha256,
        source_local_path=processed.source_saved_path,
        active_threshold=active_threshold,
        metadata={
            "document_run_id": run_id,
            "document_source_name": processed.extraction.source_name,
            "table_index": table_index,
            "table_name": table.name,
            "table_source": table.source,
            "table_confidence": table.confidence,
            "column_mapping": column_mapping,
            "step27_document_bridge": True,
        },
    )
    return result_dict(result)
