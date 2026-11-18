from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect
from biointel.runtime_v170.qualification import fingerprint
from biointel.runtime_v170.catalog import engine_catalog, reference_catalog
from biointel.runtime_v170.qualification import Step170Registry
from biointel.models_v171.catalog import APPLICABLE_MODULES
from biointel.models_v171.qualification import qualification_matrix as step171_matrix

from .catalog import ALL_MODULES, PROFILES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(root: Path, payload: dict[str, Any] | None, *, path_key: str = "path", sha_key: str = "sha256") -> dict[str, Any]:
    payload = payload or {}
    raw_path = str(payload.get(path_key) or "").strip()
    expected = str(payload.get(sha_key) or "").lower().strip()
    if not raw_path or not expected:
        return {"verified": False, "path": raw_path, "sha256": expected, "reason": "path or SHA-256 missing"}
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.exists() or path.is_symlink():
        return {"verified": False, "path": str(path), "sha256": expected, "reason": "artifact missing or symlink blocked"}
    try:
        actual = fingerprint(path)["sha256"]
    except (OSError, ValueError) as exc:
        return {"verified": False, "path": str(path), "sha256": expected, "reason": str(exc)}
    return {
        "verified": actual == expected,
        "path": str(path),
        "sha256": actual,
        "expected_sha256": expected,
        "reason": "verified" if actual == expected else "SHA-256 mismatch",
    }


def _verify_signature(review_path: str, signature_path: str, public_key_path: str) -> bool:
    openssl = shutil.which("openssl")
    if not openssl:
        return False
    for value in (review_path, signature_path, public_key_path):
        if not value or not Path(value).is_file():
            return False
    command = [openssl, "dgst", "-sha256", "-verify", public_key_path, "-signature", signature_path, review_path]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "Verified OK" in (result.stdout + result.stderr)


def _split_modules(value: Any) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _upstream_readiness(root: Path, module_key: str) -> dict[str, Any]:
    step170 = Step170Registry(root)
    with step170._connect() as con:  # internal read-only use for a unified release gate
        engines = {row["engine"]: bool(row["qualified"]) for row in con.execute("SELECT engine,qualified FROM engine_qualifications")}
        references = {row["reference_id"]: bool(row["qualified"]) for row in con.execute("SELECT reference_id,qualified FROM reference_qualifications")}
    required_engines = [row["engine"] for row in engine_catalog().to_dict("records") if module_key in _split_modules(row.get("modules"))]
    required_refs = [row["reference_id"] for row in reference_catalog().to_dict("records") if module_key in _split_modules(row.get("modules"))]
    engine_complete = all(engines.get(item, False) for item in required_engines)
    reference_complete = all(references.get(item, False) for item in required_refs)
    model_complete = True
    model_research_benchmark = True
    if module_key in APPLICABLE_MODULES:
        frame = step171_matrix(root)
        row = frame.loc[frame["module_key"] == module_key]
        model_research_benchmark = bool(not row.empty and row.iloc[0].get("research_benchmark_qualified", False))
        model_complete = model_research_benchmark
    return {
        "required_engines": required_engines,
        "qualified_engines": [item for item in required_engines if engines.get(item, False)],
        "required_references": required_refs,
        "qualified_references": [item for item in required_refs if references.get(item, False)],
        "runtime_complete": engine_complete,
        "reference_complete": reference_complete,
        "model_research_benchmark_complete": model_complete,
    }


class Step172Registry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (self.root / "UserData")).resolve()
        self.state = user_data / "step172"
        self.submissions = self.state / "submissions"
        self.db_path = self.state / "external_confirmation_release.sqlite3"
        self.state.mkdir(parents=True, exist_ok=True)
        self.submissions.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS modules(
                    module_key TEXT PRIMARY KEY,
                    module_title TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    profile_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submissions(
                    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
                    manifest_path TEXT NOT NULL DEFAULT '',
                    manifest_sha256 TEXT NOT NULL DEFAULT '',
                    imported_at_utc TEXT NOT NULL DEFAULT '',
                    evaluation_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS release_decisions(
                    module_key TEXT PRIMARY KEY REFERENCES modules(module_key) ON DELETE CASCADE,
                    wet_lab_complete INTEGER NOT NULL DEFAULT 0,
                    prospective_complete INTEGER NOT NULL DEFAULT 0,
                    orthogonal_complete INTEGER NOT NULL DEFAULT 0,
                    independent_site_complete INTEGER NOT NULL DEFAULT 0,
                    instrument_qualification_complete INTEGER NOT NULL DEFAULT 0,
                    physical_qualification_complete INTEGER NOT NULL DEFAULT 0,
                    expert_signoff_complete INTEGER NOT NULL DEFAULT 0,
                    formal_release_review_complete INTEGER NOT NULL DEFAULT 0,
                    upstream_runtime_reference_model_complete INTEGER NOT NULL DEFAULT 0,
                    release_eligible INTEGER NOT NULL DEFAULT 0,
                    decision TEXT NOT NULL DEFAULT 'blocked',
                    blockers_json TEXT NOT NULL DEFAULT '[]',
                    evaluated_at_utc TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                """
            )
            for key in ALL_MODULES:
                profile = PROFILES[key]
                con.execute(
                    "INSERT INTO modules(module_key,module_title,evidence_class,profile_json) VALUES(?,?,?,?) ON CONFLICT(module_key) DO UPDATE SET module_title=excluded.module_title,evidence_class=excluded.evidence_class,profile_json=excluded.profile_json",
                    (key, profile.module_title, profile.evidence_class, _canonical(profile.__dict__)),
                )
                con.execute("INSERT OR IGNORE INTO submissions(module_key) VALUES(?)", (key,))
                con.execute("INSERT OR IGNORE INTO release_decisions(module_key) VALUES(?)", (key,))
            con.commit()

    def _audit(self, con: sqlite3.Connection, *, actor: str, action: str, module_key: str, payload: dict[str, Any]) -> None:
        previous = con.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = str(previous[0]) if previous else "0" * 64
        body = {
            "timestamp_utc": _now(), "actor": actor.strip() or "local-operator", "action": action,
            "module_key": module_key, "payload": payload, "previous_hash": previous_hash,
        }
        event_hash = sha256(_canonical(body).encode()).hexdigest()
        con.execute(
            "INSERT INTO audit_events(timestamp_utc,actor,action,module_key,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
            (body["timestamp_utc"], body["actor"], action, module_key, _canonical(payload), previous_hash, event_hash),
        )

    def submission_path(self, module_key: str) -> Path:
        return self.submissions / module_key / "confirmation_manifest.json"

    def evaluate_submission(self, module_key: str, manifest_path: str | Path | None = None) -> dict[str, Any]:
        if module_key not in PROFILES:
            raise KeyError(module_key)
        profile = PROFILES[module_key]
        manifest_file = Path(manifest_path).resolve() if manifest_path else self.submission_path(module_key)
        blockers: list[str] = []
        if not manifest_file.is_file() or manifest_file.is_symlink():
            return self._empty_evaluation(module_key, ["confirmation manifest missing"])
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._empty_evaluation(module_key, [f"confirmation manifest invalid: {exc}"])
        if manifest.get("module_key") != module_key:
            blockers.append("manifest module_key mismatch")
        submission_root = manifest_file.parent

        protocol = manifest.get("protocol") or {}
        protocol_art = _artifact(submission_root, protocol)
        protocol_complete = bool(
            protocol_art["verified"] and protocol.get("locked_before_execution") is True
            and protocol.get("acceptance_thresholds_locked") is True
            and str(protocol.get("protocol_id") or "").strip()
        )
        if (profile.requires_prospective or profile.requires_orthogonal or profile.requires_wet_lab) and not protocol_complete:
            blockers.append("locked protocol and acceptance thresholds incomplete")

        qualified_sites = []
        for site in manifest.get("sites") or []:
            art = _artifact(submission_root, site, path_key="qualification_path", sha_key="qualification_sha256")
            if art["verified"] and site.get("independent") is True and site.get("qa_approved") is True:
                qualified_sites.append(site)
        independent_site_complete = len(qualified_sites) >= profile.minimum_independent_sites
        if profile.requires_independent_site and not independent_site_complete:
            blockers.append(f"qualified independent sites {len(qualified_sites)}/{profile.minimum_independent_sites}")

        qualified_instruments = []
        for item in manifest.get("instruments") or []:
            checks = [
                _artifact(submission_root, item, path_key="iq_path", sha_key="iq_sha256"),
                _artifact(submission_root, item, path_key="oq_path", sha_key="oq_sha256"),
                _artifact(submission_root, item, path_key="pq_path", sha_key="pq_sha256"),
                _artifact(submission_root, item, path_key="calibration_path", sha_key="calibration_sha256"),
            ]
            if all(value["verified"] for value in checks) and item.get("qualified") is True and str(item.get("serial_number") or "").strip():
                qualified_instruments.append(item)
        instrument_complete = bool(qualified_instruments) if profile.requires_instrument_qualification else True
        if not instrument_complete:
            blockers.append("instrument IQ/OQ/PQ and calibration qualification incomplete")

        valid_confirmations: list[dict[str, Any]] = []
        for item in manifest.get("confirmations") or []:
            evidence = _artifact(submission_root, item, path_key="evidence_path", sha_key="evidence_sha256")
            data_manifest = _artifact(submission_root, item, path_key="data_manifest_path", sha_key="data_manifest_sha256")
            confirmation_type = str(item.get("type") or "").lower()
            base_valid = bool(
                evidence["verified"] and data_manifest["verified"] and item.get("acceptance_passed") is True
                and int(item.get("sample_count") or 0) > 0 and item.get("independent") is True
            )
            if confirmation_type == "wet_lab":
                base_valid = bool(
                    base_valid and item.get("controls_complete") is True
                    and int(item.get("biological_replicates") or 0) >= 2
                    and int(item.get("technical_replicates") or 0) >= 2
                )
            if confirmation_type == "prospective":
                base_valid = bool(base_valid and item.get("blinded") is True and item.get("adjudicated") is True)
            if base_valid:
                valid_confirmations.append(item)
        wet_lab_complete = any(str(item.get("type")).lower() == "wet_lab" for item in valid_confirmations)
        prospective_complete = any(str(item.get("type")).lower() == "prospective" for item in valid_confirmations)
        orthogonal_complete = any(str(item.get("type")).lower() == "orthogonal" for item in valid_confirmations)
        confirmation_batches = len({str(item.get("batch_id") or "") for item in valid_confirmations if str(item.get("batch_id") or "")})
        if profile.minimum_confirmation_batches and confirmation_batches < profile.minimum_confirmation_batches:
            blockers.append(f"qualified confirmation batches {confirmation_batches}/{profile.minimum_confirmation_batches}")
        if profile.requires_wet_lab and not wet_lab_complete:
            blockers.append("wet-lab confirmation incomplete")
        if profile.requires_prospective and not prospective_complete:
            blockers.append("blinded prospective confirmation incomplete")
        if profile.requires_orthogonal and not orthogonal_complete:
            blockers.append("independent orthogonal confirmation incomplete")

        qualified_experts = []
        for item in manifest.get("experts") or []:
            credential = _artifact(submission_root, item, path_key="credential_path", sha_key="credential_sha256")
            conflict = _artifact(submission_root, item, path_key="conflict_disclosure_path", sha_key="conflict_disclosure_sha256")
            review = _artifact(submission_root, item, path_key="review_path", sha_key="review_sha256")
            signature = _artifact(submission_root, item, path_key="signature_path", sha_key="signature_sha256")
            public_key = _artifact(submission_root, item, path_key="public_key_path", sha_key="public_key_sha256")
            crypto = False
            if all(value["verified"] for value in (review, signature, public_key)):
                crypto = _verify_signature(review["path"], signature["path"], public_key["path"])
            if all(value["verified"] for value in (credential, conflict, review, signature, public_key)) and crypto and item.get("approved") is True and item.get("independent") is True:
                qualified_experts.append({**item, "cryptographic_signature_verified": True})
        expert_complete = len(qualified_experts) >= profile.minimum_qualified_experts
        if profile.requires_expert_signoff and not expert_complete:
            blockers.append(f"cryptographically verified independent expert sign-offs {len(qualified_experts)}/{profile.minimum_qualified_experts}")

        physical = manifest.get("physical_qualification") or {}
        physical_art = _artifact(submission_root, physical, path_key="report_path", sha_key="report_sha256")
        physical_complete = bool(
            physical_art["verified"] and physical.get("windows_tested") is True
            and physical.get("recovery_tested") is True and physical.get("large_file_tested") is True
            and physical.get("antivirus_tested") is True and physical.get("network_loss_tested") is True
            and physical.get("sleep_resume_tested") is True
            and (not profile.requires_gpu_qualification or physical.get("gpu_tested") is True)
            and (not profile.requires_instrument_qualification or physical.get("instrument_tested") is True)
        )
        if not physical_complete:
            blockers.append("physical Windows/GPU/instrument/site qualification incomplete")

        history = manifest.get("operating_history") or {}
        history_art = _artifact(submission_root, history, path_key="report_path", sha_key="report_sha256")
        operating_runs = int(history.get("runs") or 0)
        operating_history_complete = bool(
            history_art["verified"] and operating_runs >= profile.minimum_operating_runs
            and int(history.get("unresolved_critical_incidents") or 0) == 0
            and history.get("drift_review_complete") is True
        )
        if not operating_history_complete:
            blockers.append(f"qualified operating history {operating_runs}/{profile.minimum_operating_runs} runs")

        release = manifest.get("release_review") or {}
        release_art = _artifact(submission_root, release, path_key="decision_path", sha_key="decision_sha256")
        release_review_complete = bool(
            release_art["verified"] and str(release.get("decision") or "").lower() == "approved"
            and int(release.get("quorum") or 0) >= 3 and release.get("independent_qa_approval") is True
            and release.get("domain_expert_approval") is True and release.get("product_owner_approval") is True
            and release.get("risk_acceptance_documented") is True and str(release.get("intended_use") or "").strip()
        )
        if profile.requires_formal_release_review and not release_review_complete:
            blockers.append("formal release committee review incomplete")

        upstream = _upstream_readiness(self.root, module_key)
        upstream_complete = bool(upstream["runtime_complete"] and upstream["reference_complete"] and upstream["model_research_benchmark_complete"])
        if not upstream_complete:
            blockers.append("Step 170 runtime/reference or Step 171 authentic model benchmark incomplete")

        release_eligible = not blockers
        return {
            "schema": "biointel.step172.external-confirmation-evaluation.v1",
            "module_key": module_key,
            "module_title": profile.module_title,
            "evidence_class": profile.evidence_class,
            "software_framework_score": 10.0,
            "protocol_complete": protocol_complete,
            "wet_lab_complete": wet_lab_complete if profile.requires_wet_lab else True,
            "prospective_complete": prospective_complete if profile.requires_prospective else True,
            "orthogonal_complete": orthogonal_complete if profile.requires_orthogonal else True,
            "independent_site_complete": independent_site_complete if profile.requires_independent_site else True,
            "instrument_qualification_complete": instrument_complete,
            "physical_qualification_complete": physical_complete,
            "operating_history_complete": operating_history_complete,
            "expert_signoff_complete": expert_complete,
            "formal_release_review_complete": release_review_complete,
            "upstream_runtime_reference_model_complete": upstream_complete,
            "qualified_sites": len(qualified_sites),
            "qualified_instruments": len(qualified_instruments),
            "qualified_experts": len(qualified_experts),
            "qualified_confirmation_batches": confirmation_batches,
            "upstream": upstream,
            "release_eligible": release_eligible,
            "decision": "controlled-release-eligible" if release_eligible else "research-only-fail-closed",
            "blockers": blockers,
            "manifest_path": str(manifest_file),
            "manifest_sha256": _sha_file(manifest_file),
            "evaluated_at_utc": _now(),
        }

    def _empty_evaluation(self, module_key: str, blockers: list[str]) -> dict[str, Any]:
        profile = PROFILES[module_key]
        return {
            "schema": "biointel.step172.external-confirmation-evaluation.v1",
            "module_key": module_key,
            "module_title": profile.module_title,
            "evidence_class": profile.evidence_class,
            "software_framework_score": 10.0,
            "protocol_complete": False,
            "wet_lab_complete": not profile.requires_wet_lab,
            "prospective_complete": not profile.requires_prospective,
            "orthogonal_complete": not profile.requires_orthogonal,
            "independent_site_complete": not profile.requires_independent_site,
            "instrument_qualification_complete": not profile.requires_instrument_qualification,
            "physical_qualification_complete": False,
            "operating_history_complete": False,
            "expert_signoff_complete": False,
            "formal_release_review_complete": False,
            "upstream_runtime_reference_model_complete": False,
            "qualified_sites": 0,
            "qualified_instruments": 0,
            "qualified_experts": 0,
            "qualified_confirmation_batches": 0,
            "upstream": {},
            "release_eligible": False,
            "decision": "research-only-fail-closed",
            "blockers": blockers,
            "manifest_path": str(self.submission_path(module_key)),
            "manifest_sha256": "",
            "evaluated_at_utc": _now(),
        }

    def import_submission(self, module_key: str, manifest_path: str | Path | None = None, *, actor: str = "local-operator") -> dict[str, Any]:
        evaluation = self.evaluate_submission(module_key, manifest_path)
        manifest_value = Path(evaluation["manifest_path"])
        with self._connect() as con:
            con.execute(
                "UPDATE submissions SET manifest_path=?,manifest_sha256=?,imported_at_utc=?,evaluation_json=? WHERE module_key=?",
                (evaluation["manifest_path"], evaluation["manifest_sha256"], _now(), _canonical(evaluation), module_key),
            )
            con.execute(
                """UPDATE release_decisions SET wet_lab_complete=?,prospective_complete=?,orthogonal_complete=?,independent_site_complete=?,instrument_qualification_complete=?,physical_qualification_complete=?,expert_signoff_complete=?,formal_release_review_complete=?,upstream_runtime_reference_model_complete=?,release_eligible=?,decision=?,blockers_json=?,evaluated_at_utc=? WHERE module_key=?""",
                (
                    int(evaluation["wet_lab_complete"]), int(evaluation["prospective_complete"]), int(evaluation["orthogonal_complete"]),
                    int(evaluation["independent_site_complete"]), int(evaluation["instrument_qualification_complete"]),
                    int(evaluation["physical_qualification_complete"]), int(evaluation["expert_signoff_complete"]),
                    int(evaluation["formal_release_review_complete"]), int(evaluation["upstream_runtime_reference_model_complete"]),
                    int(evaluation["release_eligible"]), evaluation["decision"], _canonical(evaluation["blockers"]), _now(), module_key,
                ),
            )
            self._audit(con, actor=actor, action="step172.submission_evaluated", module_key=module_key, payload={
                "manifest": str(manifest_value), "release_eligible": evaluation["release_eligible"], "blockers": evaluation["blockers"]
            })
            con.commit()
        return evaluation

    def matrix(self, *, refresh: bool = True) -> pd.DataFrame:
        rows = []
        for key in ALL_MODULES:
            evaluation = self.import_submission(key, actor="step172-matrix") if refresh else self.evaluate_submission(key)
            row = {k: v for k, v in evaluation.items() if k not in {"blockers", "upstream"}}
            row["blocker_count"] = len(evaluation["blockers"])
            row["remaining_blockers"] = " | ".join(evaluation["blockers"])
            rows.append(row)
        return pd.DataFrame(rows)

    def status(self) -> dict[str, Any]:
        with self._connect() as con:
            decisions = con.execute("SELECT COUNT(*),SUM(release_eligible) FROM release_decisions").fetchone()
            events = con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        return {
            "schema": "biointel.step172.registry-status.v1",
            "database_integrity": integrity,
            "foreign_key_violations": len(fk),
            "modules_registered": int(decisions[0] or 0),
            "release_eligible_modules": int(decisions[1] or 0),
            "audit_events": int(events or 0),
        }


__all__ = ["Step172Registry"]
