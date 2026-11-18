from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from biointel.education.database import EducationDatabase
from biointel.media_tools import ffmpeg_executable


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LectureIntelligenceEngine:
    """Compatibility adapter for honest lecture-processing status and transcripts.

    The production Academy path uses the Phase 15/16 governed media services. This
    adapter deliberately does not synthesize transcripts, chapters, speakers, or
    citations when a qualified transcription provider is unavailable.
    """

    def __init__(self, db: EducationDatabase):
        self.db = db
        with self.db.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS education_lecture_processing_compat(
                    id TEXT PRIMARY KEY,
                    lecture_id TEXT NOT NULL,
                    media_path TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL,
                    error_text TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lecture_processing_compat_lecture
                    ON education_lecture_processing_compat(lecture_id, updated_at);
                """
            )

    @staticmethod
    def _provider_ready(provider: str) -> tuple[bool, str]:
        normalized = str(provider).strip().lower()
        if normalized not in {"local_ffmpeg_whisper", "configured_transcriber"}:
            return False, "Unsupported transcription provider."
        if not ffmpeg_executable():
            return False, "FFmpeg is not installed or bundled."
        if not os.environ.get("BIOINTEL_TRANSCRIPTION_COMMAND", "").strip():
            return False, "BIOINTEL_TRANSCRIPTION_COMMAND is not configured."
        return True, ""

    def submit_processing_job(
        self,
        media_path: str,
        lecture_id: str,
        provider: str = "local_ffmpeg_whisper",
    ) -> str:
        source = Path(media_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError("Lecture media file is unavailable.")
        ready, reason = self._provider_ready(provider)
        job_id = f"lecture-job-{uuid.uuid4().hex}"
        stamp = now_iso()
        state = "queued" if ready else "configuration_required"
        stage = "awaiting_worker" if ready else "provider_configuration"
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO education_lecture_processing_compat VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    str(lecture_id),
                    str(source),
                    str(provider),
                    state,
                    0.0,
                    stage,
                    reason,
                    "{}",
                    stamp,
                    stamp,
                ),
            )
        return job_id

    def process_lecture(
        self, lecture_id: str, media_title: str, video_path: str
    ) -> Dict[str, Any]:
        """Create a real job or report the exact configuration boundary.

        Processing is performed by the governed Phase 16 worker. No transcript is
        fabricated in this compatibility layer.
        """
        job_id = self.submit_processing_job(video_path, lecture_id)
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM education_lecture_processing_compat WHERE id=?", (job_id,)
            ).fetchone()
        return {
            "job_id": job_id,
            "lecture_id": str(lecture_id),
            "media_title": str(media_title),
            "state": row["state"],
            "stage": row["stage"],
            "error_text": row["error_text"],
            "transcript_created": False,
            "chapters_created": False,
        }

    def process_lecture_mock_or_real(
        self, lecture_id: str, media_title: str, video_path: str
    ) -> Dict[str, Any]:
        """Backward-compatible name; delegates to the non-synthetic job path."""
        return self.process_lecture(lecture_id, media_title, video_path)

    def get_transcript_for_lecture(self, lecture_id: str) -> Optional[Dict[str, Any]]:
        with self.db.connection() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='education_lecture_transcripts'"
            ).fetchone()
            if not table:
                return None
            rows = conn.execute(
                "SELECT * FROM education_lecture_transcripts WHERE lecture_id=? ORDER BY language",
                (lecture_id,),
            ).fetchall()
        if not rows:
            return None
        return {
            "lecture_id": str(lecture_id),
            "status": "published",
            "transcripts": [dict(row) for row in rows],
            "languages": [str(row["language"]) for row in rows],
            "segments": [],
        }