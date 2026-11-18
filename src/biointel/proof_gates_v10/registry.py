from __future__ import annotations

"""Local, checksum-bound P0/P1 evidence staging with an immutable audit chain.

The registry records what a user supplied. It never treats a hash, template or
software-only check as scientific validation, reviewer approval or controlled
release authority.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from .catalog import GATE_LABELS, GATE_ORDER, PRIORITY_MODULES


MAX_EVIDENCE_BYTES = 1024 * 1024 * 1024
MIN_STAGING_FREE_BYTES = 256 * 1024 * 1024
DISALLOWED_EVIDENCE_CLASSES = frozenset({"demo", "template", "simulation", "synthetic", "rehearsal"})
QUALIFYING_REVIEW_STATES = frozenset({"submitted", "review-ready"})
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class PriorityEvidenceRegistry:
    """SQLite-backed local evidence intake for the fixed 62-module P0/P1 portfolio."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
        self.user_data_root = Path(configured).expanduser().resolve() if configured else self.root / "UserData"
        self.base = self.user_data_root / "proof_gates_v10"
        self.artifact_root = self.base / "evidence"
        self.workspace_root = self.base / "priority_workspaces"
        self.staging_root = self.base / "staging"
        self.execution_root = self.base / "execution"
        self.execution_input_root = self.base / "execution_inputs"
        self.functional_workspace_root = self.base / "functional_workspaces"
        self.database = self.base / "priority_evidence.sqlite3"
        for directory in (
            self.base,
            self.artifact_root,
            self.workspace_root,
            self.staging_root,
            self.execution_root,
            self.execution_input_root,
            self.functional_workspace_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    gate_key TEXT NOT NULL,
                    stored_relative_path TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    source_reference TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_module_gate_idx ON artifacts(module_key, gate_key, created_at DESC);
                CREATE TABLE IF NOT EXISTS manifests (
                    manifest_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    gate_key TEXT NOT NULL,
                    stored_relative_path TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS execution_inputs (
                    input_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    stored_relative_path TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    source_reference TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS execution_inputs_module_idx ON execution_inputs(module_key, created_at DESC);
                CREATE TABLE IF NOT EXISTS execution_records (
                    record_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    execution_key TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stored_relative_path TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS execution_records_module_idx ON execution_records(module_key, created_at DESC);
                """
            )

    @staticmethod
    def _validate_module(module_key: str) -> str:
        key = str(module_key).strip()
        if key not in PRIORITY_MODULES:
            raise ValueError(f"{key!r} is not a P0/P1 priority module.")
        return key

    @staticmethod
    def _validate_gate(gate_key: str) -> str:
        gate = str(gate_key).strip()
        if gate not in GATE_ORDER:
            raise ValueError(f"Unknown proof gate: {gate!r}")
        return gate

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = _SAFE_NAME.sub("_", Path(str(value or "evidence.bin")).name).strip("._")
        return (name or "evidence.bin")[:180]

    def _safe_target(self, relative: Path) -> Path:
        target = (self.base / relative).resolve()
        try:
            target.relative_to(self.base.resolve())
        except ValueError as exc:
            raise ValueError("Unsafe evidence path.") from exc
        return target

    def storage_status(self, *, expected_bytes: int = 0) -> dict[str, int | bool]:
        """Report local free-space readiness without reserving or consuming it."""
        expected = max(0, int(expected_bytes))
        free = int(shutil.disk_usage(self.base).free)
        return {
            "free_bytes": free,
            "expected_bytes": expected,
            "minimum_headroom_bytes": MIN_STAGING_FREE_BYTES,
            "sufficient": free >= expected + MIN_STAGING_FREE_BYTES,
        }

    def _require_storage_capacity(self, expected_bytes: int) -> None:
        status = self.storage_status(expected_bytes=expected_bytes)
        if not bool(status["sufficient"]):
            raise OSError(
                "Insufficient local free space for safe staging. "
                f"Need the declared input plus {MIN_STAGING_FREE_BYTES // (1024 * 1024)} MiB headroom."
            )

    def _record_event(self, connection: sqlite3.Connection, event_type: str, payload: dict[str, Any]) -> str:
        previous = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(previous["event_hash"]) if previous else "0" * 64
        created_at = _utc_now()
        payload_json = _canonical(payload)
        material = _canonical(
            {
                "created_at": created_at,
                "event_type": event_type,
                "payload_json": payload_json,
                "previous_hash": previous_hash,
            }
        )
        event_hash = hashlib.sha256((previous_hash + material).encode("utf-8")).hexdigest()
        connection.execute(
            "INSERT INTO audit_events(created_at,event_type,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
            (created_at, event_type, payload_json, previous_hash, event_hash),
        )
        return event_hash

    def stage_stream(
        self,
        module_key: str,
        gate_key: str,
        stream: BinaryIO,
        *,
        original_name: str,
        source_reference: str,
        reviewer: str,
        evidence_class: str = "authentic",
        review_status: str = "draft",
        notes: str = "",
        max_bytes: int = MAX_EVIDENCE_BYTES,
    ) -> dict[str, Any]:
        """Stage a user-provided artifact, calculate SHA-256 and append an audit event.

        Staging is deliberately not a qualification action. Explicit demo,
        template, simulation and synthetic classes remain visible but cannot
        satisfy a proof gate.
        """
        module = self._validate_module(module_key)
        gate = self._validate_gate(gate_key)
        if not hasattr(stream, "read"):
            raise TypeError("Evidence stream must provide read().")
        limit = int(max_bytes)
        if limit <= 0 or limit > MAX_EVIDENCE_BYTES:
            raise ValueError("max_bytes must be between 1 byte and 1 GiB.")
        safe_name = self._safe_filename(original_name)
        temporary = self.staging_root / f"{uuid.uuid4().hex}.part"
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("Evidence stream returned non-byte content.")
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("Evidence artifact exceeds the 1 GiB local staging boundary.")
                    digest.update(chunk)
                    handle.write(chunk)
            artifact_id = uuid.uuid4().hex
            sha256 = digest.hexdigest()
            timestamp = _utc_now().replace("+00:00", "Z").replace(":", "")
            relative = Path("evidence") / module / gate / f"{timestamp}_{sha256[:12]}_{safe_name}"
            target = self._safe_target(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        row = {
            "artifact_id": artifact_id,
            "module_key": module,
            "gate_key": gate,
            "stored_relative_path": relative.as_posix(),
            "original_name": safe_name,
            "sha256": sha256,
            "size_bytes": total,
            "source_reference": str(source_reference).strip(),
            "reviewer": str(reviewer).strip(),
            "evidence_class": str(evidence_class).strip().lower() or "authentic",
            "review_status": str(review_status).strip().lower() or "draft",
            "notes": str(notes).strip(),
            "created_at": _utc_now(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id,module_key,gate_key,stored_relative_path,original_name,sha256,size_bytes,
                    source_reference,reviewer,evidence_class,review_status,notes,created_at
                ) VALUES(
                    :artifact_id,:module_key,:gate_key,:stored_relative_path,:original_name,:sha256,:size_bytes,
                    :source_reference,:reviewer,:evidence_class,:review_status,:notes,:created_at
                )
                """,
                row,
            )
            event_hash = self._record_event(
                connection,
                "artifact_staged",
                {key: row[key] for key in row if key not in {"notes"}},
            )
        return {**row, "event_hash": event_hash, "qualification_effect": "none"}

    def stage_execution_input(
        self,
        module_key: str,
        stream: BinaryIO,
        *,
        original_name: str,
        source_reference: str,
        notes: str = "",
        expected_size_bytes: int | None = None,
        max_bytes: int = MAX_EVIDENCE_BYTES,
    ) -> dict[str, Any]:
        """Persist a user-provided execution input with streaming SHA-256.

        This is intentionally separate from proof-gate evidence.  A staged
        input proves only that a local file was received and hashed; it does
        not prove scientific validity, permission, qualification or release.
        """
        module = self._validate_module(module_key)
        if not hasattr(stream, "read"):
            raise TypeError("Execution input stream must provide read().")
        limit = int(max_bytes)
        if limit <= 0 or limit > MAX_EVIDENCE_BYTES:
            raise ValueError("max_bytes must be between 1 byte and 1 GiB.")
        expected = None if expected_size_bytes is None else int(expected_size_bytes)
        if expected is not None and (expected < 0 or expected > limit):
            raise ValueError("Declared execution-input size must be between 0 bytes and 1 GiB.")
        source = str(source_reference).strip()
        if not source:
            raise ValueError("A local or authorised source/protocol/accession reference is required for execution input staging.")
        self._require_storage_capacity(expected or 0)

        safe_name = self._safe_filename(original_name)
        temporary = self.staging_root / f"execution-input-{uuid.uuid4().hex}.part"
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("Execution input stream returned non-byte content.")
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("Execution input exceeds the 1 GiB local staging boundary.")
                    if total > (expected or 0):
                        self._require_storage_capacity(total)
                    digest.update(chunk)
                    handle.write(chunk)
            input_id = uuid.uuid4().hex
            sha256 = digest.hexdigest()
            timestamp = _utc_now().replace("+00:00", "Z").replace(":", "")
            relative = Path("execution_inputs") / module / f"{timestamp}_{sha256[:12]}_{safe_name}"
            target = self._safe_target(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        row = {
            "input_id": input_id,
            "module_key": module,
            "stored_relative_path": relative.as_posix(),
            "original_name": safe_name,
            "sha256": sha256,
            "size_bytes": total,
            "source_reference": source,
            "notes": str(notes).strip(),
            "created_at": _utc_now(),
        }
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_inputs(
                        input_id,module_key,stored_relative_path,original_name,sha256,size_bytes,
                        source_reference,notes,created_at
                    ) VALUES(
                        :input_id,:module_key,:stored_relative_path,:original_name,:sha256,:size_bytes,
                        :source_reference,:notes,:created_at
                    )
                    """,
                    row,
                )
                event_hash = self._record_event(
                    connection,
                    "execution_input_staged",
                    {key: row[key] for key in row if key != "notes"},
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {**row, "event_hash": event_hash, "qualification_effect": "none"}

    def execution_input_rows(self, module_key: str | None = None) -> list[dict[str, Any]]:
        if module_key is not None:
            self._validate_module(module_key)
        query = "SELECT * FROM execution_inputs"
        values: list[str] = []
        if module_key is not None:
            query += " WHERE module_key=?"
            values.append(module_key)
        query += " ORDER BY created_at DESC, input_id DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, values).fetchall()]

    def write_execution_record(
        self,
        module_key: str,
        *,
        execution_key: str,
        adapter: str,
        action: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Write a checksum-bound local execution/preflight record and audit it.

        The record documents a software action such as workspace preparation or
        a runtime preflight.  Its status cannot promote a scientific rating or
        controlled-release decision.
        """
        module = self._validate_module(module_key)
        clean_execution_key = self._safe_filename(execution_key).replace(".", "_")
        clean_adapter = self._safe_filename(adapter).replace(".", "_")
        clean_action = self._safe_filename(action).replace(".", "_")
        clean_status = self._safe_filename(status).replace(".", "_")
        if not all((clean_execution_key, clean_adapter, clean_action, clean_status)):
            raise ValueError("Execution record identity is incomplete.")
        record_id = uuid.uuid4().hex
        created_at = _utc_now()
        body = {
            "schema": "biointel.step196.p0p1.execution-record.v1",
            "record_id": record_id,
            "module_key": module,
            "execution_key": clean_execution_key,
            "adapter": clean_adapter,
            "action": clean_action,
            "status": clean_status,
            "created_at": created_at,
            "controlled_release_approved": False,
            "rating_promotion": "not-automated",
            "payload": payload,
            "boundary": "This local record documents software execution state only. It does not establish data qualification, a benchmark result, independent confirmation, governance approval, licence rights or controlled release.",
        }
        raw = json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n"
        sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        timestamp = created_at.replace("+00:00", "Z").replace(":", "")
        relative = Path("execution") / module / f"{timestamp}_{clean_action}_{record_id[:12]}.json"
        target = self._safe_target(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        temporary.write_text(raw, encoding="utf-8")
        os.replace(temporary, target)
        row = {
            "record_id": record_id,
            "module_key": module,
            "execution_key": clean_execution_key,
            "adapter": clean_adapter,
            "action": clean_action,
            "status": clean_status,
            "stored_relative_path": relative.as_posix(),
            "sha256": sha256,
            "summary_json": _canonical(payload),
            "created_at": created_at,
        }
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_records(
                        record_id,module_key,execution_key,adapter,action,status,stored_relative_path,
                        sha256,summary_json,created_at
                    ) VALUES(
                        :record_id,:module_key,:execution_key,:adapter,:action,:status,:stored_relative_path,
                        :sha256,:summary_json,:created_at
                    )
                    """,
                    row,
                )
                event_hash = self._record_event(
                    connection,
                    "execution_record_written",
                    {key: row[key] for key in row if key != "summary_json"},
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {**row, "event_hash": event_hash, "qualification_effect": "none"}

    def execution_rows(self, module_key: str | None = None, *, limit: int = 200) -> list[dict[str, Any]]:
        if module_key is not None:
            self._validate_module(module_key)
        bounded_limit = max(1, min(int(limit), 5_000))
        query = "SELECT * FROM execution_records"
        values: list[Any] = []
        if module_key is not None:
            query += " WHERE module_key=?"
            values.append(module_key)
        query += " ORDER BY created_at DESC, record_id DESC LIMIT ?"
        values.append(bounded_limit)
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, values).fetchall()]

    def write_gate_manifest(
        self,
        module_key: str,
        gate_key: str,
        *,
        reviewer: str,
        source_reference: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """Create a local review manifest draft without approving any gate."""
        module = self._validate_module(module_key)
        gate = self._validate_gate(gate_key)
        manifest_id = uuid.uuid4().hex
        artifacts = self.artifact_rows(module, gate)
        payload = {
            "schema": "biointel.step196.p0p1.gate-manifest.v1",
            "manifest_id": manifest_id,
            "module_key": module,
            "module_title": PRIORITY_MODULES[module].title,
            "priority": PRIORITY_MODULES[module].priority,
            "gate_key": gate,
            "gate_label": GATE_LABELS[gate],
            "reviewer": str(reviewer).strip(),
            "source_reference": str(source_reference).strip(),
            "notes": str(notes).strip(),
            "artifact_ids": [row["artifact_id"] for row in artifacts],
            "created_at": _utc_now(),
            "controlled_release_approved": False,
            "boundary": "Draft manifest only. A local hash and manifest do not establish scientific truth, licence rights, independent confirmation, expert sign-off or release approval.",
        }
        raw = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        relative = Path("evidence") / module / gate / "manifests" / f"{manifest_id}.json"
        target = self._safe_target(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO manifests(manifest_id,module_key,gate_key,stored_relative_path,sha256,created_at) VALUES(?,?,?,?,?,?)",
                (manifest_id, module, gate, relative.as_posix(), sha256, payload["created_at"]),
            )
            event_hash = self._record_event(
                connection,
                "gate_manifest_drafted",
                {"manifest_id": manifest_id, "module_key": module, "gate_key": gate, "sha256": sha256},
            )
        return {"manifest_id": manifest_id, "relative_path": relative.as_posix(), "sha256": sha256, "event_hash": event_hash}

    def artifact_rows(self, module_key: str | None = None, gate_key: str | None = None) -> list[dict[str, Any]]:
        if module_key is not None:
            self._validate_module(module_key)
        if gate_key is not None:
            self._validate_gate(gate_key)
        query = "SELECT * FROM artifacts"
        conditions: list[str] = []
        values: list[str] = []
        if module_key is not None:
            conditions.append("module_key=?")
            values.append(module_key)
        if gate_key is not None:
            conditions.append("gate_key=?")
            values.append(gate_key)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC, artifact_id DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, values).fetchall()]

    @staticmethod
    def _candidate_artifact(row: dict[str, Any]) -> bool:
        return (
            str(row["evidence_class"]).lower() not in DISALLOWED_EVIDENCE_CLASSES
            and str(row["review_status"]).lower() in QUALIFYING_REVIEW_STATES
            and bool(str(row["source_reference"]).strip())
            and bool(str(row["reviewer"]).strip())
        )

    def verify_module(self, module_key: str) -> dict[str, Any]:
        module = self._validate_module(module_key)
        profile = PRIORITY_MODULES[module]
        gates: list[dict[str, Any]] = []
        for gate in GATE_ORDER:
            artifacts = self.artifact_rows(module, gate)
            rejected = [row for row in artifacts if str(row["evidence_class"]).lower() in DISALLOWED_EVIDENCE_CLASSES]
            candidates = [row for row in artifacts if self._candidate_artifact(row)]
            gates.append(
                {
                    "gate_key": gate,
                    "gate_label": GATE_LABELS[gate],
                    "requirement": profile.gate_requirements()[gate],
                    "artifact_count": len(artifacts),
                    "candidate_count": len(candidates),
                    "rejected_evidence_count": len(rejected),
                    "state": "ready-for-manual-review" if candidates else "blocked",
                    "reason": "Local candidate evidence requires responsible manual review." if candidates else "No review-ready non-demo artifact is staged for this gate.",
                }
            )
        candidate_for_manual_review = bool(gates) and all(row["state"] == "ready-for-manual-review" for row in gates)
        return {
            "module_key": module,
            "module_title": profile.title,
            "priority": profile.priority,
            "gates": gates,
            "candidate_for_manual_review": candidate_for_manual_review,
            "controlled_release": "not-automated",
            "rating_promotion": "not-automated",
        }

    def verify_all(self, priority: str | None = None) -> list[dict[str, Any]]:
        tier = str(priority or "").upper().strip()
        if tier and tier not in {"P0", "P1"}:
            raise ValueError("priority must be P0, P1 or empty.")
        rows: list[dict[str, Any]] = []
        for key, profile in PRIORITY_MODULES.items():
            if tier and profile.priority != tier:
                continue
            result = self.verify_module(key)
            rows.append(
                {
                    "Priority": result["priority"],
                    "Module": result["module_title"],
                    "Module key": key,
                    "Ready gates": sum(gate["state"] == "ready-for-manual-review" for gate in result["gates"]),
                    "Total artifacts": sum(int(gate["artifact_count"]) for gate in result["gates"]),
                    "Manual review candidate": result["candidate_for_manual_review"],
                    "Controlled release": "Not automated",
                }
            )
        return rows

    def prepare_priority_workspaces(self, module_key: str | None = None, *, refresh: bool = False) -> list[Path]:
        keys = [self._validate_module(module_key)] if module_key else list(PRIORITY_MODULES)
        written: list[Path] = []
        for key in keys:
            profile = PRIORITY_MODULES[key]
            directory = self.workspace_root / key
            directory.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": "biointel.step196.p0p1.workspace.v1",
                "module_key": key,
                "module_title": profile.title,
                "priority": profile.priority,
                "requirements": profile.gate_requirements(),
                "controlled_release_approved": False,
                "created_at": _utc_now(),
            }
            for name, content in (
                ("evidence_manifest_draft.json", json.dumps(payload, indent=2) + "\n"),
                (
                    "README.md",
                    f"# {profile.priority} priority remediation · {profile.title}\n\n"
                    "This local workspace is an evidence checklist, not proof of validation or release approval.\n",
                ),
            ):
                target = directory / name
                if refresh or not target.exists():
                    target.write_text(content, encoding="utf-8")
                    written.append(target)
        with self._connect() as connection:
            self._record_event(
                connection,
                "priority_workspace_prepared",
                {"module_keys": keys, "refresh": bool(refresh), "written_count": len(written)},
            )
        return written

    def audit_chain_valid(self) -> bool:
        previous_hash = "0" * 64
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY event_id ASC").fetchall()
        for row in rows:
            material = _canonical(
                {
                    "created_at": row["created_at"],
                    "event_type": row["event_type"],
                    "payload_json": row["payload_json"],
                    "previous_hash": previous_hash,
                }
            )
            expected = hashlib.sha256((previous_hash + material).encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                return False
            previous_hash = expected
        return True

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            artifact_count = int(connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
            manifest_count = int(connection.execute("SELECT COUNT(*) FROM manifests").fetchone()[0])
            execution_input_count = int(connection.execute("SELECT COUNT(*) FROM execution_inputs").fetchone()[0])
            execution_record_count = int(connection.execute("SELECT COUNT(*) FROM execution_records").fetchone()[0])
            event_count = int(connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
        verification = self.verify_all()
        manual_candidates = sum(bool(row["Manual review candidate"]) for row in verification)
        return {
            "p0_modules": len([profile for profile in PRIORITY_MODULES.values() if profile.priority == "P0"]),
            "p1_modules": len([profile for profile in PRIORITY_MODULES.values() if profile.priority == "P1"]),
            "priority_modules": len(PRIORITY_MODULES),
            "artifact_count": artifact_count,
            "manifest_count": manifest_count,
            "execution_input_count": execution_input_count,
            "execution_record_count": execution_record_count,
            "event_count": event_count,
            "manual_review_candidates": manual_candidates,
            "audit_chain_valid": self.audit_chain_valid(),
            "controlled_release_automated": False,
            "storage": self.storage_status(),
        }


__all__ = [
    "DISALLOWED_EVIDENCE_CLASSES",
    "MAX_EVIDENCE_BYTES",
    "MIN_STAGING_FREE_BYTES",
    "PriorityEvidenceRegistry",
]
