from __future__ import annotations

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .external_evidence import ExternalValidationEvidenceMixin
from .quality import ClinicalQualityMixin
from .schema import initialize_schema


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_content_or_file(
    content: bytes | None,
    path: str | Path | None,
    *,
    label: str,
) -> str:
    """Hash one non-empty in-memory payload or a streamed local artifact."""

    if content is not None and path is not None:
        raise ValueError(f"Provide either {label} content or {label} path, not both.")
    if content is not None:
        if not content:
            raise ValueError(f"{label.capitalize()} content is empty.")
        return _sha_bytes(content)
    if path is None:
        raise ValueError(f"{label.capitalize()} content or a staged local path is required.")
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label.capitalize()} staged file is unavailable.")
    if resolved.stat().st_size <= 0:
        raise ValueError(f"{label.capitalize()} staged file is empty.")
    return _sha_file(resolved)


@dataclass(frozen=True)
class AuditChainVerification:
    valid: bool
    event_count: int
    first_error_sequence: int | None
    final_hash: str


class ClinicalValidationRegistry(ClinicalQualityMixin, ExternalValidationEvidenceMixin):
    """Controlled validation registry; it never creates clinical validity by itself."""

    PROGRAM_STATUSES = {"draft", "active", "on_hold", "completed", "retired"}
    PROTOCOL_STATUSES = {"draft", "in_review", "approved", "superseded", "withdrawn"}

    TABLES = (
        "validation_sites",
        "protocols",
        "model_freezes",
        "prediction_batches",
        "outcome_batches",
        "analysis_results",
        "evidence_items",
        "quality_events",
        "training_records",
        "signatures",
        "external_validation_artifacts",
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        initialize_schema(self._connect)

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        reason: str,
        payload: dict[str, Any],
    ) -> None:
        previous = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        event = {
            "event_id": f"AUD-{uuid.uuid4().hex.upper()}",
            "timestamp": utc_now(),
            "actor": actor.strip(),
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "reason": reason.strip(),
            "payload": payload,
            "previous_hash": previous_hash,
        }
        event_hash = _sha_bytes(_canonical(event).encode())
        connection.execute(
            """INSERT INTO audit_events(event_id,timestamp,actor,action,object_type,
            object_id,reason,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                event["event_id"],
                event["timestamp"],
                event["actor"],
                action,
                object_type,
                object_id,
                event["reason"],
                _canonical(payload),
                previous_hash,
                event_hash,
            ),
        )

    def create_program(
        self,
        *,
        title: str,
        claim_profile: str,
        intended_use: str,
        decision_context: str,
        target_population: str,
        jurisdictions: list[str],
        risk_classification: str,
        prohibited_uses: list[str],
        owner: str,
        quality_owner: str,
        actor: str,
    ) -> dict[str, Any]:
        identifier = f"VAL-{uuid.uuid4().hex[:10].upper()}"
        now = utc_now()
        row = {
            "program_id": identifier,
            "title": title.strip(),
            "claim_profile": claim_profile,
            "intended_use": intended_use.strip(),
            "decision_context": decision_context.strip(),
            "target_population": target_population.strip(),
            "jurisdictions": list(jurisdictions),
            "risk_classification": risk_classification.strip(),
            "prohibited_uses": list(prohibited_uses),
            "owner": owner.strip(),
            "quality_owner": quality_owner.strip(),
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        if not row["intended_use"] or not row["prohibited_uses"]:
            raise ValueError("Intended use and prohibited uses are required")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO validation_programs(program_id,title,claim_profile,intended_use,
                decision_context,target_population,jurisdictions_json,risk_classification,
                prohibited_uses_json,owner,quality_owner,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    row["title"],
                    claim_profile,
                    row["intended_use"],
                    row["decision_context"],
                    row["target_population"],
                    _canonical(row["jurisdictions"]),
                    row["risk_classification"],
                    _canonical(row["prohibited_uses"]),
                    row["owner"],
                    row["quality_owner"],
                    "draft",
                    now,
                    now,
                ),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="validation_program.created",
                object_type="validation_program",
                object_id=identifier,
                reason="Create controlled validation program",
                payload={"claim_profile": claim_profile, "intended_use": row["intended_use"]},
            )
        return row

    def set_program_status(self, program_id: str, status: str, *, actor: str, reason: str) -> None:
        if status not in self.PROGRAM_STATUSES:
            raise ValueError(f"Unsupported program status: {status}")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE validation_programs SET status=?,updated_at=? WHERE program_id=?",
                (status, utc_now(), program_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(program_id)
            self._append_audit(
                connection,
                actor=actor,
                action="validation_program.status_changed",
                object_type="validation_program",
                object_id=program_id,
                reason=reason,
                payload={"status": status},
            )

    def register_site(
        self,
        *,
        program_id: str,
        site_name: str,
        organization: str,
        country: str,
        independent: bool,
        principal_investigator: str,
        qa_contact: str,
        laboratory_accreditation: str,
        actor: str,
    ) -> dict[str, Any]:
        identifier = f"SITE-{uuid.uuid4().hex[:10].upper()}"
        row = {
            "site_id": identifier,
            "program_id": program_id,
            "site_name": site_name.strip(),
            "organization": organization.strip(),
            "country": country.strip(),
            "independent": bool(independent),
            "laboratory_accreditation": laboratory_accreditation.strip(),
            "principal_investigator": principal_investigator.strip(),
            "qa_contact": qa_contact.strip(),
            "status": "registered",
            "created_at": utc_now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO validation_sites(site_id,program_id,site_name,organization,country,
                independent,laboratory_accreditation,principal_investigator,qa_contact,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    row["site_name"],
                    row["organization"],
                    row["country"],
                    int(independent),
                    row["laboratory_accreditation"],
                    row["principal_investigator"],
                    row["qa_contact"],
                    "registered",
                    row["created_at"],
                ),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="validation_site.registered",
                object_type="validation_site",
                object_id=identifier,
                reason="Register validation site",
                payload={"organization": row["organization"], "independent": independent},
            )
        return row

    def qualify_site(self, site_id: str, *, actor: str, reason: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE validation_sites SET status='qualified' WHERE site_id=?", (site_id,)
            )
            if cursor.rowcount != 1:
                raise KeyError(site_id)
            self._append_audit(
                connection,
                actor=actor,
                action="validation_site.qualified",
                object_type="validation_site",
                object_id=site_id,
                reason=reason,
                payload={"status": "qualified"},
            )

    def create_protocol(
        self,
        *,
        program_id: str,
        protocol_id: str,
        title: str,
        primary_endpoint: str,
        success_criterion: str,
        sample_size: int,
        statistical_plan: str,
        preregistration_reference: str,
        ethics_reference: str,
        data_management_plan: str,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        if sample_size <= 0:
            raise ValueError("Sample size must be positive")
        with self._connect() as connection:
            current = connection.execute(
                "SELECT MAX(version) AS value FROM protocols WHERE program_id=? AND protocol_id=?",
                (program_id, protocol_id),
            ).fetchone()
            version = int(current["value"] or 0) + 1
            identifier = f"PROT-{uuid.uuid4().hex[:10].upper()}"
            controlled = {
                "program_id": program_id,
                "protocol_id": protocol_id.strip(),
                "version": version,
                "title": title.strip(),
                "primary_endpoint": primary_endpoint.strip(),
                "success_criterion": success_criterion.strip(),
                "sample_size": int(sample_size),
                "statistical_plan": statistical_plan.strip(),
                "preregistration_reference": preregistration_reference.strip(),
                "ethics_reference": ethics_reference.strip(),
                "data_management_plan": data_management_plan.strip(),
                "payload": payload,
            }
            protocol_hash = _sha_bytes(_canonical(controlled).encode())
            created = utc_now()
            connection.execute(
                """INSERT INTO protocols(protocol_version_id,program_id,protocol_id,version,title,
                status,primary_endpoint,success_criterion,sample_size,statistical_plan,
                preregistration_reference,ethics_reference,data_management_plan,payload_json,
                protocol_sha256,created_by,created_at,approved_by,approved_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    controlled["protocol_id"],
                    version,
                    controlled["title"],
                    "draft",
                    controlled["primary_endpoint"],
                    controlled["success_criterion"],
                    sample_size,
                    controlled["statistical_plan"],
                    controlled["preregistration_reference"],
                    controlled["ethics_reference"],
                    controlled["data_management_plan"],
                    _canonical(payload),
                    protocol_hash,
                    actor.strip(),
                    created,
                    None,
                    None,
                ),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="protocol.created",
                object_type="protocol",
                object_id=identifier,
                reason="Create validation protocol",
                payload={"protocol_sha256": protocol_hash, "version": version},
            )
        return {
            "protocol_version_id": identifier,
            **controlled,
            "status": "draft",
            "protocol_sha256": protocol_hash,
            "created_by": actor,
            "created_at": created,
        }

    def approve_protocol(self, protocol_version_id: str, *, approver: str, reason: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE protocols SET status='approved',approved_by=?,approved_at=? WHERE protocol_version_id=?",
                (approver.strip(), utc_now(), protocol_version_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(protocol_version_id)
            self._append_audit(
                connection,
                actor=approver,
                action="protocol.approved",
                object_type="protocol",
                object_id=protocol_version_id,
                reason=reason,
                payload={"status": "approved"},
            )

    def freeze_model(
        self,
        *,
        program_id: str,
        protocol_version_id: str,
        model_id: str,
        model_path: str | Path,
        dataset_path: str | Path,
        code_path: str | Path,
        environment_path: str | Path,
        feature_spec_path: str | Path,
        intended_use: str,
        actor: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            protocol = connection.execute(
                "SELECT status FROM protocols WHERE protocol_version_id=? AND program_id=?",
                (protocol_version_id, program_id),
            ).fetchone()
            if protocol is None or protocol["status"] != "approved":
                raise ValueError("Model freeze requires an approved protocol")
            identifier = f"FRZ-{uuid.uuid4().hex[:10].upper()}"
            row = {
                "freeze_id": identifier,
                "program_id": program_id,
                "protocol_version_id": protocol_version_id,
                "model_id": model_id.strip(),
                "model_sha256": _sha_file(model_path),
                "dataset_sha256": _sha_file(dataset_path),
                "code_sha256": _sha_file(code_path),
                "environment_sha256": _sha_file(environment_path),
                "feature_spec_sha256": _sha_file(feature_spec_path),
                "intended_use": intended_use.strip(),
                "locked_by": actor.strip(),
                "locked_at": utc_now(),
                "status": "locked",
            }
            connection.execute(
                """INSERT INTO model_freezes(freeze_id,program_id,protocol_version_id,model_id,
                model_sha256,dataset_sha256,code_sha256,environment_sha256,feature_spec_sha256,
                intended_use,locked_by,locked_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row.values()),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="model_configuration.frozen",
                object_type="model_freeze",
                object_id=identifier,
                reason="Freeze prospective validation configuration",
                payload={key: value for key, value in row.items() if key.endswith("sha256")},
            )
        return row

    def lock_prediction_batch(
        self,
        *,
        program_id: str,
        freeze_id: str,
        site_id: str,
        batch_label: str,
        predictions_path: str | Path,
        sample_count: int,
        blinded: bool,
        sample_code_scheme: str,
        actor: str,
    ) -> dict[str, Any]:
        if sample_count <= 0:
            raise ValueError("Sample count must be positive")
        with self._connect() as connection:
            site = connection.execute(
                "SELECT status FROM validation_sites WHERE site_id=? AND program_id=?",
                (site_id, program_id),
            ).fetchone()
            freeze = connection.execute(
                "SELECT status FROM model_freezes WHERE freeze_id=? AND program_id=?",
                (freeze_id, program_id),
            ).fetchone()
            if site is None or site["status"] != "qualified":
                raise ValueError("Prediction lock requires a qualified site")
            if freeze is None or freeze["status"] != "locked":
                raise ValueError("Prediction lock requires a locked model freeze")
            identifier = f"PRED-{uuid.uuid4().hex[:10].upper()}"
            row = {
                "batch_id": identifier,
                "program_id": program_id,
                "freeze_id": freeze_id,
                "site_id": site_id,
                "batch_label": batch_label.strip(),
                "predictions_sha256": _sha_file(predictions_path),
                "sample_count": int(sample_count),
                "blinded": bool(blinded),
                "sample_code_scheme": sample_code_scheme.strip(),
                "locked_by": actor.strip(),
                "locked_at": utc_now(),
                "status": "locked",
            }
            values = list(row.values())
            values[7] = int(row["blinded"])
            connection.execute(
                """INSERT INTO prediction_batches(batch_id,program_id,freeze_id,site_id,batch_label,
                predictions_sha256,sample_count,blinded,sample_code_scheme,locked_by,locked_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            self._append_audit(
                connection,
                actor=actor,
                action="predictions.locked",
                object_type="prediction_batch",
                object_id=identifier,
                reason="Lock prospective predictions before outcomes",
                payload={"sample_count": sample_count, "blinded": blinded},
            )
        return row

    def register_outcome_batch(
        self,
        *,
        program_id: str,
        prediction_batch_id: str,
        outcomes_path: str | Path,
        sample_count: int,
        endpoint_name: str,
        adjudicated: bool,
        actor: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            prediction = connection.execute(
                "SELECT sample_count FROM prediction_batches WHERE batch_id=? AND program_id=?",
                (prediction_batch_id, program_id),
            ).fetchone()
            if prediction is None:
                raise KeyError(prediction_batch_id)
            if int(prediction["sample_count"]) != int(sample_count):
                raise ValueError("Outcome count must match the locked prediction count")
            identifier = f"OUT-{uuid.uuid4().hex[:10].upper()}"
            row = {
                "outcome_batch_id": identifier,
                "program_id": program_id,
                "prediction_batch_id": prediction_batch_id,
                "outcomes_sha256": _sha_file(outcomes_path),
                "sample_count": int(sample_count),
                "endpoint_name": endpoint_name.strip(),
                "adjudicated": bool(adjudicated),
                "received_by": actor.strip(),
                "received_at": utc_now(),
                "status": "received",
            }
            values = list(row.values())
            values[6] = int(row["adjudicated"])
            connection.execute(
                """INSERT INTO outcome_batches(outcome_batch_id,program_id,prediction_batch_id,
                outcomes_sha256,sample_count,endpoint_name,adjudicated,received_by,received_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            self._append_audit(
                connection,
                actor=actor,
                action="outcomes.received",
                object_type="outcome_batch",
                object_id=identifier,
                reason="Register adjudicated prospective outcomes",
                payload={"prediction_batch_id": prediction_batch_id, "adjudicated": adjudicated},
            )
        return row

    def record_analysis_result(
        self,
        *,
        program_id: str,
        protocol_version_id: str,
        result_scope: str,
        metric_name: str,
        metric_value: float,
        success_criterion: str,
        passed: bool,
        analysis_content: bytes | None,
        analyst: str,
        site_id: str | None = None,
        subgroup: str | None = None,
        lower_ci: float | None = None,
        upper_ci: float | None = None,
        analysis_path: str | Path | None = None,
    ) -> dict[str, Any]:
        if result_scope not in {"primary", "site", "subgroup", "sensitivity"}:
            raise ValueError("Unsupported result scope")
        if lower_ci is not None and upper_ci is not None and lower_ci > upper_ci:
            raise ValueError("Lower confidence limit cannot exceed upper limit")
        identifier = f"ANL-{uuid.uuid4().hex[:10].upper()}"
        row = {
            "analysis_result_id": identifier,
            "program_id": program_id,
            "protocol_version_id": protocol_version_id,
            "result_scope": result_scope,
            "site_id": site_id,
            "subgroup": subgroup,
            "metric_name": metric_name.strip(),
            "metric_value": float(metric_value),
            "lower_ci": lower_ci,
            "upper_ci": upper_ci,
            "success_criterion": success_criterion.strip(),
            "passed": bool(passed),
            "analysis_sha256": _sha_content_or_file(
                analysis_content, analysis_path, label="analysis output"
            ),
            "status": "submitted",
            "analyst": analyst.strip(),
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": utc_now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO analysis_results(analysis_result_id,program_id,protocol_version_id,
                result_scope,site_id,subgroup,metric_name,metric_value,lower_ci,upper_ci,
                success_criterion,passed,analysis_sha256,status,analyst,reviewed_by,reviewed_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    protocol_version_id,
                    result_scope,
                    site_id,
                    subgroup,
                    row["metric_name"],
                    row["metric_value"],
                    lower_ci,
                    upper_ci,
                    row["success_criterion"],
                    int(passed),
                    row["analysis_sha256"],
                    "submitted",
                    row["analyst"],
                    None,
                    None,
                    row["created_at"],
                ),
            )
            self._append_audit(
                connection,
                actor=analyst,
                action="analysis_result.recorded",
                object_type="analysis_result",
                object_id=identifier,
                reason="Record predefined validation result",
                payload={"scope": result_scope, "metric": row["metric_name"], "passed": passed},
            )
        return row

    def review_analysis_result(
        self, analysis_result_id: str, *, reviewer: str, status: str, reason: str
    ) -> None:
        if status not in {"approved", "rejected"}:
            raise ValueError("Analysis review status must be approved or rejected")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE analysis_results SET status=?,reviewed_by=?,reviewed_at=? WHERE analysis_result_id=?",
                (status, reviewer.strip(), utc_now(), analysis_result_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(analysis_result_id)
            self._append_audit(
                connection,
                actor=reviewer,
                action="analysis_result.reviewed",
                object_type="analysis_result",
                object_id=analysis_result_id,
                reason=reason,
                payload={"status": status},
            )

    def verify_audit_chain(self) -> AuditChainVerification:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
        previous_hash = "0" * 64
        final_hash = previous_hash
        for row in rows:
            event = {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "action": row["action"],
                "object_type": row["object_type"],
                "object_id": row["object_id"],
                "reason": row["reason"],
                "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"],
            }
            expected = _sha_bytes(_canonical(event).encode())
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                return AuditChainVerification(False, len(rows), int(row["sequence"]), final_hash)
            previous_hash = row["event_hash"]
            final_hash = previous_hash
        return AuditChainVerification(True, len(rows), None, final_hash)

    @staticmethod
    def _decode_row(table: str, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key in list(result):
            if key.endswith("_json"):
                result[key.removesuffix("_json")] = json.loads(result.pop(key))
        for key in (
            "independent",
            "blinded",
            "adjudicated",
            "passed",
            "effectiveness_verified",
            "test_fixture",
        ):
            if key in result:
                result[key] = bool(result[key])
        return result

    def _rows(self, table: str, program_id: str) -> list[dict[str, Any]]:
        if table not in self.TABLES:
            raise ValueError(f"Unsupported table: {table}")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE program_id=? ORDER BY rowid", (program_id,)
            ).fetchall()
        return [self._decode_row(table, row) for row in rows]

    def list_programs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM validation_programs ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode_row("validation_programs", row) for row in rows]

    def snapshot(self, program_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            program = connection.execute(
                "SELECT * FROM validation_programs WHERE program_id=?", (program_id,)
            ).fetchone()
        if program is None:
            raise KeyError(program_id)
        payload = {"program": self._decode_row("validation_programs", program)}
        for table in self.TABLES:
            payload[table.replace("validation_", "")] = self._rows(table, program_id)
        payload["audit"] = self.verify_audit_chain().__dict__
        return payload

    def export_tables(self, program_id: str) -> dict[str, list[dict[str, Any]]]:
        snapshot = self.snapshot(program_id)
        return {
            "program": [snapshot["program"]],
            **{table: snapshot[table.replace("validation_", "")] for table in self.TABLES},
        }
