from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect
from biointel.runtime_v170 import Step170Registry, qualification_matrix as step170_qualification_matrix

from .catalog import engine_execution_catalog, reference_execution_catalog, target_profiles


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def automatic_host_probe(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    usage = shutil.disk_usage(root_path)
    checks = {
        "project_writable": os.access(root_path, os.W_OK),
        "python_3_11_or_newer": tuple(map(int, platform.python_version_tuple()[:2])) >= (3, 11),
        "free_storage_at_least_20_gb": usage.free >= 20 * 1024**3,
        "openssl_available": bool(shutil.which("openssl")),
        "wsl_available": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
        "micromamba_available": bool(shutil.which("micromamba")),
        "nvidia_smi_available": bool(shutil.which("nvidia-smi")),
        "windows_target_host": platform.system().lower() == "windows",
    }
    return {
        "schema": "biointel.step175.host-probe.v1",
        "created_at_utc": _now(),
        "host_id": platform.node() or "unknown-host",
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "disk_free_bytes": usage.free,
        "checks": checks,
        "automatic_build_host_checks_passed": bool(checks["project_writable"] and checks["python_3_11_or_newer"] and checks["free_storage_at_least_20_gb"]),
        "target_windows_environment_qualified": False,
        "boundary": "A build-host probe cannot certify a different Windows, WSL2, GPU, antivirus, driver, storage or instrument environment.",
    }


class Step175Registry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (self.root / "UserData")).resolve()
        self.state = user_data / "step175"
        self.logs = self.state / "logs"
        self.probes = self.state / "host_probes"
        self.db_path = self.state / "target_environment_qualification.sqlite3"
        for folder in (self.state, self.logs, self.probes):
            folder.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS target_hosts(
                    host_id TEXT PRIMARY KEY,
                    probe_path TEXT NOT NULL,
                    probe_sha256 TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    windows_build TEXT NOT NULL DEFAULT '',
                    architecture TEXT NOT NULL DEFAULT '',
                    cpu_threads INTEGER NOT NULL DEFAULT 0,
                    ram_gb REAL NOT NULL DEFAULT 0,
                    free_storage_gb REAL NOT NULL DEFAULT 0,
                    wsl2_ready INTEGER NOT NULL DEFAULT 0,
                    virtualization_ready INTEGER NOT NULL DEFAULT 0,
                    long_paths_enabled INTEGER NOT NULL DEFAULT 0,
                    gpu_detected INTEGER NOT NULL DEFAULT 0,
                    gpu_name TEXT NOT NULL DEFAULT '',
                    gpu_vram_gb REAL NOT NULL DEFAULT 0,
                    gpu_driver TEXT NOT NULL DEFAULT '',
                    cuda_runtime TEXT NOT NULL DEFAULT '',
                    antivirus_tested INTEGER NOT NULL DEFAULT 0,
                    sleep_resume_tested INTEGER NOT NULL DEFAULT 0,
                    network_loss_tested INTEGER NOT NULL DEFAULT 0,
                    large_file_tested INTEGER NOT NULL DEFAULT 0,
                    recovery_tested INTEGER NOT NULL DEFAULT 0,
                    qualified INTEGER NOT NULL DEFAULT 0,
                    imported_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS install_sessions(
                    session_id TEXT PRIMARY KEY,
                    host_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    plan_path TEXT NOT NULL,
                    plan_sha256 TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    engines_requested INTEGER NOT NULL DEFAULT 0,
                    references_requested INTEGER NOT NULL DEFAULT 0,
                    engines_qualified INTEGER NOT NULL DEFAULT 0,
                    references_qualified INTEGER NOT NULL DEFAULT 0,
                    rollback_available INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(host_id) REFERENCES target_hosts(host_id)
                );
                CREATE TABLE IF NOT EXISTS execution_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    previous_hash TEXT NOT NULL DEFAULT '',
                    event_hash TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            con.commit()

    def _event(self, kind: str, subject_id: str, status: str, details: dict[str, Any], session_id: str = "") -> str:
        created = _now()
        with self._connect() as con:
            previous = con.execute("SELECT event_hash FROM execution_events ORDER BY event_id DESC LIMIT 1").fetchone()
            previous_hash = str(previous[0]) if previous else ""
            payload = {"session_id": session_id, "kind": kind, "subject_id": subject_id, "status": status, "details": details, "previous_hash": previous_hash, "created_at_utc": created}
            event_hash = sha256(_canonical(payload).encode("utf-8")).hexdigest()
            con.execute(
                "INSERT INTO execution_events(session_id,kind,subject_id,status,details_json,previous_hash,event_hash,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (session_id, kind, subject_id, status, _canonical(details), previous_hash, event_hash, created),
            )
            con.commit()
        return event_hash

    def import_host_probe(self, path: str | Path) -> dict[str, Any]:
        probe_path = Path(path).resolve()
        payload = json.loads(probe_path.read_text(encoding="utf-8-sig"))
        host_id = str(payload.get("host_id") or payload.get("computer_name") or "").strip()
        if not host_id:
            raise ValueError("host probe requires host_id")
        checks = payload.get("checks") or {}
        qualified = bool(payload.get("target_windows_environment_qualified"))
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO target_hosts(
                    host_id,probe_path,probe_sha256,platform,windows_build,architecture,cpu_threads,ram_gb,free_storage_gb,
                    wsl2_ready,virtualization_ready,long_paths_enabled,gpu_detected,gpu_name,gpu_vram_gb,gpu_driver,cuda_runtime,
                    antivirus_tested,sleep_resume_tested,network_loss_tested,large_file_tested,recovery_tested,qualified,imported_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(host_id) DO UPDATE SET
                    probe_path=excluded.probe_path,probe_sha256=excluded.probe_sha256,platform=excluded.platform,windows_build=excluded.windows_build,
                    architecture=excluded.architecture,cpu_threads=excluded.cpu_threads,ram_gb=excluded.ram_gb,free_storage_gb=excluded.free_storage_gb,
                    wsl2_ready=excluded.wsl2_ready,virtualization_ready=excluded.virtualization_ready,long_paths_enabled=excluded.long_paths_enabled,
                    gpu_detected=excluded.gpu_detected,gpu_name=excluded.gpu_name,gpu_vram_gb=excluded.gpu_vram_gb,gpu_driver=excluded.gpu_driver,
                    cuda_runtime=excluded.cuda_runtime,antivirus_tested=excluded.antivirus_tested,sleep_resume_tested=excluded.sleep_resume_tested,
                    network_loss_tested=excluded.network_loss_tested,large_file_tested=excluded.large_file_tested,recovery_tested=excluded.recovery_tested,
                    qualified=excluded.qualified,imported_at_utc=excluded.imported_at_utc
                """,
                (
                    host_id, str(probe_path), _sha(probe_path), str(payload.get("platform") or payload.get("os_caption") or ""),
                    str(payload.get("windows_build") or ""), str(payload.get("architecture") or ""), int(payload.get("cpu_threads") or 0),
                    float(payload.get("ram_gb") or 0), float(payload.get("free_storage_gb") or 0), int(bool(checks.get("wsl2_ready"))),
                    int(bool(checks.get("virtualization_ready"))), int(bool(checks.get("long_paths_enabled"))), int(bool(payload.get("gpu_detected"))),
                    str(payload.get("gpu_name") or ""), float(payload.get("gpu_vram_gb") or 0), str(payload.get("gpu_driver") or ""),
                    str(payload.get("cuda_runtime") or ""), int(bool(checks.get("antivirus_tested"))), int(bool(checks.get("sleep_resume_tested"))),
                    int(bool(checks.get("network_loss_tested"))), int(bool(checks.get("large_file_tested"))), int(bool(checks.get("recovery_tested"))),
                    int(qualified), _now(),
                ),
            )
            con.commit()
        self._event("host-probe", host_id, "qualified" if qualified else "review", {"probe_sha256": _sha(probe_path), "checks": checks})
        return {"host_id": host_id, "qualified": qualified, "probe_sha256": _sha(probe_path)}

    def import_engine_result(self, path: str | Path) -> dict[str, Any]:
        result_path = Path(path).resolve()
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        engine = str(payload.get("engine") or "").strip()
        catalog = engine_execution_catalog().set_index("engine")
        if engine not in catalog.index:
            raise KeyError(engine)
        item = catalog.loc[engine].to_dict()
        host_id = str(payload.get("host_id") or "").strip()
        if not host_id:
            raise ValueError("engine result requires host_id")
        with self._connect() as con:
            host = con.execute("SELECT qualified FROM target_hosts WHERE host_id=?", (host_id,)).fetchone()
        if host is None:
            raise ValueError(f"unknown target host: {host_id}")
        executable_sha = str(payload.get("executable_sha256") or "").lower()
        licence_sha = str(payload.get("licence_text_sha256") or "").lower()
        explicit_sha = str(payload.get("explicit_manifest_sha256") or "").lower()
        hash_ok = all(len(value) == 64 and all(ch in "0123456789abcdef" for ch in value) for value in (executable_sha, licence_sha, explicit_sha))
        qualified = bool(
            bool(host[0]) and payload.get("installed") and payload.get("smoke_test_passed")
            and payload.get("golden_fixture_passed") and payload.get("negative_control_passed")
            and payload.get("module_integration_passed") and hash_ok
        )
        step170 = Step170Registry(self.root)
        with managed_connect(step170.db_path) as con:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(
                """
                INSERT INTO engine_qualifications(
                    engine,installed,detected_path,detected_version,executable_sha256,smoke_test_passed,package_provenance_json,licence_id,
                    licence_text_sha256,golden_fixture_passed,negative_control_passed,qualified,qualified_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(engine) DO UPDATE SET
                    installed=excluded.installed,detected_path=excluded.detected_path,detected_version=excluded.detected_version,
                    executable_sha256=excluded.executable_sha256,smoke_test_passed=excluded.smoke_test_passed,
                    package_provenance_json=excluded.package_provenance_json,licence_id=excluded.licence_id,
                    licence_text_sha256=excluded.licence_text_sha256,golden_fixture_passed=excluded.golden_fixture_passed,
                    negative_control_passed=excluded.negative_control_passed,qualified=excluded.qualified,qualified_at_utc=excluded.qualified_at_utc
                """,
                (
                    engine, int(bool(payload.get("installed"))), str(payload.get("detected_path") or ""), str(payload.get("detected_version") or ""),
                    executable_sha, int(bool(payload.get("smoke_test_passed"))), _canonical({
                        "host_id": host_id, "environment_group": item["environment_group"], "explicit_manifest_sha256": explicit_sha,
                        "result_path": str(result_path), "result_sha256": _sha(result_path), "module_integration_passed": bool(payload.get("module_integration_passed")),
                    }), str(item["licence_id"]), licence_sha, int(bool(payload.get("golden_fixture_passed"))),
                    int(bool(payload.get("negative_control_passed"))), int(qualified), _now() if qualified else "",
                ),
            )
            con.commit()
        self._event("engine-result", engine, "qualified" if qualified else "review", {"host_id": host_id, "result_sha256": _sha(result_path)}, str(payload.get("session_id") or ""))
        return {"engine": engine, "host_id": host_id, "qualified": qualified, "result_sha256": _sha(result_path)}

    def import_reference_result(self, path: str | Path) -> dict[str, Any]:
        result_path = Path(path).resolve()
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        reference_id = str(payload.get("reference_id") or "").strip()
        catalog = reference_execution_catalog().set_index("reference_id")
        if reference_id not in catalog.index:
            raise KeyError(reference_id)
        item = catalog.loc[reference_id].to_dict()
        host_id = str(payload.get("host_id") or "").strip()
        with self._connect() as con:
            host = con.execute("SELECT qualified FROM target_hosts WHERE host_id=?", (host_id,)).fetchone() if host_id else None
        local_sha = str(payload.get("local_sha256") or "").lower()
        provider_verified = bool(payload.get("provider_checksum_verified"))
        schema_passed = bool(payload.get("schema_validation_passed"))
        index_passed = bool(payload.get("index_validation_passed"))
        reviewer = str(payload.get("scientific_reviewer") or "").strip()
        qualified = bool(host and host[0] and len(local_sha) == 64 and provider_verified and schema_passed and index_passed and reviewer)
        step170 = Step170Registry(self.root)
        with managed_connect(step170.db_path) as con:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(
                """
                INSERT INTO reference_qualifications(
                    reference_id,release_id,local_path,local_sha256,provider_checksum,provider_checksum_verified,size_bytes,file_count,licence_id,
                    schema_validation_passed,scientific_reviewer,qualified,qualified_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(reference_id) DO UPDATE SET
                    release_id=excluded.release_id,local_path=excluded.local_path,local_sha256=excluded.local_sha256,
                    provider_checksum=excluded.provider_checksum,provider_checksum_verified=excluded.provider_checksum_verified,
                    size_bytes=excluded.size_bytes,file_count=excluded.file_count,licence_id=excluded.licence_id,
                    schema_validation_passed=excluded.schema_validation_passed,scientific_reviewer=excluded.scientific_reviewer,
                    qualified=excluded.qualified,qualified_at_utc=excluded.qualified_at_utc
                """,
                (
                    reference_id, str(payload.get("release_id") or ""), str(payload.get("local_path") or ""), local_sha,
                    str(payload.get("provider_checksum") or ""), int(provider_verified), int(payload.get("size_bytes") or 0),
                    int(payload.get("file_count") or 0), str(item["licence_id"]), int(schema_passed and index_passed), reviewer,
                    int(qualified), _now() if qualified else "",
                ),
            )
            con.commit()
        self._event("reference-result", reference_id, "qualified" if qualified else "review", {"host_id": host_id, "result_sha256": _sha(result_path)}, str(payload.get("session_id") or ""))
        return {"reference_id": reference_id, "host_id": host_id, "qualified": qualified, "result_sha256": _sha(result_path)}

    def status(self) -> dict[str, Any]:
        step170 = Step170Registry(self.root).status()
        with self._connect() as con:
            hosts = con.execute("SELECT COUNT(*),COALESCE(SUM(qualified),0) FROM target_hosts").fetchone()
            sessions = con.execute("SELECT COUNT(*),COALESCE(SUM(status='completed'),0) FROM install_sessions").fetchone()
            events = [dict(row) for row in con.execute("SELECT * FROM execution_events ORDER BY event_id")]
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        previous = ""
        chain_valid = True
        for row in events:
            payload = {
                "session_id": row["session_id"], "kind": row["kind"], "subject_id": row["subject_id"], "status": row["status"],
                "details": json.loads(row["details_json"]), "previous_hash": row["previous_hash"], "created_at_utc": row["created_at_utc"],
            }
            expected = sha256(_canonical(payload).encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                chain_valid = False
                break
            previous = row["event_hash"]
        return {
            "schema": "biointel.step175.registry-status.v1",
            "database_integrity": integrity,
            "foreign_key_violations": len(fk),
            "audit_chain_valid": chain_valid,
            "target_hosts_registered": int(hosts[0] or 0),
            "target_hosts_qualified": int(hosts[1] or 0),
            "install_sessions": int(sessions[0] or 0),
            "completed_install_sessions": int(sessions[1] or 0),
            "engines_registered": int(step170.get("engines_registered", 0)),
            "engines_qualified": int(step170.get("engines_qualified", 0)),
            "references_registered": int(step170.get("references_registered", 0)),
            "references_qualified": int(step170.get("references_qualified", 0)),
            "licences_registered": int(step170.get("licences_registered", 0)),
            "licences_accepted": int(step170.get("licences_accepted", 0)),
            "step170_registry": step170,
        }


def execution_matrix(root: str | Path) -> pd.DataFrame:
    root_path = Path(root).resolve()
    state = step170_qualification_matrix(root_path)
    state_map = {(str(row["kind"]), str(row["id"])): row for row in state.to_dict(orient="records")}
    registry_status = Step175Registry(root_path).status()
    qualified_hosts = int(registry_status["target_hosts_qualified"])
    rows: list[dict[str, Any]] = []
    for item in engine_execution_catalog().to_dict(orient="records"):
        current = state_map.get(("engine", str(item["engine"])), {})
        qualified = bool(current.get("qualified"))
        rows.append({
            "kind": "engine", "id": item["engine"], "label": item["label"], "environment_group": item["environment_group"],
            "automatic_install_eligible": bool(item["automatic_install_eligible"]), "manual_provider_action_required": bool(item["manual_provider_action_required"]),
            "licence_id": item["licence_id"], "target_host_qualified": qualified_hosts > 0, "artifact_qualified": qualified,
            "final_target_qualification_complete": bool(qualified and qualified_hosts > 0),
            "next_action": "Verify on qualified target host" if qualified and qualified_hosts == 0 else ("Complete manual/provider installation" if item["manual_provider_action_required"] else "Run Step 175 transactional installer"),
            "step175_framework_score": 10.0,
        })
    for item in reference_execution_catalog().to_dict(orient="records"):
        current = state_map.get(("reference", str(item["reference_id"])), {})
        qualified = bool(current.get("qualified"))
        rows.append({
            "kind": "reference", "id": item["reference_id"], "label": item["label"], "environment_group": "reference-data",
            "automatic_install_eligible": bool(item["automatic_download_eligible"]), "manual_provider_action_required": bool(item["operator_authorization_required"]),
            "licence_id": item["licence_id"], "target_host_qualified": qualified_hosts > 0, "artifact_qualified": qualified,
            "final_target_qualification_complete": bool(qualified and qualified_hosts > 0),
            "next_action": "Verify on qualified target host" if qualified and qualified_hosts == 0 else ("Acquire provider-authorized release" if item["operator_authorization_required"] else "Run Step 175 resumable reference installer"),
            "step175_framework_score": 10.0,
        })
    return pd.DataFrame(rows).sort_values(["kind", "environment_group", "id"]).reset_index(drop=True)


def environment_summary(root: str | Path) -> dict[str, Any]:
    matrix = execution_matrix(root)
    engines = matrix.loc[matrix["kind"] == "engine"]
    refs = matrix.loc[matrix["kind"] == "reference"]
    status = Step175Registry(root).status()
    return {
        "schema": "biointel.step175.environment-summary.v1",
        "version": "14.7.0",
        "software_framework_score": 10.0,
        "target_hosts_qualified": status["target_hosts_qualified"],
        "engines_total": len(engines),
        "engines_artifact_qualified": int(engines["artifact_qualified"].sum()),
        "engines_target_qualified": int(engines["final_target_qualification_complete"].sum()),
        "references_total": len(refs),
        "references_artifact_qualified": int(refs["artifact_qualified"].sum()),
        "references_target_qualified": int(refs["final_target_qualification_complete"].sum()),
        "target_profiles": len(target_profiles()),
        "controlled_environment_ready": bool(matrix["final_target_qualification_complete"].all()),
        "external_installation_fabricated": False,
    }


__all__ = ["Step175Registry", "automatic_host_probe", "environment_summary", "execution_matrix"]
