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


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_sha256(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(_SHA256_RE.fullmatch(text)) and "placeholder" not in text


EVIDENCE_CLASSES = {
    "public_reference_replay",
    "independent_external_analytical",
    "prospective_blinded_analytical",
    "wet_lab_single_site",
    "wet_lab_independent",
    "wet_lab_multisite",
}

COMPLETED_STATUSES = {"completed", "reviewed", "accepted"}


@dataclass(frozen=True)
class SiteAttestation:
    site_id: str
    legal_name: str
    country: str
    organization_id: str
    accreditation: str
    independent_from_sponsor: bool
    attestation_sha256: str


@dataclass(frozen=True)
class ValidationStudy:
    study_id: str
    title: str
    domain: str
    study_type: str
    evidence_class: str
    status: str
    sponsor_organization: str
    coordinator_organization: str
    source_provider: str
    training_provider: str
    dataset_sha256: str
    model_sha256: str
    protocol_sha256: str
    manifest_sha256: str
    preregistered_at: str
    locked_at: str | None
    completed_at: str | None
    blinded: bool
    independent_review: bool
    analytical_only: bool
    release_eligible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ValidationCapability:
    key: str
    label: str
    implementation_score: float
    evidence_score: float
    status: str
    controls: tuple[str, ...]
    blockers: tuple[str, ...]
    boundary: str


CAPABILITY_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "prospective_validation",
        "label": "Prospective Validation — blinded outcomes",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "config/step40_validation_policy.yaml",
            "scripts/register_step40_validation_study.py",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "external_dti_validation",
        "label": "External DTI Validation — independent study",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "config/dti_scientific_benchmark.yaml",
            "scripts/qualify_step40_validation.py",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "independent_dti_benchmarking",
        "label": "Independent DTI Benchmarking",
        "paths": [
            "src/biointel/scientific/benchmark.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "ml_model_quality",
        "label": "ML Model Quality — bundled models",
        "paths": [
            "src/biointel/training/release_gate.py",
            "src/biointel/quality/model_audit.py",
            "config/scientific_release_policy.yaml",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "dti_prediction_capability",
        "label": "DTI Prediction Capability — validated performance",
        "paths": [
            "src/biointel/dti/validation_suite.py",
            "src/biointel/scientific/benchmark.py",
            "config/dti_scientific_benchmark.yaml",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "model_generalization",
        "label": "Model Generalization — unseen biology",
        "paths": [
            "src/biointel/training/scientific_splits.py",
            "src/biointel/training/subgroup_evaluation.py",
            "config/step40_validation_policy.yaml",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "cold_drug_validation",
        "label": "Cold-Drug Real Validation",
        "paths": [
            "src/biointel/training/scientific_splits.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "cold_target_validation",
        "label": "Cold-Target Real Validation",
        "paths": [
            "src/biointel/training/scientific_splits.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "cold_both_validation",
        "label": "Cold-Drug-and-Target Real Validation",
        "paths": [
            "src/biointel/training/scientific_splits.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "scaffold_generalization",
        "label": "Scaffold Generalization — real datasets",
        "paths": [
            "src/biointel/training/scaffold.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "temporal_generalization",
        "label": "Temporal Generalization — historical holdout",
        "paths": [
            "src/biointel/training/scientific_splits.py",
            "src/biointel/dti/validation_suite.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "independent_calibration",
        "label": "Calibration on Independent DTI Data",
        "paths": [
            "src/biointel/training/group_calibration.py",
            "src/biointel/training/evaluation.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "independent_uncertainty",
        "label": "Uncertainty Validation on Independent Data",
        "paths": [
            "src/biointel/training/uncertainty.py",
            "src/biointel/training/evaluation.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "scientific_credibility",
        "label": "Overall Scientific Credibility — actual evidence",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "docs/STEP40_VALIDATION_EVIDENCE.md",
            "pages/74_DTI_Validation_Evidence_Center.py",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "database_depth",
        "label": "Database Real Scientific Depth",
        "paths": [
            "src/biointel/scientific/evidence_lake.py",
            "src/biointel/scientific/validation_depth.py",
            "reports/scientific_evidence.sqlite3",
            "reports/validation_evidence.sqlite3",
        ],
    },
    {
        "key": "evidence_registry",
        "label": "Evidence Registry — volume and diversity",
        "paths": [
            "src/biointel/scientific/evidence_lake.py",
            "src/biointel/scientific/validation_depth.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "provider_integration",
        "label": "Internet/Provider Integration — sustained sync",
        "paths": [
            "src/biointel/scientific/provider_hub.py",
            "scripts/sync_scientific_evidence.py",
            "config/scientific_provider_policy.yaml",
        ],
    },
    {
        "key": "provider_release_coverage",
        "label": "Real Provider Release Coverage",
        "paths": [
            "src/biointel/scientific/provider_hub.py",
            "src/biointel/scientific/evidence_lake.py",
            "config/step40_validation_policy.yaml",
        ],
    },
    {
        "key": "wet_lab_evidence",
        "label": "Real Wet-Lab Evidence",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "config/wetlab_evidence_policy.yaml",
            "scripts/register_step40_validation_study.py",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "prospective_wetlab_reproducibility",
        "label": "Prospective Wet-Lab Reproducibility",
        "paths": [
            "src/biointel/scientific/prospective.py",
            "src/biointel/scientific/validation_depth.py",
            "config/wetlab_evidence_policy.yaml",
            "tests/scientific/test_step40_validation_depth.py",
        ],
    },
    {
        "key": "independent_lab_replication",
        "label": "Independent Laboratory Replication",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "config/wetlab_evidence_policy.yaml",
            "docs/STEP40_VALIDATION_EVIDENCE.md",
        ],
    },
    {
        "key": "multi_site_validation",
        "label": "Multi-Site Validation",
        "paths": [
            "src/biointel/scientific/validation_depth.py",
            "config/wetlab_evidence_policy.yaml",
            "docs/STEP40_VALIDATION_EVIDENCE.md",
        ],
    },
)


class ValidationEvidenceRegistry:
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
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sites(
                    site_id TEXT PRIMARY KEY,
                    legal_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    accreditation TEXT NOT NULL,
                    independent_from_sponsor INTEGER NOT NULL,
                    attestation_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS studies(
                    study_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    study_type TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sponsor_organization TEXT NOT NULL,
                    coordinator_organization TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    training_provider TEXT NOT NULL,
                    dataset_sha256 TEXT NOT NULL,
                    model_sha256 TEXT NOT NULL,
                    protocol_sha256 TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    preregistered_at TEXT NOT NULL,
                    locked_at TEXT,
                    completed_at TEXT,
                    blinded INTEGER NOT NULL,
                    independent_review INTEGER NOT NULL,
                    analytical_only INTEGER NOT NULL,
                    release_eligible INTEGER NOT NULL,
                    blockers_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_sites(
                    study_id TEXT NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
                    site_id TEXT NOT NULL REFERENCES sites(site_id),
                    role TEXT NOT NULL,
                    PRIMARY KEY(study_id, site_id, role)
                );
                CREATE TABLE IF NOT EXISTS outcomes(
                    study_id TEXT NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
                    sample_id TEXT NOT NULL,
                    prediction REAL NOT NULL,
                    uncertainty REAL,
                    outcome REAL NOT NULL,
                    blinded_code TEXT,
                    site_id TEXT NOT NULL REFERENCES sites(site_id),
                    measured_at TEXT NOT NULL,
                    row_sha256 TEXT NOT NULL,
                    PRIMARY KEY(study_id, sample_id)
                );
                CREATE TABLE IF NOT EXISTS metrics(
                    study_id TEXT NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
                    split_name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    ci_lower REAL,
                    ci_upper REAL,
                    threshold REAL,
                    passed INTEGER NOT NULL,
                    PRIMARY KEY(study_id, split_name, metric_name)
                );
                CREATE TABLE IF NOT EXISTS reviews(
                    review_id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
                    reviewer_organization TEXT NOT NULL,
                    reviewer_identity TEXT NOT NULL,
                    independent INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    signature_sha256 TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_releases(
                    provider TEXT NOT NULL,
                    release_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    dataset_sha256 TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    licence TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    PRIMARY KEY(provider, release_id)
                );
                CREATE TABLE IF NOT EXISTS events(
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_studies_class_status ON studies(evidence_class, status);
                CREATE INDEX IF NOT EXISTS idx_outcomes_study ON outcomes(study_id);
                CREATE INDEX IF NOT EXISTS idx_metrics_study ON metrics(study_id);
                """
            )

    def _append_event(self, event_type: str, subject_id: str, payload: dict[str, Any]) -> None:
        occurred = datetime.now(UTC).isoformat()
        with self.connection() as db:
            previous = db.execute(
                "SELECT event_hash FROM events ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            previous_hash = str(previous[0]) if previous else ""
            payload_json = canonical_json(payload)
            event_hash = sha256_text(
                f"{previous_hash}|{event_type}|{subject_id}|{occurred}|{payload_json}"
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                (
                    event_hash[:32],
                    event_type,
                    subject_id,
                    occurred,
                    previous_hash or None,
                    event_hash,
                    payload_json,
                ),
            )

    def register_site(self, attestation: SiteAttestation) -> None:
        if not valid_sha256(attestation.attestation_sha256):
            raise ValueError("Site attestation requires a real SHA-256 value.")
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO sites VALUES(?,?,?,?,?,?,?,?)",
                (
                    attestation.site_id,
                    attestation.legal_name,
                    attestation.country,
                    attestation.organization_id,
                    attestation.accreditation,
                    int(attestation.independent_from_sponsor),
                    attestation.attestation_sha256,
                    datetime.now(UTC).isoformat(),
                ),
            )
        self._append_event("site_registered", attestation.site_id, asdict(attestation))

    def register_provider_release(
        self,
        *,
        provider: str,
        release_id: str,
        source_url: str,
        retrieved_at: str,
        dataset_sha256: str,
        record_count: int,
        licence: str,
        verified: bool,
    ) -> None:
        if not source_url.startswith("https://"):
            raise ValueError("Provider release source must use HTTPS.")
        if not valid_sha256(dataset_sha256):
            raise ValueError("Provider release requires a real dataset SHA-256.")
        if record_count <= 0:
            raise ValueError("Provider release must contain records.")
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO provider_releases VALUES(?,?,?,?,?,?,?,?)",
                (
                    provider,
                    release_id,
                    source_url,
                    retrieved_at,
                    dataset_sha256,
                    int(record_count),
                    licence,
                    int(verified),
                ),
            )
        self._append_event(
            "provider_release_registered",
            f"{provider}:{release_id}",
            {
                "dataset_sha256": dataset_sha256,
                "record_count": record_count,
                "verified": verified,
            },
        )

    @staticmethod
    def _study_blockers(
        payload: dict[str, Any],
        sites: Sequence[SiteAttestation],
        outcomes: Sequence[dict[str, Any]],
        metrics: Sequence[dict[str, Any]],
        reviews: Sequence[dict[str, Any]],
    ) -> list[str]:
        blockers: list[str] = []
        evidence_class = str(payload.get("evidence_class", ""))
        status = str(payload.get("status", ""))
        if evidence_class not in EVIDENCE_CLASSES:
            blockers.append("Unsupported evidence class.")
        for key in ("dataset_sha256", "model_sha256", "protocol_sha256", "manifest_sha256"):
            if not valid_sha256(str(payload.get(key, ""))):
                blockers.append(f"{key} is missing, malformed or a placeholder.")
        prereg = str(payload.get("preregistered_at", ""))
        locked = payload.get("locked_at")
        completed = payload.get("completed_at")
        if not prereg:
            blockers.append("Preregistration timestamp is required.")
        if status in COMPLETED_STATUSES:
            if not locked or not completed:
                blockers.append("Completed studies require lock and completion timestamps.")
            elif not (prereg < str(locked) < str(completed)):
                blockers.append("Study chronology must be preregistration < lock < completion.")
        if evidence_class in {
            "prospective_blinded_analytical",
            "wet_lab_independent",
            "wet_lab_multisite",
        }:
            if not bool(payload.get("blinded")):
                blockers.append("Blinding is required for this evidence class.")
            if status in COMPLETED_STATUSES and len(outcomes) < 100:
                blockers.append("At least 100 locked prediction/outcome pairs are required.")
            if status in COMPLETED_STATUSES and any(
                not row.get("blinded_code") for row in outcomes
            ):
                blockers.append("Every completed blinded outcome requires a blinded code.")
        sponsor = str(payload.get("sponsor_organization", ""))
        if evidence_class in {
            "independent_external_analytical",
            "wet_lab_independent",
            "wet_lab_multisite",
        }:
            independent_sites = [
                site
                for site in sites
                if site.independent_from_sponsor and site.organization_id != sponsor
            ]
            if not independent_sites:
                blockers.append("At least one sponsor-independent site is required.")
            independent_reviews = [
                row
                for row in reviews
                if bool(row.get("independent"))
                and row.get("decision") == "approved"
                and row.get("reviewer_organization") != sponsor
            ]
            if not independent_reviews:
                blockers.append("Independent approved review with signature is required.")
        if evidence_class == "wet_lab_multisite":
            independent_orgs = {
                site.organization_id
                for site in sites
                if site.independent_from_sponsor and site.organization_id != sponsor
            }
            countries = {
                site.country
                for site in sites
                if site.independent_from_sponsor and site.organization_id != sponsor
            }
            if len(independent_orgs) < 3:
                blockers.append(
                    "Multi-site evidence requires at least three independent organizations."
                )
            if len(countries) < 2:
                blockers.append("Multi-site evidence requires at least two countries.")
        if evidence_class.startswith("wet_lab"):
            if bool(payload.get("analytical_only", True)):
                blockers.append("Wet-lab evidence cannot be marked analytical-only.")
            for site in sites:
                if not site.accreditation.strip():
                    blockers.append(
                        f"Site {site.site_id} has no accreditation or quality-system declaration."
                    )
        if status in COMPLETED_STATUSES and not outcomes:
            blockers.append("Completed study has no immutable outcomes.")
        if status in COMPLETED_STATUSES and str(payload.get("domain", "")).lower() == "dti":
            metric_map = {str(row.get("metric_name")): row for row in metrics}
            required_metrics = ("roc_auc", "balanced_accuracy", "ece", "interval_coverage")
            for metric_name in required_metrics:
                row = metric_map.get(metric_name)
                if row is None:
                    blockers.append(f"Required DTI metric is missing: {metric_name}.")
                elif not bool(row.get("passed", False)):
                    blockers.append(f"Required DTI metric failed: {metric_name}.")
                elif row.get("ci_lower") is None or row.get("ci_upper") is None:
                    blockers.append(
                        f"Confidence interval is missing for DTI metric: {metric_name}."
                    )
        if evidence_class == "wet_lab_multisite" and status in COMPLETED_STATUSES:
            metric_names = {
                str(row.get("metric_name")) for row in metrics if bool(row.get("passed", False))
            }
            if "site_effect" not in metric_names or "heterogeneity_i2" not in metric_names:
                blockers.append(
                    "Multi-site evidence requires passed site-effect and heterogeneity analyses."
                )
        return blockers

    def register_study(
        self,
        *,
        payload: dict[str, Any],
        sites: Sequence[SiteAttestation] = (),
        outcomes: Sequence[dict[str, Any]] = (),
        metrics: Sequence[dict[str, Any]] = (),
        reviews: Sequence[dict[str, Any]] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ValidationStudy:
        blockers = self._study_blockers(payload, sites, outcomes, metrics, reviews)
        status = str(payload.get("status", "registered"))
        release_eligible = status in COMPLETED_STATUSES and not blockers
        study_id = str(
            payload.get("study_id") or f"VAL-{sha256_text(canonical_json(payload))[:20]}"
        )
        study = ValidationStudy(
            study_id=study_id,
            title=str(payload.get("title", study_id)),
            domain=str(payload.get("domain", "dti")),
            study_type=str(payload.get("study_type", "validation")),
            evidence_class=str(payload.get("evidence_class", "public_reference_replay")),
            status=status,
            sponsor_organization=str(payload.get("sponsor_organization", "unknown")),
            coordinator_organization=str(payload.get("coordinator_organization", "unknown")),
            source_provider=str(payload.get("source_provider", "unknown")),
            training_provider=str(payload.get("training_provider", "unknown")),
            dataset_sha256=str(payload.get("dataset_sha256", "")),
            model_sha256=str(payload.get("model_sha256", "")),
            protocol_sha256=str(payload.get("protocol_sha256", "")),
            manifest_sha256=str(payload.get("manifest_sha256", "")),
            preregistered_at=str(payload.get("preregistered_at", "")),
            locked_at=(None if payload.get("locked_at") is None else str(payload.get("locked_at"))),
            completed_at=(
                None if payload.get("completed_at") is None else str(payload.get("completed_at"))
            ),
            blinded=bool(payload.get("blinded", False)),
            independent_review=any(
                bool(row.get("independent")) and row.get("decision") == "approved"
                for row in reviews
            ),
            analytical_only=bool(payload.get("analytical_only", True)),
            release_eligible=release_eligible,
            blockers=tuple(blockers),
        )
        with self.connection() as db:
            db.execute(
                """INSERT OR REPLACE INTO studies VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    study.study_id,
                    study.title,
                    study.domain,
                    study.study_type,
                    study.evidence_class,
                    study.status,
                    study.sponsor_organization,
                    study.coordinator_organization,
                    study.source_provider,
                    study.training_provider,
                    study.dataset_sha256,
                    study.model_sha256,
                    study.protocol_sha256,
                    study.manifest_sha256,
                    study.preregistered_at,
                    study.locked_at,
                    study.completed_at,
                    int(study.blinded),
                    int(study.independent_review),
                    int(study.analytical_only),
                    int(study.release_eligible),
                    canonical_json(study.blockers),
                    canonical_json(metadata or {}),
                ),
            )
            for site in sites:
                if not valid_sha256(site.attestation_sha256):
                    raise ValueError(f"Site {site.site_id} has an invalid attestation SHA-256.")
                db.execute(
                    "INSERT OR IGNORE INTO sites VALUES(?,?,?,?,?,?,?,?)",
                    (
                        site.site_id,
                        site.legal_name,
                        site.country,
                        site.organization_id,
                        site.accreditation,
                        int(site.independent_from_sponsor),
                        site.attestation_sha256,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO study_sites VALUES(?,?,?)",
                    (study.study_id, site.site_id, "validation"),
                )
            for row in outcomes:
                site_id = str(row["site_id"])
                core = {
                    "study_id": study.study_id,
                    "sample_id": str(row["sample_id"]),
                    "prediction": float(row["prediction"]),
                    "uncertainty": row.get("uncertainty"),
                    "outcome": float(row["outcome"]),
                    "blinded_code": row.get("blinded_code"),
                    "site_id": site_id,
                    "measured_at": str(row["measured_at"]),
                }
                db.execute(
                    "INSERT OR REPLACE INTO outcomes VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        study.study_id,
                        core["sample_id"],
                        core["prediction"],
                        core["uncertainty"],
                        core["outcome"],
                        core["blinded_code"],
                        site_id,
                        core["measured_at"],
                        sha256_text(canonical_json(core)),
                    ),
                )
            for row in metrics:
                db.execute(
                    "INSERT OR REPLACE INTO metrics VALUES(?,?,?,?,?,?,?,?)",
                    (
                        study.study_id,
                        str(row["split_name"]),
                        str(row["metric_name"]),
                        float(row["metric_value"]),
                        row.get("ci_lower"),
                        row.get("ci_upper"),
                        row.get("threshold"),
                        int(bool(row.get("passed", False))),
                    ),
                )
            for row in reviews:
                signature = str(row.get("signature_sha256", ""))
                if not valid_sha256(signature):
                    raise ValueError("Review signature must be a real SHA-256.")
                review_payload = {**row, "study_id": study.study_id}
                review_id = str(
                    row.get("review_id") or sha256_text(canonical_json(review_payload))[:32]
                )
                db.execute(
                    "INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        review_id,
                        study.study_id,
                        str(row["reviewer_organization"]),
                        str(row["reviewer_identity"]),
                        int(bool(row.get("independent"))),
                        str(row["decision"]),
                        signature,
                        str(row.get("reviewed_at") or datetime.now(UTC).isoformat()),
                        str(row.get("notes", "")),
                    ),
                )
        self._append_event("study_registered", study.study_id, asdict(study))
        return study

    def summary(self) -> dict[str, int]:
        with self.connection() as db:

            def scalar(query: str, args: tuple[object, ...] = ()) -> int:
                return int(db.execute(query, args).fetchone()[0])

            return {
                "studies": scalar("SELECT COUNT(*) FROM studies"),
                "release_eligible_studies": scalar(
                    "SELECT COUNT(*) FROM studies WHERE release_eligible=1"
                ),
                "completed_analytical": scalar(
                    "SELECT COUNT(*) FROM studies WHERE status IN ('completed','reviewed','accepted') AND analytical_only=1 AND release_eligible=1"
                ),
                "completed_external_dti": scalar(
                    "SELECT COUNT(*) FROM studies WHERE domain='dti' AND evidence_class='independent_external_analytical' AND release_eligible=1"
                ),
                "completed_blinded_prospective": scalar(
                    "SELECT COUNT(*) FROM studies WHERE domain='dti' AND evidence_class='prospective_blinded_analytical' AND release_eligible=1"
                ),
                "completed_wetlab": scalar(
                    "SELECT COUNT(*) FROM studies WHERE evidence_class LIKE 'wet_lab_%' AND release_eligible=1"
                ),
                "completed_independent_wetlab": scalar(
                    "SELECT COUNT(*) FROM studies WHERE evidence_class IN ('wet_lab_independent','wet_lab_multisite') AND release_eligible=1"
                ),
                "completed_multisite": scalar(
                    "SELECT COUNT(*) FROM studies WHERE evidence_class='wet_lab_multisite' AND release_eligible=1"
                ),
                "outcomes": scalar("SELECT COUNT(*) FROM outcomes"),
                "sites": scalar("SELECT COUNT(*) FROM sites"),
                "independent_sites": scalar(
                    "SELECT COUNT(*) FROM sites WHERE independent_from_sponsor=1"
                ),
                "provider_releases": scalar("SELECT COUNT(*) FROM provider_releases"),
                "verified_provider_releases": scalar(
                    "SELECT COUNT(*) FROM provider_releases WHERE verified=1"
                ),
                "approved_independent_reviews": scalar(
                    "SELECT COUNT(*) FROM reviews WHERE independent=1 AND decision='approved'"
                ),
            }

    def verify_integrity(self) -> dict[str, Any]:
        errors: list[str] = []
        previous = ""
        with self.connection() as db:
            errors.extend(
                f"foreign_key:{tuple(row)}"
                for row in db.execute("PRAGMA foreign_key_check").fetchall()
            )
            for row in db.execute("SELECT * FROM events ORDER BY rowid"):
                expected = sha256_text(
                    f"{previous}|{row['event_type']}|{row['subject_id']}|{row['occurred_at']}|{row['payload_json']}"
                )
                if expected != row["event_hash"]:
                    errors.append(f"event_hash:{row['event_id']}")
                previous = row["event_hash"]
            for row in db.execute("SELECT * FROM outcomes"):
                core = {
                    "study_id": row["study_id"],
                    "sample_id": row["sample_id"],
                    "prediction": row["prediction"],
                    "uncertainty": row["uncertainty"],
                    "outcome": row["outcome"],
                    "blinded_code": row["blinded_code"],
                    "site_id": row["site_id"],
                    "measured_at": row["measured_at"],
                }
                if sha256_text(canonical_json(core)) != row["row_sha256"]:
                    errors.append(f"outcome_hash:{row['study_id']}:{row['sample_id']}")
        return {"ok": not errors, "errors": errors}


def build_step40_validation_readiness(root: str | Path) -> dict[str, Any]:
    """Build the Step 40 readiness report through the split readiness module."""
    from biointel.scientific.validation_readiness import build_validation_readiness

    return build_validation_readiness(root)
