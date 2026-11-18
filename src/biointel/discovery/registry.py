from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from biointel import __version__
from biointel.database.core import connect as db_connect

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "discovery_projects.sqlite3"
SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS discovery_projects(
    project_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    indication TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT 'local_user',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','completed','archived')),
    active_target_id TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL DEFAULT '{}',
    software_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_targets(
    target_record_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES discovery_projects(project_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    scoring_json TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    provider_release_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_compounds(
    compound_record_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES discovery_projects(project_id) ON DELETE CASCADE,
    compound_id TEXT NOT NULL,
    original_smiles TEXT NOT NULL,
    standardized_smiles TEXT NOT NULL,
    inchikey TEXT,
    connectivity_key TEXT,
    profile_json TEXT NOT NULL,
    source_json TEXT NOT NULL DEFAULT '{}',
    duplicate_of TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(project_id, compound_id),
    FOREIGN KEY(duplicate_of) REFERENCES discovery_compounds(compound_record_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS discovery_rankings(
    ranking_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES discovery_projects(project_id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    output_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_evidence(
    evidence_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES discovery_projects(project_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    evidence_date TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence >= 0 AND confidence <= 1),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_events(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES discovery_projects(project_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    occurred_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admet_endpoint_models(
    model_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','blocked','qualified','retired')),
    model_card_json TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL DEFAULT '',
    training_dataset_sha256 TEXT NOT NULL DEFAULT '',
    qualification_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discovery_projects_updated ON discovery_projects(updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_targets_project ON discovery_targets(project_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_compounds_project ON discovery_compounds(project_id, updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_compounds_identity ON discovery_compounds(project_id, inchikey, connectivity_key);
CREATE INDEX IF NOT EXISTS idx_discovery_rankings_project ON discovery_rankings(project_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_evidence_entity ON discovery_evidence(project_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_discovery_events_project ON discovery_events(project_id, occurred_at_utc DESC);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _sha(value: object) -> str:
    payload = value if isinstance(value, bytes) else _json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def connect(path: str | Path = DEFAULT_PATH) -> sqlite3.Connection:
    """Open the project registry and initialize its schema only when required.

    Earlier releases executed the complete ``CREATE TABLE IF NOT EXISTS`` script on
    every read and write. ``PRAGMA user_version`` turns schema setup into a one-time
    migration per database while retaining safe initialization for temporary/test DBs.
    """

    connection = db_connect(path)
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version < SCHEMA_VERSION:
        connection.executescript(SCHEMA)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    return connection


def _event(
    connection: sqlite3.Connection,
    project_id: str,
    event_type: str,
    *,
    entity_type: str = "",
    entity_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        "INSERT INTO discovery_events(project_id,event_type,entity_type,entity_id,detail_json,occurred_at_utc) VALUES(?,?,?,?,?,?)",
        (project_id, event_type, entity_type, entity_id, _json(detail or {}), _now()),
    )


def create_project(
    project_name: str,
    *,
    indication: str = "",
    objective: str = "",
    owner: str = "local_user",
    settings: dict[str, Any] | None = None,
    path: str | Path = DEFAULT_PATH,
) -> str:
    name = str(project_name).strip()
    if not name:
        raise ValueError("project_name is required")
    project_id = "dsc-" + uuid4().hex[:20]
    now = _now()
    with closing(connect(path)) as connection:
        connection.execute(
            "INSERT INTO discovery_projects(project_id,project_name,indication,objective,owner,settings_json,software_version,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
            (project_id, name, indication.strip(), objective.strip(), owner.strip() or "local_user", _json(settings or {}), __version__, now, now),
        )
        _event(connection, project_id, "project_created", detail={"project_name": name})
        connection.commit()
    return project_id


def update_project(
    project_id: str,
    *,
    project_name: str | None = None,
    indication: str | None = None,
    objective: str | None = None,
    status: str | None = None,
    active_target_id: str | None = None,
    settings: dict[str, Any] | None = None,
    path: str | Path = DEFAULT_PATH,
) -> None:
    updates: dict[str, object] = {"updated_at_utc": _now()}
    for key, value in {
        "project_name": project_name,
        "indication": indication,
        "objective": objective,
        "status": status,
        "active_target_id": active_target_id,
    }.items():
        if value is not None:
            updates[key] = str(value).strip()
    if settings is not None:
        updates["settings_json"] = _json(settings)
    if status is not None and status not in {"active", "paused", "completed", "archived"}:
        raise ValueError("Unsupported project status")
    assignments = ",".join(f"{key}=?" for key in updates)
    with closing(connect(path)) as connection:
        cursor = connection.execute(
            f"UPDATE discovery_projects SET {assignments} WHERE project_id=?",
            (*updates.values(), project_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(project_id)
        _event(connection, project_id, "project_updated", detail=updates)
        connection.commit()


def list_projects(*, limit: int = 200, path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    with closing(connect(path)) as connection:
        return pd.read_sql_query(
            "SELECT * FROM discovery_projects ORDER BY updated_at_utc DESC LIMIT ?",
            connection,
            params=(min(max(int(limit), 1), 5000),),
        )


def get_project(project_id: str, *, path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    with closing(connect(path)) as connection:
        row = connection.execute(
            "SELECT * FROM discovery_projects WHERE project_id=?", (project_id,)
        ).fetchone()
    if row is None:
        raise KeyError(project_id)
    result = dict(row)
    result["settings"] = json.loads(result.pop("settings_json"))
    return result


def add_target_assessment(
    project_id: str,
    *,
    target_id: str,
    scoring: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    provider_releases: dict[str, Any] | None = None,
    path: str | Path = DEFAULT_PATH,
) -> str:
    evidence_rows = evidence or []
    target_record_id = "tgt-" + uuid4().hex[:20]
    now = _now()
    with closing(connect(path)) as connection:
        connection.execute(
            "INSERT INTO discovery_targets(target_record_id,project_id,target_id,evidence_json,scoring_json,evidence_sha256,provider_release_json,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (target_record_id, project_id, target_id.strip(), _json(evidence_rows), _json(scoring), _sha(evidence_rows), _json(provider_releases or {}), now),
        )
        connection.execute(
            "UPDATE discovery_projects SET active_target_id=?,updated_at_utc=? WHERE project_id=?",
            (target_id.strip(), now, project_id),
        )
        _event(connection, project_id, "target_assessment_added", entity_type="target", entity_id=target_id, detail={"target_record_id": target_record_id})
        connection.commit()
    return target_record_id


def _connectivity_key(inchikey: str | None) -> str | None:
    return str(inchikey).split("-", 1)[0] if inchikey else None


def upsert_compound(
    project_id: str,
    *,
    compound_id: str,
    original_smiles: str,
    standardized_smiles: str,
    inchikey: str | None,
    profile: dict[str, Any],
    source: dict[str, Any] | None = None,
    duplicate_policy: str = "merge_exact",
    path: str | Path = DEFAULT_PATH,
) -> dict[str, Any]:
    if duplicate_policy not in {"merge_exact", "keep_separate", "reject_exact", "merge_connectivity"}:
        raise ValueError("Unsupported duplicate_policy")
    now = _now()
    connectivity = _connectivity_key(inchikey)
    with closing(connect(path)) as connection:
        project_exists = connection.execute(
            "SELECT 1 FROM discovery_projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if project_exists is None:
            raise KeyError(project_id)
        duplicate = None
        if inchikey:
            if duplicate_policy == "merge_connectivity":
                duplicate = connection.execute(
                    "SELECT * FROM discovery_compounds WHERE project_id=? AND connectivity_key=? ORDER BY created_at_utc LIMIT 1",
                    (project_id, connectivity),
                ).fetchone()
            else:
                duplicate = connection.execute(
                    "SELECT * FROM discovery_compounds WHERE project_id=? AND inchikey=? ORDER BY created_at_utc LIMIT 1",
                    (project_id, inchikey),
                ).fetchone()
        if duplicate is not None and duplicate_policy == "reject_exact":
            raise ValueError(
                f"Duplicate molecular identity already exists as {duplicate['compound_id']}"
            )
        if duplicate is not None and duplicate_policy in {"merge_exact", "merge_connectivity"}:
            record_id = str(duplicate["compound_record_id"])
            connection.execute(
                "UPDATE discovery_compounds SET compound_id=?,original_smiles=?,standardized_smiles=?,inchikey=?,connectivity_key=?,profile_json=?,source_json=?,updated_at_utc=? WHERE compound_record_id=?",
                (compound_id.strip(), original_smiles, standardized_smiles, inchikey, connectivity, _json(profile), _json(source or {}), now, record_id),
            )
            action = "merged"
        else:
            record_id = "cmp-" + uuid4().hex[:20]
            duplicate_of = str(duplicate["compound_record_id"]) if duplicate is not None else None
            connection.execute(
                "INSERT INTO discovery_compounds(compound_record_id,project_id,compound_id,original_smiles,standardized_smiles,inchikey,connectivity_key,profile_json,source_json,duplicate_of,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,compound_id) DO UPDATE SET original_smiles=excluded.original_smiles,standardized_smiles=excluded.standardized_smiles,inchikey=excluded.inchikey,connectivity_key=excluded.connectivity_key,profile_json=excluded.profile_json,source_json=excluded.source_json,updated_at_utc=excluded.updated_at_utc",
                (record_id, project_id, compound_id.strip(), original_smiles, standardized_smiles, inchikey, connectivity, _json(profile), _json(source or {}), duplicate_of, now, now),
            )
            existing = connection.execute(
                "SELECT compound_record_id FROM discovery_compounds WHERE project_id=? AND compound_id=?",
                (project_id, compound_id.strip()),
            ).fetchone()
            record_id = str(existing[0])
            action = "inserted" if duplicate is None else "kept_separate"
        connection.execute(
            "UPDATE discovery_projects SET updated_at_utc=? WHERE project_id=?", (now, project_id)
        )
        _event(connection, project_id, "compound_upserted", entity_type="compound", entity_id=compound_id, detail={"action": action, "compound_record_id": record_id})
        connection.commit()
    return {"compound_record_id": record_id, "action": action, "duplicate_detected": duplicate is not None}


def list_compounds(project_id: str, *, path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    with closing(connect(path)) as connection:
        frame = pd.read_sql_query(
            "SELECT * FROM discovery_compounds WHERE project_id=? ORDER BY updated_at_utc DESC",
            connection,
            params=(project_id,),
        )
    if not frame.empty:
        frame["profile"] = frame["profile_json"].map(json.loads)
        frame["source"] = frame["source_json"].map(json.loads)
    return frame


def save_ranking(
    project_id: str,
    *,
    result: pd.DataFrame,
    method: str,
    parameters: dict[str, Any],
    path: str | Path = DEFAULT_PATH,
) -> str:
    ranking_id = "rnk-" + uuid4().hex[:20]
    payload = result.to_dict(orient="records")
    input_payload = {"parameters": parameters, "ids": result.iloc[:, :2].to_dict(orient="records") if not result.empty else []}
    now = _now()
    with closing(connect(path)) as connection:
        connection.execute(
            "INSERT INTO discovery_rankings(ranking_id,project_id,method,parameters_json,input_sha256,output_sha256,result_json,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (ranking_id, project_id, method, _json(parameters), _sha(input_payload), _sha(payload), _json(payload), now),
        )
        connection.execute(
            "UPDATE discovery_projects SET updated_at_utc=? WHERE project_id=?", (now, project_id)
        )
        _event(connection, project_id, "ranking_saved", entity_type="ranking", entity_id=ranking_id, detail={"rows": len(result), "method": method})
        connection.commit()
    return ranking_id


def add_evidence(
    project_id: str,
    *,
    entity_type: str,
    entity_id: str,
    evidence_type: str,
    source: str,
    payload: dict[str, Any],
    source_id: str = "",
    evidence_date: str = "",
    confidence: float = 0.5,
    path: str | Path = DEFAULT_PATH,
) -> str:
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be between 0 and 1")
    evidence_id = "evd-" + uuid4().hex[:20]
    now = _now()
    with closing(connect(path)) as connection:
        connection.execute(
            "INSERT INTO discovery_evidence(evidence_id,project_id,entity_type,entity_id,evidence_type,source,source_id,evidence_date,confidence,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (evidence_id, project_id, entity_type, entity_id, evidence_type, source, source_id, evidence_date, float(confidence), _json(payload), _sha(payload), now),
        )
        _event(connection, project_id, "evidence_added", entity_type=entity_type, entity_id=entity_id, detail={"evidence_id": evidence_id, "source": source})
        connection.commit()
    return evidence_id


def project_snapshot(project_id: str, *, path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    project = get_project(project_id, path=path)
    with closing(connect(path)) as connection:
        targets = [dict(row) for row in connection.execute("SELECT * FROM discovery_targets WHERE project_id=? ORDER BY created_at_utc", (project_id,))]
        compounds = [dict(row) for row in connection.execute("SELECT * FROM discovery_compounds WHERE project_id=? ORDER BY created_at_utc", (project_id,))]
        rankings = [dict(row) for row in connection.execute("SELECT * FROM discovery_rankings WHERE project_id=? ORDER BY created_at_utc", (project_id,))]
        evidence = [dict(row) for row in connection.execute("SELECT * FROM discovery_evidence WHERE project_id=? ORDER BY created_at_utc", (project_id,))]
        events = [dict(row) for row in connection.execute("SELECT * FROM discovery_events WHERE project_id=? ORDER BY occurred_at_utc", (project_id,))]
    for rows in (targets, compounds, rankings, evidence, events):
        for row in rows:
            for key in list(row):
                if key.endswith("_json"):
                    row[key[:-5]] = json.loads(row.pop(key))
    snapshot = {
        "schema_version": "1.0",
        "generated_at_utc": _now(),
        "software_version": __version__,
        "project": project,
        "targets": targets,
        "compounds": compounds,
        "rankings": rankings,
        "evidence": evidence,
        "events": events,
    }
    snapshot["snapshot_sha256"] = _sha(snapshot)
    return snapshot


def export_project_bundle(project_id: str, *, path: str | Path = DEFAULT_PATH) -> bytes:
    snapshot = project_snapshot(project_id, path=path)
    buffer = io.BytesIO()
    files: dict[str, bytes] = {
        "discovery_project.json": json.dumps(snapshot, indent=2, sort_keys=True, default=str).encode("utf-8"),
        "compounds.csv": pd.DataFrame(snapshot["compounds"]).to_csv(index=False).encode("utf-8"),
        "targets.csv": pd.DataFrame(snapshot["targets"]).to_csv(index=False).encode("utf-8"),
        "evidence.csv": pd.DataFrame(snapshot["evidence"]).to_csv(index=False).encode("utf-8"),
        "rankings.csv": pd.DataFrame(snapshot["rankings"]).to_csv(index=False).encode("utf-8"),
    }
    manifest = {
        "project_id": project_id,
        "software_version": __version__,
        "generated_at_utc": _now(),
        "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)} for name, content in files.items()},
    }
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buffer.getvalue()



def register_endpoint_model_card(
    *,
    model_card: dict[str, Any],
    qualification: dict[str, Any],
    path: str | Path = DEFAULT_PATH,
) -> dict[str, Any]:
    model_id = str(model_card.get("model_id", "")).strip()
    endpoint = str(model_card.get("endpoint", "")).strip()
    version = str(model_card.get("version", "")).strip()
    if not model_id or not endpoint or not version:
        raise ValueError("Model ID, endpoint and version are required.")
    status = str(qualification.get("status", "blocked"))
    if status not in {"draft", "blocked", "qualified", "retired"}:
        status = "blocked"
    now = _now()
    with closing(connect(path)) as connection:
        connection.execute(
            """INSERT INTO admet_endpoint_models(
                model_id,endpoint,version,status,model_card_json,artifact_sha256,
                training_dataset_sha256,qualification_json,created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(model_id) DO UPDATE SET
                endpoint=excluded.endpoint,version=excluded.version,status=excluded.status,
                model_card_json=excluded.model_card_json,artifact_sha256=excluded.artifact_sha256,
                training_dataset_sha256=excluded.training_dataset_sha256,
                qualification_json=excluded.qualification_json,updated_at_utc=excluded.updated_at_utc""",
            (
                model_id, endpoint, version, status, _json(model_card),
                str(model_card.get("artifact_sha256", "")),
                str(model_card.get("training_dataset_sha256", "")),
                _json(qualification), now, now,
            ),
        )
        connection.commit()
    return {"model_id": model_id, "endpoint": endpoint, "version": version, "status": status}


def list_endpoint_model_cards(*, path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    with closing(connect(path)) as connection:
        frame = pd.read_sql_query(
            "SELECT * FROM admet_endpoint_models ORDER BY endpoint,updated_at_utc DESC", connection
        )
    if not frame.empty:
        frame["model_card"] = frame["model_card_json"].map(json.loads)
        frame["qualification"] = frame["qualification_json"].map(json.loads)
    return frame

def registry_summary(path: str | Path = DEFAULT_PATH) -> dict[str, int]:
    with closing(connect(path)) as connection:
        return {
            "projects": int(connection.execute("SELECT COUNT(*) FROM discovery_projects").fetchone()[0]),
            "targets": int(connection.execute("SELECT COUNT(*) FROM discovery_targets").fetchone()[0]),
            "compounds": int(connection.execute("SELECT COUNT(*) FROM discovery_compounds").fetchone()[0]),
            "rankings": int(connection.execute("SELECT COUNT(*) FROM discovery_rankings").fetchone()[0]),
            "evidence": int(connection.execute("SELECT COUNT(*) FROM discovery_evidence").fetchone()[0]),
            "endpoint_models": int(connection.execute("SELECT COUNT(*) FROM admet_endpoint_models").fetchone()[0]),
        }
