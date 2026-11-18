from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from biointel.database.core import managed_connect
import urllib.request
from urllib.parse import unquote, urlparse
from uuid import uuid4
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class ReferencePlan:
    database_name: str
    version: str
    source_url: str
    license_name: str
    expected_size_bytes: int
    required_tools: tuple[str, ...]
    index_outputs: tuple[str, ...]
    compatibility: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BUILTIN_REFERENCE_CATALOG: tuple[ReferencePlan, ...] = (
    ReferencePlan("Human reference genome", "GRCh38", "", "Provider terms apply", 4_000_000_000, ("samtools", "bwa", "minimap2"), ("FASTA .fai", "BWA/minimap2 index"), {"genome_build": "GRCh38"}),
    ReferencePlan("ClinVar", "current", "", "NCBI data policy", 10_000_000_000, ("bcftools", "tabix"), ("bgzip VCF", "tabix index"), {"format": "VCF"}),
    ReferencePlan("gnomAD", "current", "", "Broad/gnomAD terms", 200_000_000_000, ("bcftools", "tabix"), ("tabix index",), {"format": "VCF"}),
    ReferencePlan("Ensembl", "current", "", "Ensembl terms", 50_000_000_000, ("samtools",), ("FASTA index", "annotation index"), {"formats": ["FASTA", "GTF"]}),
    ReferencePlan("Human Phenotype Ontology", "current", "", "HPO license", 2_000_000_000, (), ("ontology cache",), {"format": "OBO/TSV"}),
    ReferencePlan("UniProt", "current", "", "UniProt terms", 120_000_000_000, ("diamond",), ("DIAMOND database",), {"format": "FASTA"}),
    ReferencePlan("InterPro", "current", "", "InterPro terms", 40_000_000_000, (), ("local search index",), {"format": "TSV/XML"}),
    ReferencePlan("Reactome", "current", "", "Reactome terms", 10_000_000_000, (), ("pathway cache",), {"format": "TSV/JSON"}),
    ReferencePlan("Gene Ontology", "current", "", "GO license", 5_000_000_000, (), ("ontology cache",), {"format": "OBO/GAF"}),
    ReferencePlan("RCSB PDB metadata", "current", "", "RCSB terms", 30_000_000_000, (), ("metadata index",), {"format": "mmCIF/JSON"}),
    ReferencePlan("ChEMBL", "current", "", "ChEMBL license", 80_000_000_000, (), ("SQLite/PostgreSQL index",), {"format": "database dump"}),
    ReferencePlan("BindingDB", "current", "", "BindingDB terms", 20_000_000_000, (), ("compound-target index",), {"format": "TSV/SDF"}),
    ReferencePlan("CARD / AMR reference", "current", "", "CARD terms", 10_000_000_000, ("diamond",), ("protein database",), {"format": "FASTA/JSON"}),
    ReferencePlan("Kraken 2 database", "standard", "", "Source database licenses apply", 100_000_000_000, ("kraken2",), ("Kraken hash database",), {"format": "Kraken2 DB"}),
)


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_directory(path: Path) -> tuple[str, int, int]:
    digest = sha256()
    total_size = 0
    file_count = 0
    # Do not follow file symlinks out of the managed reference root. Reference
    # fingerprints must describe the registered asset, not arbitrary external
    # files reachable through a link.
    for file_path in sorted(
        item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
    ):
        relative = file_path.relative_to(path).as_posix()
        file_digest = _sha256_file(file_path)
        size = file_path.stat().st_size
        digest.update(f"{relative}\0{file_digest}\0{size}\n".encode("utf-8"))
        total_size += size
        file_count += 1
    return digest.hexdigest(), total_size, file_count


def fingerprint_path(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.is_file():
        return {"sha256": _sha256_file(source), "size_bytes": source.stat().st_size, "file_count": 1, "kind": "file"}
    if source.is_dir():
        digest, size, count = _sha256_directory(source)
        return {"sha256": digest, "size_bytes": size, "file_count": count, "kind": "directory"}
    raise FileNotFoundError(source)


def _safe_path_component(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip()).strip("._-")
    return cleaned[:120] or fallback


def _validate_sha256(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized and not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("Expected SHA-256 must contain exactly 64 hexadecimal characters.")
    return normalized


class ReferenceLifecycleManager:
    """Persistent local reference-data lifecycle with verification and rollback.

    The manager intentionally separates a download *plan* from activation. A version
    becomes active only after local content exists and its checksum has been recorded.
    """

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        user_data_root = Path(
            os.environ.get("BIOINTEL_USER_DATA_DIR") or self.project_root
        ).expanduser().resolve()
        preferred_state_root = user_data_root / "workspace" / "reference_lifecycle"
        legacy_state_root = self.project_root / "workspace" / "reference_lifecycle"
        # Step 112 stored lifecycle state under the application root. Preserve
        # those registrations on upgrade instead of making them appear lost.
        # New installations use UserData, while an existing legacy store remains
        # readable until the operator explicitly migrates its potentially huge
        # reference assets.
        if preferred_state_root != legacy_state_root and legacy_state_root.exists() and not preferred_state_root.exists():
            self.state_root = legacy_state_root
        else:
            self.state_root = preferred_state_root
        self.asset_root = self.state_root / "assets"
        self.download_root = self.state_root / "downloads"
        self.db_path = self.state_root / "reference_lifecycle.sqlite3"
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self.download_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    @contextmanager
    def _connection(self):
        """Yield a transaction and always close the SQLite handle.

        ``sqlite3.Connection`` as a context manager commits/rolls back but does
        not close itself. Repeated Streamlit reruns therefore used to accumulate
        handles until garbage collection, which is especially problematic on
        Windows when a database is moved, backed up, or repaired.
        """

        con = self._connect()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self) -> None:
        with self._connection() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS reference_versions(
                    reference_id TEXT PRIMARY KEY,
                    database_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    asset_kind TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    file_count INTEGER NOT NULL,
                    license_name TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    compatibility_json TEXT NOT NULL DEFAULT '{}',
                    required_tools_json TEXT NOT NULL DEFAULT '[]',
                    index_outputs_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'registered',
                    active INTEGER NOT NULL DEFAULT 0,
                    verified_at_utc TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(database_name, version)
                );
                CREATE TABLE IF NOT EXISTS reference_events(
                    event_id TEXT PRIMARY KEY,
                    reference_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(reference_id) REFERENCES reference_versions(reference_id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS download_plans(
                    plan_id TEXT PRIMARY KEY,
                    database_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    expected_size_bytes INTEGER NOT NULL,
                    checksum_expected TEXT NOT NULL DEFAULT '',
                    license_name TEXT NOT NULL,
                    license_accepted INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'planned',
                    target_path TEXT NOT NULL,
                    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reference_name_active ON reference_versions(database_name, active);
                CREATE INDEX IF NOT EXISTS idx_reference_events_ref ON reference_events(reference_id, created_at_utc);
                """
            )

    def _event(self, reference_id: str | None, event_type: str, details: dict[str, Any] | None = None) -> None:
        with self._connection() as con:
            con.execute(
                "INSERT INTO reference_events VALUES(?,?,?,?,?)",
                ("event-" + uuid4().hex, reference_id, event_type, json.dumps(details or {}, sort_keys=True, default=str), _utc_now()),
            )

    def register_path(
        self,
        database_name: str,
        version: str,
        path: str | Path,
        *,
        license_name: str,
        source_url: str = "",
        compatibility: dict[str, Any] | None = None,
        required_tools: Iterable[str] = (),
        index_outputs: Iterable[str] = (),
        copy_into_managed_storage: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        if not database_name.strip() or not version.strip():
            raise ValueError("Database name and version are required.")
        if not license_name.strip():
            raise ValueError("A licence name or terms label is required.")
        source = Path(path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        source_fingerprint = fingerprint_path(source)
        database_name = database_name.strip()
        version = version.strip()

        with self._connection() as con:
            existing = con.execute(
                "SELECT * FROM reference_versions WHERE database_name=? AND version=?",
                (database_name, version),
            ).fetchone()
        if existing is not None and not replace_existing:
            existing_record = dict(existing)
            if (
                existing_record["sha256"] == source_fingerprint["sha256"]
                and int(existing_record["size_bytes"]) == int(source_fingerprint["size_bytes"])
                and int(existing_record["file_count"]) == int(source_fingerprint["file_count"])
            ):
                return self.get_reference(existing_record["reference_id"])
            raise ValueError(
                "This database/version is already registered with different content. "
                "Use a new version label or explicitly replace the existing version."
            )

        target = source
        if copy_into_managed_storage:
            safe_name = _safe_path_component(database_name, fallback="reference")
            safe_version = _safe_path_component(version, fallback="version")
            final_root = (self.asset_root / safe_name / safe_version).resolve()
            try:
                final_root.relative_to(self.asset_root.resolve())
            except ValueError as exc:  # pragma: no cover - defensive invariant
                raise ValueError("Managed reference destination escaped the asset root.") from exc
            if source.is_dir():
                try:
                    final_root.relative_to(source)
                except ValueError:
                    pass
                else:
                    raise ValueError("Cannot copy a directory into one of its own descendants.")

            staging = final_root.with_name(final_root.name + ".staging-" + uuid4().hex)
            staging.parent.mkdir(parents=True, exist_ok=True)
            try:
                if source.is_dir():
                    shutil.copytree(source, staging, symlinks=False)
                    staged_target = staging
                    target_suffix: Path | None = None
                else:
                    staging.mkdir(parents=True, exist_ok=False)
                    copied = staging / _safe_path_component(source.name, fallback="reference.bin")
                    shutil.copy2(source, copied)
                    staged_target = copied
                    target_suffix = copied.relative_to(staging)

                # Fingerprint the complete staged copy before replacing a good
                # existing managed asset.
                fingerprint_path(staged_target)
                if final_root.exists():
                    if final_root.is_dir():
                        shutil.rmtree(final_root)
                    else:
                        final_root.unlink()
                os.replace(staging, final_root)
                target = final_root if target_suffix is None else final_root / target_suffix
            except Exception:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
                raise
        fingerprint = fingerprint_path(target)
        reference_id = existing["reference_id"] if existing is not None else "reference-" + uuid4().hex
        now = _utc_now()
        values = (
            database_name,
            version,
            str(target),
            fingerprint["kind"],
            fingerprint["sha256"],
            int(fingerprint["size_bytes"]),
            int(fingerprint["file_count"]),
            license_name.strip(),
            source_url.strip(),
            json.dumps(compatibility or {}, sort_keys=True),
            json.dumps(list(required_tools), sort_keys=True),
            json.dumps(list(index_outputs), sort_keys=True),
        )
        with self._connection() as con:
            if existing is None:
                con.execute(
                    """
                    INSERT INTO reference_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (reference_id, *values, "verified", 0, now, now),
                )
            else:
                con.execute(
                    """
                    UPDATE reference_versions
                    SET database_name=?,version=?,local_path=?,asset_kind=?,sha256=?,size_bytes=?,file_count=?,
                        license_name=?,source_url=?,compatibility_json=?,required_tools_json=?,index_outputs_json=?,
                        status='verified',active=0,verified_at_utc=?
                    WHERE reference_id=?
                    """,
                    (*values, now, reference_id),
                )
        self._event(reference_id, "replaced" if existing is not None else "registered", {"path": str(target), **fingerprint})
        return self.get_reference(reference_id)

    def get_reference(self, reference_id: str) -> dict[str, Any]:
        with self._connection() as con:
            row = con.execute("SELECT * FROM reference_versions WHERE reference_id=?", (reference_id,)).fetchone()
        if row is None:
            raise KeyError(reference_id)
        result = dict(row)
        for field in ("compatibility_json", "required_tools_json", "index_outputs_json"):
            default = "{}" if field == "compatibility_json" else "[]"
            result[field.removesuffix("_json")] = json.loads(result[field] or default)
        return result

    def list_references(self) -> pd.DataFrame:
        with self._connection() as con:
            rows = con.execute("SELECT * FROM reference_versions ORDER BY database_name, created_at_utc DESC").fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def verify(self, reference_id: str) -> dict[str, Any]:
        item = self.get_reference(reference_id)
        path = Path(item["local_path"])
        if not path.exists():
            status = "missing"
            match = False
            observed = {"sha256": "", "size_bytes": 0, "file_count": 0, "kind": item["asset_kind"]}
        else:
            observed = fingerprint_path(path)
            match = (
                observed["sha256"] == item["sha256"]
                and int(observed["size_bytes"]) == int(item["size_bytes"])
                and int(observed["file_count"]) == int(item["file_count"])
                and observed["kind"] == item["asset_kind"]
            )
            status = "active" if match and bool(item["active"]) else ("verified" if match else "changed")
        with self._connection() as con:
            con.execute(
                "UPDATE reference_versions SET status=?, verified_at_utc=? WHERE reference_id=?",
                (status, _utc_now(), reference_id),
            )
        self._event(reference_id, "verified", {"checksum_match": match, "observed": observed})
        return {"reference_id": reference_id, "database_name": item["database_name"], "version": item["version"], "path_exists": path.exists(), "checksum_match": match, "status": status, **observed}

    def verify_all(self) -> pd.DataFrame:
        frame = self.list_references()
        if frame.empty:
            return pd.DataFrame(columns=["reference_id", "database_name", "version", "path_exists", "checksum_match", "status"])
        return pd.DataFrame([self.verify(reference_id) for reference_id in frame["reference_id"].tolist()])

    def activate(self, reference_id: str) -> dict[str, Any]:
        verification = self.verify(reference_id)
        if not verification["checksum_match"]:
            raise ValueError("Only a checksum-verified reference version can be activated.")
        item = self.get_reference(reference_id)
        with self._connection() as con:
            con.execute(
                "UPDATE reference_versions SET active=0,status=CASE WHEN status='active' THEN 'verified' ELSE status END WHERE database_name=?",
                (item["database_name"],),
            )
            con.execute("UPDATE reference_versions SET active=1,status='active' WHERE reference_id=?", (reference_id,))
        self._event(reference_id, "activated", {"database_name": item["database_name"], "version": item["version"]})
        return self.get_reference(reference_id)

    def rollback(self, database_name: str) -> dict[str, Any]:
        with self._connection() as con:
            rows = con.execute(
                "SELECT rowid AS _rowid,* FROM reference_versions WHERE database_name=? ORDER BY created_at_utc DESC,_rowid DESC",
                (database_name,),
            ).fetchall()
        versions = [dict(row) for row in rows]
        active_index = next((index for index, item in enumerate(versions) if item["active"]), None)
        if active_index is None:
            raise ValueError("No active version exists for this database.")
        candidates = versions[active_index + 1 :]
        for candidate in candidates:
            if self.verify(candidate["reference_id"])["checksum_match"]:
                activated = self.activate(candidate["reference_id"])
                self._event(candidate["reference_id"], "rollback", {"from": versions[active_index]["version"], "to": candidate["version"]})
                return activated
        raise ValueError("No earlier verified version is available for rollback.")

    def create_download_plan(
        self,
        database_name: str,
        version: str,
        source_url: str,
        *,
        expected_size_bytes: int,
        license_name: str,
        license_accepted: bool,
        checksum_expected: str = "",
    ) -> dict[str, Any]:
        if not license_accepted:
            raise ValueError("Licence/terms acceptance is required before creating a download plan.")
        source_url = source_url.strip()
        if not source_url.lower().startswith(("https://", "http://", "file://")):
            raise ValueError("Only HTTP(S) or file URLs are supported.")
        if expected_size_bytes < 0:
            raise ValueError("Expected size cannot be negative.")
        plan_id = "plan-" + uuid4().hex
        checksum_expected = _validate_sha256(checksum_expected)
        safe_name = _safe_path_component(database_name, fallback="reference")
        safe_version = _safe_path_component(version, fallback="version")
        parsed = urlparse(source_url)
        filename = _safe_path_component(Path(unquote(parsed.path)).name, fallback="reference.download")
        target = self.download_root / safe_name / safe_version / filename
        now = _utc_now()
        with self._connection() as con:
            con.execute(
                "INSERT INTO download_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan_id, database_name.strip(), version.strip(), source_url, int(expected_size_bytes), checksum_expected, license_name.strip(), 1, "planned", str(target), 0, "", now, now),
            )
        return self.get_download_plan(plan_id)

    def get_download_plan(self, plan_id: str) -> dict[str, Any]:
        with self._connection() as con:
            row = con.execute("SELECT * FROM download_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise KeyError(plan_id)
        return dict(row)

    def list_download_plans(self) -> pd.DataFrame:
        with self._connection() as con:
            rows = con.execute("SELECT * FROM download_plans ORDER BY created_at_utc DESC").fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def execute_download(self, plan_id: str, *, max_download_bytes: int = 250_000_000_000, timeout_seconds: int = 120) -> dict[str, Any]:
        plan = self.get_download_plan(plan_id)
        target = Path(plan["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        existing = part.stat().st_size if part.exists() else 0
        if max_download_bytes <= 0:
            raise ValueError("Maximum download size must be positive.")
        if existing > max_download_bytes:
            raise ValueError("Existing partial download already exceeds the configured maximum size.")
        with self._connection() as con:
            con.execute(
                "UPDATE download_plans SET status='downloading',error_message='',bytes_downloaded=?,updated_at_utc=? WHERE plan_id=?",
                (existing, _utc_now(), plan_id),
            )
        request = urllib.request.Request(plan["source_url"])
        if existing:
            request.add_header("Range", f"bytes={existing}-")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_status = int(
                    getattr(response, "status", None) or response.getcode() or 200
                )
                # Some servers ignore Range and return the entire file with 200.
                # Appending that response corrupts the partial file, so restart
                # cleanly unless the server explicitly confirms a 206 response.
                resume = bool(existing and response_status == 206)
                write_mode = "ab" if resume else "wb"
                if not resume:
                    existing = 0
                content_length = response.headers.get("Content-Length")
                if content_length and existing + int(content_length) > max_download_bytes:
                    raise ValueError("Download content length exceeds the configured maximum size.")
                with part.open(write_mode) as handle:
                    while True:
                        chunk = response.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        if handle.tell() + len(chunk) > max_download_bytes:
                            raise ValueError("Download exceeded the configured maximum size.")
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            digest = _sha256_file(part)
            if plan["checksum_expected"] and digest != plan["checksum_expected"]:
                failed_size = part.stat().st_size
                part.unlink(missing_ok=True)
                raise ValueError("Downloaded file checksum does not match the expected digest.")
            os.replace(part, target)
            actual_size = target.stat().st_size
            expected_size = int(plan["expected_size_bytes"] or 0)
            size_warning = ""
            if expected_size and actual_size != expected_size:
                size_warning = f"Expected approximately {expected_size} bytes but received {actual_size} bytes."
            with self._connection() as con:
                con.execute(
                    "UPDATE download_plans SET status='completed',bytes_downloaded=?,error_message='',updated_at_utc=? WHERE plan_id=?",
                    (actual_size, _utc_now(), plan_id),
                )
            return {
                "plan_id": plan_id,
                "target_path": str(target),
                "size_bytes": actual_size,
                "sha256": digest,
                "status": "completed",
                "resumed": bool(existing),
                "size_warning": size_warning,
            }
        except Exception as exc:
            bytes_downloaded = part.stat().st_size if part.exists() else 0
            # ``failed_size`` is set when a checksum mismatch deliberately
            # deletes the corrupt partial so the next retry starts cleanly.
            bytes_downloaded = locals().get("failed_size", bytes_downloaded)
            with self._connection() as con:
                con.execute("UPDATE download_plans SET status='failed',bytes_downloaded=?,error_message=?,updated_at_utc=? WHERE plan_id=?", (bytes_downloaded, str(exc), _utc_now(), plan_id))
            raise

    def storage_summary(self) -> pd.DataFrame:
        frame = self.list_references()
        if frame.empty:
            return pd.DataFrame(columns=["database_name", "versions", "active_versions", "size_bytes", "files"])
        grouped = frame.groupby("database_name", as_index=False).agg(
            versions=("version", "count"),
            active_versions=("active", "sum"),
            size_bytes=("size_bytes", "sum"),
            files=("file_count", "sum"),
        )
        return grouped.sort_values("size_bytes", ascending=False)

    def dependency_matrix(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for plan in BUILTIN_REFERENCE_CATALOG:
            for tool in plan.required_tools or ("No external tool",):
                rows.append({"database_name": plan.database_name, "version": plan.version, "required_tool": tool, "index_outputs": ", ".join(plan.index_outputs), "expected_size_gb": round(plan.expected_size_bytes / 1_000_000_000, 2)})
        return pd.DataFrame(rows)

    def events(self) -> pd.DataFrame:
        with self._connection() as con:
            rows = con.execute(
                """
                SELECT e.event_id,e.reference_id,e.event_type,e.details_json,e.created_at_utc,
                       r.database_name,r.version
                FROM reference_events e LEFT JOIN reference_versions r ON r.reference_id=e.reference_id
                ORDER BY e.created_at_utc DESC
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def export_manifest(self) -> dict[str, Any]:
        references = self.list_references().to_dict(orient="records")
        plans = self.list_download_plans().to_dict(orient="records")
        payload = {
            "generated_at_utc": _utc_now(),
            "references": references,
            "download_plans": plans,
            "storage": self.storage_summary().to_dict(orient="records"),
            "scientific_boundary": "Reference assets remain subject to provider licences, release notes and project-specific validation.",
        }
        canonical = json.dumps(payload, sort_keys=True, default=str)
        payload["manifest_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
        return payload
