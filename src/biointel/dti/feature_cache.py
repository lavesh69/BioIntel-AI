from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from biointel.dti.drug_features import DrugFeatureSet
from biointel.dti.protein_features import ProteinFeatureSet


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _payload(values: np.ndarray, names: tuple[str, ...], metadata: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        values=np.asarray(values, dtype=np.float32),
        names=np.asarray(names, dtype=object),
        metadata=np.asarray([json.dumps(metadata, sort_keys=True)], dtype=object),
    )
    return buffer.getvalue()


def _restore(payload: bytes) -> tuple[np.ndarray, tuple[str, ...], dict[str, Any]]:
    with np.load(io.BytesIO(payload), allow_pickle=True) as data:
        values = np.asarray(data["values"], dtype=np.float32)
        names = tuple(str(item) for item in data["names"].tolist())
        metadata = json.loads(str(data["metadata"].tolist()[0]))
    return values, names, metadata


def cache_key(kind: str, value: str, settings: dict[str, Any]) -> str:
    stable = json.dumps(
        {"kind": kind, "value": value, "settings": settings},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeatureCacheStats:
    entries: int
    drug_entries: int
    protein_entries: int
    total_bytes: int
    total_hits: int
    database_path: str


class FeatureCache:
    """Persistent SQLite feature cache safe for local multi-threaded use."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_cache(
                    cache_key TEXT PRIMARY KEY,
                    feature_kind TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    payload_bytes INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    last_accessed_at_utc TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_feature_cache_kind_access "
                "ON feature_cache(feature_kind, last_accessed_at_utc)"
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(feature_cache)")}
            additions = {
                "schema_version": "TEXT NOT NULL DEFAULT 'legacy-v1'",
                "library_version": "TEXT NOT NULL DEFAULT 'bundled-runtime'",
                "parameters_json": "TEXT NOT NULL DEFAULT '{}'",
                "entity_id": "TEXT",
                "source_dataset_sha256": "TEXT",
                "validation_status": "TEXT NOT NULL DEFAULT 'valid'",
                "error_message": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE feature_cache ADD COLUMN {name} {definition}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_feature_cache_schema "
                "ON feature_cache(feature_kind, schema_version, validation_status)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_cache_profiles(
                    profile_key TEXT PRIMARY KEY,
                    feature_kind TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    library_name TEXT NOT NULL,
                    library_version TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    entry_count INTEGER NOT NULL DEFAULT 0,
                    valid_count INTEGER NOT NULL DEFAULT 0,
                    invalid_count INTEGER NOT NULL DEFAULT 0,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )

    def _get(self, key: str) -> tuple[np.ndarray, tuple[str, ...], dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM feature_cache WHERE cache_key=?", (key,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE feature_cache SET hit_count=hit_count+1, last_accessed_at_utc=? "
                "WHERE cache_key=?",
                (_utc_now(), key),
            )
        return _restore(row[0])

    def _put(
        self,
        key: str,
        feature_kind: str,
        values: np.ndarray,
        names: tuple[str, ...],
        metadata: dict[str, Any],
    ) -> None:
        payload = _payload(values, names, metadata)
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feature_cache(
                    cache_key, feature_kind, payload, payload_bytes,
                    created_at_utc, last_accessed_at_utc, hit_count,
                    schema_version, library_version, parameters_json, entity_id,
                    validation_status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'valid', NULL)
                ON CONFLICT(cache_key) DO UPDATE SET
                    feature_kind=excluded.feature_kind,
                    payload=excluded.payload,
                    payload_bytes=excluded.payload_bytes,
                    last_accessed_at_utc=excluded.last_accessed_at_utc,
                    schema_version=excluded.schema_version,
                    library_version=excluded.library_version,
                    parameters_json=excluded.parameters_json,
                    entity_id=excluded.entity_id,
                    validation_status='valid',
                    error_message=NULL
                """,
                (
                    key, feature_kind, payload, len(payload), now, now,
                    "drug-descriptors-morgan-v2" if feature_kind == "drug" else "protein-composition-protparam-v2",
                    "RDKit" if feature_kind == "drug" else "Biopython",
                    json.dumps({k: v for k, v in metadata.items() if k not in {"canonical_smiles", "sequence_length"}}, sort_keys=True),
                    str(metadata.get("canonical_smiles") or f"{feature_kind}:{key[:20]}"),
                ),
            )

    def get_drug(
        self,
        smiles: str,
        *,
        radius: int,
        n_bits: int,
        use_chirality: bool,
    ) -> DrugFeatureSet | None:
        settings = {"radius": radius, "n_bits": n_bits, "use_chirality": use_chirality}
        restored = self._get(cache_key("drug", smiles, settings))
        if restored is None:
            return None
        values, names, metadata = restored
        return DrugFeatureSet(
            values=values,
            names=names,
            canonical_smiles=str(metadata["canonical_smiles"]),
            radius=int(metadata["radius"]),
            n_bits=int(metadata["n_bits"]),
            use_chirality=bool(metadata["use_chirality"]),
        )

    def put_drug(self, input_smiles: str, feature: DrugFeatureSet) -> None:
        settings = {
            "radius": feature.radius,
            "n_bits": feature.n_bits,
            "use_chirality": feature.use_chirality,
        }
        self._put(
            cache_key("drug", input_smiles, settings),
            "drug",
            feature.values,
            feature.names,
            {
                "canonical_smiles": feature.canonical_smiles,
                **settings,
            },
        )

    def get_protein(
        self,
        sequence: str,
        *,
        include_dipeptides: bool,
    ) -> ProteinFeatureSet | None:
        settings = {"include_dipeptides": include_dipeptides}
        restored = self._get(cache_key("protein", sequence, settings))
        if restored is None:
            return None
        values, names, metadata = restored
        return ProteinFeatureSet(
            values=values,
            names=names,
            sequence_length=int(metadata["sequence_length"]),
            include_dipeptides=bool(metadata["include_dipeptides"]),
        )

    def put_protein(self, sequence: str, feature: ProteinFeatureSet) -> None:
        settings = {"include_dipeptides": feature.include_dipeptides}
        self._put(
            cache_key("protein", sequence, settings),
            "protein",
            feature.values,
            feature.names,
            {
                "sequence_length": feature.sequence_length,
                **settings,
            },
        )

    def stats(self) -> FeatureCacheStats:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN feature_kind='drug' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN feature_kind='protein' THEN 1 ELSE 0 END),
                       COALESCE(SUM(payload_bytes), 0),
                       COALESCE(SUM(hit_count), 0)
                FROM feature_cache
                """
            ).fetchone()
        return FeatureCacheStats(
            entries=int(row[0] or 0),
            drug_entries=int(row[1] or 0),
            protein_entries=int(row[2] or 0),
            total_bytes=int(row[3] or 0),
            total_hits=int(row[4] or 0),
            database_path=str(self.path),
        )

    def prune(self, *, older_than_days: int = 90, max_entries: int = 100_000) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, older_than_days))).isoformat(
            timespec="seconds"
        )
        removed = 0
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM feature_cache WHERE last_accessed_at_utc < ?", (cutoff,)
            )
            removed += max(cursor.rowcount, 0)
            count = int(connection.execute("SELECT COUNT(*) FROM feature_cache").fetchone()[0])
            overflow = max(0, count - max_entries)
            if overflow:
                keys = connection.execute(
                    "SELECT cache_key FROM feature_cache "
                    "ORDER BY last_accessed_at_utc ASC LIMIT ?",
                    (overflow,),
                ).fetchall()
                connection.executemany("DELETE FROM feature_cache WHERE cache_key=?", keys)
                removed += len(keys)
            connection.execute("PRAGMA optimize")
        return removed
