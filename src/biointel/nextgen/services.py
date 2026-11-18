from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import mimetypes
import os
import platform
import re
import shutil
import sqlite3
from biointel.database.core import managed_connect
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from uuid import uuid4

import numpy as np
import pandas as pd
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from biointel import __version__
from biointel.jobs.local_queue import LocalJobQueue


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _version_key(value: object) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", str(value))[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def _json_or(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def state_root(project_root: str | Path) -> Path:
    root = Path(project_root).resolve() / "workspace" / "step104"
    root.mkdir(parents=True, exist_ok=True)
    return root


def runtime_environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "executable": sys.executable,
        "pid": os.getpid(),
        "timestamp_utc": utc_now(),
    }


@dataclass(frozen=True)
class FileInspection:
    name: str
    size_bytes: int
    sha256: str
    detected_format: str
    mime_type: str
    compressed: bool
    confidence: float
    preview_kind: str
    preview: list[dict[str, Any]] | list[str]
    profile: dict[str, Any]
    risks: list[str]
    recommended_modules: list[str]


def _magic_format(payload: bytes, name: str) -> tuple[str, float, bool]:
    head = payload[:64]
    lower = name.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xltx")) and head.startswith(b"PK\x03\x04"):
        return ("Spreadsheet", 0.99, True)
    if head.startswith(b"PK\x03\x04"):
        return ("ZIP or Office Open XML", 0.98, True)
    if head.startswith(b"\x1f\x8b"):
        return ("GZIP", 0.99, True)
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return ("TIFF image", 0.99, False)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("PNG image", 0.99, False)
    if head.startswith(b"\xff\xd8\xff"):
        return ("JPEG image", 0.99, False)
    if head.startswith(b"%PDF"):
        return ("PDF", 0.99, False)
    text = payload[:8192].decode("utf-8-sig", errors="ignore")
    if text.startswith("##fileformat=VCF") or "\n#CHROM\tPOS\t" in text:
        return ("VCF", 0.99, lower.endswith(".gz"))
    if text.lstrip().startswith(">"):
        return ("FASTA", 0.96, lower.endswith(".gz"))
    if lower.endswith((".bed", ".bedpe")):
        return ("BED/BEDPE", 0.92, False)
    if lower.endswith((".gtf", ".gff", ".gff3")):
        return ("GTF/GFF", 0.92, False)
    if lower.endswith((".pdb",)) and ("ATOM  " in text or "HETATM" in text):
        return ("PDB structure", 0.98, False)
    if lower.endswith((".cif", ".mmcif")) and ("data_" in text[:100] or "_atom_site" in text):
        return ("mmCIF structure", 0.95, False)
    if lower.endswith((".csv", ".tsv", ".txt")):
        return ("Delimited table", 0.9, False)
    if lower.endswith(".json"):
        return ("JSON", 0.95, False)
    if lower.endswith((".xlsx", ".xls")):
        return ("Spreadsheet", 0.95, False)
    if lower.endswith((".h5ad", ".h5", ".hdf5")):
        return ("HDF5/AnnData", 0.9, False)
    return (mimetypes.guess_type(name)[0] or "Unknown binary/text", 0.35, lower.endswith((".gz", ".zip")))


def inspect_file_bytes(payload: bytes, name: str, *, max_preview_rows: int = 20) -> FileInspection:
    if len(payload) > 1_000_000_000:
        raise ValueError("The inspector accepts files up to 1 GB per bounded inspection.")
    detected, confidence, compressed = _magic_format(payload, name)
    risks: list[str] = []
    preview: list[dict[str, Any]] | list[str] = []
    profile: dict[str, Any] = {"empty": len(payload) == 0}
    preview_kind = "none"
    recommended: list[str] = []
    if not payload:
        risks.append("The file is empty.")
    lower = name.lower()
    try:
        if detected == "GZIP":
            import gzip
            inner = gzip.decompress(payload)
            if len(inner) > 250_000_000:
                raise ValueError("Expanded GZIP exceeds the 250 MB inspection preview limit")
            inner_name = name[:-3] if lower.endswith(".gz") else name + ".uncompressed"
            inner_report = inspect_file_bytes(inner, inner_name, max_preview_rows=max_preview_rows)
            return FileInspection(
                name=name, size_bytes=len(payload), sha256=sha256_bytes(payload),
                detected_format=f"GZIP-compressed {inner_report.detected_format}",
                mime_type=mimetypes.guess_type(name)[0] or "application/gzip", compressed=True,
                confidence=min(0.99, inner_report.confidence), preview_kind=inner_report.preview_kind,
                preview=inner_report.preview,
                profile={"compressed_bytes": len(payload), "expanded_bytes": len(inner), "inner": inner_report.profile},
                risks=inner_report.risks, recommended_modules=inner_report.recommended_modules,
            )
        if detected == "VCF":
            text = payload.decode("utf-8-sig", errors="replace")
            records = [line for line in text.splitlines() if line and not line.startswith("#")]
            preview = records[:max_preview_rows]
            preview_kind = "lines"
            profile.update({"records": len(records), "header_present": "#CHROM" in text, "genome_build_detected": next((line.split("=", 1)[1].rstrip(">") for line in text.splitlines() if line.startswith("##reference=")), None)})
            recommended = ["Population Genetics & GWAS", "Rare Variant & Family Genetics", "Structural Variant Lab", "Virology"]
        elif detected == "FASTA":
            text = payload.decode("utf-8-sig", errors="replace")
            headers = [line[1:].strip() for line in text.splitlines() if line.startswith(">")]
            sequence_chars = sum(len(re.sub(r"\s+", "", line)) for line in text.splitlines() if not line.startswith(">"))
            preview = headers[:max_preview_rows]
            preview_kind = "lines"
            profile.update({"sequences": len(headers), "sequence_characters": sequence_chars})
            recommended = ["Protein Language Model", "Virology", "Strain-Resolved Microbiome", "Enzyme Engineering"]
        elif detected in {"Delimited table", "JSON", "Spreadsheet"}:
            if detected == "JSON":
                obj = json.loads(payload.decode("utf-8-sig", errors="replace"))
                if isinstance(obj, dict):
                    obj = obj.get("records", obj.get("data", [obj]))
                frame = pd.DataFrame(obj)
            elif detected == "Spreadsheet":
                frame = pd.read_excel(io.BytesIO(payload), nrows=10_000)
            else:
                text = payload.decode("utf-8-sig", errors="replace")
                sep = "\t" if lower.endswith((".tsv", ".txt")) else ","
                lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
                reactome_headerless = bool(
                    lines
                    and sep == "\t"
                    and re.match(r"^R-[A-Z]{3}-\d+\t", lines[0])
                )
                if reactome_headerless:
                    frame = pd.read_csv(
                        io.StringIO("\n".join(lines)),
                        sep=sep,
                        header=None,
                        names=["pathway_id", "pathway_name", "organism"],
                        nrows=10_000,
                    )
                else:
                    frame = pd.read_csv(
                        io.StringIO(text),
                        sep=sep,
                        comment="#",
                        nrows=10_000,
                    )
            preview = frame.head(max_preview_rows).replace({np.nan: None}).to_dict(orient="records")
            preview_kind = "records"
            # pandas.duplicated requires hashable cells. Scientific JSON manifests
            # commonly contain nested dictionaries/lists, so normalize only the
            # duplicate-check view while preserving the original preview values.
            duplicate_view = frame.map(
                lambda value: safe_json(value)
                if isinstance(value, (dict, list, tuple, set))
                else value
            )
            profile.update({
                "preview_rows_loaded": len(frame),
                "columns": list(map(str, frame.columns)),
                "column_count": len(frame.columns),
                "missing_cells_preview": int(frame.isna().sum().sum()),
                "duplicate_rows_preview": int(duplicate_view.duplicated().sum()),
            })
            recommended = ["Universal table import", "Biostatistics", "Multi-Omics", "Project Workspace"]
        elif detected.startswith(("PNG", "JPEG", "TIFF")):
            from PIL import Image
            image = Image.open(io.BytesIO(payload))
            profile.update({"width": image.width, "height": image.height, "mode": image.mode, "frames": getattr(image, "n_frames", 1)})
            preview = [f"{image.width} × {image.height} pixels", f"Mode: {image.mode}"]
            preview_kind = "lines"
            recommended = ["Bioimage & Microscopy AI", "Organoid & 3D Cell Model Analytics", "Digital Pathology"]
        elif detected.startswith("ZIP"):
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = archive.infolist()
                preview = [entry.filename for entry in entries[:max_preview_rows]]
                preview_kind = "lines"
                profile.update({"entries": len(entries), "uncompressed_bytes": sum(e.file_size for e in entries), "compressed_bytes": sum(e.compress_size for e in entries)})
                if any(".." in PurePosixPath(e.filename).parts or PurePosixPath(e.filename).is_absolute() for e in entries):
                    risks.append("Archive contains unsafe traversal or absolute paths.")
                if sum(e.file_size for e in entries) > max(len(payload) * 100, 5_000_000_000):
                    risks.append("Archive expansion ratio is unusually high.")
            recommended = ["Plugin Inspector", "Reference Database Manager", "Project Workspace"]
        else:
            text = payload[:32_768].decode("utf-8-sig", errors="replace")
            preview = text.splitlines()[:max_preview_rows]
            preview_kind = "lines"
            profile.update({"utf8_replacement_characters": text.count("�")})
    except Exception as exc:
        risks.append(f"Preview parser warning: {type(exc).__name__}: {exc}")
    if len(payload) > 500_000_000:
        risks.append("Large file: downstream preview and analysis should use streaming or chunking.")
    if confidence < 0.6:
        risks.append("Low format-detection confidence; verify the file manually.")
    return FileInspection(
        name=name, size_bytes=len(payload), sha256=sha256_bytes(payload), detected_format=detected,
        mime_type=mimetypes.guess_type(name)[0] or "application/octet-stream", compressed=compressed,
        confidence=confidence, preview_kind=preview_kind, preview=preview, profile=profile, risks=risks,
        recommended_modules=recommended,
    )


class NextGenStore:
    def __init__(self, project_root: str | Path) -> None:
        self.root = state_root(project_root)
        self.db_path = self.root / "platform.sqlite3"
        self.assets = self.root / "assets"
        self.assets.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _initialize(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects(
                    project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_assets(
                    asset_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, logical_name TEXT NOT NULL,
                    source_path TEXT NOT NULL DEFAULT '', stored_path TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, media_type TEXT NOT NULL DEFAULT '', module_key TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    UNIQUE(project_id, sha256, logical_name)
                );
                CREATE TABLE IF NOT EXISTS project_snapshots(
                    snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, label TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS workflows(
                    workflow_id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    definition_json TEXT NOT NULL, definition_sha256 TEXT NOT NULL, validation_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS references_v2(
                    reference_id TEXT PRIMARY KEY, database_name TEXT NOT NULL, version TEXT NOT NULL,
                    local_path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                    license_name TEXT NOT NULL DEFAULT 'Unknown', compatibility_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'registered', active INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL, UNIQUE(database_name, version)
                );
                CREATE TABLE IF NOT EXISTS citations_v2(
                    citation_id TEXT PRIMARY KEY, identifier TEXT NOT NULL, identifier_type TEXT NOT NULL,
                    title TEXT NOT NULL, year INTEGER, status TEXT NOT NULL DEFAULT 'unverified',
                    evidence_level TEXT NOT NULL DEFAULT 'Unrated', metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL, UNIQUE(identifier_type, identifier)
                );
                CREATE TABLE IF NOT EXISTS claims_v2(
                    claim_id TEXT PRIMARY KEY, claim_text TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claim_citations_v2(
                    claim_id TEXT NOT NULL, citation_id TEXT NOT NULL, support_type TEXT NOT NULL DEFAULT 'supports',
                    note TEXT NOT NULL DEFAULT '', PRIMARY KEY(claim_id, citation_id),
                    FOREIGN KEY(claim_id) REFERENCES claims_v2(claim_id) ON DELETE CASCADE,
                    FOREIGN KEY(citation_id) REFERENCES citations_v2(citation_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS models_v2(
                    model_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL, model_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL, framework TEXT NOT NULL DEFAULT 'Unknown', status TEXT NOT NULL DEFAULT 'registered',
                    evaluation_protocol TEXT NOT NULL DEFAULT '', metrics_json TEXT NOT NULL DEFAULT '{}',
                    dataset_manifest_json TEXT NOT NULL DEFAULT '{}', approved_by TEXT NOT NULL DEFAULT '',
                    approval_note TEXT NOT NULL DEFAULT '', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE TABLE IF NOT EXISTS instrument_connectors_v2(
                    connector_id TEXT PRIMARY KEY, name TEXT NOT NULL, folder_path TEXT NOT NULL,
                    file_patterns_json TEXT NOT NULL DEFAULT '["*"]', stability_seconds INTEGER NOT NULL DEFAULT 5,
                    enabled INTEGER NOT NULL DEFAULT 1, last_scan_utc TEXT NOT NULL DEFAULT '', created_at_utc TEXT NOT NULL,
                    UNIQUE(folder_path)
                );
                CREATE TABLE IF NOT EXISTS instrument_imports_v2(
                    import_id TEXT PRIMARY KEY, connector_id TEXT NOT NULL, file_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, sample_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'imported', imported_at_utc TEXT NOT NULL,
                    FOREIGN KEY(connector_id) REFERENCES instrument_connectors_v2(connector_id) ON DELETE CASCADE,
                    UNIQUE(connector_id, sha256)
                );
                CREATE TABLE IF NOT EXISTS reviews_v2(
                    review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL DEFAULT '', result_ref TEXT NOT NULL,
                    result_version TEXT NOT NULL, reviewer TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                    decision TEXT NOT NULL DEFAULT '', locked INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_comments_v2(
                    comment_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, author TEXT NOT NULL,
                    body TEXT NOT NULL, resolution_status TEXT NOT NULL DEFAULT 'open', created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(review_id) REFERENCES reviews_v2(review_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS lakehouse_files_v2(
                    file_id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL, extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, modified_ns INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL DEFAULT '', sample_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active', metadata_json TEXT NOT NULL DEFAULT '{}', indexed_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS benchmarks_v2(
                    benchmark_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                    definition_json TEXT NOT NULL, locked_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE TABLE IF NOT EXISTS benchmark_runs_v2(
                    run_id TEXT PRIMARY KEY, benchmark_id TEXT NOT NULL, status TEXT NOT NULL,
                    metrics_json TEXT NOT NULL, environment_json TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(benchmark_id) REFERENCES benchmarks_v2(benchmark_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS plugins_v2(
                    plugin_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL, archive_sha256 TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, permissions_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'inspected',
                    installed_path TEXT NOT NULL DEFAULT '', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE INDEX IF NOT EXISTS idx_assets_project ON project_assets(project_id, created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_lake_name ON lakehouse_files_v2(name);
                CREATE INDEX IF NOT EXISTS idx_lake_sha ON lakehouse_files_v2(sha256);
                CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews_v2(status, updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_models_status ON models_v2(status, updated_at_utc DESC);
                """
            )

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Project name is required")
        project_id = "project-" + uuid4().hex
        now = utc_now()
        with self._connect() as con:
            con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)", (project_id, name, description.strip(), "active", now, now))
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return dict(row)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM projects ORDER BY updated_at_utc DESC").fetchall()]

    def attach_asset(self, project_id: str, payload: bytes, logical_name: str, *, module_key: str = "", media_type: str = "", source_path: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        self.get_project(project_id)
        digest = sha256_bytes(payload)
        asset_dir = self.assets / "project_assets" / project_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(logical_name).name)[:180] or "asset.bin"
        stored = asset_dir / f"{digest[:12]}-{safe_name}"
        if not stored.exists():
            stored.write_bytes(payload)
        asset_id = "asset-" + uuid4().hex
        now = utc_now()
        with self._connect() as con:
            existing = con.execute("SELECT * FROM project_assets WHERE project_id=? AND sha256=? AND logical_name=?", (project_id, digest, logical_name)).fetchone()
            if existing is not None:
                return dict(existing)
            con.execute(
                "INSERT INTO project_assets VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (asset_id, project_id, logical_name, source_path, str(stored.relative_to(self.root)), digest, len(payload), media_type, module_key, safe_json(metadata or {}), now),
            )
            con.execute("UPDATE projects SET updated_at_utc=? WHERE project_id=?", (now, project_id))
        return self.list_assets(project_id)[0]

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM project_assets WHERE project_id=? ORDER BY created_at_utc DESC", (project_id,)).fetchall()
        return [{**dict(row), "metadata": _json_or(row["metadata_json"], {})} for row in rows]

    def create_snapshot(self, project_id: str, label: str) -> dict[str, Any]:
        project = self.get_project(project_id); assets = self.list_assets(project_id)
        manifest = {"schema": "biointel.project_snapshot.v1", "project": project, "assets": [{k: v for k, v in item.items() if k != "metadata_json"} for item in assets], "created_at_utc": utc_now()}
        payload = safe_json(manifest).encode("utf-8")
        snapshot = {"snapshot_id": "snapshot-" + uuid4().hex, "project_id": project_id, "label": label.strip() or "Snapshot", "manifest_json": payload.decode("utf-8"), "manifest_sha256": sha256_bytes(payload), "created_at_utc": utc_now()}
        with self._connect() as con:
            con.execute("INSERT INTO project_snapshots VALUES(?,?,?,?,?,?)", tuple(snapshot.values()))
        return {**snapshot, "manifest": manifest}

    def list_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM project_snapshots WHERE project_id=? ORDER BY created_at_utc DESC", (project_id,)).fetchall()
        return [{**dict(row), "manifest": _json_or(row["manifest_json"], {})} for row in rows]

    @staticmethod
    def validate_workflow(definition: dict[str, Any]) -> dict[str, Any]:
        nodes = definition.get("nodes", []); edges = definition.get("edges", [])
        node_map = {str(n.get("id")): n for n in nodes if n.get("id")}
        errors: list[str] = []; warnings: list[str] = []
        if len(node_map) != len(nodes): errors.append("Node IDs must be present and unique.")
        adjacency = {node_id: [] for node_id in node_map}; indegree = {node_id: 0 for node_id in node_map}
        for edge in edges:
            source, target = str(edge.get("source", "")), str(edge.get("target", ""))
            if source not in node_map or target not in node_map:
                errors.append(f"Unknown edge endpoint: {source} → {target}"); continue
            if source == target:
                errors.append(f"Self-cycle on node {source}"); continue
            source_type = str(edge.get("output_type", node_map[source].get("output_type", "any")))
            target_type = str(edge.get("input_type", node_map[target].get("input_type", "any")))
            if source_type != "any" and target_type != "any" and source_type != target_type:
                errors.append(f"Type mismatch {source_type} → {target_type} for {source} → {target}")
            adjacency[source].append(target); indegree[target] += 1
        queue = [node for node, degree in indegree.items() if degree == 0]; order = []
        while queue:
            node = queue.pop(0); order.append(node)
            for child in adjacency[node]:
                indegree[child] -= 1
                if indegree[child] == 0: queue.append(child)
        if len(order) != len(node_map): errors.append("Workflow contains a cycle.")
        if not nodes: warnings.append("Workflow has no nodes.")
        cache_keys = {node_id: sha256_bytes(safe_json(node_map[node_id]).encode("utf-8"))[:16] for node_id in node_map}
        return {"valid": not errors, "errors": errors, "warnings": warnings, "topological_order": order, "cache_keys": cache_keys, "node_count": len(nodes), "edge_count": len(edges)}

    def save_workflow(self, name: str, definition: dict[str, Any], workflow_id: str | None = None) -> dict[str, Any]:
        validation = self.validate_workflow(definition)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))
        payload = safe_json(definition); digest = sha256_bytes(payload.encode("utf-8")); now = utc_now()
        with self._connect() as con:
            if workflow_id:
                row = con.execute("SELECT version FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
                if row is None: raise KeyError(workflow_id)
                version = int(row["version"]) + 1
                con.execute("UPDATE workflows SET name=?, version=?, definition_json=?, definition_sha256=?, validation_json=?, updated_at_utc=? WHERE workflow_id=?", (name, version, payload, digest, safe_json(validation), now, workflow_id))
            else:
                workflow_id = "workflow-" + uuid4().hex; version = 1
                con.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?,?)", (workflow_id, name, version, payload, digest, safe_json(validation), now, now))
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        if row is None: raise KeyError(workflow_id)
        return {**dict(row), "definition": _json_or(row["definition_json"], {}), "validation": _json_or(row["validation_json"], {})}

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM workflows ORDER BY updated_at_utc DESC").fetchall()
        return [{**dict(row), "validation": _json_or(row["validation_json"], {})} for row in rows]

    def job_queue(self) -> LocalJobQueue:
        return LocalJobQueue(self.root / "jobs.sqlite3")

    def register_reference(self, database_name: str, version: str, path: str | Path, *, license_name: str = "Unknown", compatibility: dict[str, Any] | None = None) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        digest = sha256_path(source); reference_id = "reference-" + uuid4().hex; now = utc_now()
        with self._connect() as con:
            existing = con.execute("SELECT * FROM references_v2 WHERE database_name=? AND version=?", (database_name, version)).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO references_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?)", (reference_id, database_name.strip(), version.strip(), str(source), digest, source.stat().st_size, license_name.strip() or "Unknown", safe_json(compatibility or {}), "verified", 0, now))
        return self.list_references()[0]

    def list_references(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM references_v2 ORDER BY database_name, created_at_utc DESC").fetchall()
        return [{**dict(row), "compatibility": _json_or(row["compatibility_json"], {})} for row in rows]

    def activate_reference(self, reference_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT database_name FROM references_v2 WHERE reference_id=?", (reference_id,)).fetchone()
            if row is None: raise KeyError(reference_id)
            con.execute("UPDATE references_v2 SET active=0 WHERE database_name=?", (row["database_name"],))
            con.execute("UPDATE references_v2 SET active=1, status='active' WHERE reference_id=?", (reference_id,))
            result = con.execute("SELECT * FROM references_v2 WHERE reference_id=?", (reference_id,)).fetchone()
        return dict(result)

    def verify_references(self) -> pd.DataFrame:
        rows = []
        for item in self.list_references():
            path = Path(item["local_path"]); current = sha256_path(path) if path.is_file() else ""
            rows.append({"reference_id": item["reference_id"], "database_name": item["database_name"], "version": item["version"], "path_exists": path.is_file(), "checksum_match": bool(current and current == item["sha256"]), "active": bool(item["active"]), "size_bytes": item["size_bytes"]})
        return pd.DataFrame(rows)

    def register_citation(self, identifier: str, identifier_type: str, title: str, *, year: int | None = None, status: str = "unverified", evidence_level: str = "Unrated", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        ident = identifier.strip(); kind = identifier_type.strip().upper()
        if not ident or not title.strip(): raise ValueError("Identifier and title are required")
        citation_id = "citation-" + uuid4().hex
        with self._connect() as con:
            existing = con.execute("SELECT * FROM citations_v2 WHERE identifier_type=? AND identifier=?", (kind, ident)).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO citations_v2 VALUES(?,?,?,?,?,?,?,?,?)", (citation_id, ident, kind, title.strip(), year, status, evidence_level, safe_json(metadata or {}), utc_now()))
            row = con.execute("SELECT * FROM citations_v2 WHERE citation_id=?", (citation_id,)).fetchone()
        return dict(row)

    def list_citations(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM citations_v2 ORDER BY created_at_utc DESC").fetchall()
        return [{**dict(row), "metadata": _json_or(row["metadata_json"], {})} for row in rows]

    def create_claim(self, claim_text: str, context: str = "") -> dict[str, Any]:
        if not claim_text.strip(): raise ValueError("Claim text is required")
        claim_id = "claim-" + uuid4().hex
        with self._connect() as con:
            con.execute("INSERT INTO claims_v2 VALUES(?,?,?,?)", (claim_id, claim_text.strip(), context.strip(), utc_now()))
        return {"claim_id": claim_id, "claim_text": claim_text.strip(), "context": context.strip()}

    def link_claim(self, claim_id: str, citation_id: str, support_type: str = "supports", note: str = "") -> None:
        with self._connect() as con:
            con.execute("INSERT OR REPLACE INTO claim_citations_v2 VALUES(?,?,?,?)", (claim_id, citation_id, support_type, note))

    def evidence_matrix(self) -> pd.DataFrame:
        query = """
            SELECT c.claim_id,c.claim_text,c.context,x.citation_id,x.identifier,x.identifier_type,x.title,x.year,x.status,x.evidence_level,l.support_type,l.note
            FROM claims_v2 c LEFT JOIN claim_citations_v2 l ON l.claim_id=c.claim_id
            LEFT JOIN citations_v2 x ON x.citation_id=l.citation_id ORDER BY c.created_at_utc DESC
        """
        with self._connect() as con:
            return pd.read_sql_query(query, con)

    def register_model(self, name: str, version: str, path: str | Path, *, framework: str = "Unknown", evaluation_protocol: str = "", metrics: dict[str, Any] | None = None, dataset_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        model_id = "model-" + uuid4().hex; now = utc_now(); digest = sha256_path(source)
        with self._connect() as con:
            existing = con.execute("SELECT * FROM models_v2 WHERE name=? AND version=?", (name, version)).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO models_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (model_id, name.strip(), version.strip(), str(source), digest, framework, "registered", evaluation_protocol, safe_json(metrics or {}), safe_json(dataset_manifest or {}), "", "", now, now))
        return self.list_models()[0]

    def list_models(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM models_v2 ORDER BY updated_at_utc DESC").fetchall()
        return [{**dict(row), "metrics": _json_or(row["metrics_json"], {}), "dataset_manifest": _json_or(row["dataset_manifest_json"], {})} for row in rows]

    def set_model_status(self, model_id: str, status: str, *, reviewer: str = "", note: str = "") -> dict[str, Any]:
        allowed = {"registered", "review", "approved", "deployed", "retired", "rejected"}
        if status not in allowed: raise ValueError(f"Unsupported status: {status}")
        with self._connect() as con:
            current = con.execute("SELECT * FROM models_v2 WHERE model_id=?", (model_id,)).fetchone()
            if current is None:
                raise KeyError(model_id)
            if status in {"approved", "rejected"} and not reviewer.strip():
                raise ValueError("A named reviewer is required for approval or rejection")
            if status == "deployed" and str(current["status"]) not in {"approved", "deployed"}:
                raise ValueError("Only an approved model can be deployed")
            con.execute("UPDATE models_v2 SET status=?, approved_by=?, approval_note=?, updated_at_utc=? WHERE model_id=?", (status, reviewer, note, utc_now(), model_id))
            row = con.execute("SELECT * FROM models_v2 WHERE model_id=?", (model_id,)).fetchone()
        return dict(row)

    def add_connector(self, name: str, folder_path: str | Path, *, patterns: list[str] | None = None, stability_seconds: int = 5) -> dict[str, Any]:
        folder = Path(folder_path).expanduser().resolve()
        if not folder.is_dir(): raise NotADirectoryError(folder)
        connector_id = "connector-" + uuid4().hex
        with self._connect() as con:
            existing = con.execute("SELECT * FROM instrument_connectors_v2 WHERE folder_path=?", (str(folder),)).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO instrument_connectors_v2 VALUES(?,?,?,?,?,?,?,?)", (connector_id, name.strip() or folder.name, str(folder), safe_json(patterns or ["*"]), max(2, min(int(stability_seconds), 3600)), 1, "", utc_now()))
        return self.list_connectors()[0]

    def list_connectors(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM instrument_connectors_v2 ORDER BY created_at_utc DESC").fetchall()
        return [{**dict(row), "patterns": _json_or(row["file_patterns_json"], ["*"])} for row in rows]

    def scan_connector(self, connector_id: str, *, max_files: int = 500) -> dict[str, Any]:
        with self._connect() as con:
            connector = con.execute("SELECT * FROM instrument_connectors_v2 WHERE connector_id=?", (connector_id,)).fetchone()
        if connector is None: raise KeyError(connector_id)
        folder = Path(connector["folder_path"]); patterns = _json_or(connector["file_patterns_json"], ["*"])
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(p for p in folder.glob(pattern) if p.is_file())
        candidates = sorted(set(candidates), key=lambda p: p.stat().st_mtime)[:max_files]
        imported = duplicates = unstable = 0; rows = []
        now_epoch = time.time(); stability_seconds = int(connector["stability_seconds"])
        with self._connect() as con:
            for path in candidates:
                stat = path.stat()
                if now_epoch - stat.st_mtime < stability_seconds:
                    unstable += 1; rows.append({"path": str(path), "status": "unstable_recent_file"}); continue
                digest = sha256_path(path)
                existing = con.execute("SELECT 1 FROM instrument_imports_v2 WHERE connector_id=? AND sha256=?", (connector_id, digest)).fetchone()
                if existing:
                    duplicates += 1; rows.append({"path": str(path), "status": "duplicate"}); continue
                sample_match = re.search(r"(?:sample|s)[-_]?([A-Za-z0-9]+)", path.stem, re.I)
                sample_id = sample_match.group(1) if sample_match else ""
                import_id = "import-" + uuid4().hex
                con.execute("INSERT INTO instrument_imports_v2 VALUES(?,?,?,?,?,?,?,?)", (import_id, connector_id, str(path), digest, stat.st_size, sample_id, "needs_sample_review" if not sample_id else "imported", utc_now()))
                imported += 1; rows.append({"path": str(path), "status": "imported", "sample_id": sample_id, "sha256": digest})
            con.execute("UPDATE instrument_connectors_v2 SET last_scan_utc=? WHERE connector_id=?", (utc_now(), connector_id))
        return {"imported": imported, "duplicates": duplicates, "unstable": unstable, "files": rows}

    def create_review(self, result_ref: str, version: str, reviewer: str, *, project_id: str = "") -> dict[str, Any]:
        review_id = "review-" + uuid4().hex; now = utc_now()
        with self._connect() as con:
            con.execute("INSERT INTO reviews_v2 VALUES(?,?,?,?,?,?,?,?,?,?)", (review_id, project_id, result_ref.strip(), version.strip(), reviewer.strip(), "open", "", 0, now, now))
        return self.get_review(review_id)

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM reviews_v2 WHERE review_id=?", (review_id,)).fetchone()
            comments = con.execute("SELECT * FROM review_comments_v2 WHERE review_id=? ORDER BY created_at_utc", (review_id,)).fetchall()
        if row is None: raise KeyError(review_id)
        return {**dict(row), "comments": [dict(x) for x in comments]}

    def list_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM reviews_v2 ORDER BY updated_at_utc DESC").fetchall()]

    def add_review_comment(self, review_id: str, author: str, body: str) -> dict[str, Any]:
        review = self.get_review(review_id)
        if review["locked"]: raise ValueError("Review is locked")
        comment_id = "comment-" + uuid4().hex
        with self._connect() as con:
            con.execute("INSERT INTO review_comments_v2 VALUES(?,?,?,?,?,?)", (comment_id, review_id, author.strip(), body.strip(), "open", utc_now()))
            con.execute("UPDATE reviews_v2 SET updated_at_utc=? WHERE review_id=?", (utc_now(), review_id))
        return self.get_review(review_id)

    def decide_review(self, review_id: str, decision: str, *, lock: bool = True) -> dict[str, Any]:
        allowed = {"approved", "rejected", "changes_requested"}
        if decision not in allowed: raise ValueError("Unsupported decision")
        with self._connect() as con:
            con.execute("UPDATE reviews_v2 SET status='closed', decision=?, locked=?, updated_at_utc=? WHERE review_id=?", (decision, 1 if lock else 0, utc_now(), review_id))
        return self.get_review(review_id)

    def index_folder(self, folder_path: str | Path, *, project_id: str = "", max_files: int = 5000, max_hash_bytes: int = 2_000_000_000) -> dict[str, Any]:
        folder = Path(folder_path).expanduser().resolve()
        if not folder.is_dir(): raise NotADirectoryError(folder)
        indexed = unchanged = errors = 0; hashed_bytes = 0
        paths = (p for p in folder.rglob("*") if p.is_file())
        with self._connect() as con:
            for path in paths:
                if indexed + unchanged + errors >= max_files: break
                try:
                    stat = path.stat(); existing = con.execute("SELECT modified_ns,size_bytes FROM lakehouse_files_v2 WHERE path=?", (str(path),)).fetchone()
                    if existing and int(existing["modified_ns"]) == stat.st_mtime_ns and int(existing["size_bytes"]) == stat.st_size:
                        unchanged += 1; continue
                    if hashed_bytes + stat.st_size > max_hash_bytes:
                        errors += 1; continue
                    digest = sha256_path(path); hashed_bytes += stat.st_size
                    file_id = "file-" + uuid4().hex
                    con.execute(
                        """INSERT INTO lakehouse_files_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(path) DO UPDATE SET name=excluded.name,extension=excluded.extension,size_bytes=excluded.size_bytes,
                           modified_ns=excluded.modified_ns,sha256=excluded.sha256,media_type=excluded.media_type,project_id=excluded.project_id,indexed_at_utc=excluded.indexed_at_utc""",
                        (file_id, str(path), path.name, path.suffix.lower(), stat.st_size, stat.st_mtime_ns, digest, mimetypes.guess_type(path.name)[0] or "", project_id, "", "active", "{}", utc_now()),
                    ); indexed += 1
                except Exception:
                    errors += 1
        return {"indexed_or_updated": indexed, "unchanged": unchanged, "errors_or_limits": errors, "hashed_bytes": hashed_bytes, "max_files": max_files}

    def search_files(self, query: str = "", *, extension: str = "", duplicates_only: bool = False, limit: int = 500) -> pd.DataFrame:
        clauses = ["1=1"]; params: list[Any] = []
        if query.strip(): clauses.append("(name LIKE ? OR path LIKE ? OR sample_id LIKE ?)"); token = f"%{query.strip()}%"; params += [token, token, token]
        if extension.strip(): clauses.append("extension=?"); params.append(extension if extension.startswith(".") else "." + extension)
        if duplicates_only: clauses.append("sha256 IN (SELECT sha256 FROM lakehouse_files_v2 GROUP BY sha256 HAVING COUNT(*)>1)")
        params.append(min(max(int(limit), 1), 5000))
        with self._connect() as con:
            return pd.read_sql_query(f"SELECT * FROM lakehouse_files_v2 WHERE {' AND '.join(clauses)} ORDER BY indexed_at_utc DESC LIMIT ?", con, params=params)

    def register_benchmark(self, name: str, version: str, definition: dict[str, Any]) -> dict[str, Any]:
        payload = safe_json(definition); digest = sha256_bytes(payload.encode("utf-8")); benchmark_id = "benchmark-" + uuid4().hex
        with self._connect() as con:
            existing = con.execute("SELECT * FROM benchmarks_v2 WHERE name=? AND version=?", (name, version)).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO benchmarks_v2 VALUES(?,?,?,?,?,?)", (benchmark_id, name.strip(), version.strip(), payload, digest, utc_now()))
            row = con.execute("SELECT * FROM benchmarks_v2 WHERE benchmark_id=?", (benchmark_id,)).fetchone()
        return dict(row)

    def list_benchmarks(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [{**dict(row), "definition": _json_or(row["definition_json"], {})} for row in con.execute("SELECT * FROM benchmarks_v2 ORDER BY created_at_utc DESC").fetchall()]

    def run_benchmark(self, benchmark_id: str, candidate: dict[str, float]) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM benchmarks_v2 WHERE benchmark_id=?", (benchmark_id,)).fetchone()
        if row is None: raise KeyError(benchmark_id)
        definition = _json_or(row["definition_json"], {}); expected = definition.get("expected", {}); tolerances = definition.get("tolerances", {})
        checks = []
        for metric, target in expected.items():
            actual = candidate.get(metric); tolerance = float(tolerances.get(metric, 0))
            passed = actual is not None and abs(float(actual) - float(target)) <= tolerance
            checks.append({"metric": metric, "expected": target, "actual": actual, "tolerance": tolerance, "passed": passed})
        status = "passed" if checks and all(x["passed"] for x in checks) else "failed"
        result = {"status": status, "checks": checks, "candidate": candidate}
        run_id = "benchmark-run-" + uuid4().hex
        with self._connect() as con:
            con.execute("INSERT INTO benchmark_runs_v2 VALUES(?,?,?,?,?,?)", (run_id, benchmark_id, status, safe_json(result), safe_json(runtime_environment()), utc_now()))
        return {"run_id": run_id, **result}

    def inspect_plugin(self, payload: bytes, archive_name: str) -> dict[str, Any]:
        if len(payload) > 250_000_000: raise ValueError("Plugin archive exceeds the 250 MB inspection limit")
        findings: list[str] = []; permissions: list[str] = []; manifest: dict[str, Any] = {}; entries = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            total = sum(i.file_size for i in infos)
            if total > 1_000_000_000: findings.append("Expanded plugin exceeds the 1 GB safe limit.")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts: findings.append(f"Unsafe path: {info.filename}")
                if info.file_size > 200_000_000: findings.append(f"Very large member: {info.filename}")
                entries.append({"name": info.filename, "size_bytes": info.file_size, "compressed_bytes": info.compress_size})
            manifest_name = next((i.filename for i in infos if PurePosixPath(i.filename).name in {"plugin.json", "manifest.json"}), None)
            if manifest_name:
                manifest = json.loads(archive.read(manifest_name).decode("utf-8-sig"))
                permissions = list(map(str, manifest.get("permissions", [])))
            else:
                findings.append("Missing plugin.json or manifest.json.")
            forbidden = {"subprocess", "shell", "network", "filesystem_write", "secrets", "camera", "microphone"}
            risky = sorted(set(permissions).intersection(forbidden))
            if risky: findings.append("High-risk permissions requested: " + ", ".join(risky))
        name = str(manifest.get("name", Path(archive_name).stem)); version = str(manifest.get("version", "0.0.0"))
        compatible = _version_key(manifest.get("min_biointel_version", "0")) <= _version_key(__version__)
        if not compatible: findings.append("Plugin declares an incompatible minimum BioIntel version.")
        return {"archive_name": archive_name, "archive_sha256": sha256_bytes(payload), "name": name, "version": version, "manifest": manifest, "permissions": permissions, "entries": entries[:5000], "entry_count": len(entries), "findings": findings, "safe_to_register": not findings, "signature_status": "not_cryptographically_verified"}

    def register_plugin_inspection(self, inspection: dict[str, Any]) -> dict[str, Any]:
        plugin_id = "plugin-" + uuid4().hex; now = utc_now(); status = "review_required" if inspection.get("findings") else "inspected"
        with self._connect() as con:
            existing = con.execute("SELECT * FROM plugins_v2 WHERE name=? AND version=?", (inspection["name"], inspection["version"])).fetchone()
            if existing is not None: return dict(existing)
            con.execute("INSERT INTO plugins_v2 VALUES(?,?,?,?,?,?,?,?,?,?)", (plugin_id, inspection["name"], inspection["version"], inspection["archive_sha256"], safe_json(inspection.get("manifest", {})), safe_json(inspection.get("permissions", [])), status, "", now, now))
            row = con.execute("SELECT * FROM plugins_v2 WHERE plugin_id=?", (plugin_id,)).fetchone()
        return dict(row)

    def install_plugin_archive(self, payload: bytes, inspection: dict[str, Any], *, trust_unverified: bool = False) -> dict[str, Any]:
        if inspection.get("findings"):
            raise ValueError("Plugin findings must be resolved before installation")
        if inspection.get("signature_status") != "verified" and not trust_unverified:
            raise ValueError("The plugin signature is not verified; explicit manual trust is required")
        plugin_dir = self.root / "plugins" / re.sub(r"[^A-Za-z0-9._-]+", "_", f"{inspection['name']}-{inspection['version']}")
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        archive_path = plugin_dir / "plugin.zip"
        archive_path.write_bytes(payload)
        extracted = plugin_dir / "content"
        extracted.mkdir()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                relative = PurePosixPath(info.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe plugin path: {info.filename}")
                target = extracted.joinpath(*relative.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        record = self.register_plugin_inspection(inspection)
        with self._connect() as con:
            con.execute("UPDATE plugins_v2 SET status='installed_disabled', installed_path=?, updated_at_utc=? WHERE plugin_id=?", (str(plugin_dir), utc_now(), record["plugin_id"]))
            row = con.execute("SELECT * FROM plugins_v2 WHERE plugin_id=?", (record["plugin_id"],)).fetchone()
        return dict(row)

    def set_plugin_status(self, plugin_id: str, status: str) -> dict[str, Any]:
        if status not in {"installed_disabled", "enabled", "disabled", "removed"}:
            raise ValueError("Unsupported plugin status")
        with self._connect() as con:
            row = con.execute("SELECT * FROM plugins_v2 WHERE plugin_id=?", (plugin_id,)).fetchone()
            if row is None:
                raise KeyError(plugin_id)
            if status == "enabled" and not row["installed_path"]:
                raise ValueError("Plugin must be installed before it can be enabled")
            if status == "removed" and row["installed_path"]:
                path = Path(row["installed_path"])
                if path.exists() and self.root in path.resolve().parents:
                    shutil.rmtree(path)
            con.execute("UPDATE plugins_v2 SET status=?, installed_path=CASE WHEN ?='removed' THEN '' ELSE installed_path END, updated_at_utc=? WHERE plugin_id=?", (status, status, utc_now(), plugin_id))
            updated = con.execute("SELECT * FROM plugins_v2 WHERE plugin_id=?", (plugin_id,)).fetchone()
        return dict(updated)

    def list_plugins(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [{**dict(row), "manifest": _json_or(row["manifest_json"], {}), "permissions": _json_or(row["permissions_json"], [])} for row in con.execute("SELECT * FROM plugins_v2 ORDER BY updated_at_utc DESC").fetchall()]


class ProvenanceLedger:
    def __init__(self, project_root: str | Path) -> None:
        self.path = state_root(project_root) / "provenance_ledger.jsonl"
        self.path.touch(exist_ok=True)

    def _records(self) -> list[dict[str, Any]]:
        records = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try: records.append(json.loads(line))
                except Exception: records.append({"parse_error": True, "raw": line})
        return records

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        records = self._records(); previous = records[-1].get("record_hash", "GENESIS") if records else "GENESIS"
        body = {"schema": "biointel.provenance_ledger.v2", "record_id": "event-" + uuid4().hex, "event_type": event_type, "timestamp_utc": utc_now(), "previous_hash": previous, "payload": payload, "environment": runtime_environment()}
        record_hash = sha256_bytes(safe_json(body).encode("utf-8")); record = {**body, "record_hash": record_hash}
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(safe_json(record) + "\n"); handle.flush(); os.fsync(handle.fileno())
        return record

    def verify(self) -> dict[str, Any]:
        records = self._records(); previous = "GENESIS"; errors = []
        for index, record in enumerate(records):
            if record.get("parse_error"):
                errors.append({"index": index, "error": "parse_error"}); continue
            stored = record.get("record_hash", ""); body = {k: v for k, v in record.items() if k != "record_hash"}
            computed = sha256_bytes(safe_json(body).encode("utf-8"))
            if record.get("previous_hash") != previous: errors.append({"index": index, "error": "previous_hash_mismatch"})
            if stored != computed: errors.append({"index": index, "error": "record_hash_mismatch"})
            previous = stored
        return {"valid": not errors, "records": len(records), "errors": errors, "head_hash": previous, "path": str(self.path)}

    def records(self) -> pd.DataFrame:
        rows = []
        for record in self._records():
            rows.append({"record_id": record.get("record_id"), "event_type": record.get("event_type"), "timestamp_utc": record.get("timestamp_utc"), "previous_hash": record.get("previous_hash"), "record_hash": record.get("record_hash"), "payload": safe_json(record.get("payload", {}))})
        return pd.DataFrame(rows)

# Compatibility re-exports; implementations are split to keep service modules maintainable.
from biointel.nextgen.assistant_reporting import LocalCopilot, build_report_bundle
