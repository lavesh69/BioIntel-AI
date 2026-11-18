from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect
from biointel.external_v172 import PROFILES as STEP172_PROFILES, Step172Registry
from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES, Step173Registry
from biointel.models_v171.catalog import APPLICABLE_MODULES
from biointel.models_v171.qualification import qualification_matrix as step171_matrix

from .catalog import PHASES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _phase_commands(module_key: str) -> dict[int, str]:
    return {
        1: "RUN_STEP174_LOCAL_ENVIRONMENT_QUALIFICATION_WINDOWS.bat",
        2: "PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute",
        3: "DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat",
        4: f"python scripts\\step174_realworld_manager.py prepare-model-cohort --module {module_key}",
        5: f"python scripts\\step174_realworld_manager.py prepare-benchmark --module {module_key}",
        6: f"python scripts\\step172_evidence_manager.py prepare {module_key}",
        7: f"python scripts\\step174_realworld_manager.py prepare-expert-kit --module {module_key}",
        8: f"python scripts\\step174_realworld_manager.py prepare-history --module {module_key}",
        9: f"python scripts\\step174_realworld_manager.py prepare-release --module {module_key}",
    }


def automatic_environment_probe(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    usage = shutil.disk_usage(root_path)
    nvidia = shutil.which("nvidia-smi")
    wsl = shutil.which("wsl") or shutil.which("wsl.exe")
    micromamba = shutil.which("micromamba")
    openssl = shutil.which("openssl")
    checks = {
        "project_writable": os.access(root_path, os.W_OK),
        "disk_free_gib_at_least_20": usage.free >= 20 * 1024**3,
        "python_supported": sys.version_info >= (3, 11),
        "openssl_available": bool(openssl),
        "wsl_available_on_host": bool(wsl),
        "micromamba_available_on_host": bool(micromamba),
        "nvidia_runtime_detected": bool(nvidia),
        "running_on_windows": platform.system().lower() == "windows",
    }
    return {
        "schema": "biointel.step174.environment-probe.v1",
        "created_at_utc": _now(),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "disk_free_bytes": usage.free,
        "checks": checks,
        "automatic_checks_passed": bool(checks["project_writable"] and checks["python_supported"] and checks["disk_free_gib_at_least_20"]),
        "target_windows_qualification_complete": False,
        "boundary": "This automatic build-host probe cannot certify a different Windows/GPU/instrument/site environment.",
    }


def _confirmation_complete(module_key: str, external: dict[str, Any]) -> tuple[bool, list[str]]:
    profile = STEP172_PROFILES[module_key]
    required = ["protocol_complete"]
    if profile.requires_independent_site:
        required.append("independent_site_complete")
    if profile.requires_wet_lab:
        required.append("wet_lab_complete")
    if profile.requires_prospective:
        required.append("prospective_complete")
    if profile.requires_orthogonal:
        required.append("orthogonal_complete")
    missing = [field for field in required if not bool(external.get(field))]
    return not missing, missing


def build_phase_execution_matrix(root: str | Path, *, refresh: bool = False) -> pd.DataFrame:
    root_path = Path(root).resolve()
    final = Step173Registry(root_path).latest(refresh=refresh)
    final_rows = {str(row["module_key"]): row for row in final.to_dict(orient="records")}
    models = step171_matrix(root_path)
    model_rows = {str(row["module_key"]): row for row in models.to_dict(orient="records")}
    external = Step172Registry(root_path).matrix(refresh=refresh)
    external_rows = {str(row["module_key"]): row for row in external.to_dict(orient="records")}

    rows: list[dict[str, Any]] = []
    for module_key in ALL_MODULES:
        base = final_rows[module_key]
        ext = external_rows.get(module_key, {})
        model = model_rows.get(module_key, {})
        model_required = module_key in APPLICABLE_MODULES
        commands = _phase_commands(module_key)

        p1 = bool(ext.get("physical_qualification_complete"))
        p2 = int(base.get("qualified_engines") or 0) >= int(base.get("required_engines") or 0)
        p3 = int(base.get("qualified_references") or 0) >= int(base.get("required_references") or 0)
        p4 = True if not model_required else bool(
            model.get("full_task_specific_domain_model") and model.get("real_public_or_official_cohort_present")
        )
        p5 = True if not model_required else bool(
            model.get("checksum_locked_holdout_complete")
            and model.get("leakage_audit_pass")
            and model.get("calibration_audit_pass")
            and model.get("technical_partition_audit_pass")
            and model.get("independent_external_site_complete")
        )
        p6, confirmation_missing = _confirmation_complete(module_key, ext)
        p7 = bool(ext.get("expert_signoff_complete"))
        p8 = bool(ext.get("operating_history_complete"))
        p9 = bool(ext.get("formal_release_review_complete") and ext.get("upstream_runtime_reference_model_complete"))
        status = {1: p1, 2: p2, 3: p3, 4: p4, 5: p5, 6: p6, 7: p7, 8: p8, 9: p9}
        applicable = {phase: True for phase in range(1, 10)}
        if not model_required:
            applicable[4] = False
            applicable[5] = False
        required_count = sum(applicable.values())
        completed_count = sum(status[phase] for phase in range(1, 10) if applicable[phase])
        first_incomplete = next((phase for phase in range(1, 10) if applicable[phase] and not status[phase]), None)

        blockers: dict[int, list[str]] = {
            1: [] if p1 else ["physical Windows/GPU/instrument/site qualification incomplete"],
            2: [] if p2 else [str(base.get("missing_engines") or "missing specialist engines")],
            3: [] if p3 else [str(base.get("missing_references") or "missing production references")],
            4: [] if p4 else [
                field for field, passed in (
                    ("full task-specific domain model", bool(model.get("full_task_specific_domain_model"))),
                    ("real public or official cohort", bool(model.get("real_public_or_official_cohort_present"))),
                ) if not passed
            ],
            5: [] if p5 else [
                field for field, passed in (
                    ("checksum-locked holdout", bool(model.get("checksum_locked_holdout_complete"))),
                    ("leakage audit", bool(model.get("leakage_audit_pass"))),
                    ("calibration audit", bool(model.get("calibration_audit_pass"))),
                    ("technical partition audit", bool(model.get("technical_partition_audit_pass"))),
                    ("independent external site", bool(model.get("independent_external_site_complete"))),
                ) if not passed
            ],
            6: confirmation_missing,
            7: [] if p7 else ["cryptographically verified independent expert sign-off incomplete"],
            8: [] if p8 else ["qualified operating history incomplete"],
            9: [] if p9 else ["formal release review or upstream qualification incomplete"],
        }
        phase_blockers = " | ".join(
            f"P{phase}:{'; '.join(items)}" for phase, items in blockers.items() if applicable[phase] and items
        )
        next_command = commands.get(first_incomplete, "VERIFY_STEP174_WINDOWS.bat") if first_incomplete else "VERIFY_STEP174_WINDOWS.bat"
        rows.append({
            "schema": "biointel.step174.phase-execution.v1",
            "module_key": module_key,
            "module_title": FINAL_PROFILES[module_key].module_title,
            "evidence_class": FINAL_PROFILES[module_key].evidence_class,
            "software_phase_automation_rating": 10.0,
            "phase_1_complete": p1,
            "phase_2_complete": p2,
            "phase_3_complete": p3,
            "phase_4_applicable": applicable[4],
            "phase_4_complete": p4,
            "phase_5_applicable": applicable[5],
            "phase_5_complete": p5,
            "phase_6_complete": p6,
            "phase_7_complete": p7,
            "phase_8_complete": p8,
            "phase_9_complete": p9,
            "required_phases": required_count,
            "completed_phases": completed_count,
            "phase_completion_fraction": round(completed_count / required_count if required_count else 1.0, 4),
            "next_phase": first_incomplete or 0,
            "next_command": next_command,
            "phase_blockers": phase_blockers,
            "actual_practical_readiness_rating": float(base["actual_practical_readiness_rating"]),
            "controlled_release_eligible": bool(base["controlled_release_eligible"]),
            "decision": base["decision"],
            "all_phase_software_automation_available": True,
            "all_external_phases_complete": completed_count == required_count,
            "external_evidence_fabricated": False,
        })
    return pd.DataFrame(rows).sort_values(
        ["completed_phases", "actual_practical_readiness_rating", "module_title"], ascending=[True, True, True]
    ).reset_index(drop=True)


class Step174ExecutionRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (self.root / "UserData")).resolve()
        self.state = user_data / "step174"
        self.state.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state / "phase1_to_9_execution.sqlite3"
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
                CREATE TABLE IF NOT EXISTS execution_runs(
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at_utc TEXT NOT NULL,
                    version TEXT NOT NULL,
                    module_count INTEGER NOT NULL,
                    phase_automation_ready_count INTEGER NOT NULL,
                    controlled_release_count INTEGER NOT NULL,
                    matrix_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS module_phase_snapshots(
                    run_id INTEGER NOT NULL,
                    module_key TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    completed_phases INTEGER NOT NULL,
                    controlled_release_eligible INTEGER NOT NULL,
                    PRIMARY KEY(run_id,module_key),
                    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS audit_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at_utc TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                """
            )
            con.commit()

    def refresh(self) -> pd.DataFrame:
        matrix = build_phase_execution_matrix(self.root, refresh=False)
        records = matrix.to_dict(orient="records")
        matrix_hash = sha256(_canonical(records).encode()).hexdigest()
        status = "controlled-release-complete" if bool(matrix["controlled_release_eligible"].all()) else "external-execution-pending"
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO execution_runs(created_at_utc,version,module_count,phase_automation_ready_count,controlled_release_count,matrix_sha256,status) VALUES(?,?,?,?,?,?,?)",
                (_now(), "14.6.0", len(matrix), int(matrix["all_phase_software_automation_available"].sum()), int(matrix["controlled_release_eligible"].sum()), matrix_hash, status),
            )
            run_id = int(cur.lastrowid)
            for row in records:
                payload = _canonical(row)
                con.execute(
                    "INSERT INTO module_phase_snapshots(run_id,module_key,snapshot_json,snapshot_sha256,completed_phases,controlled_release_eligible) VALUES(?,?,?,?,?,?)",
                    (run_id, row["module_key"], payload, sha256(payload.encode()).hexdigest(), row["completed_phases"], int(row["controlled_release_eligible"])),
                )
            previous = con.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous_hash = str(previous[0]) if previous else "0" * 64
            audit_payload = {"run_id": run_id, "matrix_sha256": matrix_hash, "status": status, "module_count": len(matrix)}
            event_hash = sha256(f"{previous_hash}|{_canonical(audit_payload)}".encode()).hexdigest()
            con.execute(
                "INSERT INTO audit_events(created_at_utc,action,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                (_now(), "refresh-phase1-to-9-execution", _canonical(audit_payload), previous_hash, event_hash),
            )
            con.commit()
        return matrix

    def latest(self, *, refresh: bool = False) -> pd.DataFrame:
        if refresh:
            return self.refresh()
        with self._connect() as con:
            run = con.execute("SELECT run_id FROM execution_runs ORDER BY run_id DESC LIMIT 1").fetchone()
            if not run:
                return self.refresh()
            rows = con.execute(
                "SELECT snapshot_json FROM module_phase_snapshots WHERE run_id=? ORDER BY completed_phases,module_key", (run[0],)
            ).fetchall()
        return pd.DataFrame([json.loads(row[0]) for row in rows])

    def status(self) -> dict[str, Any]:
        with self._connect() as con:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            runs = con.execute("SELECT COUNT(*) FROM execution_runs").fetchone()[0]
            latest = con.execute("SELECT * FROM execution_runs ORDER BY run_id DESC LIMIT 1").fetchone()
            events = con.execute("SELECT previous_hash,event_hash,payload_json FROM audit_events ORDER BY sequence").fetchall()
        previous = "0" * 64
        chain_ok = True
        for row in events:
            expected = sha256(f"{previous}|{row['payload_json']}".encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                chain_ok = False
                break
            previous = row["event_hash"]
        return {
            "schema": "biointel.step174.registry-status.v1",
            "database_integrity": integrity,
            "foreign_key_violations": len(fk),
            "audit_chain_valid": chain_ok,
            "execution_runs": int(runs or 0),
            "latest_run": dict(latest) if latest else {},
        }


__all__ = ["Step174ExecutionRegistry", "automatic_environment_probe", "build_phase_execution_matrix"]
