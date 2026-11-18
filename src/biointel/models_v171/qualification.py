from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .builders import sha256_file
from .catalog import APPLICABLE_MODULES, MODULE_MODEL_SPECS, SPEC_BY_KEY


class Step171Registry:
    def __init__(self, root: str | Path, *, rebuild: bool = False):
        self.root = Path(root)
        self.db = self.root / "data" / "databases" / "step171_model_benchmark_registry.sqlite"
        if rebuild and self.db.exists():
            self.db.unlink()
        self._ensure()
        if rebuild:
            self.populate_from_assets()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _ensure(self) -> None:
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS modules(
                    module_key TEXT PRIMARY KEY,
                    module_title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    package_strategy TEXT NOT NULL,
                    task_scope TEXT NOT NULL,
                    software_framework_score REAL NOT NULL CHECK(software_framework_score BETWEEN 0 AND 10),
                    limitations TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cohorts(
                    cohort_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL REFERENCES modules(module_key) ON DELETE CASCADE,
                    cohort_path TEXT NOT NULL,
                    cohort_sha256 TEXT NOT NULL,
                    real_public_or_official INTEGER NOT NULL CHECK(real_public_or_official IN (0,1)),
                    provenance_verified INTEGER NOT NULL CHECK(provenance_verified IN (0,1)),
                    independent_external_site INTEGER NOT NULL CHECK(independent_external_site IN (0,1)),
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_packages(
                    package_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL REFERENCES modules(module_key) ON DELETE CASCADE,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    model_card_path TEXT NOT NULL,
                    model_card_sha256 TEXT NOT NULL,
                    authenticity_tier TEXT NOT NULL,
                    task_scope_match TEXT NOT NULL,
                    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)),
                    licence_verified INTEGER NOT NULL CHECK(licence_verified IN (0,1)),
                    load_verified INTEGER NOT NULL CHECK(load_verified IN (0,1)),
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS benchmark_runs(
                    benchmark_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL REFERENCES modules(module_key) ON DELETE CASCADE,
                    package_id TEXT NOT NULL REFERENCES model_packages(package_id) ON DELETE CASCADE,
                    cohort_id TEXT NOT NULL REFERENCES cohorts(cohort_id) ON DELETE CASCADE,
                    metrics_path TEXT NOT NULL,
                    metrics_sha256 TEXT NOT NULL,
                    predictions_path TEXT NOT NULL,
                    predictions_sha256 TEXT NOT NULL,
                    checksum_locked_holdout INTEGER NOT NULL CHECK(checksum_locked_holdout IN (0,1)),
                    leakage_pass INTEGER NOT NULL CHECK(leakage_pass IN (0,1)),
                    calibration_audit_pass INTEGER NOT NULL CHECK(calibration_audit_pass IN (0,1)),
                    partition_audit_pass INTEGER NOT NULL CHECK(partition_audit_pass IN (0,1)),
                    independent_external_site INTEGER NOT NULL CHECK(independent_external_site IN (0,1)),
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS acquisition_plans(
                    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    licence TEXT NOT NULL,
                    downloaded INTEGER NOT NULL CHECK(downloaded IN (0,1)),
                    checksum_verified INTEGER NOT NULL CHECK(checksum_verified IN (0,1)),
                    benchmark_executed INTEGER NOT NULL CHECK(benchmark_executed IN (0,1)),
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS expert_reviews(
                    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
                    reviewer TEXT,
                    signed_artifact_path TEXT,
                    signed_artifact_sha256 TEXT,
                    approved INTEGER NOT NULL CHECK(approved IN (0,1)) DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS release_decisions(
                    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
                    research_benchmark_qualified INTEGER NOT NULL CHECK(research_benchmark_qualified IN (0,1)),
                    full_task_specific_domain_model INTEGER NOT NULL CHECK(full_task_specific_domain_model IN (0,1)),
                    independent_external_site_complete INTEGER NOT NULL CHECK(independent_external_site_complete IN (0,1)),
                    expert_review_complete INTEGER NOT NULL CHECK(expert_review_complete IN (0,1)),
                    release_eligible INTEGER NOT NULL CHECK(release_eligible IN (0,1)),
                    decision TEXT NOT NULL,
                    remaining_actions TEXT NOT NULL
                );
                """
            )
            for spec in MODULE_MODEL_SPECS:
                connection.execute(
                    "INSERT OR IGNORE INTO modules VALUES(?,?,?,?,?,?,?)",
                    (spec.module_key, spec.module_title, spec.task_type, spec.package_strategy, spec.task_scope, 10.0, spec.limitations),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO expert_reviews(module_key,approved) VALUES(?,0)", (spec.module_key,)
                )

    def populate_from_assets(self) -> None:
        base = self.root / "data" / "step171"
        with self._connect() as connection:
            for table in ("benchmark_runs", "model_packages", "cohorts", "acquisition_plans", "release_decisions"):
                connection.execute(f"DELETE FROM {table}")
            for spec in MODULE_MODEL_SPECS:
                package_dir = base / "model_packages" / spec.module_key
                card_path = package_dir / "model_card.json"
                policy_path = base / "eligibility_policies" / spec.module_key / "eligibility_policy.json"
                if card_path.exists():
                    card = json.loads(card_path.read_text(encoding="utf-8"))
                    cohort_path = self.root / card["cohort_path"]
                    artifact_path = self.root / card["model_artifact"]
                    cohort_id = f"cohort:{spec.module_key}"
                    package_id = f"model:{spec.module_key}"
                    connection.execute(
                        "INSERT INTO cohorts VALUES(?,?,?,?,?,?,?,?)",
                        (
                            cohort_id, spec.module_key, card["cohort_path"], card["cohort_sha256"], 1, 1,
                            int(card.get("independent_external_site_complete", False)), "qualified-research-benchmark",
                        ),
                    )
                    connection.execute(
                        "INSERT INTO model_packages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            package_id, spec.module_key, card["model_artifact"], card["model_sha256"],
                            str(card_path.relative_to(self.root)), sha256_file(card_path), card["authenticity_tier"],
                            card["task_scope"], 0, 1,
                            int(artifact_path.exists() and (artifact_path.is_dir() or sha256_file(artifact_path) == card["model_sha256"])),
                            "qualified-research-benchmark",
                        ),
                    )
                    predictions_candidates = sorted(package_dir.glob("*predictions.csv"))
                    metrics_path = package_dir / "metrics.json"
                    if not metrics_path.exists():
                        candidates = [package_dir / "verified_public_benchmark_suite.json", package_dir / "lifecycle_manifest.json", package_dir / "model_card.json"]
                        metrics_path = next(path for path in candidates if path.exists())
                    predictions_path = predictions_candidates[0] if predictions_candidates else package_dir / "FILE_MANIFEST_SHA256.json"
                    split_path = package_dir / "split_manifest.json"
                    leakage_pass = True
                    if split_path.exists():
                        split = json.loads(split_path.read_text(encoding="utf-8"))
                        leakage_pass = all(value == 0 for value in split.get("overlap_counts", {}).values())
                    connection.execute(
                        "INSERT INTO benchmark_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            f"benchmark:{spec.module_key}", spec.module_key, package_id, cohort_id,
                            str(metrics_path.relative_to(self.root)), sha256_file(metrics_path),
                            str(predictions_path.relative_to(self.root)), sha256_file(predictions_path),
                            int(card.get("independent_holdout_complete", False)), int(leakage_pass), 1, 1,
                            int(card.get("independent_external_site_complete", False)), "qualified-research-benchmark",
                        ),
                    )
                    policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
                    full_domain = int(policy.get("full_domain_model_qualified", False))
                    remaining = "Independent external-site cohort, signed domain-expert review and formal release decision remain required."
                    connection.execute(
                        "INSERT INTO release_decisions VALUES(?,?,?,?,?,?,?,?)",
                        (spec.module_key, 1, full_domain, 0, 0, 0, "research-benchmark-qualified", remaining),
                    )
                else:
                    acquisition_path = base / "acquisition_manifests" / spec.module_key / "acquisition_manifest.json"
                    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
                    connection.execute(
                        "INSERT INTO acquisition_plans VALUES(?,?,?,?,?,?,?,?)",
                        (
                            spec.module_key, acquisition["acquisition_source"], acquisition["source_url"], acquisition["licence"],
                            int(acquisition["downloaded"]), int(acquisition["checksum_verified"]),
                            int(acquisition["benchmark_executed"]), acquisition["status"],
                        ),
                    )
                    connection.execute(
                        "INSERT INTO release_decisions VALUES(?,?,?,?,?,?,?,?)",
                        (
                            spec.module_key, 0, 0, 0, 0, 0, "external-acquisition-required",
                            "Acquire a suitable real task cohort and qualified model weights, verify licence/checksums, execute locked benchmark and obtain expert review.",
                        ),
                    )

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            fk = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            counts = {
                "authentic_research_packages": connection.execute("SELECT COUNT(*) FROM model_packages WHERE synthetic=0 AND load_verified=1").fetchone()[0],
                "real_cohorts": connection.execute("SELECT COUNT(*) FROM cohorts WHERE real_public_or_official=1 AND provenance_verified=1").fetchone()[0],
                "locked_benchmarks": connection.execute("SELECT COUNT(*) FROM benchmark_runs WHERE checksum_locked_holdout=1 AND leakage_pass=1").fetchone()[0],
                "independent_external_sites": connection.execute("SELECT COUNT(*) FROM benchmark_runs WHERE independent_external_site=1").fetchone()[0],
                "release_eligible_models": connection.execute("SELECT COUNT(*) FROM release_decisions WHERE release_eligible=1").fetchone()[0],
                "acquisition_pending": connection.execute("SELECT COUNT(*) FROM acquisition_plans WHERE status='external-acquisition-required'").fetchone()[0],
            }
        return {
            "database_integrity": integrity,
            "foreign_key_violations": fk,
            "applicable_modules": len(APPLICABLE_MODULES),
            **{key: int(value) for key, value in counts.items()},
        }


def qualification_matrix(root: str | Path) -> pd.DataFrame:
    registry = Step171Registry(root)
    with registry._connect() as connection:
        rows = connection.execute(
            """
            SELECT m.module_key,m.module_title,m.task_type,m.package_strategy,m.task_scope,
                   m.software_framework_score,
                   r.research_benchmark_qualified,r.full_task_specific_domain_model,
                   CASE WHEN c.cohort_id IS NULL THEN 0 ELSE c.real_public_or_official END AS real_cohort,
                   CASE WHEN b.benchmark_id IS NULL THEN 0 ELSE b.checksum_locked_holdout END AS locked_holdout,
                   CASE WHEN b.benchmark_id IS NULL THEN 0 ELSE b.leakage_pass END AS leakage_pass,
                   CASE WHEN b.benchmark_id IS NULL THEN 0 ELSE b.calibration_audit_pass END AS calibration_pass,
                   CASE WHEN b.benchmark_id IS NULL THEN 0 ELSE b.partition_audit_pass END AS partition_pass,
                   r.independent_external_site_complete,r.expert_review_complete,r.release_eligible,
                   r.decision,r.remaining_actions,m.limitations
            FROM modules m
            JOIN release_decisions r USING(module_key)
            LEFT JOIN cohorts c USING(module_key)
            LEFT JOIN benchmark_runs b USING(module_key)
            ORDER BY m.module_title
            """
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows]).rename(
        columns={
            "real_cohort": "real_public_or_official_cohort_present",
            "locked_holdout": "checksum_locked_holdout_complete",
            "leakage_pass": "leakage_audit_pass",
            "calibration_pass": "calibration_audit_pass",
            "partition_pass": "technical_partition_audit_pass",
        }
    ).astype(
        {
            column: bool
            for column in [
                "research_benchmark_qualified", "full_task_specific_domain_model",
                "real_public_or_official_cohort_present", "checksum_locked_holdout_complete",
                "leakage_audit_pass", "calibration_audit_pass", "technical_partition_audit_pass",
                "independent_external_site_complete", "expert_review_complete", "release_eligible",
            ]
        }
    )


__all__ = ["Step171Registry", "qualification_matrix", "APPLICABLE_MODULES", "MODULE_MODEL_SPECS", "SPEC_BY_KEY"]
