from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from biointel.media_tools import ffmpeg_executable

_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
_ALLOWED_MEDIA = {".aac", ".flac", ".m4a", ".m4v", ".mov", ".mp3", ".mp4", ".ogg", ".wav", ".webm"}
_LANGUAGE_CODES = {
    "auto": None,
    "english": "en",
    "en": "en",
    "hindi": "hi",
    "hi": "hi",
    "hinglish": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_model_dir(root: str | Path | None = None) -> Path:
    configured = os.environ.get("BIOINTEL_TRANSCRIPTION_MODEL", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    project = Path(root).resolve() if root else Path(__file__).resolve().parents[3]
    candidate = project / "models" / "education" / "faster-whisper-tiny"
    if candidate.is_dir():
        return candidate
    return Path(__file__).resolve().parents[3] / "models" / "education" / "faster-whisper-tiny"


@lru_cache(maxsize=8)
def _manifest_status(model_dir_text: str, manifest_mtime_ns: int) -> dict[str, Any]:
    model_dir = Path(model_dir_text)
    manifest_path = model_dir / "MODEL_MANIFEST_SHA256.json"
    if not manifest_path.is_file():
        return {"valid": False, "reason": "Model manifest is missing.", "model_sha256": ""}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return {"valid": False, "reason": f"Model manifest is unreadable: {exc}", "model_sha256": ""}
    failures: list[str] = []
    for row in payload.get("files", []):
        path = model_dir / str(row.get("path", ""))
        if (
            not path.is_file()
            or path.stat().st_size != int(row.get("size_bytes", -1))
            or _sha256(path) != str(row.get("sha256", ""))
        ):
            failures.append(str(row.get("path", "")))
    return {
        "valid": not failures and len(payload.get("files", [])) == len(_MODEL_FILES),
        "reason": "" if not failures else "Model hash mismatch: " + ", ".join(failures),
        "model_sha256": str(payload.get("model_manifest_sha256", "")),
        "revision": str(payload.get("revision", "")),
        "license": str(payload.get("license", "")),
    }


def local_transcription_readiness(root: str | Path | None = None) -> dict[str, Any]:
    model_dir = default_model_dir(root)
    manifest = model_dir / "MODEL_MANIFEST_SHA256.json"
    missing = [name for name in _MODEL_FILES if not (model_dir / name).is_file()]
    try:
        package_version = metadata.version("faster-whisper")
    except metadata.PackageNotFoundError:
        package_version = ""
    ffmpeg_path = ffmpeg_executable() or ""
    integrity = (
        _manifest_status(str(model_dir), manifest.stat().st_mtime_ns)
        if manifest.is_file() and not missing
        else {"valid": False, "reason": "Bundled model files are incomplete.", "model_sha256": ""}
    )
    ready = bool(ffmpeg_path and package_version and not missing and integrity.get("valid"))
    reasons: list[str] = []
    if not ffmpeg_path:
        reasons.append("FFmpeg is unavailable.")
    if not package_version:
        reasons.append("faster-whisper is not installed.")
    if missing:
        reasons.append("Missing model files: " + ", ".join(missing))
    if not integrity.get("valid") and not missing:
        reasons.append(str(integrity.get("reason") or "Model integrity failed."))
    return {
        "provider": "local_faster_whisper",
        "state": "ready" if ready else "configuration_required",
        "ready": ready,
        "credential_required": False,
        "network_required_at_runtime": False,
        "ffmpeg_path": ffmpeg_path,
        "package_version": package_version,
        "model_path": str(model_dir),
        "model_manifest_sha256": str(integrity.get("model_sha256", "")),
        "model_revision": str(integrity.get("revision", "")),
        "model_license": str(integrity.get("license", "")),
        "supported_language_modes": ["auto", "english", "hindi", "hinglish"],
        "reason": " ".join(reasons),
    }


@lru_cache(maxsize=2)
def _load_model(model_path: str, compute_type: str, cpu_threads: int):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_path,
        device="cpu",
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        local_files_only=True,
    )


def transcribe_local(
    source_path: str | Path,
    *,
    root: str | Path | None = None,
    language: str = "auto",
    beam_size: int | None = None,
) -> dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Lecture media file is unavailable.")
    if source.suffix.casefold() not in _ALLOWED_MEDIA:
        raise ValueError("Unsupported lecture media type for local transcription.")
    readiness = local_transcription_readiness(root)
    if not readiness["ready"]:
        raise RuntimeError(readiness["reason"] or "Local transcription is not ready.")
    language_key = str(language).strip().casefold() or "auto"
    if language_key not in _LANGUAGE_CODES:
        raise ValueError("Language must be auto, English, Hindi, or Hinglish.")
    compute_type = os.environ.get("BIOINTEL_TRANSCRIPTION_COMPUTE_TYPE", "int8").strip() or "int8"
    configured_threads = int(os.environ.get("BIOINTEL_TRANSCRIPTION_CPU_THREADS", "0") or 0)
    cpu_threads = configured_threads if configured_threads > 0 else max(1, min(os.cpu_count() or 2, 8))
    configured_beam = int(os.environ.get("BIOINTEL_TRANSCRIPTION_BEAM_SIZE", "3") or 3)
    selected_beam = max(1, min(int(beam_size or configured_beam), 8))
    model = _load_model(readiness["model_path"], compute_type, cpu_threads)
    stream, info = model.transcribe(
        str(source),
        language=_LANGUAGE_CODES[language_key],
        beam_size=selected_beam,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )
    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for item in stream:
        body = str(item.text).strip()
        if body:
            text_parts.append(body)
        words = [
            {
                "start": round(float(word.start), 3),
                "end": round(float(word.end), 3),
                "word": str(word.word),
                "probability": round(float(word.probability), 6),
            }
            for word in (item.words or [])
        ]
        segments.append(
            {
                "id": int(item.id),
                "start": round(float(item.start), 3),
                "end": round(float(item.end), 3),
                "text": body,
                "avg_logprob": round(float(item.avg_logprob), 6),
                "no_speech_prob": round(float(item.no_speech_prob), 6),
                "words": words,
            }
        )
        if len(segments) > 100_000:
            raise RuntimeError("Transcript segment safety limit exceeded.")
    text = " ".join(text_parts).strip()
    if not text:
        raise RuntimeError("No speech was detected; no transcript was persisted.")
    return {
        "schema": "biointel.education.local-transcription.v1",
        "provider": readiness["provider"],
        "provider_version": readiness["package_version"],
        "model_path": readiness["model_path"],
        "model_manifest_sha256": readiness["model_manifest_sha256"],
        "model_revision": readiness["model_revision"],
        "requested_language": language_key,
        "detected_language": str(info.language or ""),
        "language_probability": round(float(info.language_probability or 0.0), 6),
        "duration_seconds": round(float(info.duration or 0.0), 3),
        "duration_after_vad_seconds": round(float(info.duration_after_vad or 0.0), 3),
        "source_path": str(source),
        "source_size_bytes": source.stat().st_size,
        "source_sha256": _sha256(source),
        "compute_type": compute_type,
        "cpu_threads": cpu_threads,
        "beam_size": selected_beam,
        "text": text,
        "segments": segments,
        "segment_count": len(segments),
        "generated_at": utc_now(),
        "network_used": False,
    }
