from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any

from biointel.shiro.ingestion.service import IngestionService
from biointel.shiro.storage.repositories import ShiroRepository


class ShiroJobManager:
    """Small local background runner backed by durable SQLite job state."""

    def __init__(self, repository: ShiroRepository, ingestion: IngestionService, max_workers: int = 2) -> None:
        self.repository = repository
        self.ingestion = ingestion
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(max_workers, 4)), thread_name_prefix="shiro")
        self._futures: dict[str, Future[Any]] = {}
        self._lock = RLock()

    def _track(self, job_id: str, future: Future[Any]) -> None:
        with self._lock:
            self._futures[job_id] = future
        future.add_done_callback(lambda _future: self._forget(job_id))

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def submit_ingestion(
        self,
        project_id: str,
        content: bytes,
        filename: str,
        **kwargs: object,
    ) -> dict[str, Any]:
        job_id = self.repository.create_job(project_id, "ingestion")
        future = self._executor.submit(
            self.ingestion.ingest_bytes,
            project_id,
            content,
            filename,
            job_id=job_id,
            cancelled=lambda: self.repository.job_cancel_requested(project_id, job_id),
            **kwargs,
        )
        self._track(job_id, future)
        return self.repository.get_job(job_id, project_id) or {"job_id": job_id, "state": "queued"}

    def submit_rebuild(self, project_id: str) -> dict[str, Any]:
        job_id = self.repository.create_job(project_id, "index_rebuild")
        future = self._executor.submit(
            self.ingestion.rebuild_index,
            project_id,
            job_id=job_id,
            cancelled=lambda: self.repository.job_cancel_requested(project_id, job_id),
        )
        self._track(job_id, future)
        return self.repository.get_job(job_id, project_id) or {"job_id": job_id, "state": "queued"}

    def cancel(self, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.repository.request_job_cancel(project_id, job_id)
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None and future.cancel():
            self.repository.update_job(job_id, "cancelled", 1.0, "Cancelled before execution.")
        return self.repository.get_job(job_id, project_id) or result