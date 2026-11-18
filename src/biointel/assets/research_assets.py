from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import mimetypes
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.database.core import (
    connect,
    database_health,
    json_text,
    rows_as_dicts,
    transaction,
    utc_now,
)
from biointel.ui.navigation import PAGE_CATALOG


@dataclass(frozen=True)
class AssetSummary:
    assets: int
    collections: int
    links: int
    tags: int
    notes: int
    favourites: int
    total_bytes: int
    asset_types: dict[str, int]


SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_collections (
    collection_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    accent TEXT NOT NULL DEFAULT 'violet',
    pinned INTEGER NOT NULL DEFAULT 0
        CHECK(pinned IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_collections_category
    ON asset_collections(category);
CREATE INDEX IF NOT EXISTS idx_collections_pinned
    ON asset_collections(pinned);

CREATE TABLE IF NOT EXISTS research_assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    title TEXT NOT NULL,
    path TEXT,
    source TEXT NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_type
    ON research_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_status
    ON research_assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_title
    ON research_assets(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_assets_path
    ON research_assets(path);

CREATE TABLE IF NOT EXISTS collection_assets (
    collection_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at_utc TEXT NOT NULL,
    PRIMARY KEY(collection_id, asset_id),
    FOREIGN KEY(collection_id)
        REFERENCES asset_collections(collection_id)
        ON DELETE CASCADE,
    FOREIGN KEY(asset_id)
        REFERENCES research_assets(asset_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_collection_assets_asset
    ON collection_assets(asset_id);

CREATE TABLE IF NOT EXISTS asset_tags (
    asset_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY(asset_id, tag),
    FOREIGN KEY(asset_id)
        REFERENCES research_assets(asset_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_tags_tag
    ON asset_tags(tag);

CREATE TABLE IF NOT EXISTS asset_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    note TEXT NOT NULL,
    author_label TEXT NOT NULL DEFAULT 'Local researcher',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY(asset_id)
        REFERENCES research_assets(asset_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_notes_asset
    ON asset_notes(asset_id);

CREATE TABLE IF NOT EXISTS asset_favourites (
    asset_id TEXT PRIMARY KEY,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(asset_id)
        REFERENCES research_assets(asset_id)
        ON DELETE CASCADE
);
"""


def initialize_asset_store(
    path: str | Path,
) -> None:
    with transaction(path) as connection:
        connection.executescript(SCHEMA)
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS research_assets_fts
                USING fts5(
                    asset_id UNINDEXED,
                    title,
                    description,
                    source,
                    content='research_assets',
                    content_rowid='rowid'
                )
                """
            )
            connection.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS research_assets_ai
                AFTER INSERT ON research_assets BEGIN
                    INSERT INTO research_assets_fts(
                        rowid, asset_id, title, description, source
                    ) VALUES (
                        new.rowid, new.asset_id, new.title,
                        new.description, new.source
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS research_assets_ad
                AFTER DELETE ON research_assets BEGIN
                    INSERT INTO research_assets_fts(
                        research_assets_fts,
                        rowid, asset_id, title, description, source
                    ) VALUES (
                        'delete', old.rowid, old.asset_id,
                        old.title, old.description, old.source
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS research_assets_au
                AFTER UPDATE ON research_assets BEGIN
                    INSERT INTO research_assets_fts(
                        research_assets_fts,
                        rowid, asset_id, title, description, source
                    ) VALUES (
                        'delete', old.rowid, old.asset_id,
                        old.title, old.description, old.source
                    );
                    INSERT INTO research_assets_fts(
                        rowid, asset_id, title, description, source
                    ) VALUES (
                        new.rowid, new.asset_id, new.title,
                        new.description, new.source
                    );
                END;
                """
            )
        except sqlite3.OperationalError:
            pass


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            hasher.update(chunk)
    return hasher.hexdigest()


def _asset_type(
    path: Path,
) -> str:
    suffix = path.suffix.lower()
    if suffix == ".joblib":
        return "model"
    if suffix in {".csv", ".tsv", ".fasta", ".fa"}:
        return "dataset"
    if suffix in {".json", ".jsonl"}:
        return "metadata"
    if suffix in {".md", ".txt"}:
        return "document"
    if suffix in {".html", ".pdf", ".docx"}:
        return "report"
    if suffix in {".sqlite3", ".db"}:
        return "database"
    if suffix in {".py", ".bat", ".ps1", ".yaml", ".yml", ".toml"}:
        return "source"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        return "image"
    return "file"


def _upsert_asset(
    connection: sqlite3.Connection,
    *,
    asset_id: str,
    asset_type: str,
    title: str,
    source: str,
    path: str | None = None,
    sha256: str | None = None,
    size_bytes: int = 0,
    mime_type: str = "application/octet-stream",
    status: str = "active",
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now()
    connection.execute(
        """
        INSERT INTO research_assets(
            asset_id, asset_type, title, path, source,
            sha256, size_bytes, mime_type, status,
            description, metadata_json,
            created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            asset_type = excluded.asset_type,
            title = excluded.title,
            path = excluded.path,
            source = excluded.source,
            sha256 = excluded.sha256,
            size_bytes = excluded.size_bytes,
            mime_type = excluded.mime_type,
            status = excluded.status,
            description = excluded.description,
            metadata_json = excluded.metadata_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            asset_id,
            asset_type,
            title,
            path,
            source,
            sha256,
            int(size_bytes),
            mime_type,
            status,
            description,
            json_text(metadata or {}),
            now,
            now,
        ),
    )


def _collection_specs() -> list[tuple[str, str, str, str, str, int]]:
    return [
        (
            "COLL-DATA",
            "Data Library",
            "Curated datasets, templates and sequence/compound libraries.",
            "Data",
            "cyan",
            1,
        ),
        (
            "COLL-MODELS",
            "Trusted Models",
            "Versioned model artifacts and model cards.",
            "Modeling",
            "violet",
            1,
        ),
        (
            "COLL-REPORTS",
            "Reports & Evidence",
            "Generated reports, executive summaries and evidence packages.",
            "Evidence",
            "emerald",
            1,
        ),
        (
            "COLL-DATABASES",
            "Database Systems",
            "SQLite registries and professional warehouses.",
            "Data",
            "blue",
            1,
        ),
        (
            "COLL-PROTOCOLS",
            "Protocols & Guides",
            "Operational guides, milestone notes and release instructions.",
            "Knowledge",
            "amber",
            0,
        ),
        (
            "COLL-SOURCE",
            "Source & Automation",
            "Application source, scripts and Windows automation.",
            "Engineering",
            "rose",
            0,
        ),
        (
            "COLL-SEQUENCE",
            "Sequence Research",
            "Sequence libraries, FASTA packs and sequence modules.",
            "Scientific",
            "cyan",
            0,
        ),
        (
            "COLL-CHEMISTRY",
            "Chemistry Research",
            "Molecule libraries, SMILES tools and chemical data.",
            "Scientific",
            "violet",
            0,
        ),
        (
            "COLL-VALIDATION",
            "Validation & Drift",
            "External validation, drift and quality assets.",
            "Validation",
            "emerald",
            0,
        ),
        (
            "COLL-GOVERNANCE",
            "Governance & Release",
            "Project governance, approvals and release readiness.",
            "Governance",
            "amber",
            0,
        ),
        (
            "COLL-UI",
            "Professional UI",
            "Pages, theme system and interface configuration.",
            "Design",
            "rose",
            0,
        ),
        (
            "COLL-FAVOURITES",
            "Executive Favourites",
            "High-value assets pinned for rapid access.",
            "Executive",
            "violet",
            1,
        ),
    ]


def _collection_for_asset(
    asset_type: str,
    relative: str,
) -> str:
    lower = relative.lower()
    if asset_type == "model":
        return "COLL-MODELS"
    if asset_type == "database":
        return "COLL-DATABASES"
    if asset_type == "report":
        return "COLL-REPORTS"
    if asset_type == "dataset":
        if "sequence" in lower or "fasta" in lower:
            return "COLL-SEQUENCE"
        if "molecule" in lower or "smiles" in lower:
            return "COLL-CHEMISTRY"
        if "validation" in lower or "drift" in lower:
            return "COLL-VALIDATION"
        return "COLL-DATA"
    if "governance" in lower or "release" in lower or "audit" in lower:
        return "COLL-GOVERNANCE"
    if "theme" in lower or "/pages/" in f"/{lower}" or lower.startswith("pages/"):
        return "COLL-UI"
    if asset_type == "source":
        return "COLL-SOURCE"
    return "COLL-PROTOCOLS"


def seed_asset_store(
    root: str | Path,
    *,
    replace_demo: bool = True,
) -> AssetSummary:
    project_root = Path(root).resolve()
    database = runtime_database_path(project_root, "assets.sqlite3")
    initialize_asset_store(database)

    ignored_parts = {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".black_cache",
        ".git",
        ".venv",
    }
    files = [
        path
        for path in project_root.rglob("*")
        if path.is_file()
        and not any(part in ignored_parts for part in path.parts)
        and path.resolve() != database.resolve()
        and path.suffix.lower() not in {".pyc", ".tmp", ".lock", ".wal", ".shm"}
        and not path.name.endswith(("-wal", "-shm"))
    ]

    with transaction(database) as connection:
        if replace_demo:
            connection.execute("DELETE FROM asset_notes")
            connection.execute("DELETE FROM asset_tags")
            connection.execute("DELETE FROM asset_favourites")
            connection.execute("DELETE FROM collection_assets")
            connection.execute("DELETE FROM research_assets")
            connection.execute("DELETE FROM asset_collections")

        for spec in _collection_specs():
            now = utc_now()
            connection.execute(
                """
                INSERT INTO asset_collections(
                    collection_id, name, description,
                    category, accent, pinned,
                    created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    category = excluded.category,
                    accent = excluded.accent,
                    pinned = excluded.pinned,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (*spec, now, now),
            )

        asset_ids: list[str] = []
        for position, file_path in enumerate(files):
            relative = file_path.relative_to(project_root).as_posix()
            asset_id = (
                "file:"
                + hashlib.sha1(
                    relative.encode("utf-8"),
                    usedforsecurity=False,
                ).hexdigest()
            )
            asset_type = _asset_type(file_path)
            mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            try:
                size_bytes = file_path.stat().st_size
                digest = None if size_bytes > 32 * 1024 * 1024 else _sha256(file_path)
            except FileNotFoundError:
                # SQLite WAL/SHM and temporary files may disappear during indexing.
                continue
            _upsert_asset(
                connection,
                asset_id=asset_id,
                asset_type=asset_type,
                title=file_path.name,
                path=relative,
                source="BioIntel project file index",
                sha256=digest,
                size_bytes=size_bytes,
                mime_type=mime_type,
                status="available",
                description=(f"Indexed {asset_type} asset from {relative}."),
                metadata={
                    "suffix": file_path.suffix.lower(),
                    "parent": file_path.parent.name,
                    "large_file_hash_deferred": digest is None,
                },
            )
            asset_ids.append(asset_id)
            collection_id = _collection_for_asset(
                asset_type,
                relative,
            )
            connection.execute(
                """
                INSERT INTO collection_assets(
                    collection_id, asset_id, position, added_at_utc
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(collection_id, asset_id) DO UPDATE SET
                    position = excluded.position
                """,
                (
                    collection_id,
                    asset_id,
                    position,
                    utc_now(),
                ),
            )

            tags = {
                asset_type,
                file_path.suffix.lower().lstrip(".") or "no-extension",
                file_path.parent.name.lower(),
            }
            if "data" in file_path.parts:
                tags.add("data")
            if "models" in file_path.parts:
                tags.add("model")
            if "reports" in file_path.parts:
                tags.add("report")
            if "pages" in file_path.parts:
                tags.add("ui")
            for tag in sorted(tags):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO asset_tags(
                        asset_id, tag
                    ) VALUES (?, ?)
                    """,
                    (asset_id, tag),
                )

        for position, page in enumerate(PAGE_CATALOG):
            asset_id = f"module:{page.key}"
            _upsert_asset(
                connection,
                asset_id=asset_id,
                asset_type="module",
                title=page.title,
                path=page.path,
                source="BioIntel UI catalog",
                status="available",
                description=page.description,
                metadata={
                    "icon": page.icon,
                    "category": page.category,
                    "keywords": list(page.keywords),
                    "featured": page.featured,
                },
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_assets(
                    collection_id, asset_id, position, added_at_utc
                ) VALUES ('COLL-UI', ?, ?, ?)
                """,
                (
                    asset_id,
                    position,
                    utc_now(),
                ),
            )
            for tag in {
                "module",
                page.category.lower(),
                *page.keywords,
            }:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO asset_tags(
                        asset_id, tag
                    ) VALUES (?, ?)
                    """,
                    (asset_id, str(tag).lower()),
                )
            asset_ids.append(asset_id)

        molecules = pd.read_csv(
            project_root / "data" / "coverage" / "molecule_analysis_library_1000.csv",
            nrows=100,
        )
        for position, row in enumerate(molecules.itertuples(index=False)):
            asset_id = f"bookmark:compound:{row.drug_id}"
            _upsert_asset(
                connection,
                asset_id=asset_id,
                asset_type="bookmark",
                title=f"Compound {row.drug_id}",
                source="BioIntel molecule coverage library",
                status="bookmarked",
                description=(
                    f"SMILES bookmark · MW {float(row.molecular_weight):.2f} · "
                    f"LogP {float(row.logp):.2f}."
                ),
                metadata={
                    "canonical_smiles": row.canonical_smiles,
                    "molecular_weight": row.molecular_weight,
                    "logp": row.logp,
                    "tpsa": row.tpsa,
                },
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_assets(
                    collection_id, asset_id, position, added_at_utc
                ) VALUES ('COLL-CHEMISTRY', ?, ?, ?)
                """,
                (asset_id, position, utc_now()),
            )
            for tag in ("bookmark", "compound", "smiles"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO asset_tags(
                        asset_id, tag
                    ) VALUES (?, ?)
                    """,
                    (asset_id, tag),
                )
            asset_ids.append(asset_id)

        targets = pd.read_csv(
            project_root / "data" / "libraries" / "protein_library_160.csv",
        )
        for position, row in enumerate(targets.itertuples(index=False)):
            asset_id = f"bookmark:target:{row.target_id}"
            _upsert_asset(
                connection,
                asset_id=asset_id,
                asset_type="bookmark",
                title=f"Target {row.target_id}",
                source="BioIntel 5X protein library",
                status="bookmarked",
                description=(
                    f"{row.target_family} target · " f"{int(row.sequence_length):,} amino acids."
                ),
                metadata={
                    "target_family": row.target_family,
                    "sequence_length": row.sequence_length,
                    "sequence_preview": str(row.protein_sequence)[:80],
                },
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_assets(
                    collection_id, asset_id, position, added_at_utc
                ) VALUES ('COLL-SEQUENCE', ?, ?, ?)
                """,
                (asset_id, position, utc_now()),
            )
            for tag in (
                "bookmark",
                "target",
                str(row.target_family).lower(),
            ):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO asset_tags(
                        asset_id, tag
                    ) VALUES (?, ?)
                    """,
                    (asset_id, tag),
                )
            asset_ids.append(asset_id)

        note_assets = asset_ids[: min(500, len(asset_ids))]
        for index, asset_id in enumerate(note_assets):
            now = utc_now()
            connection.execute(
                """
                INSERT INTO asset_notes(
                    asset_id, note, author_label,
                    created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    (
                        "Professional Step 21 index note. Confirm provenance, "
                        "scientific scope and release suitability before use."
                    ),
                    ("Data steward" if index % 2 == 0 else "Research reviewer"),
                    now,
                    now,
                ),
            )

        favourite_ids = [
            asset_id
            for asset_id in asset_ids
            if (asset_id.startswith("module:") or "model" in asset_id or "report" in asset_id)
        ][:40]
        for position, asset_id in enumerate(favourite_ids):
            connection.execute(
                """
                INSERT OR IGNORE INTO asset_favourites(
                    asset_id, created_at_utc
                ) VALUES (?, ?)
                """,
                (asset_id, utc_now()),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_assets(
                    collection_id, asset_id, position, added_at_utc
                ) VALUES ('COLL-FAVOURITES', ?, ?, ?)
                """,
                (
                    asset_id,
                    position,
                    utc_now(),
                ),
            )

        try:
            connection.execute(
                """
                INSERT INTO research_assets_fts(
                    research_assets_fts
                ) VALUES ('rebuild')
                """
            )
        except sqlite3.OperationalError:
            pass

    return asset_summary(database)


def asset_summary(
    path: str | Path,
) -> AssetSummary:
    initialize_asset_store(path)
    with connect(path, read_only=True) as connection:
        counts = {
            "assets": int(connection.execute("SELECT COUNT(*) FROM research_assets").fetchone()[0]),
            "collections": int(
                connection.execute("SELECT COUNT(*) FROM asset_collections").fetchone()[0]
            ),
            "links": int(
                connection.execute("SELECT COUNT(*) FROM collection_assets").fetchone()[0]
            ),
            "tags": int(connection.execute("SELECT COUNT(*) FROM asset_tags").fetchone()[0]),
            "notes": int(connection.execute("SELECT COUNT(*) FROM asset_notes").fetchone()[0]),
            "favourites": int(
                connection.execute("SELECT COUNT(*) FROM asset_favourites").fetchone()[0]
            ),
            "total_bytes": int(
                connection.execute(
                    "SELECT COALESCE(SUM(size_bytes), 0) FROM research_assets"
                ).fetchone()[0]
            ),
        }
        asset_types = {
            str(row["asset_type"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT asset_type, COUNT(*) AS count
                FROM research_assets
                GROUP BY asset_type
                ORDER BY count DESC
                """
            )
        }
    return AssetSummary(
        assets=counts["assets"],
        collections=counts["collections"],
        links=counts["links"],
        tags=counts["tags"],
        notes=counts["notes"],
        favourites=counts["favourites"],
        total_bytes=counts["total_bytes"],
        asset_types=asset_types,
    )


def search_assets(
    path: str | Path,
    query: str = "",
    *,
    asset_type: str = "all",
    collection_id: str = "all",
    favourites_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    initialize_asset_store(path)
    safe_limit = min(max(int(limit), 1), 1000)
    filters: list[str] = []
    parameters: list[object] = []

    if asset_type != "all":
        filters.append("a.asset_type = ?")
        parameters.append(asset_type)
    if collection_id != "all":
        filters.append(
            """
            EXISTS(
                SELECT 1
                FROM collection_assets ca
                WHERE ca.asset_id = a.asset_id
                  AND ca.collection_id = ?
            )
            """
        )
        parameters.append(collection_id)
    if favourites_only:
        filters.append(
            """
            EXISTS(
                SELECT 1
                FROM asset_favourites f
                WHERE f.asset_id = a.asset_id
            )
            """
        )

    where = " AND " + " AND ".join(filters) if filters else ""

    with connect(path, read_only=True) as connection:
        if query.strip():
            try:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.*,
                        EXISTS(
                            SELECT 1 FROM asset_favourites f
                            WHERE f.asset_id = a.asset_id
                        ) AS is_favourite,
                        bm25(research_assets_fts) AS relevance
                    FROM research_assets_fts
                    JOIN research_assets a
                      ON a.rowid = research_assets_fts.rowid
                    WHERE research_assets_fts MATCH ?
                    {where}
                    ORDER BY relevance, a.title
                    LIMIT ?
                    """,
                    [
                        query.strip(),
                        *parameters,
                        safe_limit,
                    ],
                ).fetchall()
                return rows_as_dicts(rows)
            except sqlite3.OperationalError:
                pass

            like = f"%{query.strip()}%"
            filters.insert(
                0,
                """
                (
                    a.title LIKE ? COLLATE NOCASE
                    OR a.description LIKE ? COLLATE NOCASE
                    OR a.source LIKE ? COLLATE NOCASE
                    OR a.path LIKE ? COLLATE NOCASE
                )
                """,
            )
            parameters = [
                like,
                like,
                like,
                like,
                *parameters,
            ]
            where = "WHERE " + " AND ".join(filters)
        else:
            where = "WHERE " + " AND ".join(filters) if filters else ""

        rows = connection.execute(
            f"""
            SELECT
                a.*,
                EXISTS(
                    SELECT 1 FROM asset_favourites f
                    WHERE f.asset_id = a.asset_id
                ) AS is_favourite,
                0.0 AS relevance
            FROM research_assets a
            {where}
            ORDER BY is_favourite DESC, a.title
            LIMIT ?
            """,
            [*parameters, safe_limit],
        ).fetchall()
    return rows_as_dicts(rows)


def list_collections(
    path: str | Path,
) -> list[dict[str, Any]]:
    initialize_asset_store(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT
                c.*,
                COUNT(ca.asset_id) AS asset_count,
                COALESCE(SUM(a.size_bytes), 0) AS total_bytes
            FROM asset_collections c
            LEFT JOIN collection_assets ca
              ON ca.collection_id = c.collection_id
            LEFT JOIN research_assets a
              ON a.asset_id = ca.asset_id
            GROUP BY c.collection_id
            ORDER BY c.pinned DESC, c.name
            """
        ).fetchall()
    return rows_as_dicts(rows)


def asset_notes(
    path: str | Path,
    asset_id: str,
) -> list[dict[str, Any]]:
    initialize_asset_store(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM asset_notes
            WHERE asset_id = ?
            ORDER BY created_at_utc DESC
            """,
            (asset_id,),
        ).fetchall()
    return rows_as_dicts(rows)


def toggle_favourite(
    path: str | Path,
    asset_id: str,
) -> bool:
    initialize_asset_store(path)
    with transaction(path) as connection:
        exists = connection.execute(
            """
            SELECT 1
            FROM asset_favourites
            WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        if exists:
            connection.execute(
                """
                DELETE FROM asset_favourites
                WHERE asset_id = ?
                """,
                (asset_id,),
            )
            return False
        connection.execute(
            """
            INSERT INTO asset_favourites(
                asset_id, created_at_utc
            ) VALUES (?, ?)
            """,
            (asset_id, utc_now()),
        )
        return True


def asset_health(
    path: str | Path,
    summary=None,
) -> dict[str, object]:
    summary = summary or asset_summary(path)
    health = database_health(
        path,
        name="Research Assets & Collections",
    )
    populated = summary.assets > 0 and summary.collections > 0
    return {
        "database": asdict(health),
        "summary": asdict(summary),
        "populated": populated,
        "healthy": (health.exists and health.integrity == "ok" and health.table_count >= 6),
    }


def get_asset(
    path: str | Path,
    asset_id: str,
) -> dict[str, Any]:
    initialize_asset_store(path)
    with connect(path, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                a.*,
                EXISTS(
                    SELECT 1 FROM asset_favourites f
                    WHERE f.asset_id = a.asset_id
                ) AS is_favourite
            FROM research_assets a
            WHERE a.asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown asset: {asset_id}")
        tags = [
            str(item["tag"])
            for item in connection.execute(
                """
                SELECT tag
                FROM asset_tags
                WHERE asset_id = ?
                ORDER BY tag
                """,
                (asset_id,),
            )
        ]
        collections = rows_as_dicts(
            connection.execute(
                """
                SELECT c.collection_id, c.name, c.category
                FROM asset_collections c
                JOIN collection_assets ca
                  ON ca.collection_id = c.collection_id
                WHERE ca.asset_id = ?
                ORDER BY c.pinned DESC, c.name
                """,
                (asset_id,),
            ).fetchall()
        )
    payload = dict(row)
    payload["tags"] = tags
    payload["collections"] = collections
    return payload


def add_asset_note(
    path: str | Path,
    asset_id: str,
    note: str,
    *,
    author_label: str = "Local researcher",
) -> dict[str, Any]:
    cleaned = note.strip()
    if not cleaned:
        raise ValueError("Note cannot be empty.")
    initialize_asset_store(path)
    now = utc_now()
    with transaction(path) as connection:
        exists = connection.execute(
            """
            SELECT 1
            FROM research_assets
            WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        if not exists:
            raise KeyError(f"Unknown asset: {asset_id}")
        cursor = connection.execute(
            """
            INSERT INTO asset_notes(
                asset_id, note, author_label,
                created_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                cleaned,
                author_label.strip() or "Local researcher",
                now,
                now,
            ),
        )
        note_id = int(cursor.lastrowid)
    return {
        "note_id": note_id,
        "asset_id": asset_id,
        "note": cleaned,
        "author_label": author_label.strip() or "Local researcher",
        "created_at_utc": now,
    }
