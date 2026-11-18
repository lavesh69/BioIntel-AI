from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable
from uuid import uuid4

from biointel.shiro.config import ShiroSettings
from biointel.shiro.core.safety import neutralize_untrusted_text
from biointel.shiro.exceptions import ProjectAccessError, UserCancellationError
from biointel.shiro.ingestion.chunking import CHUNKING_VERSION, chunk_sections
from biointel.shiro.ingestion.extractors import ExtractedSection, extract_document, safe_filename
from biointel.shiro.models import ChunkRecord, IngestionResult, SourceRecord
from biointel.shiro.retrieval.vector_store import EmbeddingProvider
from biointel.shiro.storage.repositories import ShiroRepository, utc_now

CancelCheck = Callable[[], bool]


class IngestionService:
    def __init__(self, settings: ShiroSettings, repository: ShiroRepository, embeddings: EmbeddingProvider) -> None:
        self.settings = settings
        self.repository = repository
        self.embeddings = embeddings

    @staticmethod
    def _raise_if_cancelled(cancelled: CancelCheck | None) -> None:
        if cancelled and cancelled():
            raise UserCancellationError("The Shiro job was cancelled by the user.")

    @staticmethod
    def _job_result(result: IngestionResult) -> dict[str, object]:
        value = result.to_dict()
        value["source"].pop("file_path", None)
        return value

    def ingest_bytes(
        self,
        project_id: str,
        content: bytes,
        filename: str,
        *,
        project_name: str | None = None,
        source_type: str | None = None,
        internal: bool = True,
        external: bool = False,
        synthetic: bool = False,
        confidential: bool = True,
        metadata: dict[str, object] | None = None,
        job_id: str | None = None,
        cancelled: CancelCheck | None = None,
    ) -> IngestionResult:
        safe = safe_filename(filename)
        project = project_id.strip()
        if not project:
            raise ValueError("An active project is required before evidence ingestion.")
        self._raise_if_cancelled(cancelled)
        digest = hashlib.sha256(content).hexdigest()
        existing = self.repository.find_source_by_hash(project, digest)
        if existing is not None:
            count = sum(1 for _chunk, _source in self.repository.list_chunks(project, source_ids=[existing.source_id]))
            result = IngestionResult(job_id or "duplicate-" + digest[:16], existing, count, "completed", True)
            if job_id:
                self.repository.update_job(job_id, "completed", 1.0, result=self._job_result(result))
            return result
        active_job = job_id or self.repository.create_job(project, "ingestion")
        self.repository.update_job(active_job, "running", 0.05)
        stored_path: Path | None = None
        persisted = False
        try:
            extraction = extract_document(
                content,
                safe,
                self.settings.max_file_size_mb * 1024 * 1024,
                ocr_enabled=self.settings.ocr_enabled,
                ocr_language=self.settings.ocr_language,
                ocr_max_pages=self.settings.ocr_max_pages,
            )
            self._raise_if_cancelled(cancelled)
            cleaned: list[ExtractedSection] = []
            injection_count = 0
            detections: list[str] = []
            total_sections = max(1, len(extraction.sections))
            for index, section in enumerate(extraction.sections, start=1):
                self._raise_if_cancelled(cancelled)
                text, found = neutralize_untrusted_text(section.text)
                if found:
                    injection_count += 1
                    detections.extend(found)
                cleaned.append(ExtractedSection(text, section.location, section.section))
                self.repository.update_job(active_job, "running", 0.1 + 0.2 * index / total_sections)
            warnings = list(extraction.warnings)
            if injection_count:
                warnings.append(f"Prompt-like instructions were neutralized in {injection_count} extracted section(s).")
            drafts = chunk_sections(cleaned, self.settings.chunk_size, self.settings.chunk_overlap)
            if not drafts:
                raise ValueError("The document produced no indexable chunks.")
            self.repository.update_job(active_job, "running", 0.35)
            vectors: list[tuple[float, ...]] = []
            batch_size = 128
            for start in range(0, len(drafts), batch_size):
                self._raise_if_cancelled(cancelled)
                batch = drafts[start : start + batch_size]
                vectors.extend(self.embeddings.embed([draft.text for draft in batch]))
                progress = 0.35 + 0.35 * min(len(drafts), start + len(batch)) / len(drafts)
                self.repository.update_job(active_job, "running", progress)
            self._raise_if_cancelled(cancelled)
            source_id = "src-" + uuid4().hex
            project_folder = hashlib.sha256(project.encode("utf-8")).hexdigest()[:24]
            evidence_dir = self.settings.data_dir / "evidence" / project_folder
            evidence_dir.mkdir(parents=True, exist_ok=True)
            stored_path = evidence_dir / f"{source_id}{Path(safe).suffix.casefold()}"
            stored_path.write_bytes(content)
            source_metadata = dict(metadata or {})
            source_metadata.update({
                "project_name": project_name or project,
                "embedding_model": self.settings.embedding_model,
                "embedding_version": self.embeddings.model_version,
                "embedding_dimension": self.embeddings.dimension,
                "preprocessing_version": self.embeddings.preprocessing_version,
                "chunking_version": CHUNKING_VERSION,
                "index_created_at": utc_now(),
                "prompt_injection_detected": bool(injection_count),
                "prompt_injection_signatures": sorted(set(detections)),
            })
            source = SourceRecord(
                source_id=source_id, project_id=project, filename=safe,
                source_type=source_type or extraction.source_type, mime_type=extraction.mime_type,
                byte_size=len(content), sha256=digest, uploaded_at=utc_now(), author=extraction.author,
                internal=internal, external=external, synthetic=synthetic, confidential=confidential,
                warnings=tuple(warnings), metadata=source_metadata, file_path=str(stored_path),
            )
            chunks = tuple(
                ChunkRecord(
                    chunk_id="chk-" + hashlib.sha256(f"{source_id}:{draft.ordinal}:{draft.text}".encode("utf-8")).hexdigest()[:24],
                    source_id=source_id, project_id=project, ordinal=draft.ordinal, text=draft.text,
                    location=draft.location, section=draft.section, embedding=vectors[index],
                    metadata={"parent_source_id": source_id, "chunking_version": CHUNKING_VERSION},
                )
                for index, draft in enumerate(drafts)
            )
            self._raise_if_cancelled(cancelled)
            self.repository.add_source(source, chunks)
            persisted = True
            result = IngestionResult(active_job, source, len(chunks), "completed")
            self.repository.update_job(active_job, "completed", 1.0, result=self._job_result(result))
            return result
        except UserCancellationError as exc:
            self.repository.update_job(active_job, "cancelled", 1.0, str(exc))
            raise
        except Exception as exc:
            self.repository.update_job(active_job, "failed", 1.0, str(exc))
            raise
        finally:
            if stored_path is not None and not persisted:
                stored_path.unlink(missing_ok=True)

    def rebuild_index(
        self,
        project_id: str,
        *,
        job_id: str | None = None,
        cancelled: CancelCheck | None = None,
    ) -> dict[str, object]:
        active_job = job_id or self.repository.create_job(project_id, "index_rebuild")
        self.repository.update_job(active_job, "running", 0.05)
        try:
            pairs = self.repository.list_chunks(project_id)
            if not pairs:
                result = {"job_id": active_job, "project_id": project_id, "chunks_rebuilt": 0, "state": "completed"}
                self.repository.update_job(active_job, "completed", 1.0, result=result)
                return result
            values: list[tuple[str, tuple[float, ...]]] = []
            batch_size = 128
            for start in range(0, len(pairs), batch_size):
                self._raise_if_cancelled(cancelled)
                batch = pairs[start : start + batch_size]
                vectors = self.embeddings.embed([chunk.text for chunk, _source in batch])
                values.extend((chunk.chunk_id, vectors[index]) for index, (chunk, _source) in enumerate(batch))
                self.repository.update_job(active_job, "running", 0.1 + 0.75 * (start + len(batch)) / len(pairs))
            self._raise_if_cancelled(cancelled)
            count = self.repository.update_embeddings(project_id, values)
            result = {
                "job_id": active_job, "project_id": project_id, "chunks_rebuilt": count,
                "state": "completed", "embedding_model": self.settings.embedding_model,
                "dimension": self.embeddings.dimension,
            }
            self.repository.update_job(active_job, "completed", 1.0, result=result)
            return result
        except UserCancellationError as exc:
            self.repository.update_job(active_job, "cancelled", 1.0, str(exc))
            raise
        except Exception as exc:
            self.repository.update_job(active_job, "failed", 1.0, str(exc))
            raise

    def delete_source(self, project_id: str, source_id: str) -> SourceRecord:
        source = self.repository.delete_source(project_id, source_id)
        path = Path(source.file_path).resolve()
        evidence_root = (self.settings.data_dir / "evidence").resolve()
        if path.is_relative_to(evidence_root):
            path.unlink(missing_ok=True)
        else:
            raise ProjectAccessError("Stored evidence path was outside the managed Shiro directory.")
        return source