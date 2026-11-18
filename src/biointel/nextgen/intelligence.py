from __future__ import annotations

import hashlib
import html
import io
import json
import math
import sqlite3
import textwrap
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from uuid import uuid4

import numpy as np
import pandas as pd

from biointel.database.core import managed_connect


PREFERRED_ENTITY_COLUMNS: tuple[str, ...] = (
    "patient_id", "patient", "subject", "sample_id", "sample", "slide_id", "slide",
    "isolate_id", "isolate", "cell", "cluster", "region", "candidate_id", "candidate",
    "variant_id", "variant", "gene", "transcript", "isoform", "construct_id", "construct",
    "model_id", "model", "drug", "compound", "ligand", "event", "path", "population",
)

SCORE_COLUMN_HINTS: tuple[str, ...] = (
    "score", "confidence", "probability", "risk", "priority", "rank", "support",
    "effect", "signal", "tumour_probability", "embedding_score", "utility",
)

HANDOFF_TARGETS: dict[str, tuple[str, ...]] = {
    "digital_pathology_foundation": ("clinical_biomarker_survival", "spatial_medicine_tme"),
    "long_read_epigenome": ("clinical_biomarker_survival", "pangenome_population_medicine"),
    "single_cell_long_read_isoforms": ("spatial_medicine_tme", "clinical_biomarker_survival"),
    "biomedical_foundation_model_hub": ("digital_pathology_foundation", "protein_ligand_codesign", "federated_biomedical_ai"),
    "amr_surveillance": ("strain_microbiome", "pathogen_outbreak_genomics"),
    "spatial_medicine_tme": ("single_cell_long_read_isoforms", "clinical_biomarker_survival"),
    "gene_therapy_vector": ("cell_therapy_cart", "autonomous_lab_planner"),
    "cell_therapy_cart": ("gene_therapy_vector", "clinical_biomarker_survival"),
    "federated_biomedical_ai": ("clinical_biomarker_survival", "biomedical_foundation_model_hub"),
    "clinical_biomarker_survival": ("synthetic_cohort_trial", "federated_biomedical_ai"),
    "protein_ligand_codesign": ("admet_discovery", "ai_protein_design"),
    "pangenome_population_medicine": ("rare_disease_genome", "clinical_biomarker_survival"),
    "pharmacovigilance_intelligence": ("biomedical_knowledge_graph", "clinical_biomarker_survival"),
    "synthetic_cohort_trial": ("autonomous_lab_planner", "clinical_biomarker_survival"),
    "autonomous_lab_planner": ("synthetic_cohort_trial", "lab_analytics_command_center"),
}


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    module_key: str
    signature: str
    parameters: dict[str, Any]
    summary: dict[str, Any]
    completed_at_utc: str
    result_rows: int
    result_columns: int
    result_sha256: str
    preview: list[dict[str, Any]]
    extras: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def _frame_digest(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"empty-frame").hexdigest()
    bounded = frame.head(50_000).copy()
    for column in bounded.columns:
        if bounded[column].dtype == "object":
            bounded[column] = bounded[column].map(
                lambda value: _safe_json(value) if isinstance(value, (dict, list, tuple, set)) else value
            )
    payload = pd.util.hash_pandas_object(bounded, index=True).values.tobytes()
    payload += "|".join(map(str, bounded.columns)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _database_path(project_root: str | Path) -> Path:
    root = Path(project_root).resolve() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root / "step130_scientific_intelligence.sqlite3"


def connect(project_root: str | Path, *, path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path).resolve() if path is not None else _database_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = managed_connect(target, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_snapshots (
            run_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            signature TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            completed_at_utc TEXT NOT NULL,
            result_rows INTEGER NOT NULL,
            result_columns INTEGER NOT NULL,
            result_sha256 TEXT NOT NULL,
            preview_json TEXT NOT NULL,
            extras_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_snapshots_module
            ON run_snapshots(module_key, completed_at_utc DESC);

        CREATE TABLE IF NOT EXISTS review_decisions (
            decision_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            run_id TEXT,
            entity_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_decisions_module
            ON review_decisions(module_key, created_at_utc DESC);

        CREATE TABLE IF NOT EXISTS evidence_board_items (
            item_id TEXT PRIMARY KEY,
            board_id TEXT NOT NULL,
            module_key TEXT NOT NULL,
            run_id TEXT,
            entity_id TEXT NOT NULL,
            claim TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            confidence REAL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_board
            ON evidence_board_items(board_id, created_at_utc DESC);

        CREATE TABLE IF NOT EXISTS handoffs (
            handoff_id TEXT PRIMARY KEY,
            source_module TEXT NOT NULL,
            target_module TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_handoffs_target
            ON handoffs(target_module, updated_at_utc DESC);

        CREATE TABLE IF NOT EXISTS scenario_runs (
            scenario_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            run_id TEXT,
            name TEXT NOT NULL,
            parameter TEXT NOT NULL,
            baseline REAL NOT NULL,
            values_json TEXT NOT NULL,
            results_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scenarios_module
            ON scenario_runs(module_key, created_at_utc DESC);

        CREATE TABLE IF NOT EXISTS validation_cohorts (
            cohort_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            module_key TEXT NOT NULL,
            cohort_role TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            locked INTEGER NOT NULL,
            blinded INTEGER NOT NULL,
            notes TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_validation_cohort_source
            ON validation_cohorts(module_key, cohort_role, source_sha256);
        """
    )
    return connection


def persist_run_snapshot(
    *,
    project_root: str | Path,
    module_key: str,
    signature: str,
    parameters: Mapping[str, Any],
    summary: Mapping[str, Any],
    result: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame] | None,
    completed_at_utc: str,
    path: str | Path | None = None,
) -> str:
    result_frame = pd.DataFrame(result)
    digest = _frame_digest(result_frame)
    run_id = "RUN-" + hashlib.sha256(
        f"{module_key}|{signature}|{completed_at_utc}|{digest}".encode("utf-8")
    ).hexdigest()[:16].upper()
    preview = result_frame.head(200).replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")
    extra_sizes = {
        str(name): int(len(pd.DataFrame(table)))
        for name, table in dict(extras or {}).items()
        if table is not None
    }
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO run_snapshots(
                run_id, module_key, signature, parameters_json, summary_json,
                completed_at_utc, result_rows, result_columns, result_sha256,
                preview_json, extras_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                module_key,
                signature,
                _safe_json(dict(parameters)),
                _safe_json(dict(summary)),
                completed_at_utc,
                int(len(result_frame)),
                int(len(result_frame.columns)),
                digest,
                _safe_json(preview),
                _safe_json(extra_sizes),
                now,
            ),
        )
        connection.execute(
            """DELETE FROM run_snapshots
               WHERE module_key=? AND run_id NOT IN (
                   SELECT run_id FROM run_snapshots WHERE module_key=?
                   ORDER BY completed_at_utc DESC LIMIT 200
               )""",
            (module_key, module_key),
        )
        connection.commit()
    return run_id


def list_run_snapshots(
    project_root: str | Path,
    module_key: str | None = None,
    *,
    limit: int = 100,
    path: str | Path | None = None,
) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                """SELECT * FROM run_snapshots WHERE module_key=?
                   ORDER BY completed_at_utc DESC LIMIT ?""",
                (module_key, int(limit)),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM run_snapshots ORDER BY completed_at_utc DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        for source, target in (
            ("parameters_json", "parameters"),
            ("summary_json", "summary"),
            ("preview_json", "preview"),
            ("extras_json", "extras"),
        ):
            try:
                record[target] = json.loads(record.pop(source))
            except Exception:
                record[target] = {}
        records.append(record)
    return pd.DataFrame(records)


def _mapping_diff(left: Mapping[str, Any], right: Mapping[str, Any], *, section: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if _safe_json(a) != _safe_json(b):
            rows.append({"section": section, "field": key, "run_a": a, "run_b": b, "changed": True})
    return rows


def compare_run_snapshots(run_a: Mapping[str, Any], run_b: Mapping[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "section": "result",
            "field": "result_rows",
            "run_a": int(run_a.get("result_rows", 0)),
            "run_b": int(run_b.get("result_rows", 0)),
            "changed": int(run_a.get("result_rows", 0)) != int(run_b.get("result_rows", 0)),
        },
        {
            "section": "result",
            "field": "result_columns",
            "run_a": int(run_a.get("result_columns", 0)),
            "run_b": int(run_b.get("result_columns", 0)),
            "changed": int(run_a.get("result_columns", 0)) != int(run_b.get("result_columns", 0)),
        },
        {
            "section": "result",
            "field": "result_sha256",
            "run_a": run_a.get("result_sha256"),
            "run_b": run_b.get("result_sha256"),
            "changed": run_a.get("result_sha256") != run_b.get("result_sha256"),
        },
    ]
    rows.extend(_mapping_diff(run_a.get("parameters", {}) or {}, run_b.get("parameters", {}) or {}, section="parameter"))
    rows.extend(_mapping_diff(run_a.get("summary", {}) or {}, run_b.get("summary", {}) or {}, section="summary"))
    rows.extend(_mapping_diff(run_a.get("extras", {}) or {}, run_b.get("extras", {}) or {}, section="advanced_table"))
    return pd.DataFrame(rows)


def infer_entity_column(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    lower_map = {str(column).lower(): str(column) for column in frame.columns}
    for candidate in PREFERRED_ENTITY_COLUMNS:
        if candidate in lower_map:
            column = lower_map[candidate]
            count = frame[column].nunique(dropna=True)
            if 0 < count <= 100_000:
                return column
    categorical = [
        str(column)
        for column in frame.columns
        if not pd.api.types.is_numeric_dtype(frame[column])
        and 0 < frame[column].nunique(dropna=True) <= min(max(len(frame), 1), 100_000)
    ]
    return categorical[0] if categorical else None


def infer_score_column(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    numeric = [str(column) for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    for hint in SCORE_COLUMN_HINTS:
        for column in numeric:
            if hint in column.lower() and pd.to_numeric(frame[column], errors="coerce").notna().any():
                return column
    for column in numeric:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) > 1 and values.nunique() > 1:
            return column
    return numeric[0] if numeric else None


def save_review_decision(
    *,
    project_root: str | Path,
    module_key: str,
    entity_id: str,
    decision: str,
    note: str,
    reviewer: str,
    run_id: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    path: str | Path | None = None,
) -> str:
    decision_id = "REV-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute(
            """INSERT INTO review_decisions(
                decision_id, module_key, run_id, entity_id, decision, note,
                evidence_json, reviewer, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision_id, module_key, run_id, str(entity_id), str(decision), str(note),
                _safe_json(dict(evidence or {})), str(reviewer or "local-reviewer"), utc_now(),
            ),
        )
        connection.commit()
    return decision_id


def list_review_decisions(
    project_root: str | Path,
    module_key: str | None = None,
    *,
    path: str | Path | None = None,
) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                "SELECT * FROM review_decisions WHERE module_key=? ORDER BY created_at_utc DESC LIMIT 500",
                (module_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM review_decisions ORDER BY created_at_utc DESC LIMIT 1000"
            ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _normalise_confidence(value: Any, values: pd.Series | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if 0 <= number <= 1:
        return number
    if values is not None:
        clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if not clean.empty and clean.max() > clean.min():
            return float(np.clip((number - clean.min()) / (clean.max() - clean.min()), 0, 1))
    return float(np.clip(number / 100.0, 0, 1))


def build_evidence_items(
    *,
    module_key: str,
    result: pd.DataFrame,
    run_id: str | None,
    max_items: int = 50,
) -> pd.DataFrame:
    frame = pd.DataFrame(result).head(max_items).copy()
    if frame.empty:
        return pd.DataFrame(columns=["module_key", "run_id", "entity_id", "claim", "evidence_status", "confidence", "source", "payload"])
    entity_column = infer_entity_column(frame)
    score_column = infer_score_column(frame)
    score_values = frame[score_column] if score_column else None
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        entity_id = str(row.get(entity_column, f"row-{index + 1}")) if entity_column else f"row-{index + 1}"
        confidence = _normalise_confidence(row.get(score_column), score_values) if score_column else None
        evidence_status = str(row.get("evidence_status", row.get("source_kind", "screening")))
        claim = f"{entity_id} was prioritised by {module_key.replace('_', ' ')}"
        if score_column:
            claim += f" using {score_column.replace('_', ' ')}={row.get(score_column)}"
        rows.append({
            "module_key": module_key,
            "run_id": run_id,
            "entity_id": entity_id,
            "claim": claim,
            "evidence_status": evidence_status,
            "confidence": confidence,
            "source": f"BioIntel run {run_id or 'current-session'}",
            "payload": row.to_dict(),
        })
    return pd.DataFrame(rows)


def add_evidence_items(
    *,
    project_root: str | Path,
    board_id: str,
    items: pd.DataFrame,
    path: str | Path | None = None,
) -> list[str]:
    ids: list[str] = []
    with connect(project_root, path=path) as connection:
        for _, row in pd.DataFrame(items).iterrows():
            item_id = "EVI-" + uuid4().hex[:16].upper()
            confidence = row.get("confidence")
            confidence_value = None if pd.isna(confidence) else float(confidence)
            connection.execute(
                """INSERT INTO evidence_board_items(
                    item_id, board_id, module_key, run_id, entity_id, claim,
                    evidence_status, confidence, source, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id, str(board_id), str(row.get("module_key", "unknown")), row.get("run_id"),
                    str(row.get("entity_id", "unknown")), str(row.get("claim", "")),
                    str(row.get("evidence_status", "screening")), confidence_value,
                    str(row.get("source", "local")), _safe_json(row.get("payload", {})), utc_now(),
                ),
            )
            ids.append(item_id)
        connection.commit()
    return ids


def list_evidence_board(
    project_root: str | Path,
    board_id: str | None = None,
    *,
    path: str | Path | None = None,
) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if board_id:
            rows = connection.execute(
                "SELECT * FROM evidence_board_items WHERE board_id=? ORDER BY created_at_utc DESC LIMIT 2000",
                (board_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM evidence_board_items ORDER BY created_at_utc DESC LIMIT 2000"
            ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def create_handoff(
    *,
    project_root: str | Path,
    source_module: str,
    target_module: str,
    payload: Mapping[str, Any],
    run_id: str | None = None,
    path: str | Path | None = None,
) -> str:
    if source_module == target_module:
        raise ValueError("Source and target modules must be different")
    handoff_id = "HOF-" + uuid4().hex[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute(
            """INSERT INTO handoffs(
                handoff_id, source_module, target_module, run_id, status,
                payload_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (handoff_id, source_module, target_module, run_id, "ready", _safe_json(dict(payload)), now, now),
        )
        connection.commit()
    return handoff_id


def list_handoffs(
    project_root: str | Path,
    *,
    target_module: str | None = None,
    source_module: str | None = None,
    path: str | Path | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[Any] = []
    if target_module:
        clauses.append("target_module=?")
        params.append(target_module)
    if source_module:
        clauses.append("source_module=?")
        params.append(source_module)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(project_root, path=path) as connection:
        rows = connection.execute(
            f"SELECT * FROM handoffs{where} ORDER BY updated_at_utc DESC LIMIT 1000",  # noqa: S608 - fixed clauses only
            tuple(params),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _score_summary(result: pd.DataFrame) -> tuple[str | None, float | None]:
    score_column = infer_score_column(result)
    if not score_column:
        return None, None
    values = pd.to_numeric(result[score_column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return score_column, None
    return score_column, float(values.mean())


def evaluate_threshold_scenarios(
    *,
    data: pd.DataFrame,
    analyser: Callable[[pd.DataFrame, float], tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]],
    thresholds: Sequence[float],
    max_rows: int = 50_000,
) -> pd.DataFrame:
    frame = pd.DataFrame(data).head(max_rows).copy()
    if frame.empty:
        raise ValueError("Scenario simulation requires non-empty input data")
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        value = float(np.clip(float(threshold), 0.0, 1.0))
        started = time.perf_counter()
        try:
            result, summary, secondary, extras = analyser(frame, value)
            result_frame = pd.DataFrame(result)
            score_column, mean_score = _score_summary(result_frame)
            rows.append({
                "threshold": value,
                "status": "completed",
                "result_rows": int(len(result_frame)),
                "secondary_rows": int(len(pd.DataFrame(secondary))) if secondary is not None else 0,
                "advanced_tables": int(len(extras or {})),
                "score_column": score_column,
                "mean_score": mean_score,
                "runtime_seconds": round(time.perf_counter() - started, 4),
                "summary": _safe_json(summary),
                "error": "",
            })
        except Exception as exc:
            rows.append({
                "threshold": value,
                "status": "failed",
                "result_rows": 0,
                "secondary_rows": 0,
                "advanced_tables": 0,
                "score_column": None,
                "mean_score": None,
                "runtime_seconds": round(time.perf_counter() - started, 4),
                "summary": "{}",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            })
    return pd.DataFrame(rows)


def save_scenario_run(
    *,
    project_root: str | Path,
    module_key: str,
    name: str,
    baseline: float,
    results: pd.DataFrame,
    run_id: str | None = None,
    parameter: str = "threshold",
    path: str | Path | None = None,
) -> str:
    scenario_id = "SCN-" + uuid4().hex[:16].upper()
    values = pd.to_numeric(results.get(parameter, pd.Series(dtype=float)), errors="coerce").dropna().tolist()
    with connect(project_root, path=path) as connection:
        connection.execute(
            """INSERT INTO scenario_runs(
                scenario_id, module_key, run_id, name, parameter, baseline,
                values_json, results_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scenario_id, module_key, run_id, str(name), parameter, float(baseline),
                _safe_json(values), _safe_json(results.replace({np.nan: None}).to_dict(orient="records")), utc_now(),
            ),
        )
        connection.execute(
            """DELETE FROM scenario_runs
               WHERE module_key=? AND scenario_id NOT IN (
                   SELECT scenario_id FROM scenario_runs WHERE module_key=?
                   ORDER BY created_at_utc DESC LIMIT 200
               )""",
            (module_key, module_key),
        )
        connection.commit()
    return scenario_id


def list_scenarios(
    project_root: str | Path,
    module_key: str | None = None,
    *,
    path: str | Path | None = None,
) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                "SELECT * FROM scenario_runs WHERE module_key=? ORDER BY created_at_utc DESC LIMIT 500",
                (module_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM scenario_runs ORDER BY created_at_utc DESC LIMIT 1000"
            ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def register_validation_cohort(
    *,
    project_root: str | Path,
    name: str,
    module_key: str,
    cohort_role: str,
    source_bytes: bytes,
    row_count: int,
    column_count: int,
    locked: bool,
    blinded: bool,
    notes: str = "",
    metadata: Mapping[str, Any] | None = None,
    path: str | Path | None = None,
) -> str:
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    cohort_id = "COH-" + hashlib.sha256(
        f"{module_key}|{cohort_role}|{source_hash}".encode("utf-8")
    ).hexdigest()[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute(
            """INSERT INTO validation_cohorts(
                cohort_id, name, module_key, cohort_role, source_sha256,
                row_count, column_count, locked, blinded, notes,
                metadata_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(module_key, cohort_role, source_sha256) DO UPDATE SET
                name=excluded.name,
                row_count=excluded.row_count,
                column_count=excluded.column_count,
                locked=excluded.locked,
                blinded=excluded.blinded,
                notes=excluded.notes,
                metadata_json=excluded.metadata_json,
                updated_at_utc=excluded.updated_at_utc
            """,
            (
                cohort_id, str(name), module_key, cohort_role, source_hash,
                int(row_count), int(column_count), int(bool(locked)), int(bool(blinded)), str(notes),
                _safe_json(dict(metadata or {})), now, now,
            ),
        )
        connection.commit()
    return cohort_id


def list_validation_cohorts(
    project_root: str | Path,
    module_key: str | None = None,
    *,
    path: str | Path | None = None,
) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                "SELECT * FROM validation_cohorts WHERE module_key=? ORDER BY updated_at_utc DESC",
                (module_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM validation_cohorts ORDER BY updated_at_utc DESC"
            ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


from .intelligence_reporting import audit_visuals, build_publication_bundle, build_scientific_story

