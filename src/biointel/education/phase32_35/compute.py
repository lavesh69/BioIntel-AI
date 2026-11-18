from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from .base import (
    Conflict,
    IntegrityFailure,
    Missing,
    PermissionDenied,
    PlatformStore,
    ResearchPlatformError,
    canonical_json,
    new_id,
    now_utc,
)

SUPPORTED_FORMATS = {
    "FASTA",
    "FASTQ",
    "BAM",
    "CRAM",
    "SAM",
    "VCF",
    "BCF",
    "GFF",
    "GTF",
    "BED",
    "CSV",
    "TSV",
    "XLSX",
    "JSON",
    "HDF5",
    "ANNDATA",
    "MATRIX_MARKET",
    "PDB",
    "MMCIF",
    "MZML",
    "IMAGE_METADATA",
    "DICOM_METADATA",
}
REMOTE_ADAPTER_TYPES = {
    "institution_worker",
    "docker",
    "kubernetes",
    "slurm",
    "ssh_batch",
    "object_storage",
}
RUN_STATES = {
    "queued",
    "preparing",
    "running",
    "paused",
    "retrying",
    "completed",
    "failed",
    "cancelled",
    "partially_completed",
    "blocked",
    "awaiting_resources",
}
PROJECT_ASSET_TYPES = {
    "sample_sheet",
    "analysis",
    "notebook",
    "report",
    "reference",
    "approval",
    "publication",
    "export",
    "issue",
    "milestone",
}
HANDOFF_DESTINATIONS = {"studio", "shiro", "discovery_agents"}

NATIVE_TOOLS = {
    "file_manifest": {
        "version": "1.0.0",
        "inputs": sorted(SUPPORTED_FORMATS),
        "outputs": ["JSON"],
        "description": "Streaming file identity and format manifest",
    },
    "fasta_qc": {
        "version": "1.0.0",
        "inputs": ["FASTA"],
        "outputs": ["JSON"],
        "description": "Streaming sequence count, length, GC, and ambiguous-base metrics",
    },
    "fastq_qc": {
        "version": "1.0.0",
        "inputs": ["FASTQ"],
        "outputs": ["JSON"],
        "description": "Streaming read count, length, and quality-character metrics",
    },
    "vcf_qc": {
        "version": "1.0.0",
        "inputs": ["VCF"],
        "outputs": ["JSON"],
        "description": "Streaming variant and filter summary",
    },
    "tabular_qc": {
        "version": "1.0.0",
        "inputs": ["CSV", "TSV"],
        "outputs": ["JSON"],
        "description": "Streaming row, column, and missing-cell summary",
    },
    "structure_inspect": {
        "version": "1.0.0",
        "inputs": ["PDB", "MMCIF"],
        "outputs": ["JSON"],
        "description": "Streaming structural-record metadata inspection",
    },
}

INITIAL_WORKFLOW_LIBRARY = {
    "genomics_fasta_qc": {
        "domain": "genomics",
        "steps": [
            {"id": "manifest", "tool": "file_manifest", "dependencies": []},
            {"id": "qc", "tool": "fasta_qc", "dependencies": ["manifest"]},
        ],
        "status": "native_executable",
    },
    "genomics_fastq_qc": {
        "domain": "genomics",
        "steps": [
            {"id": "manifest", "tool": "file_manifest", "dependencies": []},
            {"id": "qc", "tool": "fastq_qc", "dependencies": ["manifest"]},
        ],
        "status": "native_executable",
    },
    "variant_vcf_qc": {
        "domain": "population_genetics",
        "steps": [{"id": "qc", "tool": "vcf_qc", "dependencies": []}],
        "status": "native_executable",
    },
    "omics_table_qc": {
        "domain": "transcriptomics_proteomics_microbiome",
        "steps": [{"id": "qc", "tool": "tabular_qc", "dependencies": []}],
        "status": "native_executable",
    },
    "structure_metadata": {
        "domain": "structural_biology",
        "steps": [{"id": "inspect", "tool": "structure_inspect", "dependencies": []}],
        "status": "native_executable",
    },
    "alignment_variant_annotation": {
        "domain": "genomics",
        "steps": [],
        "status": "adapter_only_not_bundled",
    },
    "single_cell_clustering": {
        "domain": "single_cell",
        "steps": [],
        "status": "adapter_only_not_bundled",
    },
    "taxonomic_classification": {
        "domain": "metagenomics",
        "steps": [],
        "status": "adapter_only_not_bundled",
    },
    "docking": {
        "domain": "structural_biology",
        "steps": [],
        "status": "adapter_only_not_bundled",
    },
    "phylogenetics": {
        "domain": "pathogen_surveillance",
        "steps": [],
        "status": "adapter_only_not_bundled",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_format(path: Path, declared: str = "") -> tuple[str, dict[str, Any]]:
    declared = declared.upper().replace(" ", "_")
    suffixes = {
        ".fa": "FASTA",
        ".fasta": "FASTA",
        ".fq": "FASTQ",
        ".fastq": "FASTQ",
        ".bam": "BAM",
        ".cram": "CRAM",
        ".sam": "SAM",
        ".vcf": "VCF",
        ".bcf": "BCF",
        ".gff": "GFF",
        ".gff3": "GFF",
        ".gtf": "GTF",
        ".bed": "BED",
        ".csv": "CSV",
        ".tsv": "TSV",
        ".xlsx": "XLSX",
        ".json": "JSON",
        ".h5": "HDF5",
        ".hdf5": "HDF5",
        ".h5ad": "ANNDATA",
        ".mtx": "MATRIX_MARKET",
        ".pdb": "PDB",
        ".cif": "MMCIF",
        ".mmcif": "MMCIF",
        ".mzml": "MZML",
        ".dcm": "DICOM_METADATA",
    }
    inferred = suffixes.get(path.suffix.lower(), declared)
    if not inferred or inferred not in SUPPORTED_FORMATS:
        raise ResearchPlatformError("Unsupported research data format.")
    with path.open("rb") as handle:
        head = handle.read(4096)
    valid = True
    detail = "extension and bounded signature inspection"
    if inferred == "FASTA":
        valid = head.lstrip().startswith(b">")
    elif inferred == "FASTQ":
        lines = head.splitlines()
        valid = len(lines) >= 3 and lines[0].startswith(b"@") and lines[2].startswith(b"+")
    elif inferred == "CRAM":
        valid = head.startswith(b"CRAM")
    elif inferred == "BCF":
        valid = head.startswith(b"BCF")
    elif inferred == "VCF":
        valid = head.startswith(b"##fileformat=VCF")
    elif inferred in {"HDF5", "ANNDATA"}:
        valid = head.startswith(b"\x89HDF\r\n\x1a\n")
    elif inferred == "XLSX":
        valid = head.startswith(b"PK")
    elif inferred == "JSON":
        valid = head.lstrip().startswith((b"{", b"["))
    elif inferred == "MATRIX_MARKET":
        valid = head.startswith(b"%%MatrixMarket")
    elif inferred == "MMCIF":
        valid = head.lstrip().startswith(b"data_")
    elif inferred == "PDB":
        valid = any(head.startswith(prefix) for prefix in (b"HEADER", b"ATOM", b"MODEL", b"TITLE"))
    elif inferred == "MZML":
        valid = b"<mzML" in head or b"<indexedmzML" in head
    elif inferred == "DICOM_METADATA":
        valid = len(head) >= 132 and head[128:132] == b"DICM"
        detail = "metadata container signature only; no diagnostic interpretation"
    elif inferred == "BAM":
        valid = head.startswith((b"BAM\x01", b"\x1f\x8b"))
        detail = "BAM/BGZF signature only"
    if not valid:
        raise IntegrityFailure(f"{inferred} signature validation failed.")
    return inferred, {"validation": detail, "head_bytes_inspected": len(head)}


class ResearchCompute:
    def __init__(self, database: str | Path, storage_root: str | Path):
        self.store = PlatformStore(database)
        self.storage_root = Path(storage_root).resolve() / "phase34-research-compute"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.storage_root / ".adapter-key"
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(self.key_path, 0o600)
        except OSError:
            pass
        self._cipher = Fernet(self.key_path.read_bytes())
        self.seed_native_tools()

    def _audit(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        object_type: str,
        object_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_compute_audit VALUES(?,?,?,?,?,?,?,?)""",
                (
                    new_id("computeaudit"),
                    tenant_id,
                    actor_id,
                    action,
                    object_type,
                    object_id,
                    canonical_json(details or {}),
                    now_utc(),
                ),
            )

    def seed_native_tools(self) -> int:
        count = 0
        with self.store.connection() as connection:
            for name, definition in NATIVE_TOOLS.items():
                checksum = hashlib.sha256(canonical_json(definition).encode()).hexdigest()
                result = connection.execute(
                    """INSERT OR IGNORE INTO education_p34_tools
                    (tool_id,tool_name,tool_version,source,adapter_type,handler_key,
                     executable_reference,container_reference,checksum,licence,
                     parameters_schema_json,expected_inputs_json,expected_outputs_json,
                     resource_requirements_json,permission_level,validation_status,
                     approved,approved_by,approved_at_utc,state)
                    VALUES(?,?,?,'BioIntel built-in','native_python',?,'','',?,
                    'BioIntel internal',?,?,?,?,'researcher',
                    'Internal Technical Validation',1,'system',?,'active')""",
                    (
                        new_id("tool"),
                        name,
                        definition["version"],
                        name,
                        checksum,
                        canonical_json({"type": "object", "additionalProperties": False}),
                        canonical_json(definition["inputs"]),
                        canonical_json(definition["outputs"]),
                        canonical_json({"cpu": 1, "memory_mb": 512}),
                        now_utc(),
                    ),
                )
                count += int(result.rowcount == 1)
        return count

    def create_project(
        self,
        tenant_id: str,
        owner_id: str,
        institution_id: str,
        *,
        title: str,
        hypothesis: str = "",
        objectives: list[str] | None = None,
        milestones: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise ResearchPlatformError("Research project title is required.")
        project_id = new_id("research")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_research_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project_id,
                    tenant_id,
                    owner_id,
                    institution_id,
                    title[:300],
                    hypothesis[:5000],
                    canonical_json(objectives or []),
                    canonical_json(milestones or []),
                    "[]",
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO education_p34_project_members VALUES(?,?,?,?,?)",
                (project_id, owner_id, "owner", timestamp, owner_id),
            )
        self._audit(tenant_id, owner_id, "project_created", "project", project_id)
        return self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=?",
            (project_id,),
        ) or {}

    def projects(self, tenant_id: str, *, include_archived: bool = False) -> list[dict[str, Any]]:
        state_clause = "" if include_archived else " AND state='active'"
        return self.store.all(
            "SELECT * FROM education_p34_research_projects WHERE tenant_id=?"
            f"{state_clause} ORDER BY updated_at_utc DESC",
            (tenant_id,),
        )

    def add_project_asset(
        self,
        project_id: str,
        actor_id: str,
        *,
        asset_type: str,
        title: str,
        content: dict[str, Any],
        version: str = "1.0.0",
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=? AND state='active'",
            (project_id,),
        )
        if not project:
            raise Missing("Active research project not found.")
        if asset_type not in PROJECT_ASSET_TYPES:
            raise ResearchPlatformError("Unsupported project asset type.")
        if source_run_id:
            source = self.store.one(
                "SELECT run_id FROM education_p34_runs WHERE run_id=? AND project_id=?",
                (source_run_id, project_id),
            )
            if not source:
                raise Missing("Source run does not belong to this project.")
        asset_id = new_id("projectasset")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_project_assets VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    asset_id,
                    project_id,
                    asset_type,
                    title[:300],
                    version[:80],
                    canonical_json(content),
                    source_run_id,
                    "active",
                    now_utc(),
                    actor_id,
                ),
            )
        self._audit(
            project["tenant_id"],
            actor_id,
            "project_asset_added",
            asset_type,
            asset_id,
        )
        return self.store.one(
            "SELECT * FROM education_p34_project_assets WHERE asset_id=?",
            (asset_id,),
        ) or {}

    def project_workspace(self, project_id: str) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=?",
            (project_id,),
        )
        if not project:
            raise Missing("Research project not found.")
        return {
            "project": project,
            "members": self.store.all(
                "SELECT * FROM education_p34_project_members WHERE project_id=? ORDER BY role,user_id",
                (project_id,),
            ),
            "assets": self.store.all(
                """SELECT * FROM education_p34_project_assets
                WHERE project_id=? AND archive_state!='deleted'
                ORDER BY created_at_utc DESC""",
                (project_id,),
            ),
            "datasets": self.store.all(
                """SELECT * FROM education_p34_datasets
                WHERE project_id=? AND archive_state!='deleted'
                ORDER BY created_at_utc DESC""",
                (project_id,),
            ),
            "workflows": self.store.all(
                "SELECT * FROM education_p34_workflows WHERE project_id=? ORDER BY created_at_utc DESC",
                (project_id,),
            ),
            "runs": self.store.all(
                "SELECT * FROM education_p34_runs WHERE project_id=? ORDER BY created_at_utc DESC",
                (project_id,),
            ),
        }

    def archive_project(self, project_id: str, actor_id: str) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=?",
            (project_id,),
        )
        if not project:
            raise Missing("Research project not found.")
        if project["owner_id"] != actor_id:
            raise PermissionDenied("Only the project owner may archive it.")
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p34_research_projects
                SET state='archived',updated_at_utc=? WHERE project_id=?""",
                (now_utc(), project_id),
            )
        self._audit(project["tenant_id"], actor_id, "project_archived", "project", project_id)
        return self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=?",
            (project_id,),
        ) or {}

    @staticmethod
    def _safe_import_session(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in row.items()
            if key not in {"encrypted_request", "staging_location"}
        }

    def begin_dataset_import(
        self,
        project_id: str,
        actor_id: str,
        *,
        title: str,
        source_paths: list[str | Path],
        source: str,
        licence: str,
        consent_status: str,
        access_level: str,
        declared_format: str = "",
        description: str = "",
        sample_count: int | None = None,
        metadata_schema: dict[str, Any] | None = None,
        data_dictionary: dict[str, Any] | None = None,
        version: str = "1.0.0",
        lineage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=? AND state='active'",
            (project_id,),
        )
        if not project:
            raise Missing("Active research project not found.")
        if not source_paths or len(source_paths) > 10_000:
            raise ResearchPlatformError("Dataset requires between one and 10,000 files.")
        manifest = []
        resolved_paths = []
        total = 0
        for index, source_path in enumerate(source_paths):
            path = Path(source_path).resolve()
            if not path.is_file():
                raise Missing(f"Dataset file not found: {path.name}")
            size = path.stat().st_size
            if size > 2 * 1024**4:
                raise ResearchPlatformError("A dataset file exceeds the 2 TiB registry limit.")
            file_format, validation = detect_format(path, declared_format)
            digest = sha256_file(path)
            safe_name = f"{index:05d}-{path.name}"
            manifest.append(
                {
                    "name": path.name,
                    "staged_name": safe_name,
                    "size_bytes": size,
                    "sha256": digest,
                    "format": file_format,
                    "validation": validation,
                }
            )
            resolved_paths.append(str(path))
            total += size
        session_id = new_id("datasetimport")
        staging = (
            self.storage_root
            / project["tenant_id"]
            / project_id
            / "import-staging"
            / session_id
        ).resolve()
        staging.mkdir(parents=True, exist_ok=False)
        request = {
            "title": title,
            "source_paths": resolved_paths,
            "source": source,
            "licence": licence,
            "consent_status": consent_status,
            "access_level": access_level,
            "declared_format": declared_format,
            "description": description,
            "sample_count": sample_count,
            "metadata_schema": metadata_schema or {},
            "data_dictionary": data_dictionary or {},
            "version": version,
            "lineage": lineage or [],
        }
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_dataset_import_sessions
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    project_id,
                    project["tenant_id"],
                    actor_id,
                    self._cipher.encrypt(canonical_json(request).encode()).decode(),
                    canonical_json(manifest),
                    str(staging),
                    "pending",
                    0,
                    total,
                    new_id("support"),
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        row = self.store.one(
            "SELECT * FROM education_p34_dataset_import_sessions WHERE session_id=?",
            (session_id,),
        )
        return self._safe_import_session(row or {})

    def resume_dataset_import(
        self,
        session_id: str,
        actor_id: str,
        *,
        max_bytes: int = 256 * 1024**2,
    ) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p34_dataset_import_sessions WHERE session_id=?",
            (session_id,),
        )
        if not row:
            raise Missing("Dataset import session not found.")
        if row["actor_id"] != actor_id:
            raise PermissionDenied("Only the import owner may resume it.")
        if row["state"] == "completed":
            return self._safe_import_session(row)
        if row["state"] == "cancelled":
            raise Conflict("Dataset import session is not resumable.")
        if max_bytes < 1:
            raise ResearchPlatformError("Import byte budget must be positive.")
        staging = Path(row["staging_location"]).resolve()
        if not staging.is_relative_to(self.storage_root) or not staging.is_dir():
            raise IntegrityFailure("Dataset import staging directory is unsafe or missing.")
        request = json.loads(self._cipher.decrypt(row["encrypted_request"].encode()))
        manifest = json.loads(row["source_manifest_json"])
        remaining_budget = max_bytes
        try:
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_dataset_import_sessions
                    SET state='copying',updated_at_utc=? WHERE session_id=?""",
                    (now_utc(), session_id),
                )
            for source_text, item in zip(request["source_paths"], manifest, strict=True):
                source_path = Path(source_text).resolve()
                if (
                    not source_path.is_file()
                    or source_path.stat().st_size != item["size_bytes"]
                ):
                    raise IntegrityFailure("Import source changed or disappeared.")
                target = staging / item["staged_name"]
                partial = target.with_name(f"{target.name}.part")
                if target.is_file():
                    continue
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > item["size_bytes"]:
                    raise IntegrityFailure("Resumable import offset exceeds source size.")
                with source_path.open("rb") as source_handle, partial.open("ab") as target_handle:
                    source_handle.seek(offset)
                    while remaining_budget:
                        block = source_handle.read(min(4 * 1024**2, remaining_budget))
                        if not block:
                            break
                        target_handle.write(block)
                        remaining_budget -= len(block)
                if partial.stat().st_size == item["size_bytes"]:
                    if sha256_file(partial) != item["sha256"]:
                        raise IntegrityFailure("Resumable import checksum mismatch.")
                    os.replace(partial, target)
                if remaining_budget == 0:
                    break
            imported = sum(
                (staging / item["staged_name"]).stat().st_size
                if (staging / item["staged_name"]).exists()
                else (staging / f"{item['staged_name']}.part").stat().st_size
                if (staging / f"{item['staged_name']}.part").exists()
                else 0
                for item in manifest
            )
            complete = imported == int(row["total_bytes"])
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_dataset_import_sessions
                    SET state=?,imported_bytes=?,updated_at_utc=? WHERE session_id=?""",
                    ("copying" if complete else "paused", imported, now_utc(), session_id),
                )
            if complete:
                values = dict(request)
                values["source_paths"] = [staging / item["staged_name"] for item in manifest]
                dataset = self.register_dataset(row["project_id"], actor_id, **values)
                with self.store.connection() as connection:
                    connection.execute(
                        """UPDATE education_p34_dataset_import_sessions
                        SET state='completed',dataset_id=?,updated_at_utc=? WHERE session_id=?""",
                        (dataset["dataset_id"], now_utc(), session_id),
                    )
                shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_dataset_import_sessions
                    SET state='failed',updated_at_utc=? WHERE session_id=?""",
                    (now_utc(), session_id),
                )
            raise
        refreshed = self.store.one(
            "SELECT * FROM education_p34_dataset_import_sessions WHERE session_id=?",
            (session_id,),
        )
        return self._safe_import_session(refreshed or {})

    def cancel_dataset_import(self, session_id: str, actor_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p34_dataset_import_sessions WHERE session_id=?",
            (session_id,),
        )
        if not row:
            raise Missing("Dataset import session not found.")
        if row["actor_id"] != actor_id:
            raise PermissionDenied("Only the import owner may cancel it.")
        staging = Path(row["staging_location"]).resolve()
        if not staging.is_relative_to(self.storage_root):
            raise IntegrityFailure("Dataset import staging path is unsafe.")
        if staging.exists():
            shutil.rmtree(staging)
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p34_dataset_import_sessions
                SET state='cancelled',updated_at_utc=? WHERE session_id=?""",
                (now_utc(), session_id),
            )
        refreshed = self.store.one(
            "SELECT * FROM education_p34_dataset_import_sessions WHERE session_id=?",
            (session_id,),
        )
        return self._safe_import_session(refreshed or {})

    def register_dataset(
        self,
        project_id: str,
        actor_id: str,
        *,
        title: str,
        source_paths: list[str | Path],
        source: str,
        licence: str,
        consent_status: str,
        access_level: str,
        declared_format: str = "",
        description: str = "",
        sample_count: int | None = None,
        metadata_schema: dict[str, Any] | None = None,
        data_dictionary: dict[str, Any] | None = None,
        version: str = "1.0.0",
        lineage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=? AND state='active'",
            (project_id,),
        )
        if not project:
            raise Missing("Active research project not found.")
        if not source_paths or len(source_paths) > 10_000:
            raise ResearchPlatformError("Dataset requires between one and 10,000 files.")
        dataset_id = new_id("dataset")
        destination = self.storage_root / project["tenant_id"] / project_id / "datasets" / dataset_id
        destination.mkdir(parents=True, exist_ok=False)
        manifest = []
        total = 0
        try:
            for index, source_path in enumerate(source_paths):
                path = Path(source_path).resolve()
                if not path.is_file():
                    raise Missing(f"Dataset file not found: {path.name}")
                if path.stat().st_size > 2 * 1024**4:
                    raise ResearchPlatformError("A dataset file exceeds the 2 TiB registry limit.")
                file_format, validation = detect_format(path, declared_format)
                digest = sha256_file(path)
                target = destination / f"{index:05d}-{path.name}"
                shutil.copyfile(path, target)
                if sha256_file(target) != digest:
                    raise IntegrityFailure("Copied dataset file checksum mismatch.")
                manifest.append(
                    {
                        "path": target.name,
                        "original_name": path.name,
                        "size_bytes": path.stat().st_size,
                        "sha256": digest,
                        "format": file_format,
                        "validation": validation,
                    }
                )
                total += path.stat().st_size
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        manifest_hash = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
        detected_formats = sorted({row["format"] for row in manifest})
        dataset_format = detected_formats[0] if len(detected_formats) == 1 else "MIXED"
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_datasets
                (dataset_id,project_id,tenant_id,owner_id,institution_id,title,description,
                 source,licence,consent_status,access_level,format,sample_count,
                 metadata_schema_json,data_dictionary_json,version,lineage_json,quality_status,
                 archive_state,storage_location,total_size_bytes,manifest_sha256,
                 created_at_utc,created_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'validated','active',?,?,?,?,?)""",
                (
                    dataset_id,
                    project_id,
                    project["tenant_id"],
                    actor_id,
                    project["institution_id"],
                    title[:300],
                    description[:5000],
                    source[:1000],
                    licence[:300],
                    consent_status[:120],
                    access_level[:80],
                    dataset_format,
                    sample_count,
                    canonical_json(metadata_schema or {}),
                    canonical_json(data_dictionary or {}),
                    version[:80],
                    canonical_json(lineage or []),
                    str(destination),
                    total,
                    manifest_hash,
                    timestamp,
                    actor_id,
                ),
            )
            for row in manifest:
                connection.execute(
                    """INSERT INTO education_p34_dataset_files VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        new_id("datasetfile"),
                        dataset_id,
                        row["path"],
                        row["size_bytes"],
                        row["sha256"],
                        row["format"],
                        "validated",
                        canonical_json(row["validation"]),
                        row["size_bytes"],
                        "completed",
                        timestamp,
                    ),
                )
            connection.execute(
                """INSERT INTO education_p34_import_history VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("import"),
                    dataset_id,
                    hashlib.sha256(
                        canonical_json([str(Path(path).name) for path in source_paths]).encode()
                    ).hexdigest(),
                    total,
                    total,
                    "completed",
                    new_id("support"),
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            project["tenant_id"],
            actor_id,
            "dataset_registered",
            "dataset",
            dataset_id,
            {"files": len(manifest), "sha256": manifest_hash},
        )
        return self.dataset(dataset_id)

    def dataset(self, dataset_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p34_datasets WHERE dataset_id=?",
            (dataset_id,),
        )
        if not row:
            raise Missing("Research dataset not found.")
        row["files"] = self.store.all(
            "SELECT * FROM education_p34_dataset_files WHERE dataset_id=? ORDER BY relative_path",
            (dataset_id,),
        )
        return row

    def datasets(self, project_id: str) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT * FROM education_p34_datasets
            WHERE project_id=? AND archive_state='active' ORDER BY created_at_utc DESC""",
            (project_id,),
        )

    def approved_tools(self) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT tool_id,tool_name,tool_version,adapter_type,handler_key,checksum,
            licence,expected_inputs_json,expected_outputs_json,resource_requirements_json,
            permission_level,validation_status,state FROM education_p34_tools
            WHERE approved=1 AND state='active' ORDER BY tool_name"""
        )

    def define_workflow(
        self,
        project_id: str,
        actor_id: str,
        *,
        name: str,
        domain: str,
        version: str,
        steps: list[dict[str, Any]],
        approve: bool = False,
        approver_role: str = "",
    ) -> dict[str, Any]:
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=?",
            (project_id,),
        )
        if not project:
            raise Missing("Research project not found.")
        if not steps:
            raise ResearchPlatformError("Workflow requires at least one controlled step.")
        by_id = {}
        tools = {
            row["tool_name"]: row
            for row in self.store.all(
                "SELECT * FROM education_p34_tools WHERE approved=1 AND state='active'"
            )
        }
        for step in steps:
            step_id = str(step.get("id", ""))
            tool_name = str(step.get("tool", ""))
            if not step_id or step_id in by_id:
                raise ResearchPlatformError("Workflow step IDs must be unique and non-empty.")
            if tool_name not in tools:
                raise PermissionDenied(f"Workflow tool is not approved: {tool_name}")
            if any(key in step for key in ("command", "shell", "executable")):
                raise PermissionDenied("Ordinary workflows cannot contain arbitrary commands.")
            parameters = dict(step.get("parameters", {}))
            parameter_schema = json.loads(tools[tool_name]["parameters_schema_json"])
            if parameters and parameter_schema.get("additionalProperties") is False:
                raise ResearchPlatformError(
                    f"Tool {tool_name} does not accept workflow parameters."
                )
            resources = dict(step.get("resources", {}))
            cpu = max(1, min(int(resources.get("cpu", 1)), 128))
            memory_mb = max(128, min(int(resources.get("memory_mb", 512)), 1_048_576))
            disk_mb = max(128, min(int(resources.get("disk_mb", 1024)), 10_485_760))
            by_id[step_id] = {
                "id": step_id,
                "tool": tool_name,
                "tool_id": tools[tool_name]["tool_id"],
                "dependencies": list(step.get("dependencies", [])),
                "parameters": parameters,
                "inputs": json.loads(tools[tool_name]["expected_inputs_json"]),
                "outputs": json.loads(tools[tool_name]["expected_outputs_json"]),
                "resources": {
                    "cpu": cpu,
                    "memory_mb": memory_mb,
                    "disk_mb": disk_mb,
                    "gpu": 0,
                },
                "timeout_seconds": int(step.get("timeout_seconds", 300)),
                "retries": int(step.get("retries", 0)),
                "cache": bool(step.get("cache", True)),
                "checkpoint": bool(step.get("checkpoint", True)),
            }
        for step in by_id.values():
            if set(step["dependencies"]).difference(by_id):
                raise ResearchPlatformError("Workflow dependency is missing.")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ResearchPlatformError("Workflow dependency graph contains a cycle.")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id]["dependencies"]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in by_id:
            visit(step_id)
        if approve and approver_role not in {"platform_administrator", "institution_administrator"}:
            raise PermissionDenied("Administrator approval is required for workflow activation.")
        specification = {
            "schema": "biointel.research-workflow.v1",
            "name": name,
            "domain": domain,
            "version": version,
            "steps": list(by_id.values()),
            "execution": "controlled_native_adapters_only",
        }
        digest = hashlib.sha256(canonical_json(specification).encode()).hexdigest()
        workflow_id = new_id("workflow")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_workflows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    workflow_id,
                    project_id,
                    name[:300],
                    domain[:120],
                    version[:80],
                    canonical_json(specification),
                    digest,
                    "Internal Technical Validation",
                    "approved" if approve else "draft",
                    actor_id if approve else None,
                    timestamp if approve else None,
                    timestamp,
                    actor_id,
                ),
            )
        self._audit(project["tenant_id"], actor_id, "workflow_defined", "workflow", workflow_id)
        return self.store.one(
            "SELECT * FROM education_p34_workflows WHERE workflow_id=?",
            (workflow_id,),
        ) or {}

    def workflows(self, project_id: str, *, approved_only: bool = False) -> list[dict[str, Any]]:
        state_clause = " AND state='approved'" if approved_only else ""
        return self.store.all(
            "SELECT * FROM education_p34_workflows WHERE project_id=?"
            f"{state_clause} ORDER BY created_at_utc DESC",
            (project_id,),
        )

    def set_quota(
        self,
        tenant_id: str,
        administrator_id: str,
        *,
        administrator_role: str,
        user_id: str = "*",
        max_concurrent_runs: int = 2,
        max_queued_runs: int = 100,
        max_cpu: int = 8,
        max_memory_mb: int = 32_768,
        max_disk_mb: int = 262_144,
        max_gpu: int = 0,
    ) -> dict[str, Any]:
        if administrator_role not in {"platform_administrator", "institution_administrator"}:
            raise PermissionDenied("Administrator role is required to configure compute quotas.")
        values = (
            max(1, min(max_concurrent_runs, 1024)),
            max(1, min(max_queued_runs, 100_000)),
            max(1, min(max_cpu, 4096)),
            max(128, min(max_memory_mb, 4_194_304)),
            max(128, min(max_disk_mb, 104_857_600)),
            max(0, min(max_gpu, 1024)),
        )
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_compute_quotas VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,user_id) DO UPDATE SET
                max_concurrent_runs=excluded.max_concurrent_runs,
                max_queued_runs=excluded.max_queued_runs,max_cpu=excluded.max_cpu,
                max_memory_mb=excluded.max_memory_mb,max_disk_mb=excluded.max_disk_mb,
                max_gpu=excluded.max_gpu,updated_at_utc=excluded.updated_at_utc,
                updated_by=excluded.updated_by""",
                (
                    tenant_id,
                    user_id,
                    *values,
                    now_utc(),
                    administrator_id,
                ),
            )
        return self.quota(tenant_id, user_id)

    def quota(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        row = self.store.one(
            """SELECT * FROM education_p34_compute_quotas
            WHERE tenant_id=? AND user_id IN (?, '*')
            ORDER BY CASE WHEN user_id=? THEN 0 ELSE 1 END LIMIT 1""",
            (tenant_id, user_id, user_id),
        )
        return row or {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "max_concurrent_runs": 2,
            "max_queued_runs": 100,
            "max_cpu": 8,
            "max_memory_mb": 32768,
            "max_disk_mb": 262144,
            "max_gpu": 0,
            "source": "safe_default",
        }

    def submit_run(
        self,
        project_id: str,
        workflow_id: str,
        dataset_id: str,
        user_id: str,
        *,
        idempotency_key: str,
        parameters: dict[str, Any] | None = None,
        priority: int = 50,
        max_retries: int = 1,
        timeout_seconds: int = 900,
        cpu_limit: int = 1,
        memory_limit_mb: int = 1024,
        disk_limit_mb: int = 4096,
        gpu_limit: int = 0,
        seed: int = 42,
    ) -> dict[str, Any]:
        existing = self.store.one(
            "SELECT * FROM education_p34_runs WHERE idempotency_key=?",
            (idempotency_key,),
        )
        if existing:
            return existing
        workflow = self.store.one(
            """SELECT * FROM education_p34_workflows
            WHERE workflow_id=? AND project_id=? AND state='approved'""",
            (workflow_id, project_id),
        )
        dataset = self.store.one(
            "SELECT * FROM education_p34_datasets WHERE dataset_id=? AND project_id=?",
            (dataset_id, project_id),
        )
        project = self.store.one(
            "SELECT * FROM education_p34_research_projects WHERE project_id=? AND state='active'",
            (project_id,),
        )
        if not workflow:
            raise PermissionDenied("Only an approved workflow may run.")
        if not dataset or not project:
            raise Missing("Run project or dataset not found.")
        if dataset["tenant_id"] != project["tenant_id"]:
            raise PermissionDenied("Dataset tenant does not match project tenant.")
        quota = self.quota(project["tenant_id"], user_id)
        queued = self.store.one(
            """SELECT COUNT(*) AS count FROM education_p34_runs
            WHERE tenant_id=? AND user_id=? AND state IN ('queued','retrying','awaiting_resources')""",
            (project["tenant_id"], user_id),
        )
        if int((queued or {}).get("count", 0)) >= int(quota["max_queued_runs"]):
            raise PermissionDenied("Per-user queued-run quota is exhausted.")
        requested = {
            "cpu": max(1, min(cpu_limit, 128)),
            "memory_mb": max(128, min(memory_limit_mb, 1_048_576)),
            "disk_mb": max(128, min(disk_limit_mb, 10_485_760)),
            "gpu": max(0, min(gpu_limit, 128)),
        }
        if (
            requested["cpu"] > int(quota["max_cpu"])
            or requested["memory_mb"] > int(quota["max_memory_mb"])
            or requested["disk_mb"] > int(quota["max_disk_mb"])
            or requested["gpu"] > int(quota["max_gpu"])
        ):
            raise PermissionDenied("Requested resources exceed the applicable compute quota.")
        if requested["gpu"]:
            raise PermissionDenied("Local native worker has no validated GPU execution path.")
        dataset_formats = {
            row["format"]
            for row in self.store.all(
                "SELECT format FROM education_p34_dataset_files WHERE dataset_id=?",
                (dataset_id,),
            )
        }
        specification = json.loads(workflow["specification_json"])
        for step in specification["steps"]:
            allowed = set(step["inputs"])
            if not dataset_formats.issubset(allowed):
                raise ResearchPlatformError(
                    f"Dataset format is incompatible with workflow step {step['id']}."
                )
        run_id = new_id("run")
        support = new_id("support")
        environment = {
            "os": platform.platform(),
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "execution": "local_native",
            "environment_lock": "Python runtime and approved tool checksums captured in bundle",
            "resources": requested,
            "gpu_validated": False,
        }
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_runs
                (run_id,idempotency_key,project_id,workflow_id,dataset_id,tenant_id,user_id,
                 institution_id,state,priority,max_retries,timeout_seconds,cpu_limit,
                 memory_limit_mb,disk_limit_mb,seed,parameters_json,workflow_version,
                 environment_json,support_reference,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?, 'queued',?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    idempotency_key,
                    project_id,
                    workflow_id,
                    dataset_id,
                    project["tenant_id"],
                    user_id,
                    project["institution_id"],
                    max(0, min(priority, 100)),
                    max(0, min(max_retries, 10)),
                    max(1, min(timeout_seconds, 7 * 24 * 3600)),
                    requested["cpu"],
                    requested["memory_mb"],
                    requested["disk_mb"],
                    seed,
                    canonical_json(parameters or {}),
                    workflow["version"],
                    canonical_json(environment),
                    support,
                    now_utc(),
                ),
            )
            for step in specification["steps"]:
                connection.execute(
                    """INSERT INTO education_p34_run_steps
                    (run_step_id,run_id,step_id,tool_id,state,input_manifest_json)
                    VALUES(?,?,?,?, 'queued','{}')""",
                    (new_id("runstep"), run_id, step["id"], step["tool_id"]),
                )
        self._audit(project["tenant_id"], user_id, "run_submitted", "run", run_id)
        return self.run(run_id)

    def run(self, run_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM education_p34_runs WHERE run_id=?", (run_id,))
        if not row:
            raise Missing("Research Compute run not found.")
        return row

    @staticmethod
    def _topological_steps(specification: dict[str, Any]) -> list[dict[str, Any]]:
        pending = {step["id"]: step for step in specification["steps"]}
        ordered = []
        completed: set[str] = set()
        while pending:
            ready = [
                step
                for step in pending.values()
                if set(step["dependencies"]).issubset(completed)
            ]
            if not ready:
                raise IntegrityFailure("Approved workflow graph is no longer acyclic.")
            for step in sorted(ready, key=lambda item: item["id"]):
                ordered.append(step)
                completed.add(step["id"])
                pending.pop(step["id"])
        return ordered

    def _dataset_paths(self, dataset_id: str) -> list[Path]:
        dataset = self.dataset(dataset_id)
        base = Path(dataset["storage_location"]).resolve()
        paths = []
        for row in dataset["files"]:
            path = (base / row["relative_path"]).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise IntegrityFailure("Dataset file escaped storage or is missing.")
            if sha256_file(path) != row["sha256"]:
                raise IntegrityFailure("Dataset file checksum changed.")
            paths.append(path)
        return paths

    @staticmethod
    def _file_manifest(paths: list[Path]) -> dict[str, Any]:
        return {
            "files": [
                {"name": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path in paths
            ]
        }

    @staticmethod
    def _fasta_qc(paths: list[Path]) -> dict[str, Any]:
        sequences = 0
        bases = 0
        gc = 0
        ambiguous = 0
        for path in paths:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    text = line.strip().upper()
                    if not text:
                        continue
                    if text.startswith(">"):
                        sequences += 1
                        continue
                    bases += len(text)
                    gc += text.count("G") + text.count("C")
                    ambiguous += sum(character not in {"A", "C", "G", "T", "U"} for character in text)
        return {
            "sequence_count": sequences,
            "total_bases": bases,
            "mean_length": bases / sequences if sequences else 0,
            "gc_fraction": gc / bases if bases else 0,
            "ambiguous_bases": ambiguous,
        }

    @staticmethod
    def _fastq_qc(paths: list[Path]) -> dict[str, Any]:
        reads = 0
        bases = 0
        quality_sum = 0
        for path in paths:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                record = []
                for line in handle:
                    record.append(line.rstrip("\n"))
                    if len(record) == 4:
                        if not record[0].startswith("@") or not record[2].startswith("+"):
                            raise IntegrityFailure("Malformed FASTQ record.")
                        reads += 1
                        bases += len(record[1])
                        quality_sum += sum(max(0, ord(character) - 33) for character in record[3])
                        record = []
                if record:
                    raise IntegrityFailure("Truncated FASTQ record.")
        return {
            "read_count": reads,
            "total_bases": bases,
            "mean_read_length": bases / reads if reads else 0,
            "mean_quality": quality_sum / bases if bases else 0,
        }

    @staticmethod
    def _vcf_qc(paths: list[Path]) -> dict[str, Any]:
        variants = 0
        passed = 0
        samples = 0
        for path in paths:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith("#CHROM"):
                        samples = max(samples, max(0, len(line.rstrip().split("\t")) - 9))
                    elif not line.startswith("#") and line.strip():
                        columns = line.rstrip().split("\t")
                        variants += 1
                        passed += int(len(columns) > 6 and columns[6] in {"PASS", "."})
        return {"variant_count": variants, "pass_count": passed, "sample_count": samples}

    @staticmethod
    def _tabular_qc(paths: list[Path]) -> dict[str, Any]:
        rows = 0
        columns: set[str] = set()
        missing = 0
        for path in paths:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                columns.update(reader.fieldnames or [])
                for row in reader:
                    rows += 1
                    missing += sum(value is None or str(value).strip() == "" for value in row.values())
        return {"row_count": rows, "column_count": len(columns), "columns": sorted(columns), "missing_cells": missing}

    @staticmethod
    def _structure_inspect(paths: list[Path]) -> dict[str, Any]:
        atoms = 0
        models = 0
        chains: set[str] = set()
        for path in paths:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith(("ATOM  ", "HETATM")):
                        atoms += 1
                        if len(line) > 21:
                            chains.add(line[21].strip() or "_")
                    elif line.startswith("MODEL"):
                        models += 1
        return {"atom_records": atoms, "models": max(models, 1 if atoms else 0), "chains": sorted(chains)}

    def _handler(self, key: str) -> Callable[[list[Path]], dict[str, Any]]:
        handlers = {
            "file_manifest": self._file_manifest,
            "fasta_qc": self._fasta_qc,
            "fastq_qc": self._fastq_qc,
            "vcf_qc": self._vcf_qc,
            "tabular_qc": self._tabular_qc,
            "structure_inspect": self._structure_inspect,
        }
        if key not in handlers:
            raise PermissionDenied("Approved tool has no controlled local handler.")
        return handlers[key]

    def execute_run(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id is None:
            candidate = self.store.one(
                """SELECT run_id FROM education_p34_runs
                WHERE state IN ('queued','retrying') ORDER BY priority DESC,created_at_utc LIMIT 1"""
            )
            if not candidate:
                raise Missing("No queued Research Compute run.")
            run_id = candidate["run_id"]
        with self.store.connection() as connection:
            claimed = connection.execute(
                """UPDATE education_p34_runs SET state='preparing',attempt=attempt+1,
                started_at_utc=COALESCE(started_at_utc,?)
                WHERE run_id=? AND state IN ('queued','retrying')""",
                (now_utc(), run_id),
            )
            if claimed.rowcount != 1:
                raise Conflict("Run is not claimable; duplicate execution was prevented.")
        run = self.run(run_id)
        quota = self.quota(run["tenant_id"], run["user_id"])
        active = self.store.one(
            """SELECT COUNT(*) AS count FROM education_p34_runs
            WHERE tenant_id=? AND user_id=? AND state IN ('preparing','running')""",
            (run["tenant_id"], run["user_id"]),
        )
        if int((active or {}).get("count", 0)) > int(quota["max_concurrent_runs"]):
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_runs SET state='awaiting_resources',
                    safe_message=? WHERE run_id=?""",
                    ("Per-user concurrency quota is currently occupied.", run_id),
                )
            return self.run(run_id)
        workflow = self.store.one(
            "SELECT * FROM education_p34_workflows WHERE workflow_id=?",
            (run["workflow_id"],),
        )
        if not workflow or workflow["state"] != "approved":
            raise PermissionDenied("Workflow approval was revoked before execution.")
        workspace = self.storage_root / run["tenant_id"] / run["project_id"] / "runs" / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        dataset_size = self.store.one(
            "SELECT COALESCE(SUM(size_bytes),0) AS bytes FROM education_p34_dataset_files WHERE dataset_id=?",
            (run["dataset_id"],),
        )
        configured_disk_bytes = int(run["disk_limit_mb"]) * 1024**2
        required_scratch_bytes = min(
            configured_disk_bytes,
            max(64 * 1024**2, int((dataset_size or {}).get("bytes", 0)) * 4),
        )
        if shutil.disk_usage(workspace).free < required_scratch_bytes:
            with self.store.connection() as connection:
                connection.execute(
                    "UPDATE education_p34_runs SET state='awaiting_resources',safe_message=? WHERE run_id=?",
                    ("Insufficient free disk for the bounded dataset scratch estimate.", run_id),
                )
            return self.run(run_id)
        specification = json.loads(workflow["specification_json"])
        started = time.monotonic()
        completed_steps = 0
        try:
            paths = self._dataset_paths(run["dataset_id"])
            with self.store.connection() as connection:
                connection.execute(
                    "UPDATE education_p34_runs SET state='running' WHERE run_id=?",
                    (run_id,),
                )
            for step in self._topological_steps(specification):
                fresh = self.run(run_id)
                if fresh["cancellation_requested"]:
                    with self.store.connection() as connection:
                        connection.execute(
                            "UPDATE education_p34_runs SET state='cancelled',ended_at_utc=? WHERE run_id=?",
                            (now_utc(), run_id),
                        )
                    return self.run(run_id)
                if time.monotonic() - started > int(run["timeout_seconds"]):
                    raise TimeoutError("run_timeout")
                existing_step = self.store.one(
                    """SELECT * FROM education_p34_run_steps
                    WHERE run_id=? AND step_id=?""",
                    (run_id, step["id"]),
                )
                if existing_step and existing_step["state"] == "completed":
                    checkpoint = json.loads(existing_step["checkpoint_json"])
                    output_path = workspace / f"{step['id']}.json"
                    if (
                        checkpoint.get("completed")
                        and output_path.is_file()
                        and sha256_file(output_path) == checkpoint.get("sha256")
                    ):
                        completed_steps += 1
                        continue
                    raise IntegrityFailure("Completed-step checkpoint integrity failed.")
                tool = self.store.one(
                    """SELECT * FROM education_p34_tools
                    WHERE tool_id=? AND approved=1 AND state='active'""",
                    (step["tool_id"],),
                )
                if not tool:
                    raise PermissionDenied("A workflow tool was disabled or revoked.")
                step_started = time.monotonic()
                with self.store.connection() as connection:
                    connection.execute(
                        """UPDATE education_p34_run_steps SET state='running',
                        attempt=attempt+1,started_at_utc=? WHERE run_id=? AND step_id=?""",
                        (now_utc(), run_id, step["id"]),
                    )
                output = self._handler(tool["handler_key"])(paths)
                if time.monotonic() - step_started > int(step["timeout_seconds"]):
                    raise TimeoutError(f"step_timeout:{step['id']}")
                output["parameters"] = step["parameters"]
                output["tool"] = {
                    "name": tool["tool_name"],
                    "version": tool["tool_version"],
                    "checksum": tool["checksum"],
                }
                output_path = workspace / f"{step['id']}.json"
                output_path.write_text(
                    json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                digest = sha256_file(output_path)
                relative = output_path.relative_to(workspace).as_posix()
                elapsed = time.monotonic() - step_started
                with self.store.connection() as connection:
                    connection.execute(
                        """UPDATE education_p34_run_steps SET state='completed',
                        output_manifest_json=?,checkpoint_json=?,ended_at_utc=?,log_text=?
                        WHERE run_id=? AND step_id=?""",
                        (
                            canonical_json({"path": relative, "sha256": digest}),
                            canonical_json({"completed": True, "sha256": digest}),
                            now_utc(),
                            f"Controlled native tool completed in {elapsed:.6f}s",
                            run_id,
                            step["id"],
                        ),
                    )
                    connection.execute(
                        """INSERT OR REPLACE INTO education_p34_run_artifacts
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            new_id("artifact"),
                            run_id,
                            step["id"],
                            "result",
                            relative,
                            output_path.stat().st_size,
                            digest,
                            "application/json",
                            0,
                            now_utc(),
                        ),
                    )
                completed_steps += 1
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_runs SET state='completed',ended_at_utc=?,
                    safe_message='Controlled local workflow completed.'
                    WHERE run_id=?""",
                    (now_utc(), run_id),
                )
        except Exception as exc:
            state = "partially_completed" if completed_steps else "failed"
            code = "timeout" if isinstance(exc, TimeoutError) else type(exc).__name__.lower()
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p34_runs SET state=?,ended_at_utc=?,failure_code=?,
                    safe_message=? WHERE run_id=?""",
                    (
                        state,
                        now_utc(),
                        code,
                        "Workflow stopped safely; completed checkpoints were retained.",
                        run_id,
                    ),
                )
            if isinstance(exc, (PermissionDenied, IntegrityFailure, ResearchPlatformError)):
                raise
        return self.run(run_id)

    def cancel_run(self, run_id: str, actor_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        if run["user_id"] != actor_id:
            raise PermissionDenied("Only the run owner may request cancellation.")
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p34_runs SET cancellation_requested=1,
                state=CASE WHEN state IN ('queued','retrying','paused','awaiting_resources')
                THEN 'cancelled' ELSE state END,
                ended_at_utc=CASE WHEN state IN ('queued','retrying','paused','awaiting_resources')
                THEN ? ELSE ended_at_utc END WHERE run_id=?""",
                (now_utc(), run_id),
            )
        return self.run(run_id)

    def retry_run(self, run_id: str, actor_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        if run["user_id"] != actor_id:
            raise PermissionDenied("Only the run owner may retry.")
        if run["state"] not in {"failed", "partially_completed", "cancelled"}:
            raise Conflict("Run is not retryable.")
        if int(run["attempt"]) > int(run["max_retries"]):
            raise Conflict("Run retry limit is exhausted.")
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p34_runs SET state='retrying',
                cancellation_requested=0,failure_code='',safe_message='',ended_at_utc=NULL
                WHERE run_id=?""",
                (run_id,),
            )
            connection.execute(
                """UPDATE education_p34_run_steps SET state='queued'
                WHERE run_id=? AND state!='completed'""",
                (run_id,),
            )
        return self.run(run_id)

    def clone_run(
        self,
        run_id: str,
        actor_id: str,
        *,
        idempotency_key: str,
        parameter_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = self.run(run_id)
        parameters = json.loads(source["parameters_json"])
        parameters.update(parameter_overrides or {})
        environment = json.loads(source["environment_json"])
        resources = environment.get("resources", {})
        return self.submit_run(
            source["project_id"],
            source["workflow_id"],
            source["dataset_id"],
            actor_id,
            idempotency_key=idempotency_key,
            parameters=parameters,
            priority=source["priority"],
            max_retries=source["max_retries"],
            timeout_seconds=source["timeout_seconds"],
            cpu_limit=resources.get("cpu", source["cpu_limit"]),
            memory_limit_mb=resources.get("memory_mb", source["memory_limit_mb"]),
            disk_limit_mb=resources.get("disk_mb", source["disk_limit_mb"]),
            gpu_limit=resources.get("gpu", 0),
            seed=source["seed"],
        )

    def runs(self, project_id: str) -> list[dict[str, Any]]:
        return self.store.all(
            "SELECT * FROM education_p34_runs WHERE project_id=? ORDER BY created_at_utc DESC",
            (project_id,),
        )

    def compare_runs(self, run_ids: list[str]) -> dict[str, Any]:
        if len(run_ids) < 2 or len(run_ids) > 20:
            raise ResearchPlatformError("Compare between two and twenty runs.")
        rows = []
        for run_id in run_ids:
            run = self.run(run_id)
            artifacts = self.store.all(
                "SELECT relative_path,sha256,size_bytes FROM education_p34_run_artifacts WHERE run_id=?",
                (run_id,),
            )
            rows.append(
                {
                    "run_id": run_id,
                    "state": run["state"],
                    "workflow_version": run["workflow_version"],
                    "seed": run["seed"],
                    "artifacts": artifacts,
                }
            )
        return {"runs": rows, "computed": True}

    def export_run_bundle(self, run_id: str) -> bytes:
        run = self.run(run_id)
        workflow = self.store.one(
            "SELECT * FROM education_p34_workflows WHERE workflow_id=?",
            (run["workflow_id"],),
        )
        dataset = self.dataset(run["dataset_id"])
        artifacts = self.store.all(
            "SELECT * FROM education_p34_run_artifacts WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )
        manifest = {
            "schema": "biointel.phase34.reproducibility-bundle.v1",
            "run": run,
            "workflow": workflow,
            "input_manifest_sha256": dataset["manifest_sha256"],
            "artifacts": artifacts,
            "provenance_graph": {
                "nodes": [
                    {"id": run["dataset_id"], "type": "dataset"},
                    {"id": run["workflow_id"], "type": "workflow"},
                    {"id": run_id, "type": "run"},
                    *[{"id": row["artifact_id"], "type": "artifact"} for row in artifacts],
                ],
                "edges": [
                    {"source": run["dataset_id"], "target": run_id, "relation": "input_to"},
                    {"source": run["workflow_id"], "target": run_id, "relation": "defines"},
                    *[
                        {"source": run_id, "target": row["artifact_id"], "relation": "generated"}
                        for row in artifacts
                    ],
                ],
            },
            "claim_boundary": "Local controlled native execution; no remote/HPC validation.",
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
            workspace = (
                self.storage_root
                / run["tenant_id"]
                / run["project_id"]
                / "runs"
                / run_id
            ).resolve()
            for artifact in artifacts:
                path = (workspace / artifact["relative_path"]).resolve()
                if not path.is_relative_to(workspace) or sha256_file(path) != artifact["sha256"]:
                    raise IntegrityFailure("Run artifact integrity failed during export.")
                archive.write(path, f"artifacts/{artifact['relative_path']}")
        return stream.getvalue()

    def inspect_run_bundle(self, data: bytes) -> dict[str, Any]:
        if len(data) > 256 * 1024**2:
            raise ResearchPlatformError("Run bundle exceeds the 256 MiB in-memory inspection limit.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            items = archive.infolist()
            if len(items) > 10_000:
                raise IntegrityFailure("Run bundle contains too many archive entries.")
            total_uncompressed = sum(item.file_size for item in items)
            if total_uncompressed > 2 * 1024**3:
                raise IntegrityFailure("Run bundle uncompressed size exceeds 2 GiB.")
            for item in items:
                if item.file_size > 1024**3:
                    raise IntegrityFailure("Run bundle contains an oversized entry.")
                if item.compress_size and item.file_size / item.compress_size > 1000:
                    raise IntegrityFailure("Run bundle compression ratio is unsafe.")
            if archive.testzip():
                raise IntegrityFailure("Run bundle CRC validation failed.")
            names = [item.filename for item in items]
            if "manifest.json" not in names:
                raise IntegrityFailure("Run bundle manifest is missing.")
            for name in names:
                path = Path(name.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise IntegrityFailure("Unsafe run bundle path.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("schema") != "biointel.phase34.reproducibility-bundle.v1":
                raise IntegrityFailure("Unsupported run bundle schema.")
        return {
            "valid": True,
            "run_id": manifest["run"]["run_id"],
            "artifact_count": len(manifest["artifacts"]),
            "import_execution_performed": False,
        }

    def import_run_bundle(
        self,
        tenant_id: str,
        actor_id: str,
        data: bytes,
    ) -> dict[str, Any]:
        inspection = self.inspect_run_bundle(data)
        digest = hashlib.sha256(data).hexdigest()
        existing = self.store.one(
            "SELECT * FROM education_p34_imported_run_bundles WHERE bundle_sha256=?",
            (digest,),
        )
        if existing:
            return existing
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        imported_id = new_id("importedrun")
        destination = (
            self.storage_root / tenant_id / "imported-run-bundles" / f"{imported_id}.zip"
        ).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".zip.part")
        temporary.write_bytes(data)
        if sha256_file(temporary) != digest:
            temporary.unlink(missing_ok=True)
            raise IntegrityFailure("Imported run bundle checksum mismatch.")
        os.replace(temporary, destination)
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_imported_run_bundles
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    imported_id,
                    tenant_id,
                    actor_id,
                    inspection["run_id"],
                    digest,
                    str(destination),
                    canonical_json(manifest),
                    "reference_only",
                    now_utc(),
                ),
            )
        self._audit(
            tenant_id,
            actor_id,
            "run_bundle_imported_reference_only",
            "imported_run_bundle",
            imported_id,
            {"execution_performed": False},
        )
        return self.store.one(
            "SELECT * FROM education_p34_imported_run_bundles WHERE imported_bundle_id=?",
            (imported_id,),
        ) or {}

    def add_result_note(
        self,
        run_id: str,
        author_id: str,
        *,
        note_type: str,
        body: str,
    ) -> dict[str, Any]:
        run = self.run(run_id)
        if note_type not in {"annotation", "comment", "warning"}:
            raise ResearchPlatformError("Unsupported result note type.")
        if not body.strip():
            raise ResearchPlatformError("Result note cannot be empty.")
        note_id = new_id("resultnote")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_result_notes VALUES(?,?,?,?,?,?)""",
                (note_id, run_id, author_id, note_type, body[:10_000], now_utc()),
            )
        self._audit(run["tenant_id"], author_id, "result_note_added", note_type, note_id)
        return self.store.one(
            "SELECT * FROM education_p34_result_notes WHERE note_id=?",
            (note_id,),
        ) or {}

    def review_run(
        self,
        run_id: str,
        reviewer_id: str,
        *,
        reviewer_role: str,
        decision: str,
        comments: str = "",
    ) -> dict[str, Any]:
        run = self.run(run_id)
        if reviewer_role not in {
            "project_reviewer",
            "institution_administrator",
            "platform_administrator",
        }:
            raise PermissionDenied("Reviewer role is required.")
        if decision not in {"approved", "changes_requested", "rejected"}:
            raise ResearchPlatformError("Unsupported review decision.")
        review_id = new_id("runreview")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_run_reviews VALUES(?,?,?,?,?,?)""",
                (review_id, run_id, reviewer_id, decision, comments[:10_000], now_utc()),
            )
        self._audit(run["tenant_id"], reviewer_id, "run_reviewed", "run", run_id)
        return self.store.one(
            "SELECT * FROM education_p34_run_reviews WHERE review_id=?",
            (review_id,),
        ) or {}

    def publish_to_project(
        self,
        run_id: str,
        actor_id: str,
        *,
        title: str,
    ) -> dict[str, Any]:
        run = self.run(run_id)
        if run["state"] != "completed":
            raise Conflict("Only completed runs can be published to a project.")
        approval = self.store.one(
            """SELECT review_id FROM education_p34_run_reviews
            WHERE run_id=? AND decision='approved' ORDER BY created_at_utc DESC LIMIT 1""",
            (run_id,),
        )
        if not approval:
            raise PermissionDenied("A reviewer approval is required before project publication.")
        return self.add_project_asset(
            run["project_id"],
            actor_id,
            asset_type="report",
            title=title,
            content={
                "run_id": run_id,
                "review_id": approval["review_id"],
                "claim_boundary": "Research output; no clinical or scientific truth guarantee.",
            },
            source_run_id=run_id,
        )

    def create_handoff(
        self,
        run_id: str,
        actor_id: str,
        *,
        destination: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run = self.run(run_id)
        if destination not in HANDOFF_DESTINATIONS:
            raise ResearchPlatformError("Unsupported Research Compute handoff destination.")
        handoff_id = new_id("computehandoff")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_handoffs VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    handoff_id,
                    run_id,
                    destination,
                    canonical_json(payload),
                    "review_required",
                    now_utc(),
                    actor_id,
                    None,
                    None,
                ),
            )
        self._audit(
            run["tenant_id"],
            actor_id,
            "review_gated_handoff_created",
            destination,
            handoff_id,
        )
        return self.store.one(
            "SELECT * FROM education_p34_handoffs WHERE handoff_id=?",
            (handoff_id,),
        ) or {}

    def register_remote_adapter(
        self,
        tenant_id: str,
        administrator_id: str,
        *,
        administrator_role: str,
        adapter_type: str,
        endpoint: str,
        allowed_hosts: list[str],
        command_templates: list[str],
        credentials: dict[str, Any],
        resource_limits: dict[str, Any],
    ) -> dict[str, Any]:
        if administrator_role not in {"platform_administrator", "institution_administrator"}:
            raise PermissionDenied("Administrator role is required.")
        if adapter_type not in REMOTE_ADAPTER_TYPES:
            raise ResearchPlatformError("Unsupported remote compute adapter type.")
        if not allowed_hosts or not command_templates:
            raise ResearchPlatformError("Remote adapters require host allowlist and command templates.")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
            raise ResearchPlatformError("Remote adapter endpoint must use an HTTPS or SSH URI.")
        normalized_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
        if parsed.hostname.lower() not in normalized_hosts:
            raise PermissionDenied("Remote endpoint hostname is not in the adapter allowlist.")
        if any(
            any(token in template for token in (";", "&&", "||", "|", "`", "$(", "\n", "\r", ">", "<"))
            for template in command_templates
        ):
            raise PermissionDenied("Unsafe shell metacharacter in command template.")
        adapter_id = new_id("compute-adapter")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p34_remote_adapters VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    adapter_id,
                    tenant_id,
                    adapter_type,
                    endpoint[:1000],
                    canonical_json(sorted(normalized_hosts)),
                    canonical_json(command_templates),
                    self._cipher.encrypt(canonical_json(credentials).encode()).decode(),
                    canonical_json(resource_limits),
                    "Configured - External Validation Required",
                    0,
                    now_utc(),
                    administrator_id,
                ),
            )
        return {
            "adapter_id": adapter_id,
            "adapter_type": adapter_type,
            "enabled": False,
            "validation_status": "Configured - External Validation Required",
            "credentials_exposed": False,
        }

    def remote_adapter_status(self, adapter_id: str) -> dict[str, Any]:
        row = self.store.one(
            """SELECT adapter_id,tenant_id,adapter_type,endpoint,allowed_hosts_json,
            command_templates_json,resource_limits_json,validation_status,enabled,
            created_at_utc,created_by FROM education_p34_remote_adapters
            WHERE adapter_id=?""",
            (adapter_id,),
        )
        if not row:
            raise Missing("Remote compute adapter not found.")
        row.update(
            {
                "credentials_exposed": False,
                "health_check_performed": False,
                "job_polling_performed": False,
                "remote_cancellation_performed": False,
                "log_retrieval_performed": False,
                "capability": "configured_interface_only",
            }
        )
        return row

    def result_explorer(self, run_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        steps = self.store.all(
            "SELECT * FROM education_p34_run_steps WHERE run_id=? ORDER BY step_id",
            (run_id,),
        )
        artifacts = self.store.all(
            "SELECT * FROM education_p34_run_artifacts WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )
        return {
            "run": run,
            "steps": steps,
            "artifacts": artifacts,
            "reviews": self.store.all(
                "SELECT * FROM education_p34_run_reviews WHERE run_id=? ORDER BY created_at_utc",
                (run_id,),
            ),
            "notes": self.store.all(
                "SELECT * FROM education_p34_result_notes WHERE run_id=? ORDER BY created_at_utc",
                (run_id,),
            ),
            "handoffs": self.store.all(
                "SELECT * FROM education_p34_handoffs WHERE run_id=? ORDER BY created_at_utc",
                (run_id,),
            ),
            "quality_metrics": {
                "completed_steps": sum(row["state"] == "completed" for row in steps),
                "total_steps": len(steps),
                "verified_artifacts": len(artifacts),
            },
            "warnings": [row["warning_text"] for row in steps if row["warning_text"]],
            "provenance_available_in_export_bundle": True,
            "remote_compute_used": False,
            "claim_boundary": "Research support only; results require human scientific review.",
        }
