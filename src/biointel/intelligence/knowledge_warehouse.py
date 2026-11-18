from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.data.dataset_registry import list_datasets
from biointel.database.core import (
    connect,
    database_health,
    json_text,
    rows_as_dicts,
    transaction,
    utc_now,
)
from biointel.portfolio.project_registry import list_projects
from biointel.training.model_artifact import (
    load_model_artifact_cached,
)
from biointel.training.model_catalog import sync_model_catalog
from biointel.ui.navigation import PAGE_CATALOG


@dataclass(frozen=True)
class KnowledgeSummary:
    entities: int
    relations: int
    protocols: int
    saved_queries: int
    entity_types: dict[str, int]
    statuses: dict[str, int]


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    external_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    confidence REAL NOT NULL DEFAULT 1.0
        CHECK(confidence >= 0.0 AND confidence <= 1.0),
    tags TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entities_type
    ON knowledge_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_status
    ON knowledge_entities(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_source
    ON knowledge_entities(source);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_name
    ON knowledge_entities(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_external
    ON knowledge_entities(external_id);

CREATE TABLE IF NOT EXISTS knowledge_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 1.0,
    evidence TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(source_entity_id, target_entity_id, relation_type),
    FOREIGN KEY(source_entity_id)
        REFERENCES knowledge_entities(entity_id)
        ON DELETE CASCADE,
    FOREIGN KEY(target_entity_id)
        REFERENCES knowledge_entities(entity_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_rel_source
    ON knowledge_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_rel_target
    ON knowledge_relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_rel_type
    ON knowledge_relations(relation_type);

CREATE TABLE IF NOT EXISTS knowledge_protocols (
    protocol_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    objective TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '1.0',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_protocol_category
    ON knowledge_protocols(category);
CREATE INDEX IF NOT EXISTS idx_protocol_risk
    ON knowledge_protocols(risk_level);

CREATE TABLE IF NOT EXISTS knowledge_saved_queries (
    query_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    query_text TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'all',
    pinned INTEGER NOT NULL DEFAULT 0
        CHECK(pinned IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_query_pinned
    ON knowledge_saved_queries(pinned);
"""


def initialize_knowledge_warehouse(
    path: str | Path,
) -> None:
    with transaction(path) as connection:
        connection.executescript(SCHEMA)
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_entities_fts
                USING fts5(
                    entity_id UNINDEXED,
                    name,
                    summary,
                    tags,
                    content='knowledge_entities',
                    content_rowid='rowid'
                )
                """
            )
            connection.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS knowledge_entities_ai
                AFTER INSERT ON knowledge_entities BEGIN
                    INSERT INTO knowledge_entities_fts(
                        rowid, entity_id, name, summary, tags
                    ) VALUES (
                        new.rowid, new.entity_id, new.name,
                        new.summary, new.tags
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS knowledge_entities_ad
                AFTER DELETE ON knowledge_entities BEGIN
                    INSERT INTO knowledge_entities_fts(
                        knowledge_entities_fts,
                        rowid,
                        entity_id,
                        name,
                        summary,
                        tags
                    ) VALUES (
                        'delete', old.rowid, old.entity_id,
                        old.name, old.summary, old.tags
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS knowledge_entities_au
                AFTER UPDATE ON knowledge_entities BEGIN
                    INSERT INTO knowledge_entities_fts(
                        knowledge_entities_fts,
                        rowid,
                        entity_id,
                        name,
                        summary,
                        tags
                    ) VALUES (
                        'delete', old.rowid, old.entity_id,
                        old.name, old.summary, old.tags
                    );
                    INSERT INTO knowledge_entities_fts(
                        rowid, entity_id, name, summary, tags
                    ) VALUES (
                        new.rowid, new.entity_id, new.name,
                        new.summary, new.tags
                    );
                END;
                """
            )
        except sqlite3.OperationalError:
            # Some minimal SQLite builds omit FTS5. LIKE search remains active.
            pass


def _upsert_entity(
    connection: sqlite3.Connection,
    *,
    entity_id: str,
    entity_type: str,
    name: str,
    summary: str,
    source: str,
    external_id: str | None = None,
    status: str = "active",
    confidence: float = 1.0,
    tags: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now()
    connection.execute(
        """
        INSERT INTO knowledge_entities(
            entity_id, entity_type, name, summary, source,
            external_id, status, confidence, tags,
            metadata_json, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            entity_type = excluded.entity_type,
            name = excluded.name,
            summary = excluded.summary,
            source = excluded.source,
            external_id = excluded.external_id,
            status = excluded.status,
            confidence = excluded.confidence,
            tags = excluded.tags,
            metadata_json = excluded.metadata_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            entity_id,
            entity_type,
            name,
            summary,
            source,
            external_id,
            status,
            float(confidence),
            tags,
            json_text(metadata or {}),
            now,
            now,
        ),
    )


def _upsert_relation(
    connection: sqlite3.Connection,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    score: float = 1.0,
    evidence: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO knowledge_relations(
            source_entity_id, target_entity_id, relation_type,
            score, evidence, metadata_json, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            source_entity_id,
            target_entity_id,
            relation_type
        ) DO UPDATE SET
            score = excluded.score,
            evidence = excluded.evidence,
            metadata_json = excluded.metadata_json
        """,
        (
            source_entity_id,
            target_entity_id,
            relation_type,
            float(score),
            evidence,
            json_text(metadata or {}),
            utc_now(),
        ),
    )


def _protocol_rows() -> list[dict[str, object]]:
    categories = {
        "Data": (
            "Dataset intake and provenance",
            "Validate source, schema, identifiers and licensing metadata.",
            [
                "Record source and acquisition date",
                "Validate required columns",
                "Run duplicate/conflict checks",
                "Register dataset hash",
                "Document limitations",
            ],
        ),
        "Sequence": (
            "Sequence quality characterisation",
            "Characterise DNA, RNA or protein inputs before analysis.",
            [
                "Parse FASTA records",
                "Detect sequence type",
                "Validate symbols",
                "Calculate composition statistics",
                "Record quality findings",
            ],
        ),
        "Chemistry": (
            "Molecule standardisation",
            "Prepare molecular structures for descriptor and ML workflows.",
            [
                "Parse SMILES",
                "Canonicalise structure",
                "Calculate descriptors",
                "Flag unsupported chemistry",
                "Record structure provenance",
            ],
        ),
        "Modeling": (
            "Leakage-resistant model training",
            "Train and compare models using grouped held-out evaluation.",
            [
                "Freeze dataset version",
                "Select drug/target/scaffold split",
                "Fit candidate models",
                "Evaluate validation and test sets",
                "Register artifact and model card",
            ],
        ),
        "Validation": (
            "Independent external validation",
            "Evaluate a frozen model against independent labelled data.",
            [
                "Verify dataset independence",
                "Load trusted frozen artifact",
                "Generate predictions",
                "Calculate held-out metrics",
                "Review drift and applicability",
            ],
        ),
        "Governance": (
            "Research release readiness",
            "Verify evidence, decisions, gates and reproducibility before release.",
            [
                "Review milestones",
                "Review decisions",
                "Verify approval gates",
                "Build evidence package",
                "Record release disposition",
            ],
        ),
    }
    risk_cycle = ("Low", "Medium", "High")
    rows: list[dict[str, object]] = []
    counter = 1
    for category, (base_name, objective, steps) in categories.items():
        for variant in range(1, 7):
            rows.append(
                {
                    "protocol_id": f"PROT-{counter:03d}",
                    "name": f"{base_name} · Level {variant}",
                    "category": category,
                    "objective": objective,
                    "steps": [f"{step} — control {variant}" for step in steps],
                    "acceptance": (
                        "All required evidence is present, checks pass, "
                        "exceptions are documented and a reviewer decision exists."
                    ),
                    "risk": risk_cycle[(variant - 1) % len(risk_cycle)],
                    "tags": f"{category.lower()},professional,step21,level-{variant}",
                }
            )
            counter += 1
    return rows


def seed_knowledge_warehouse(
    root: str | Path,
    *,
    replace_demo: bool = True,
) -> KnowledgeSummary:
    project_root = Path(root).resolve()
    database = runtime_database_path(project_root, "knowledge.sqlite3")
    initialize_knowledge_warehouse(database)

    molecules = pd.read_csv(
        project_root / "data" / "coverage" / "molecule_analysis_library_1000.csv"
    )
    named_compounds_path = (
        project_root / "data" / "chemistry" / "common_compound_directory_5000.csv"
    )
    named_compounds = (
        pd.read_csv(named_compounds_path) if named_compounds_path.is_file() else pd.DataFrame()
    )
    sequences = pd.read_csv(project_root / "data" / "coverage" / "sequence_library_800.csv")
    interactions = pd.read_csv(
        project_root / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv",
        nrows=2500,
        usecols=[
            "drug_id",
            "canonical_smiles",
            "target_id",
            "target_family",
            "label",
            "p_activity",
        ],
    )
    lookups = pd.read_csv(project_root / "data" / "coverage" / "external_lookup_starters_20.csv")
    datasets = list_datasets(
        runtime_database_path(project_root, "datasets.sqlite3"),
        limit=5000,
    )
    projects = list_projects(runtime_database_path(project_root, "projects.sqlite3"))
    models = sync_model_catalog(project_root / "models")

    with transaction(database) as connection:
        if replace_demo:
            connection.execute("DELETE FROM knowledge_relations")
            connection.execute("DELETE FROM knowledge_entities")
            connection.execute("DELETE FROM knowledge_protocols")
            connection.execute("DELETE FROM knowledge_saved_queries")

        for row in molecules.itertuples(index=False):
            _upsert_entity(
                connection,
                entity_id=f"compound:{row.drug_id}",
                entity_type="compound",
                name=str(row.drug_id),
                summary=(
                    f"RDKit-valid molecule with molecular weight "
                    f"{float(row.molecular_weight):.2f}, LogP "
                    f"{float(row.logp):.2f} and TPSA {float(row.tpsa):.2f}."
                ),
                source="BioIntel molecule coverage library",
                external_id=str(row.drug_id),
                confidence=0.95,
                tags="compound,smiles,descriptor,synthetic-demo",
                metadata={
                    "canonical_smiles": row.canonical_smiles,
                    "molecular_weight": row.molecular_weight,
                    "logp": row.logp,
                    "tpsa": row.tpsa,
                    "ring_count": row.ring_count,
                },
            )

        canonical_to_compound = {
            str(row.canonical_smiles): f"compound:{row.drug_id}"
            for row in molecules.itertuples(index=False)
        }
        for row in named_compounds.itertuples(index=False):
            entity_id = f"named_compound:{row.compound_key}"
            _upsert_entity(
                connection,
                entity_id=entity_id,
                entity_type="named_compound",
                name=str(row.common_name),
                summary=(
                    f"{str(row.name_type).replace('_', ' ')} with formula "
                    f"{row.molecular_formula}, molecular weight "
                    f"{float(row.molecular_weight):.2f} and source {row.source}."
                ),
                source=str(row.source),
                external_id=str(row.source_identifier),
                status="reference",
                confidence=(0.98 if row.name_type == "curated_common_name" else 0.82),
                tags=("compound-name,smiles," f"{row.name_type},{row.chemistry_category}"),
                metadata={
                    "aliases": row.aliases,
                    "canonical_smiles": row.canonical_smiles,
                    "molecular_formula": row.molecular_formula,
                    "molecular_weight": row.molecular_weight,
                    "logp": row.logp,
                    "tpsa": row.tpsa,
                    "lipinski_violations": row.lipinski_violations,
                    "chemistry_category": row.chemistry_category,
                    "name_type": row.name_type,
                },
            )
            matching = canonical_to_compound.get(str(row.canonical_smiles))
            if matching:
                _upsert_relation(
                    connection,
                    source_entity_id=entity_id,
                    target_entity_id=matching,
                    relation_type="same_canonical_structure",
                    score=1.0,
                    evidence="Canonical SMILES identity",
                )

        for row in sequences.itertuples(index=False):
            _upsert_entity(
                connection,
                entity_id=f"sequence:{row.record_id}",
                entity_type=str(row.sequence_type).lower(),
                name=str(row.record_id),
                summary=(
                    f"{row.sequence_type} sequence from the {row.family} "
                    f"coverage family; length {int(row.length):,}."
                ),
                source="BioIntel sequence coverage library",
                external_id=str(row.record_id),
                confidence=0.95,
                tags=(f"sequence,{str(row.sequence_type).lower()}," f"{row.family},synthetic-demo"),
                metadata={
                    "family": row.family,
                    "length": int(row.length),
                    "sequence_preview": str(row.sequence)[:80],
                },
            )

        target_rows = (
            interactions[["target_id", "target_family"]].drop_duplicates().itertuples(index=False)
        )
        for row in target_rows:
            _upsert_entity(
                connection,
                entity_id=f"target:{row.target_id}",
                entity_type="target",
                name=str(row.target_id),
                summary=(
                    f"Synthetic target from the {row.target_family} family "
                    "used in grouped DTI software benchmarks."
                ),
                source="BioIntel 5X DTI pack",
                external_id=str(row.target_id),
                confidence=0.90,
                tags=(f"target,{str(row.target_family).lower()}," "dti,synthetic-demo"),
                metadata={"target_family": row.target_family},
            )

        for index, row in enumerate(
            interactions.itertuples(index=False),
            start=1,
        ):
            entity_id = f"interaction:5x:{index:05d}"
            _upsert_entity(
                connection,
                entity_id=entity_id,
                entity_type="interaction_candidate",
                name=(f"{row.drug_id} ↔ {row.target_id}"),
                summary=(
                    f"Deterministic benchmark interaction candidate with "
                    f"label {int(row.label)} and p_activity "
                    f"{float(row.p_activity):.4f}."
                ),
                source="BioIntel 5X DTI pack",
                status="benchmark",
                confidence=0.70,
                tags=(f"dti,interaction,{str(row.target_family).lower()}," "synthetic-demo"),
                metadata={
                    "drug_id": row.drug_id,
                    "target_id": row.target_id,
                    "canonical_smiles": row.canonical_smiles,
                    "target_family": row.target_family,
                    "label": int(row.label),
                    "p_activity": float(row.p_activity),
                },
            )
            compound_id = f"compound:{row.drug_id}"
            target_id = f"target:{row.target_id}"
            _upsert_relation(
                connection,
                source_entity_id=entity_id,
                target_entity_id=compound_id,
                relation_type="involves_compound",
                score=1.0,
                evidence="5X deterministic software benchmark",
            )
            _upsert_relation(
                connection,
                source_entity_id=entity_id,
                target_entity_id=target_id,
                relation_type="involves_target",
                score=1.0,
                evidence="5X deterministic software benchmark",
            )
            _upsert_relation(
                connection,
                source_entity_id=compound_id,
                target_entity_id=target_id,
                relation_type="benchmark_association",
                score=float(row.p_activity),
                evidence=("Synthetic benchmark association; not experimental evidence."),
                metadata={"label": int(row.label)},
            )

        for record in datasets:
            _upsert_entity(
                connection,
                entity_id=f"dataset:{record.dataset_sha256}",
                entity_type="dataset",
                name=(f"{record.dataset_name} · {record.dataset_version}"),
                summary=(
                    f"{record.task_type} dataset with {record.row_count:,} rows "
                    f"and SHA-256 {record.dataset_sha256[:12]}…"
                ),
                source=record.source_description,
                external_id=record.dataset_sha256,
                status="registered",
                confidence=1.0,
                tags=(f"dataset,{record.task_type},registered,lineage"),
                metadata=asdict(record),
            )
            if record.parent_sha256:
                parent_id = f"dataset:{record.parent_sha256}"
                if connection.execute(
                    """
                    SELECT 1 FROM knowledge_entities
                    WHERE entity_id = ?
                    """,
                    (parent_id,),
                ).fetchone():
                    _upsert_relation(
                        connection,
                        source_entity_id=f"dataset:{record.dataset_sha256}",
                        target_entity_id=parent_id,
                        relation_type="derived_from",
                        score=1.0,
                        evidence="Dataset registry lineage",
                    )

        for entry in models:
            model_path = project_root / "models" / entry.filename
            try:
                artifact = load_model_artifact_cached(
                    model_path,
                    trusted_root=project_root / "models",
                )
                metadata = artifact.metadata
                summary = (
                    f"{metadata.task_type} {metadata.model_name} model trained "
                    f"on {metadata.train_rows:,} rows; lifecycle {entry.state}."
                )
                extra = {
                    "catalog": asdict(entry),
                    "metadata": asdict(metadata),
                }
                dataset_id = f"dataset:{metadata.dataset_sha256}"
            except Exception as exc:
                summary = f"Trusted model artifact; metadata load error: {exc}"
                extra = {"catalog": asdict(entry)}
                dataset_id = ""
            model_id = f"model:{entry.filename}"
            _upsert_entity(
                connection,
                entity_id=model_id,
                entity_type="model",
                name=entry.filename,
                summary=summary,
                source="BioIntel trusted model catalog",
                external_id=entry.filename,
                status=entry.state,
                confidence=1.0,
                tags=(f"model,{entry.state}," f"{'default' if entry.is_default else 'candidate'}"),
                metadata=extra,
            )
            if (
                dataset_id
                and connection.execute(
                    """
                SELECT 1 FROM knowledge_entities
                WHERE entity_id = ?
                """,
                    (dataset_id,),
                ).fetchone()
            ):
                _upsert_relation(
                    connection,
                    source_entity_id=model_id,
                    target_entity_id=dataset_id,
                    relation_type="trained_on",
                    score=1.0,
                    evidence="Trusted model artifact metadata",
                )

        for project in projects:
            project_id = f"project:{project.project_id}"
            _upsert_entity(
                connection,
                entity_id=project_id,
                entity_type="project",
                name=f"{project.project_code} · {project.name}",
                summary=project.objective,
                source="BioIntel project portfolio",
                external_id=project.project_code,
                status=project.status,
                confidence=1.0,
                tags="project,portfolio,governance," + ",".join(project.tags),
                metadata=asdict(project),
            )
            if project.dataset_sha256:
                dataset_id = f"dataset:{project.dataset_sha256}"
                if connection.execute(
                    "SELECT 1 FROM knowledge_entities WHERE entity_id = ?",
                    (dataset_id,),
                ).fetchone():
                    _upsert_relation(
                        connection,
                        source_entity_id=project_id,
                        target_entity_id=dataset_id,
                        relation_type="uses_dataset",
                        evidence="Project registry link",
                    )
            if project.model_filename:
                model_id = f"model:{project.model_filename}"
                if connection.execute(
                    "SELECT 1 FROM knowledge_entities WHERE entity_id = ?",
                    (model_id,),
                ).fetchone():
                    _upsert_relation(
                        connection,
                        source_entity_id=project_id,
                        target_entity_id=model_id,
                        relation_type="uses_model",
                        evidence="Project registry link",
                    )

        for page in PAGE_CATALOG:
            _upsert_entity(
                connection,
                entity_id=f"module:{page.key}",
                entity_type="module",
                name=page.title,
                summary=page.description,
                source="BioIntel UI catalog",
                external_id=page.key,
                status="available",
                confidence=1.0,
                tags=(f"module,{page.category.lower()}," + ",".join(page.keywords)),
                metadata={
                    "path": page.path,
                    "icon": page.icon,
                    "category": page.category,
                    "featured": page.featured,
                },
            )

        for row in lookups.itertuples(index=False):
            lookup_id = (
                f"external:{str(row.database).lower().replace(' ', '-')}:" f"{row.query_value}"
            )
            _upsert_entity(
                connection,
                entity_id=lookup_id,
                entity_type="external_reference",
                name=f"{row.query_value} · {row.description}",
                summary=(f"Starter {row.query_type} for {row.database} lookup."),
                source="BioIntel external lookup starter catalog",
                external_id=str(row.query_value),
                status="lookup_ready",
                confidence=0.90,
                tags=(f"external,{str(row.database).lower().replace(' ', '-')}," "starter"),
                metadata={
                    "database": row.database,
                    "query_type": row.query_type,
                },
            )

        for protocol in _protocol_rows():
            now = utc_now()
            connection.execute(
                """
                INSERT INTO knowledge_protocols(
                    protocol_id, name, category, objective,
                    steps_json, acceptance_criteria, risk_level,
                    tags, version, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '1.0', ?, ?)
                ON CONFLICT(protocol_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    objective = excluded.objective,
                    steps_json = excluded.steps_json,
                    acceptance_criteria = excluded.acceptance_criteria,
                    risk_level = excluded.risk_level,
                    tags = excluded.tags,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    protocol["protocol_id"],
                    protocol["name"],
                    protocol["category"],
                    protocol["objective"],
                    json_text(protocol["steps"]),
                    protocol["acceptance"],
                    protocol["risk"],
                    protocol["tags"],
                    now,
                    now,
                ),
            )

        saved_queries = [
            (
                "QUERY-001",
                "Active models",
                "model active",
                "model",
                1,
                "Trusted active model artifacts.",
            ),
            (
                "QUERY-002",
                "High confidence compounds",
                "compound descriptor",
                "compound",
                1,
                "Compound records with descriptor metadata.",
            ),
            (
                "QUERY-003",
                "DTI benchmark candidates",
                "interaction benchmark",
                "interaction_candidate",
                1,
                "Synthetic software benchmark candidates.",
            ),
            (
                "QUERY-004",
                "Governance modules",
                "governance release evidence",
                "module",
                0,
                "Governance and evidence UI modules.",
            ),
            (
                "QUERY-005",
                "Registered datasets",
                "dataset registered lineage",
                "dataset",
                1,
                "Traceable dataset versions and lineage.",
            ),
            (
                "QUERY-006",
                "External starters",
                "external starter",
                "external_reference",
                0,
                "UniProt and ChEMBL starter records.",
            ),
        ]
        for query in saved_queries:
            connection.execute(
                """
                INSERT INTO knowledge_saved_queries(
                    query_id, name, query_text, scope,
                    pinned, description, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_id) DO UPDATE SET
                    name = excluded.name,
                    query_text = excluded.query_text,
                    scope = excluded.scope,
                    pinned = excluded.pinned,
                    description = excluded.description
                """,
                (*query, utc_now()),
            )

        try:
            connection.execute(
                """
                INSERT INTO knowledge_entities_fts(
                    knowledge_entities_fts
                ) VALUES ('rebuild')
                """
            )
        except sqlite3.OperationalError:
            pass

    return knowledge_summary(database)


def knowledge_summary(
    path: str | Path,
) -> KnowledgeSummary:
    initialize_knowledge_warehouse(path)
    with connect(path, read_only=True) as connection:
        entities = int(connection.execute("SELECT COUNT(*) FROM knowledge_entities").fetchone()[0])
        relations = int(
            connection.execute("SELECT COUNT(*) FROM knowledge_relations").fetchone()[0]
        )
        protocols = int(
            connection.execute("SELECT COUNT(*) FROM knowledge_protocols").fetchone()[0]
        )
        saved_queries = int(
            connection.execute("SELECT COUNT(*) FROM knowledge_saved_queries").fetchone()[0]
        )
        entity_types = {
            str(row["entity_type"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT entity_type, COUNT(*) AS count
                FROM knowledge_entities
                GROUP BY entity_type
                ORDER BY count DESC
                """
            )
        }
        statuses = {
            str(row["status"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM knowledge_entities
                GROUP BY status
                ORDER BY count DESC
                """
            )
        }
    return KnowledgeSummary(
        entities=entities,
        relations=relations,
        protocols=protocols,
        saved_queries=saved_queries,
        entity_types=entity_types,
        statuses=statuses,
    )


def search_knowledge(
    path: str | Path,
    query: str = "",
    *,
    entity_type: str = "all",
    status: str = "all",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    initialize_knowledge_warehouse(path)
    safe_limit = min(max(int(limit), 1), 500)
    safe_offset = max(int(offset), 0)
    filters: list[str] = []
    parameters: list[object] = []

    if entity_type != "all":
        filters.append("e.entity_type = ?")
        parameters.append(entity_type)
    if status != "all":
        filters.append("e.status = ?")
        parameters.append(status)

    where = " AND " + " AND ".join(filters) if filters else ""

    with connect(path, read_only=True) as connection:
        if query.strip():
            try:
                rows = connection.execute(
                    f"""
                    SELECT
                        e.entity_id,
                        e.entity_type,
                        e.name,
                        e.summary,
                        e.source,
                        e.external_id,
                        e.status,
                        e.confidence,
                        e.tags,
                        e.metadata_json,
                        bm25(knowledge_entities_fts) AS relevance
                    FROM knowledge_entities_fts
                    JOIN knowledge_entities e
                      ON e.rowid = knowledge_entities_fts.rowid
                    WHERE knowledge_entities_fts MATCH ?
                    {where}
                    ORDER BY relevance, e.name
                    LIMIT ? OFFSET ?
                    """,
                    [
                        query.strip(),
                        *parameters,
                        safe_limit,
                        safe_offset,
                    ],
                ).fetchall()
                return rows_as_dicts(rows)
            except sqlite3.OperationalError:
                pass

            like_query = f"%{query.strip()}%"
            query_where = """
                (
                    e.name LIKE ? COLLATE NOCASE
                    OR e.summary LIKE ? COLLATE NOCASE
                    OR e.tags LIKE ? COLLATE NOCASE
                    OR e.external_id LIKE ? COLLATE NOCASE
                )
                """
            rows = connection.execute(
                f"""
                SELECT
                    e.*,
                    0.0 AS relevance
                FROM knowledge_entities e
                WHERE {query_where}
                {where}
                ORDER BY e.confidence DESC, e.name
                LIMIT ? OFFSET ?
                """,
                [
                    like_query,
                    like_query,
                    like_query,
                    like_query,
                    *parameters,
                    safe_limit,
                    safe_offset,
                ],
            ).fetchall()
            return rows_as_dicts(rows)

        rows = connection.execute(
            f"""
            SELECT
                e.*,
                0.0 AS relevance
            FROM knowledge_entities e
            WHERE 1 = 1
            {where}
            ORDER BY e.confidence DESC, e.name
            LIMIT ? OFFSET ?
            """,
            [
                *parameters,
                safe_limit,
                safe_offset,
            ],
        ).fetchall()
        return rows_as_dicts(rows)


def knowledge_relations(
    path: str | Path,
    entity_id: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    initialize_knowledge_warehouse(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT
                r.relation_id,
                r.relation_type,
                r.score,
                r.evidence,
                r.source_entity_id,
                source.name AS source_name,
                source.entity_type AS source_type,
                r.target_entity_id,
                target.name AS target_name,
                target.entity_type AS target_type
            FROM knowledge_relations r
            JOIN knowledge_entities source
              ON source.entity_id = r.source_entity_id
            JOIN knowledge_entities target
              ON target.entity_id = r.target_entity_id
            WHERE r.source_entity_id = ?
               OR r.target_entity_id = ?
            ORDER BY r.score DESC, r.relation_id
            LIMIT ?
            """,
            (
                entity_id,
                entity_id,
                min(max(int(limit), 1), 500),
            ),
        ).fetchall()
    return rows_as_dicts(rows)


def list_protocols(
    path: str | Path,
    *,
    category: str = "all",
) -> list[dict[str, Any]]:
    initialize_knowledge_warehouse(path)
    with connect(path, read_only=True) as connection:
        if category == "all":
            rows = connection.execute(
                """
                SELECT *
                FROM knowledge_protocols
                ORDER BY category, name
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM knowledge_protocols
                WHERE category = ?
                ORDER BY name
                """,
                (category,),
            ).fetchall()
    return rows_as_dicts(rows)


def knowledge_health(
    path: str | Path,
) -> dict[str, object]:
    summary = knowledge_summary(path)
    health = database_health(
        path,
        name="Research Knowledge Warehouse",
    )
    populated = summary.entities > 0
    return {
        "database": asdict(health),
        "summary": asdict(summary),
        "populated": populated,
        "healthy": (health.exists and health.integrity == "ok" and health.table_count >= 4),
    }


def list_saved_queries(
    path: str | Path,
) -> list[dict[str, Any]]:
    initialize_knowledge_warehouse(path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM knowledge_saved_queries
            ORDER BY pinned DESC, name
            """
        ).fetchall()
    return rows_as_dicts(rows)
