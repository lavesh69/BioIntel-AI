from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import DEFAULT_TENANT, utc_now
from .service import SciencePulseService


class SciencePulseScheduler:
    """Persistent scheduler embedded in BioIntel's single hidden background worker."""

    def __init__(
        self,
        root: str | Path,
        *,
        service: SciencePulseService | None = None,
        worker_id: str = "",
    ) -> None:
        self.root = Path(root).resolve()
        self.service = service or SciencePulseService(self.root)
        self.store = self.service.store
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.offline = (
            os.environ.get("BIOINTEL_RUNTIME_SMOKE_TEST") == "1"
            or os.environ.get("BIOINTEL_SCIENCE_PULSE_OFFLINE") == "1"
        )
        self._last_tick = 0.0
        self.recover_stale_runs()

    def _lease(self, ttl_seconds: int = 45) -> bool:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM sp_worker_leases WHERE lease_key='science-pulse-scheduler'"
            ).fetchone()
            if (
                row
                and row["owner_id"] != self.worker_id
                and str(row["expires_at"]) > now.isoformat(timespec="seconds")
            ):
                return False
            connection.execute(
                """
                INSERT INTO sp_worker_leases VALUES('science-pulse-scheduler',?,?,?)
                ON CONFLICT(lease_key) DO UPDATE SET owner_id=excluded.owner_id,
                    heartbeat_at=excluded.heartbeat_at,expires_at=excluded.expires_at
                """,
                (
                    self.worker_id,
                    now.isoformat(timespec="seconds"),
                    expires.isoformat(timespec="seconds"),
                ),
            )
        return True

    def recover_stale_runs(self, stale_minutes: int = 30) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=max(1, stale_minutes))
        ).isoformat(timespec="seconds")
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id,tenant_id,source_key FROM sp_sync_runs
                WHERE status='running' AND started_at<?
                """,
                (cutoff,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE sp_sync_runs SET status='recovered_after_restart',finished_at=?,
                        error_text='Worker restart recovered a stale running synchronization.'
                    WHERE run_id=?
                    """,
                    (utc_now(), row["run_id"]),
                )
                connection.execute(
                    """
                    UPDATE sp_sources SET next_sync_at=?,last_error=?
                    WHERE tenant_id=? AND source_key=?
                    """,
                    (
                        utc_now(),
                        "Stale run recovered; source scheduled for safe retry.",
                        row["tenant_id"],
                        row["source_key"],
                    ),
                )
        return len(rows)

    def tick(self, *, force: bool = False, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        if not force and now_monotonic - self._last_tick < 15:
            return {"status": "not_due", "processed": 0}
        self._last_tick = now_monotonic
        if not self._lease():
            return {"status": "duplicate_worker_suppressed", "processed": 0}
        if self.offline:
            return {
                "status": "offline_cache_only",
                "processed": 0,
                "reason": (
                    "runtime smoke test"
                    if os.environ.get("BIOINTEL_RUNTIME_SMOKE_TEST") == "1"
                    else "offline mode"
                ),
            }
        results: list[dict[str, Any]] = []
        for source in self.store.due_sources(tenant_id=tenant_id):
            source_key = str(source["source_key"])
            slot = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            results.append(
                self.service.sync_source(
                    source_key,
                    trigger="scheduled",
                    tenant_id=tenant_id,
                    idempotency_key=f"scheduled:{tenant_id}:{source_key}:{slot}",
                )
            )
        digest_results = self._scheduled_digests(tenant_id)
        return {
            "status": "completed",
            "processed": len(results),
            "source_results": results,
            "digests": digest_results,
        }

    def _scheduled_digests(self, tenant_id: str) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        frequencies: list[str] = []
        if now.minute < 15:
            frequencies.append("hourly")
        if now.hour == 6:
            frequencies.append("daily")
        if now.weekday() == 0 and now.hour == 6:
            frequencies.append("weekly")
        if not frequencies:
            return []
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT user_id FROM sp_user_preferences WHERE tenant_id=?
                UNION SELECT DISTINCT user_id FROM sp_alert_rules WHERE tenant_id=? AND enabled=1
                """,
                (tenant_id, tenant_id),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            for frequency in frequencies:
                result = self.service.generate_digest(
                    str(row["user_id"]),
                    frequency=frequency,
                    tenant_id=tenant_id,
                    now=now,
                )
                results.append(
                    {
                        "user_id": row["user_id"],
                        "frequency": frequency,
                        "status": result["status"],
                        "item_count": result.get("item_count", 0),
                    }
                )
        return results

    def force_sync(
        self, source_key: str, *, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        return self.service.sync_source(
            source_key,
            trigger="administrator_force",
            tenant_id=tenant_id,
            idempotency_key=f"force:{tenant_id}:{source_key}:{utc_now()}",
        )

    def repair(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        recovered = self.recover_stale_runs(stale_minutes=1)
        with self.store.connect() as connection:
            changed = connection.execute(
                """
                UPDATE sp_sources SET circuit_open_until='',consecutive_failures=0,
                    next_sync_at=?,status='EXTERNAL_VALIDATION_REQUIRED',last_error=''
                WHERE tenant_id=? AND status='CIRCUIT_OPEN'
                """,
                (utc_now(), tenant_id),
            ).rowcount
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "stale_runs_recovered": recovered,
            "circuits_reset": changed,
            "database_integrity": integrity,
        }

    def diagnostics(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        health = self.service.health(tenant_id)
        health["worker_id"] = self.worker_id
        health["offline"] = self.offline
        health["worker_pid"] = os.getpid()
        return health

    def shutdown(self) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                DELETE FROM sp_worker_leases
                WHERE lease_key='science-pulse-scheduler' AND owner_id=?
                """,
                (self.worker_id,),
            )


__all__ = ["SciencePulseScheduler"]
