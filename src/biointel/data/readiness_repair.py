from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.data.readiness import (
    backfill_missing_dataset_readiness,
    initialize_readiness_schema,
)
from biointel.database.core import transaction


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _largest_record_list(value: Any) -> list[dict[str, Any]] | None:
    candidates: list[list[dict[str, Any]]] = []

    def visit(item: Any) -> None:
        if isinstance(item, list) and item and all(isinstance(row, dict) for row in item):
            candidates.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)

    visit(value)
    return max(candidates, key=len) if candidates else None


def _read_tabular(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        return pd.DataFrame()
    if suffix in {".tsv", ".txt"}:
        if re.match(r"^R-[A-Z]{3}-\d+\t", lines[0]):
            return pd.read_csv(
                path,
                sep="\t",
                header=None,
                names=["pathway_id", "pathway_name", "organism"],
                comment="#",
                low_memory=False,
            )
        return pd.read_csv(path, sep="\t", comment="#", low_memory=False)
    return pd.read_csv(path, comment="#", low_memory=False)


def _profile_file(path: Path) -> tuple[list[tuple[str, str]], dict[str, float | str], int]:
    suffix = path.suffix.casefold()
    columns: list[tuple[str, str]] = []
    metrics: dict[str, float | str] = {
        "file_bytes": float(path.stat().st_size),
        "parse_status": "parsed",
    }
    record_count = 0

    if suffix in {".csv", ".tsv", ".txt"}:
        frame = _read_tabular(path)
        record_count = int(len(frame))
        columns = [(str(name), str(dtype)) for name, dtype in frame.dtypes.items()]
        metrics.update(
            {
                "record_count": float(record_count),
                "column_count": float(len(frame.columns)),
                "missing_cells": float(frame.isna().sum().sum()),
                "duplicate_rows": float(frame.duplicated().sum()),
            }
        )
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        records = _largest_record_list(payload)
        if records:
            frame = pd.json_normalize(records, sep=".")
        elif isinstance(payload, dict):
            frame = pd.json_normalize([payload], sep=".")
        elif isinstance(payload, list):
            frame = pd.json_normalize(payload, sep=".")
        else:
            frame = pd.DataFrame({"value": [payload]})
        record_count = int(len(frame))
        columns = [(str(name), str(dtype)) for name, dtype in frame.dtypes.items()]
        duplicate_view = frame.map(
            lambda value: json.dumps(value, sort_keys=True, default=str)
            if isinstance(value, (dict, list, tuple, set))
            else value
        )
        metrics.update(
            {
                "record_count": float(record_count),
                "column_count": float(len(frame.columns)),
                "missing_cells": float(frame.isna().sum().sum()),
                "duplicate_rows": float(duplicate_view.duplicated().sum()),
            }
        )
    elif suffix in {".fa", ".fasta", ".fna", ".faa"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        headers = [line[1:].strip() for line in text.splitlines() if line.startswith(">")]
        sequence_chars = sum(
            len(re.sub(r"\s+", "", line))
            for line in text.splitlines()
            if line and not line.startswith(">")
        )
        record_count = len(headers)
        columns = [
            ("record_id", "string"),
            ("description", "string"),
            ("sequence", "sequence"),
            ("sequence_length", "integer"),
        ]
        metrics.update(
            {
                "record_count": float(record_count),
                "column_count": 4.0,
                "sequence_characters": float(sequence_chars),
                "empty_sequences": 0.0 if sequence_chars else float(record_count),
            }
        )
    elif suffix in {".cif", ".mmcif"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        atom_count = 0
        try:
            from Bio.PDB.MMCIF2Dict import MMCIF2Dict

            payload = MMCIF2Dict(str(path))
            atom_ids = payload.get("_atom_site.id", [])
            atom_count = len(atom_ids) if isinstance(atom_ids, list) else int(bool(atom_ids))
            field_count = len(payload)
        except Exception:
            field_count = sum(1 for line in text.splitlines() if line.startswith("_"))
        record_count = atom_count or field_count
        columns = [
            ("mmcif_category", "string"),
            ("field_name", "string"),
            ("value", "string"),
        ]
        metrics.update(
            {
                "record_count": float(record_count),
                "column_count": 3.0,
                "atom_site_records": float(atom_count),
                "line_count": float(len(text.splitlines())),
            }
        )
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        record_count = len([line for line in text.splitlines() if line.strip()])
        columns = [("line_text", "string")]
        metrics.update(
            {
                "record_count": float(record_count),
                "column_count": 1.0,
                "line_count": float(record_count),
                "replacement_characters": float(text.count("�")),
            }
        )

    return columns, metrics, record_count


def _semantic_role(name: str, dtype: str) -> str:
    lowered = name.casefold()
    if lowered in {"target", "label", "diagnosis_label", "outcome"}:
        return "label"
    if lowered.endswith("_id") or lowered in {"id", "accession", "stable_id", "record_id"}:
        return "identifier"
    if "organism" in lowered or "taxonomy" in lowered:
        return "organism"
    if "url" in lowered or "source" in lowered or "provider" in lowered:
        return "provenance"
    if "sequence" in lowered:
        return "sequence"
    if any(token in dtype.casefold() for token in ("int", "float", "double")):
        return "measurement"
    return "metadata"


def repair_bundled_dataset_profiles(root: str | Path) -> dict[str, int]:
    """Backfill schema and QC records for packaged datasets added after Step 31."""

    project_root = Path(root).resolve()
    initialize_readiness_schema(project_root)
    database = runtime_database_path(project_root, "datasets.sqlite3")
    repaired = 0
    skipped = 0
    failed = 0
    repaired_shas: list[str] = []
    now = _utc_now()

    with transaction(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT d.dataset_sha256,d.dataset_name,d.row_count,
                   SUM(CASE WHEN c.column_name IS NOT NULL THEN 1 ELSE 0 END) AS column_count,
                   (SELECT COUNT(*) FROM dataset_qc_metrics q WHERE q.dataset_sha256=d.dataset_sha256) AS qc_count
            FROM datasets d
            LEFT JOIN dataset_columns c USING(dataset_sha256)
            GROUP BY d.dataset_sha256
            HAVING column_count=0 OR qc_count<3
            ORDER BY d.dataset_name
            """
        ).fetchall()

        for row in rows:
            sha = str(row["dataset_sha256"])
            file_row = connection.execute(
                """
                SELECT relative_path,file_format,role,size_bytes
                FROM dataset_files
                WHERE dataset_sha256=?
                ORDER BY CASE WHEN role IN ('primary','primary_data') THEN 0 ELSE 1 END,
                         size_bytes DESC
                LIMIT 1
                """,
                (sha,),
            ).fetchone()
            if file_row is None:
                skipped += 1
                continue
            path = project_root / str(file_row["relative_path"])
            if not path.is_file():
                skipped += 1
                continue
            try:
                columns, metrics, records = _profile_file(path)
            except Exception as exc:
                failed += 1
                metric_id = hashlib.sha256(f"{sha}|profile_error".encode()).hexdigest()[:28]
                connection.execute(
                    """
                    INSERT OR REPLACE INTO dataset_qc_metrics(
                        qc_id,dataset_sha256,metric_name,metric_value,metric_text,unit,
                        scope,scope_id,status,threshold_json,created_at_utc
                    ) VALUES (?,?,?,NULL,?,NULL,'dataset','', 'warning','{}',?)
                    """,
                    (metric_id, sha, "profile_error", f"{type(exc).__name__}: {exc}", now),
                )
                continue

            if int(row["column_count"] or 0) == 0:
                for position, (name, dtype) in enumerate(columns, start=1):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dataset_columns(
                            dataset_sha256,column_name,ordinal_position,data_type,semantic_role,
                            unit,description,nullable,metadata_json
                        ) VALUES (?,?,?,?,?,NULL,?,1,?)
                        """,
                        (
                            sha,
                            name,
                            position,
                            dtype,
                            _semantic_role(name, dtype),
                            f"Automatically profiled from {path.name}",
                            json.dumps({"profiled_from": path.relative_to(project_root).as_posix()}),
                        ),
                    )

            for metric_name, value in metrics.items():
                metric_id = hashlib.sha256(f"{sha}|{metric_name}".encode()).hexdigest()[:28]
                numeric = float(value) if isinstance(value, (int, float)) else None
                text_value = None if numeric is not None else str(value)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO dataset_qc_metrics(
                        qc_id,dataset_sha256,metric_name,metric_value,metric_text,unit,
                        scope,scope_id,status,threshold_json,created_at_utc
                    ) VALUES (?,?,?,?,?,NULL,'dataset','',?,'{}',?)
                    """,
                    (
                        metric_id,
                        sha,
                        metric_name,
                        numeric,
                        text_value,
                        "passed" if metric_name != "parse_status" or text_value == "parsed" else "warning",
                        now,
                    ),
                )

            if records > int(row["row_count"] or 0):
                connection.execute(
                    "UPDATE datasets SET row_count=? WHERE dataset_sha256=?",
                    (records, sha),
                )
            connection.execute("DELETE FROM dataset_readiness WHERE dataset_sha256=?", (sha,))
            connection.execute("DELETE FROM dataset_validation_issues WHERE dataset_sha256=?", (sha,))
            repaired += 1
            repaired_shas.append(sha)

    if repaired_shas:
        backfill_missing_dataset_readiness(project_root)
    return {"repaired": repaired, "skipped": skipped, "failed": failed}
