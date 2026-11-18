from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from biointel.database.core import managed_connect
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMPLETED_STATUSES = {"completed", "approved", "accepted", "published", "closed"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_sha256(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(_SHA256_RE.fullmatch(text)) and text not in {"0" * 64, "f" * 64}


@dataclass(frozen=True)
class OperationalArtifact:
    artifact_type: str
    uri: str
    sha256: str
    observed_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class OperationalAttestation:
    signer_organization: str
    signer_identity: str
    signer_role: str
    independent: bool
    decision: str
    signature_sha256: str
    signed_at: str
    notes: str = ""


@dataclass(frozen=True)
class OperationalEvidence:
    evidence_id: str
    area_key: str
    title: str
    status: str
    evidence_class: str
    issuer_organization: str
    subject_organization: str
    environment: str
    country: str
    started_at: str
    ended_at: str
    manifest_sha256: str
    release_eligible: bool
    blockers: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RealWorldCapability:
    key: str
    label: str
    implementation_score: float
    evidence_score: float
    implementation_status: str
    evidence_status: str
    passed_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    qualifying_evidence: int
    blockers: tuple[str, ...]
    boundary: str


AREA_LABELS: dict[str, str] = {
    "pharma_rnd_deployment": "Real Pharma R&D Deployment Evidence",
    "clinical_deployment": "Real Clinical Deployment Evidence",
    "publication_grade_dti": "Publication-Grade DTI Evidence",
    "peer_reviewed_validation": "Peer-Reviewed Validation Evidence",
    "regulatory_approval": "Regulatory Approval Evidence",
    "gxp_operating_history": "Completed GxP Operating History",
    "regulatory_inspection": "Successful Regulatory Inspection History",
    "production_sla_history": "Production SLA Operating History",
    "multitenant_production": "Real Multi-Tenant Production History",
    "kubernetes_production": "Real Kubernetes Production History",
    "cloud_scale": "Real Cloud Scale Evidence",
    "sustained_high_load": "Sustained High-Load Production Evidence",
    "disaster_recovery_drill": "Disaster-Recovery Drill Evidence",
    "high_availability": "High-Availability Production Evidence",
    "commercial_saas_history": "Commercial SaaS Operating History",
    "enterprise_customer_validation": "Enterprise Customer Validation",
    "pharma_customer_validation": "Pharmaceutical Customer Validation",
    "overall_platform_maturity": "Real-World Overall Platform Maturity",
}

BASELINE_BLOCKERS: dict[str, tuple[str, ...]] = {
    "pharma_rnd_deployment": ("Import a sponsor-signed production R&D deployment dossier covering at least 90 days.",),
    "clinical_deployment": ("Import approved clinical protocol, ethics decision and production operating evidence.",),
    "publication_grade_dti": ("Register a DOI-linked DTI publication with code, data and reproducibility bundle.",),
    "peer_reviewed_validation": ("Register accepted peer-reviewed validation and at least two independent reviews.",),
    "regulatory_approval": ("Import a verifiable regulator decision letter and approved intended-use identifier.",),
    "gxp_operating_history": ("Record at least 180 days of validated operation, training, deviations and CAPA metrics.",),
    "regulatory_inspection": ("Import an authority inspection report and evidence that critical findings are closed.",),
    "production_sla_history": ("Import at least 90 days of signed SLA telemetry and incident/postmortem evidence.",),
    "multitenant_production": ("Import 90-day production evidence for at least three independent tenants with zero isolation breaches.",),
    "kubernetes_production": ("Import 90-day multi-zone Kubernetes operating, upgrade and rollback evidence.",),
    "cloud_scale": ("Import cloud billing/telemetry evidence for regional autoscaling and at least one million requests.",),
    "sustained_high_load": ("Import a 24-hour production-like load run with latency, error and saturation metrics.",),
    "disaster_recovery_drill": ("Import a completed restore drill with measured RTO/RPO and checksum verification.",),
    "high_availability": ("Import 90-day availability history and a successful multi-zone failover event.",),
    "commercial_saas_history": ("Import 180-day billing/support history for at least three paying customers.",),
    "enterprise_customer_validation": ("Import signed external enterprise acceptance against measurable success criteria.",),
    "pharma_customer_validation": ("Import signed pharmaceutical customer acceptance and scientific decision-use evidence.",),
    "overall_platform_maturity": ("Complete qualifying evidence across all external operating-history categories.",),
}

# Each area has five executable/documented controls. The readiness score is based on
# repository controls; the evidence score is based only on accepted registry records.
CONTROL_DEFINITIONS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    key: (
        ("Evidence registry and hard qualification rules", "src/biointel/realworld/evidence.py", (key, "release_eligible")),
        ("Real-world evidence policy", "config/step41_realworld_evidence_policy.yaml", (key, "external_attestation")),
        ("Auditable import template", "data/templates/step41_operational_evidence_manifest.json", ("manifest_sha256", "artifacts", "attestations")),
        ("Qualification and registration tooling", "scripts/qualify_step41_realworld.py", ("build_step41_realworld_readiness", "integrity")),
        ("Automated controls test", "tests/operations/test_step41_realworld_operations.py", (key, "implementation_average")),
    )
    for key in AREA_LABELS
}


class RealWorldEvidenceRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = managed_connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_records(
                    evidence_id TEXT PRIMARY KEY,
                    area_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    issuer_organization TEXT NOT NULL,
                    subject_organization TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    country TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    release_eligible INTEGER NOT NULL,
                    blockers_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts(
                    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
                    artifact_type TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metrics(
                    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    threshold REAL,
                    comparator TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    window_start TEXT,
                    window_end TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attestations(
                    attestation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
                    signer_organization TEXT NOT NULL,
                    signer_identity TEXT NOT NULL,
                    signer_role TEXT NOT NULL,
                    independent INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    signature_sha256 TEXT NOT NULL,
                    signed_at TEXT NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entities(
                    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    country TEXT NOT NULL,
                    external INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_chain(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    chain_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_realworld_area ON evidence_records(area_key, release_eligible);
                CREATE INDEX IF NOT EXISTS idx_realworld_artifact ON artifacts(evidence_id, artifact_type);
                CREATE INDEX IF NOT EXISTS idx_realworld_metric ON metrics(evidence_id, metric_name);
                CREATE INDEX IF NOT EXISTS idx_realworld_entity ON entities(evidence_id, entity_type);
                """
            )

    @staticmethod
    def _duration_days(started_at: str, ended_at: str) -> float:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            return max((end - start).total_seconds() / 86400.0, 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _metric_map(metrics: Sequence[dict[str, Any]]) -> dict[str, float]:
        result: dict[str, float] = {}
        for item in metrics:
            try:
                result[str(item["metric_name"])] = float(item["metric_value"])
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def _qualify(
        self,
        payload: dict[str, Any],
        artifacts: Sequence[OperationalArtifact],
        metrics: Sequence[dict[str, Any]],
        attestations: Sequence[OperationalAttestation],
        entities: Sequence[dict[str, Any]],
    ) -> tuple[bool, tuple[str, ...]]:
        blockers: list[str] = []
        area = str(payload.get("area_key", ""))
        if area not in AREA_LABELS or area == "overall_platform_maturity":
            blockers.append("A supported non-aggregate area_key is required.")
        if str(payload.get("status", "")).lower() not in COMPLETED_STATUSES:
            blockers.append("Evidence status must be completed, approved, accepted, published or closed.")
        if str(payload.get("evidence_class", "")).lower() in {"demo", "template", "rehearsal", "simulation"}:
            blockers.append("Demo, template, rehearsal and simulation evidence cannot qualify as real operating history.")
        if not valid_sha256(str(payload.get("manifest_sha256", ""))):
            blockers.append("A valid immutable manifest SHA-256 is required.")
        if len(artifacts) < 2:
            blockers.append("At least two independently verifiable artifacts are required.")
        if any(not valid_sha256(item.sha256) for item in artifacts):
            blockers.append("Every artifact requires a valid SHA-256 digest.")
        approved_independent = [
            item for item in attestations
            if item.independent and item.decision.lower() in {"approved", "accepted", "passed"}
            and valid_sha256(item.signature_sha256)
            and item.signer_organization != str(payload.get("subject_organization", ""))
        ]
        if not approved_independent:
            blockers.append("At least one independent external signed approval is required.")
        duration_days = self._duration_days(str(payload.get("started_at", "")), str(payload.get("ended_at", "")))
        metric = self._metric_map(metrics)
        artifact_types = {item.artifact_type for item in artifacts}
        entity_types = [str(item.get("entity_type", "")) for item in entities]
        external_entities = [item for item in entities if bool(item.get("external"))]
        metadata = dict(payload.get("metadata") or {})

        def require(condition: bool, message: str) -> None:
            if not condition:
                blockers.append(message)

        if area == "pharma_rnd_deployment":
            require(duration_days >= 90, "Pharma R&D deployment requires at least 90 days of operating history.")
            require(metadata.get("subject_sector") == "pharmaceutical", "Subject organization must be identified as pharmaceutical.")
            require(metric.get("projects_completed", 0) >= 1, "At least one completed R&D project is required.")
            require(metric.get("decision_adoption", 0) >= 1, "Documented scientific decision adoption is required.")
            require("deployment_dossier" in artifact_types, "A signed deployment dossier is required.")
        elif area == "clinical_deployment":
            require(duration_days >= 90, "Clinical deployment requires at least 90 days of operating history.")
            require(metadata.get("ethics_approved") is True, "Ethics/IRB approval must be recorded.")
            require("clinical_protocol" in artifact_types and "ethics_decision" in artifact_types, "Clinical protocol and ethics decision artifacts are required.")
            require(metric.get("critical_safety_events", 1) == 0, "No unresolved critical safety event may be present.")
        elif area == "publication_grade_dti":
            require(str(metadata.get("doi", "")).startswith("10."), "A valid DOI is required.")
            require({"manuscript", "dataset", "source_code", "reproducibility_bundle"}.issubset(artifact_types), "Manuscript, dataset, source code and reproducibility bundle are required.")
            require(metadata.get("dti_domain") is True, "Publication must be a Drug–Target Interaction study.")
        elif area == "peer_reviewed_validation":
            require(str(metadata.get("doi", "")).startswith("10."), "A DOI-linked validation publication is required.")
            require(metadata.get("peer_reviewed") is True, "Peer-reviewed status must be verified.")
            require(len(approved_independent) >= 2, "At least two independent signed validation reviews are required.")
        elif area == "regulatory_approval":
            require(bool(metadata.get("regulatory_authority")), "Regulatory authority is required.")
            require(bool(metadata.get("approval_id")), "Regulatory approval identifier is required.")
            require(bool(metadata.get("intended_use")), "Approved intended use is required.")
            require("regulatory_decision_letter" in artifact_types, "Regulatory decision letter artifact is required.")
        elif area == "gxp_operating_history":
            require(duration_days >= 180, "GxP operating history requires at least 180 days.")
            require(metric.get("training_compliance", 0) >= 0.95, "Training compliance must be at least 95%.")
            require(metric.get("audit_trail_completeness", 0) >= 0.99, "Audit-trail completeness must be at least 99%.")
            require(metric.get("capa_closure_rate", 0) >= 0.90, "CAPA closure rate must be at least 90%.")
            require({"validation_report", "sop_index", "training_report"}.issubset(artifact_types), "Validation, SOP and training artifacts are required.")
        elif area == "regulatory_inspection":
            require(bool(metadata.get("regulatory_authority")), "Inspection authority is required.")
            require(metric.get("open_critical_findings", 1) == 0, "Critical inspection findings must be closed.")
            require("inspection_report" in artifact_types, "Authority inspection report is required.")
            require("capa_evidence" in artifact_types or metric.get("findings_total", 0) == 0, "CAPA closure evidence is required when findings exist.")
        elif area == "production_sla_history":
            require(duration_days >= 90, "SLA evidence requires at least 90 days.")
            require(metric.get("availability_percent", 0) >= 99.9, "Availability must be at least 99.9%.")
            require(metric.get("error_rate_percent", 100) <= 1.0, "Error rate must be at most 1.0%.")
            require(metric.get("p95_latency_ms", 10**9) <= 1000, "P95 latency must be at most 1000 ms.")
            require("signed_sla_report" in artifact_types and "incident_postmortems" in artifact_types, "Signed SLA report and incident postmortems are required.")
        elif area == "multitenant_production":
            require(duration_days >= 90, "Multi-tenant production history requires at least 90 days.")
            require(entity_types.count("tenant") >= 3 and len(external_entities) >= 3, "At least three external tenant organizations are required.")
            require(metric.get("isolation_tests", 0) >= 1000, "At least 1,000 tenant-isolation checks are required.")
            require(metric.get("confirmed_isolation_breaches", 1) == 0, "Confirmed tenant-isolation breaches must be zero.")
        elif area == "kubernetes_production":
            require(duration_days >= 90, "Kubernetes production history requires at least 90 days.")
            require(metric.get("availability_percent", 0) >= 99.9, "Kubernetes availability must be at least 99.9%.")
            require(metric.get("availability_zones", 0) >= 2, "At least two availability zones are required.")
            require(metric.get("successful_upgrades", 0) >= 1, "At least one successful production upgrade is required.")
            require("rollback_drill" in artifact_types, "A verified rollback drill artifact is required.")
        elif area == "cloud_scale":
            require(metric.get("total_requests", 0) >= 1_000_000, "At least one million measured requests are required.")
            require(metric.get("autoscale_events", 0) >= 10, "At least ten successful autoscale events are required.")
            require(metric.get("regions", 0) >= 2, "At least two cloud regions are required.")
            require("cloud_telemetry_export" in artifact_types and "cost_report" in artifact_types, "Cloud telemetry and cost evidence are required.")
        elif area == "sustained_high_load":
            require(duration_days >= 1, "High-load qualification must run for at least 24 hours.")
            require(metric.get("total_requests", 0) >= 1_000_000, "At least one million requests are required.")
            require(metric.get("error_rate_percent", 100) <= 1.0, "Error rate must be at most 1.0%.")
            require(metric.get("p95_latency_ms", 10**9) <= 1000, "P95 latency must be at most 1000 ms.")
            require("load_test_report" in artifact_types, "A raw load-test report is required.")
        elif area == "disaster_recovery_drill":
            require(metric.get("rto_minutes", 10**9) <= 240, "Measured RTO must be four hours or less.")
            require(metric.get("rpo_minutes", 10**9) <= 60, "Measured RPO must be one hour or less.")
            require(metric.get("restore_checksum_match", 0) == 1, "Restored-data checksum verification must pass.")
            require("drill_report" in artifact_types and "restore_manifest" in artifact_types, "DR drill and restore manifest artifacts are required.")
        elif area == "high_availability":
            require(duration_days >= 90, "HA evidence requires at least 90 days.")
            require(metric.get("availability_percent", 0) >= 99.95, "HA availability must be at least 99.95%.")
            require(metric.get("successful_failovers", 0) >= 1, "At least one successful failover is required.")
            require(metric.get("availability_zones", 0) >= 2, "At least two availability zones are required.")
            require("failover_report" in artifact_types, "A failover report is required.")
        elif area == "commercial_saas_history":
            require(duration_days >= 180, "Commercial SaaS history requires at least 180 days.")
            require(metric.get("paying_customers", 0) >= 3, "At least three paying customers are required.")
            require(metric.get("completed_billing_cycles", 0) >= 3, "At least three completed billing cycles are required.")
            require(metric.get("support_sla_percent", 0) >= 95, "Support SLA attainment must be at least 95%.")
            require("billing_export" in artifact_types and "support_report" in artifact_types, "Billing and support evidence are required.")
        elif area == "enterprise_customer_validation":
            require(duration_days >= 30, "Enterprise validation requires at least 30 days.")
            require(any(item.get("entity_type") == "customer" and item.get("external") for item in entities), "An external enterprise customer is required.")
            require(metric.get("success_criteria_passed", 0) >= 1, "At least one measurable customer success criterion must pass.")
            require("customer_acceptance" in artifact_types, "Signed customer acceptance is required.")
        elif area == "pharma_customer_validation":
            require(duration_days >= 30, "Pharma validation requires at least 30 days.")
            require(metadata.get("customer_sector") == "pharmaceutical", "Customer must be identified as pharmaceutical.")
            require(metric.get("scientific_decisions_supported", 0) >= 1, "At least one documented scientific decision is required.")
            require("customer_acceptance" in artifact_types and "scientific_outcome_report" in artifact_types, "Customer acceptance and scientific outcome artifacts are required.")

        return not blockers, tuple(dict.fromkeys(blockers))

    def _append_audit(self, db: sqlite3.Connection, evidence_id: str, event_type: str, payload: dict[str, Any]) -> None:
        previous = db.execute("SELECT chain_hash FROM audit_chain ORDER BY event_id DESC LIMIT 1").fetchone()
        previous_hash = str(previous[0]) if previous else "GENESIS"
        payload_sha = sha256_text(canonical_json(payload))
        created_at = datetime.now(UTC).isoformat()
        chain_hash = sha256_text(f"{previous_hash}|{evidence_id}|{event_type}|{payload_sha}|{created_at}")
        db.execute(
            "INSERT INTO audit_chain(evidence_id,event_type,payload_sha256,previous_hash,chain_hash,created_at) VALUES(?,?,?,?,?,?)",
            (evidence_id, event_type, payload_sha, previous_hash, chain_hash, created_at),
        )

    def register_evidence(
        self,
        *,
        payload: dict[str, Any],
        artifacts: Sequence[OperationalArtifact],
        metrics: Sequence[dict[str, Any]],
        attestations: Sequence[OperationalAttestation],
        entities: Sequence[dict[str, Any]] = (),
    ) -> OperationalEvidence:
        eligible, blockers = self._qualify(payload, artifacts, metrics, attestations, entities)
        evidence_id = str(payload.get("evidence_id") or sha256_text(canonical_json(payload))[:24])
        metadata = dict(payload.get("metadata") or {})
        record = OperationalEvidence(
            evidence_id=evidence_id,
            area_key=str(payload.get("area_key", "")),
            title=str(payload.get("title", evidence_id)),
            status=str(payload.get("status", "draft")),
            evidence_class=str(payload.get("evidence_class", "unknown")),
            issuer_organization=str(payload.get("issuer_organization", "unknown")),
            subject_organization=str(payload.get("subject_organization", "unknown")),
            environment=str(payload.get("environment", "unknown")),
            country=str(payload.get("country", "unknown")),
            started_at=str(payload.get("started_at", "")),
            ended_at=str(payload.get("ended_at", "")),
            manifest_sha256=str(payload.get("manifest_sha256", "")),
            release_eligible=eligible,
            blockers=blockers,
            metadata=metadata,
        )
        now = datetime.now(UTC).isoformat()
        with self.connection() as db:
            db.execute("DELETE FROM evidence_records WHERE evidence_id=?", (evidence_id,))
            db.execute(
                """INSERT INTO evidence_records(
                    evidence_id,area_key,title,status,evidence_class,issuer_organization,subject_organization,
                    environment,country,started_at,ended_at,manifest_sha256,release_eligible,blockers_json,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.evidence_id, record.area_key, record.title, record.status, record.evidence_class,
                    record.issuer_organization, record.subject_organization, record.environment, record.country,
                    record.started_at, record.ended_at, record.manifest_sha256, int(record.release_eligible),
                    canonical_json(record.blockers), canonical_json(record.metadata), now,
                ),
            )
            for item in artifacts:
                db.execute(
                    "INSERT INTO artifacts(evidence_id,artifact_type,uri,sha256,observed_at,metadata_json) VALUES(?,?,?,?,?,?)",
                    (evidence_id, item.artifact_type, item.uri, item.sha256, item.observed_at, canonical_json(item.metadata)),
                )
            for item in metrics:
                db.execute(
                    """INSERT INTO metrics(evidence_id,metric_name,metric_value,unit,threshold,comparator,passed,window_start,window_end,metadata_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        evidence_id, str(item["metric_name"]), float(item["metric_value"]), str(item.get("unit", "")),
                        None if item.get("threshold") is None else float(item["threshold"]), str(item.get("comparator", ">=")),
                        int(bool(item.get("passed", True))), item.get("window_start"), item.get("window_end"),
                        canonical_json(dict(item.get("metadata") or {})),
                    ),
                )
            for item in attestations:
                db.execute(
                    """INSERT INTO attestations(evidence_id,signer_organization,signer_identity,signer_role,independent,decision,signature_sha256,signed_at,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        evidence_id, item.signer_organization, item.signer_identity, item.signer_role, int(item.independent),
                        item.decision, item.signature_sha256, item.signed_at, item.notes,
                    ),
                )
            for item in entities:
                db.execute(
                    "INSERT INTO entities(evidence_id,entity_type,entity_key,organization,country,external,metadata_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        evidence_id, str(item.get("entity_type", "unknown")), str(item.get("entity_key", "unknown")),
                        str(item.get("organization", "unknown")), str(item.get("country", "unknown")),
                        int(bool(item.get("external"))), canonical_json(dict(item.get("metadata") or {})),
                    ),
                )
            self._append_audit(db, evidence_id, "registered", {"record": asdict(record), "artifacts": len(artifacts), "metrics": len(metrics), "attestations": len(attestations)})
        return record

    def summary(self) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                """SELECT COUNT(*) total, SUM(release_eligible) qualifying,
                COUNT(DISTINCT area_key) areas, COUNT(DISTINCT CASE WHEN release_eligible=1 THEN area_key END) qualifying_areas
                FROM evidence_records"""
            ).fetchone()
            counts = {
                str(r["area_key"]): {"total": int(r["total"]), "qualifying": int(r["qualifying"] or 0)}
                for r in db.execute("SELECT area_key,COUNT(*) total,SUM(release_eligible) qualifying FROM evidence_records GROUP BY area_key")
            }
            artifacts = int(db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
            metrics = int(db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0])
            attestations = int(db.execute("SELECT COUNT(*) FROM attestations").fetchone()[0])
            independent = int(db.execute("SELECT COUNT(*) FROM attestations WHERE independent=1 AND decision IN ('approved','accepted','passed')").fetchone()[0])
            entities = int(db.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        return {
            "records": int(row["total"] or 0), "qualifying_records": int(row["qualifying"] or 0),
            "areas_with_records": int(row["areas"] or 0), "qualifying_areas": int(row["qualifying_areas"] or 0),
            "artifacts": artifacts, "metrics": metrics, "attestations": attestations,
            "independent_approvals": independent, "entities": entities, "area_counts": counts,
        }

    def area_qualifying_count(self, area_key: str) -> int:
        with self.connection() as db:
            return int(db.execute("SELECT COUNT(*) FROM evidence_records WHERE area_key=? AND release_eligible=1", (area_key,)).fetchone()[0])

    def verify_integrity(self) -> dict[str, Any]:
        failures: list[str] = []
        with self.connection() as db:
            fk = db.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                failures.append(f"foreign_key_issues:{len(fk)}")
            previous = "GENESIS"
            for row in db.execute("SELECT * FROM audit_chain ORDER BY event_id"):
                expected = sha256_text(f"{previous}|{row['evidence_id']}|{row['event_type']}|{row['payload_sha256']}|{row['created_at']}")
                if row["previous_hash"] != previous or row["chain_hash"] != expected:
                    failures.append(f"audit_chain:{row['event_id']}")
                previous = str(row["chain_hash"])
            invalid = int(db.execute("SELECT COUNT(*) FROM artifacts WHERE length(sha256)<>64").fetchone()[0])
            if invalid:
                failures.append(f"invalid_artifact_hashes:{invalid}")
        return {"ok": not failures, "failures": failures}


def _control_passes(root: Path, control: tuple[str, str, tuple[str, ...]]) -> bool:
    _, relative, tokens = control
    path = root / relative
    if not path.is_file() or path.stat().st_size == 0:
        return False
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return all(token.lower() in text for token in tokens)


def build_step41_realworld_readiness(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    registry = RealWorldEvidenceRegistry(base / "reports" / "realworld_evidence.sqlite3")
    summary = registry.summary()
    capabilities: list[RealWorldCapability] = []
    non_aggregate_keys = [key for key in AREA_LABELS if key != "overall_platform_maturity"]
    for key, label in AREA_LABELS.items():
        controls = CONTROL_DEFINITIONS[key]
        passed = tuple(control[0] for control in controls if _control_passes(base, control))
        failed = tuple(control[0] for control in controls if control[0] not in passed)
        implementation_score = round(10.0 * len(passed) / len(controls), 1)
        if key == "overall_platform_maturity":
            qualifying = sum(registry.area_qualifying_count(item) > 0 for item in non_aggregate_keys)
            evidence_score = round(10.0 * qualifying / len(non_aggregate_keys), 1)
            blockers = tuple(
                BASELINE_BLOCKERS[item][0] for item in non_aggregate_keys if registry.area_qualifying_count(item) == 0
            )
        else:
            qualifying = registry.area_qualifying_count(key)
            evidence_score = 10.0 if qualifying > 0 else 0.0
            blockers = () if qualifying else BASELINE_BLOCKERS[key]
        capabilities.append(
            RealWorldCapability(
                key=key, label=label, implementation_score=implementation_score, evidence_score=evidence_score,
                implementation_status="complete" if implementation_score == 10.0 else "incomplete",
                evidence_status="qualified" if evidence_score == 10.0 else "external_evidence_required",
                passed_controls=passed, failed_controls=failed, qualifying_evidence=int(qualifying), blockers=blockers,
                boundary="Repository controls can be 10/10; external approvals, customers and operating history require authentic third-party evidence.",
            )
        )
    return {
        "schema": "biointel.step41.realworld-readiness.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "capabilities": [asdict(item) for item in capabilities],
        "capability_count": len(capabilities),
        "implementation_average": round(sum(item.implementation_score for item in capabilities) / len(capabilities), 1),
        "evidence_average": round(sum(item.evidence_score for item in capabilities) / len(capabilities), 1),
        "all_implementation_targets_complete": all(item.implementation_score == 10.0 for item in capabilities),
        "all_external_evidence_qualified": all(item.evidence_score == 10.0 for item in capabilities),
        "summary": summary,
        "integrity": registry.verify_integrity(),
        "dual_score_policy": "10/10 implementation readiness is separate from real approvals, customer validation and production operating history.",
    }
