from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import html
import json
import os
import platform
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Iterator
from uuid import uuid4

import pandas as pd

from biointel.io.uploads import UploadReadError, read_uploaded_table_bytes
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.live_experience import LiveExperienceStore, get_live_store

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None

from biointel import __version__


# Streamlit is configured for a 1 GB request/upload ceiling.  Files above the
# interactive boundary are accepted, then staged to local disk and queued so a
# page never creates another full in-memory copy while rendering a preview.
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
INTERACTIVE_UPLOAD_BYTES = 100 * 1024 * 1024
STAGING_CHUNK_BYTES = 8 * 1024 * 1024
_PRESERVED_UPLOAD_KEYS = frozenset({"dti_batch_prediction", "instrument_import"})


def _upload_limit_label(limit_bytes: int | float) -> str:
    """Present an upload limit without implying every screen accepts 1 GB."""

    normalized = max(0, int(limit_bytes))
    if normalized >= MAX_UPLOAD_BYTES:
        return "1 GB"
    return f"{normalized / (1024 * 1024):g} MB"


class WorkflowCancelled(RuntimeError):
    """Raised by cooperative workflows after an operator cancellation request."""


@dataclass(frozen=True)
class UploadProfile:
    """Deterministic metadata used for upload safety and provenance."""

    filename: str
    extension: str
    content_type: str
    size_bytes: int
    size_mb: float
    sha256: str
    allowed: bool
    within_soft_limit: bool
    within_hard_limit: bool
    requires_staging: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowRun:
    """Mutable runtime state for one interactive analysis execution."""

    label: str
    started_at_utc: str
    started_monotonic: float
    stages: list[dict[str, Any]] = field(default_factory=list)
    completed_at_utc: str | None = None
    elapsed_seconds: float | None = None
    status: str = "running"
    error: str = ""
    _streamlit_status: Any = field(default=None, repr=False)
    _progress_widget: Any = field(default=None, repr=False)
    _detail_placeholder: Any = field(default=None, repr=False)
    _timeline_placeholder: Any = field(default=None, repr=False)
    _store: LiveExperienceStore | None = field(default=None, repr=False)
    run_id: str = ""
    page_key: str = ""
    _cancel_key: str = field(default="", repr=False)
    _last_progress: float = field(default=0.0, repr=False)

    def stage(self, label: str, *, detail: str = "", progress: float | None = None) -> None:
        event = {
            "label": str(label),
            "detail": str(detail),
            "progress": None if progress is None else round(float(progress), 4),
            "occurred_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.stages.append(event)
        if progress is not None:
            self._last_progress = max(self._last_progress, min(1.0, max(0.0, float(progress))))
        if self._store is not None and self.run_id:
            try:
                self._store.add_stage(
                    self.run_id,
                    sequence_no=len(self.stages),
                    label=str(label),
                    detail=str(detail),
                    progress=self._last_progress if progress is not None else None,
                    status="running",
                )
            except (OSError, sqlite3.Error):
                pass
        suffix = f" — {detail}" if detail else ""
        elapsed = max(0.0, time.perf_counter() - self.started_monotonic)
        if self._streamlit_status is not None:
            self._streamlit_status.update(label=f"{label}{suffix}", state="running")
        if self._progress_widget is not None:
            progress_text = f"{label}{suffix} · {elapsed:.1f}s"
            try:
                self._progress_widget.progress(self._last_progress, text=progress_text)
            except TypeError:  # Older supported Streamlit builds.
                self._progress_widget.progress(self._last_progress)
        if self._detail_placeholder is not None:
            self._detail_placeholder.caption(
                f"Stage {len(self.stages)} · {label}" + (f" · {detail}" if detail else "")
            )
        if self._timeline_placeholder is not None:
            self._timeline_placeholder.markdown(
                _live_timeline_html(self, terminal_status="running"),
                unsafe_allow_html=True,
            )

    @property
    def cancel_requested(self) -> bool:
        if not self._cancel_key or st is None:
            return False
        return bool(st.session_state.get(self._cancel_key, False))

    def request_cancel(self) -> None:
        if self._cancel_key and st is not None:
            st.session_state[self._cancel_key] = True

    def check_cancelled(self) -> None:
        if self.cancel_requested:
            raise WorkflowCancelled(f"{self.label} was cancelled by the operator.")

    def finish(self, *, status: str, error: str = "") -> None:
        self.status = status
        self.error = error
        self.completed_at_utc = datetime.now(UTC).isoformat(timespec="seconds")
        self.elapsed_seconds = round(time.perf_counter() - self.started_monotonic, 4)

    def manifest(
        self,
        *,
        parameters: dict[str, Any] | None = None,
        inputs: Iterable[UploadProfile | dict[str, Any]] | None = None,
        outputs: dict[str, Any] | None = None,
        method: str = "",
    ) -> dict[str, Any]:
        serialized_inputs: list[dict[str, Any]] = []
        for item in inputs or []:
            serialized_inputs.append(
                item.to_dict() if isinstance(item, UploadProfile) else dict(item)
            )
        return {
            "manifest_schema": "biointel.interactive_run.v1",
            "workflow": self.label,
            "status": self.status,
            "method": method,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "elapsed_seconds": self.elapsed_seconds,
            "stages": list(self.stages),
            "parameters": parameters or {},
            "inputs": serialized_inputs,
            "outputs": outputs or {},
            "software": {
                "biointel_ai": __version__,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "error": self.error,
        }


def _safe_extension(filename: str) -> str:
    lowered = str(filename or "upload").lower()
    for suffix in (
        ".csv.gz", ".tsv.gz", ".txt.gz", ".maf.gz", ".vcf.gz",
        ".fastq.gz", ".fq.gz", ".fasta.gz", ".fa.gz",
    ):
        if lowered.endswith(suffix):
            return suffix
    suffixes = Path(filename or "upload").suffixes
    return suffixes[-1].lower() if suffixes else ""


def _content_signature_error(extension: str, data: bytes | bytearray | memoryview) -> str:
    """Return an actionable error for common binary-container mismatches."""

    header = bytes(data[:16])
    zip_extensions = {".zip", ".docx", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods"}
    if extension in zip_extensions and header and not header.startswith(b"PK"):
        return f"{extension} content does not have a valid ZIP/Office container signature."
    if extension == ".xls" and header and not header.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return ".xls content does not have a valid legacy Excel container signature."
    if extension == ".pdf" and header and not header.lstrip().startswith(b"%PDF-"):
        return "PDF content does not have a valid %PDF signature."
    if extension.endswith(".gz") and header and not header.startswith(b"\x1f\x8b"):
        return f"{extension} content does not have a valid gzip signature."
    return ""


def profile_upload(
    filename: str,
    data: bytes | bytearray | memoryview,
    *,
    content_type: str = "application/octet-stream",
    allowed_extensions: Iterable[str] | None = None,
    soft_limit_mb: float = 100.0,
    hard_limit_mb: float = 1024.0,
) -> UploadProfile:
    """Validate an in-memory upload without trusting the client filename."""

    normalized_allowed = {
        value.lower() if str(value).startswith(".") else f".{str(value).lower()}"
        for value in (allowed_extensions or [])
    }
    extension = _safe_extension(filename)
    size_bytes = len(data)
    size_mb = size_bytes / (1024 * 1024)
    extension_allowed = not normalized_allowed or extension in normalized_allowed
    signature_error = _content_signature_error(extension, data)
    allowed = extension_allowed and not signature_error
    effective_soft_limit_mb = min(max(float(soft_limit_mb), 0.001), INTERACTIVE_UPLOAD_BYTES / (1024 * 1024))
    effective_hard_limit_mb = min(max(float(hard_limit_mb), 0.001), MAX_UPLOAD_BYTES / (1024 * 1024))
    within_soft = size_mb <= effective_soft_limit_mb
    within_hard = size_mb <= effective_hard_limit_mb
    warnings: list[str] = []
    if not extension_allowed:
        warnings.append(
            f"Extension {extension or '(none)'} is not in the accepted set: "
            + ", ".join(sorted(normalized_allowed))
        )
    if signature_error:
        warnings.append(signature_error)
    if not within_soft and within_hard:
        warnings.append(
            f"Large upload ({size_mb:.1f} MB). It is accepted up to {_upload_limit_label(effective_hard_limit_mb * 1024 * 1024)}, but must be staged to local disk for background-safe processing."
        )
    if not within_hard:
        warnings.append(
            f"Upload exceeds the {effective_hard_limit_mb:g} MB per-file safety limit. Choose a smaller file or split it before staging."
        )
    if size_bytes == 0:
        warnings.append("The uploaded file is empty.")
    return UploadProfile(
        filename=Path(filename or "upload").name,
        extension=extension,
        content_type=str(content_type or "application/octet-stream"),
        size_bytes=size_bytes,
        size_mb=round(size_mb, 4),
        sha256=hashlib.sha256(data).hexdigest(),
        allowed=allowed,
        within_soft_limit=within_soft,
        within_hard_limit=within_hard,
        requires_staging=bool(allowed and within_hard and not within_soft and size_bytes > 0),
        warnings=tuple(warnings),
    )


def profile_streamlit_upload(
    uploaded_file: Any,
    *,
    allowed_extensions: Iterable[str] | None = None,
    soft_limit_mb: float = 100.0,
    hard_limit_mb: float = 1024.0,
    enforce_requested_limit: bool = False,
) -> UploadProfile:
    """Profile a Streamlit upload without copying large files into page memory.

    Most legacy pages carried smaller per-page parser limits.  Their files are
    now accepted up to the global 1 GB ceiling, but a file beyond the requested
    interactive threshold is streamed to a staging workflow instead of being
    handed to an in-memory parser.  The two protected modules retain their
    original limits through ``enforce_requested_limit``.
    """

    effective_hard_limit_mb = (
        float(hard_limit_mb)
        if enforce_requested_limit
        else MAX_UPLOAD_BYTES / (1024 * 1024)
    )
    cache_key = (
        str(getattr(uploaded_file, "name", "upload")),
        int(getattr(uploaded_file, "size", -1) or -1),
        tuple(sorted(str(item).lower() for item in (allowed_extensions or []))),
        float(soft_limit_mb),
        effective_hard_limit_mb,
        bool(enforce_requested_limit),
    )
    cached = getattr(uploaded_file, "_biointel_upload_profile_cache", None)
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == cache_key:
        return cached[1]
    advertised_size = int(getattr(uploaded_file, "size", 0) or 0)
    effective_soft_limit_mb = min(
        max(float(soft_limit_mb), 0.001),
        INTERACTIVE_UPLOAD_BYTES / (1024 * 1024),
    )
    soft_limit_bytes = int(effective_soft_limit_mb * 1024 * 1024)
    hard_limit_bytes = int(min(effective_hard_limit_mb, MAX_UPLOAD_BYTES / (1024 * 1024)) * 1024 * 1024)

    if advertised_size <= soft_limit_bytes:
        if hasattr(uploaded_file, "getbuffer"):
            data = uploaded_file.getbuffer()
        else:
            data = uploaded_file.getvalue()
        profile = profile_upload(
            getattr(uploaded_file, "name", "upload"),
            data,
            content_type=getattr(uploaded_file, "type", "application/octet-stream"),
            allowed_extensions=allowed_extensions,
            soft_limit_mb=effective_soft_limit_mb,
            hard_limit_mb=hard_limit_bytes / (1024 * 1024),
        )
    else:
        normalized_allowed = {
            value.lower() if str(value).startswith(".") else f".{str(value).lower()}"
            for value in (allowed_extensions or [])
        }
        filename = str(getattr(uploaded_file, "name", "upload"))
        extension = _safe_extension(filename)
        extension_allowed = not normalized_allowed or extension in normalized_allowed
        within_hard = advertised_size <= hard_limit_bytes
        digest = hashlib.sha256()
        header = b""
        observed_size = 0
        if within_hard:
            try:
                if hasattr(uploaded_file, "seek"):
                    uploaded_file.seek(0)
                while True:
                    chunk = uploaded_file.read(STAGING_CHUNK_BYTES)
                    if not chunk:
                        break
                    if len(header) < 16:
                        header += bytes(chunk[: 16 - len(header)])
                    observed_size += len(chunk)
                    if observed_size > hard_limit_bytes:
                        within_hard = False
                        break
                    digest.update(chunk)
            finally:
                if hasattr(uploaded_file, "seek"):
                    try:
                        uploaded_file.seek(0)
                    except Exception:
                        pass
        size_bytes = observed_size or advertised_size
        size_mb = size_bytes / (1024 * 1024)
        signature_error = _content_signature_error(extension, header)
        allowed = extension_allowed and not signature_error
        within_soft = size_bytes <= soft_limit_bytes
        warnings: list[str] = []
        if not extension_allowed:
            warnings.append(
                f"Extension {extension or '(none)'} is not in the accepted set: "
                + ", ".join(sorted(normalized_allowed))
            )
        if signature_error:
            warnings.append(signature_error)
        if not within_hard:
            warnings.append(
                f"Upload exceeds the {hard_limit_bytes / (1024 * 1024):g} MB per-file safety limit. Choose a smaller file or split it before staging."
            )
        elif not within_soft:
            warnings.append(
                f"Large upload ({size_mb:.1f} MB). It is accepted up to {_upload_limit_label(hard_limit_bytes)}, but must be staged to local disk for background-safe processing."
            )
        profile = UploadProfile(
            filename=Path(filename).name,
            extension=extension,
            content_type=str(getattr(uploaded_file, "type", "application/octet-stream") or "application/octet-stream"),
            size_bytes=size_bytes,
            size_mb=round(size_mb, 4),
            sha256=digest.hexdigest() if within_hard and observed_size else "",
            allowed=allowed,
            within_soft_limit=within_soft,
            within_hard_limit=within_hard,
            requires_staging=bool(allowed and within_hard and not within_soft and size_bytes > 0),
            warnings=tuple(warnings),
        )
    try:
        setattr(uploaded_file, "_biointel_upload_profile_cache", (cache_key, profile))
    except Exception:
        pass
    return profile


def stage_streamlit_upload(
    uploaded_file: Any,
    destination: str | Path,
    *,
    max_bytes: int = 1024 * 1024 * 1024,
    chunk_size: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    """Atomically stream an uploaded file to disk with a bounded size.

    This avoids a second ``getvalue()``/``getbuffer()`` copy for large uploads.
    The final path is replaced only after the stream is complete and fsynced, so
    interrupted writes never masquerade as valid reference assets.
    """

    if uploaded_file is None:
        raise ValueError("No uploaded file was supplied.")
    if max_bytes <= 0 or chunk_size <= 0:
        raise ValueError("Upload size and chunk size limits must be positive.")
    advertised_size = int(getattr(uploaded_file, "size", 0) or 0)
    if advertised_size > max_bytes:
        raise ValueError(f"Upload exceeds the configured maximum of {max_bytes:,} bytes.")

    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".upload-" + uuid4().hex + ".part")
    digest = hashlib.sha256()
    written = 0
    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        with temporary.open("wb") as handle:
            while True:
                chunk = uploaded_file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"Upload exceeded the configured maximum of {max_bytes:,} bytes.")
                handle.write(chunk)
                digest.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if written == 0:
            raise ValueError("Uploaded file is empty.")
        os.replace(temporary, target)
        return {
            "path": str(target),
            "size_bytes": written,
            "sha256": digest.hexdigest(),
        }
    finally:
        temporary.unlink(missing_ok=True)
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                pass


def _safe_upload_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value or "upload.dat").name).strip("._")
    return cleaned[:120] or "scientific_upload.dat"


def _staging_root() -> Path:
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return (Path(local_app_data) / "BioIntelAI" / "UserData").resolve()
    return (Path(__file__).resolve().parents[3] / "UserData").resolve()


def stage_large_streamlit_upload(
    uploaded_file: Any,
    *,
    module_key: str,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Stage one accepted large upload and queue a bounded local inspection job."""

    root = Path(project_root).resolve() if project_root is not None else Path(__file__).resolve().parents[3]
    safe_module = _safe_upload_name(module_key).replace(".", "_")
    directory = _staging_root() / "staged_uploads" / safe_module
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = directory / f"{stamp}-{uuid4().hex[:10]}-{_safe_upload_name(str(getattr(uploaded_file, 'name', 'upload.dat')))}"
    staged = stage_streamlit_upload(uploaded_file, destination, max_bytes=MAX_UPLOAD_BYTES)
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    job = queue.submit(
        "scientific_large_file_inspect",
        {
            "path": staged["path"],
            "module_key": str(module_key),
            "original_name": str(getattr(uploaded_file, "name", destination.name)),
        },
        priority=80,
        max_attempts=2,
        stages=["verify_path", "stream_hash", "sample", "finalize"],
        resources={"memory_mb": 256, "io_bound": True},
        estimated_seconds=max(5.0, float(staged["size_bytes"]) / (40 * 1024 * 1024)),
    )
    manifest = {
        "module_key": str(module_key),
        "original_name": str(getattr(uploaded_file, "name", destination.name)),
        "size_bytes": int(staged["size_bytes"]),
        "sha256": str(staged["sha256"]),
        "staged_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "queued_for_background_review",
        "job_id": job.job_id,
    }
    destination.with_suffix(destination.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def render_upload_preflight(
    uploaded_file: Any,
    *,
    key: str,
    allowed_extensions: Iterable[str] | None = None,
    soft_limit_mb: float = 100.0,
    hard_limit_mb: float = 1024.0,
    show_hash: bool = True,
    block_on_failure: bool = True,
    block_large_files: bool = True,
    module_key: str | None = None,
    preserve_requested_limit: bool | None = None,
) -> UploadProfile | None:
    """Render upload safety state and stage eligible files above the preview limit.

    ``hard_limit_mb`` remains a contextual parser hint for legacy pages.  Unless
    a page is one of the protected modules, the accepted file ceiling is the
    platform-wide 1 GB limit.  Files larger than the page's safe interactive
    threshold are atomically staged and sent to the local background queue.
    """

    if uploaded_file is None:
        return None
    if preserve_requested_limit is None:
        preserve_requested_limit = key in _PRESERVED_UPLOAD_KEYS
    profile = profile_streamlit_upload(
        uploaded_file,
        allowed_extensions=allowed_extensions,
        soft_limit_mb=soft_limit_mb,
        hard_limit_mb=hard_limit_mb,
        enforce_requested_limit=bool(preserve_requested_limit),
    )
    effective_limit_bytes = int(
        min(
            float(hard_limit_mb) if preserve_requested_limit else MAX_UPLOAD_BYTES / (1024 * 1024),
            MAX_UPLOAD_BYTES / (1024 * 1024),
        )
        * 1024
        * 1024
    )
    if st is None:  # pragma: no cover
        return profile
    columns = st.columns([1.45, 0.8, 0.9, 1.15])
    columns[0].caption(f"**File:** {profile.filename}")
    columns[1].caption(f"**Size:** {profile.size_mb:.2f} MB")
    columns[2].caption("**Mode:** staged background" if profile.requires_staging else "**Mode:** interactive preview")
    columns[3].caption(
        f"**SHA-256:** `{profile.sha256[:12]}…`"
        if show_hash and profile.sha256
        else "**Hash:** calculated during staging"
        if show_hash
        else f"**Type:** {profile.extension or 'unknown'}"
    )
    for warning in profile.warnings:
        if not profile.allowed or not profile.within_hard_limit or profile.size_bytes == 0:
            st.error(warning)
        else:
            st.warning(warning)
    if profile.allowed and profile.within_hard_limit and profile.size_bytes > 0 and not profile.requires_staging:
        st.caption(
            "✓ Upload preflight passed · file identity is recorded in exported run provenance."
        )
    st.session_state[f"{key}_upload_profile"] = profile.to_dict()
    if block_on_failure and (
        not profile.allowed or not profile.within_hard_limit or profile.size_bytes == 0
    ):
        st.stop()
    if profile.requires_staging:
        st.info(
            f"This file is within the {_upload_limit_label(effective_limit_bytes)} limit. To protect the desktop UI, it is staged to protected local storage and queued for bounded background inspection; it will not be loaded into an interactive dataframe.",
        )
        staging_key = f"{key}_staged_manifest"
        signature = f"{profile.filename}:{profile.size_bytes}:{profile.sha256}"
        existing = st.session_state.get(staging_key)
        if block_large_files:
            if not isinstance(existing, dict) or existing.get("upload_signature") != signature:
                try:
                    with st.spinner("Staging the large upload safely to local storage…"):
                        manifest = stage_large_streamlit_upload(
                            uploaded_file,
                            module_key=module_key or key,
                        )
                    manifest["upload_signature"] = signature
                    st.session_state[staging_key] = manifest
                    existing = manifest
                except (OSError, ValueError, sqlite3.Error) as exc:
                    st.error(f"Large-file staging failed safely: {exc}")
                    st.stop()
            if isinstance(existing, dict):
                st.success(
                    f"Large upload staged · background inspection job `{existing.get('job_id', 'queued')}`. Open Background Job Center when the inspection is complete."
                )
            st.stop()
    return profile


def render_upload_collection_preflight(
    uploaded_files: Iterable[Any] | None,
    *,
    key: str,
    allowed_extensions: Iterable[str] | None = None,
    per_file_soft_limit_mb: float = 100.0,
    per_file_hard_limit_mb: float = 1024.0,
    combined_hard_limit_mb: float = 1024.0,
    block_on_failure: bool = True,
    block_large_files: bool = True,
    module_key: str | None = None,
) -> list[UploadProfile]:
    """Validate a multi-file upload and expose aggregate size/provenance."""

    files = list(uploaded_files or [])
    profiles = [
        profile_streamlit_upload(
            item,
            allowed_extensions=allowed_extensions,
            soft_limit_mb=per_file_soft_limit_mb,
            hard_limit_mb=per_file_hard_limit_mb,
            enforce_requested_limit=False,
        )
        for item in files
    ]
    if st is None:  # pragma: no cover
        return profiles
    if not profiles:
        return profiles
    total_bytes = sum(profile.size_bytes for profile in profiles)
    total_mb = total_bytes / (1024 * 1024)
    invalid = [
        profile
        for profile in profiles
        if not profile.allowed or not profile.within_hard_limit or profile.size_bytes == 0
    ]
    columns = st.columns(3)
    columns[0].caption(f"**Files:** {len(profiles):,}")
    columns[1].caption(f"**Combined size:** {total_mb:.2f} MB")
    combined_limit_bytes = min(
        int(float(combined_hard_limit_mb) * 1024 * 1024),
        MAX_UPLOAD_BYTES,
    )
    combined_large = total_bytes > INTERACTIVE_UPLOAD_BYTES
    columns[2].caption(
        f"**Preflight:** {'Blocked' if invalid or total_bytes > combined_limit_bytes else ('Stage batch' if combined_large else 'Passed')}"
    )
    if total_bytes > combined_limit_bytes:
        st.error(
            "Combined upload exceeds the 1 GB staging limit. Stage fewer files at a time."
        )
    for profile in invalid[:8]:
        st.error(f"{profile.filename}: " + "; ".join(profile.warnings))
    if len(invalid) > 8:
        st.error(f"{len(invalid) - 8} additional invalid files are not shown.")
    if not invalid and total_bytes <= combined_limit_bytes and not combined_large:
        st.caption(
            "✓ Batch upload preflight passed · per-file hashes are available to the run manifest."
        )
    st.session_state[f"{key}_upload_profiles"] = [profile.to_dict() for profile in profiles]
    if block_on_failure and (invalid or total_bytes > combined_limit_bytes):
        st.stop()
    if combined_large:
        st.info(
            "The selected batch is within the 1 GB boundary but above the safe interactive preview budget. It will be staged as separate local background-inspection jobs."
        )
        staging_key = f"{key}_staged_manifests"
        signature = "|".join(
            f"{profile.filename}:{profile.size_bytes}:{profile.sha256}" for profile in profiles
        )
        existing = st.session_state.get(staging_key)
        if block_large_files:
            if not isinstance(existing, dict) or existing.get("upload_signature") != signature:
                try:
                    with st.spinner("Staging the upload batch safely to local storage…"):
                        manifests = [
                            stage_large_streamlit_upload(item, module_key=module_key or key)
                            for item in files
                        ]
                    existing = {"upload_signature": signature, "manifests": manifests}
                    st.session_state[staging_key] = existing
                except (OSError, ValueError, sqlite3.Error) as exc:
                    st.error(f"Large batch staging failed safely: {exc}")
                    st.stop()
            if isinstance(existing, dict):
                count = len(existing.get("manifests", []))
                st.success(f"{count} file(s) staged for local background inspection.")
            st.stop()
    return profiles


def require_usable_upload(profile: UploadProfile | None) -> None:
    if profile is None:
        return
    if not profile.allowed:
        raise ValueError("Unsupported upload extension.")
    if not profile.within_hard_limit:
        raise ValueError("Upload exceeds the configured per-file safety limit.")
    if profile.requires_staging:
        raise ValueError("This upload requires staged background processing above the interactive preview boundary.")
    if profile.size_bytes == 0:
        raise ValueError("Uploaded file is empty.")


def _cache_data(*, ttl: int = 600, max_entries: int = 64):
    if st is None:

        def decorator(func):
            return func

        return decorator
    return st.cache_data(ttl=ttl, max_entries=max_entries, show_spinner=False)


@_cache_data(ttl=600, max_entries=64)
def _read_uploaded_table_cached(
    data: bytes,
    filename: str,
    separator: str | None,
    encoding: str | None,
    low_memory: bool,
    index_column: str | int | None,
    sheet_name: str | int | None,
    max_rows: int | None,
    max_columns: int,
    max_cells: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    result = read_uploaded_table_bytes(
        data,
        filename,
        separator=separator,
        encoding=encoding,
        low_memory=low_memory,
        index_column=index_column,
        sheet_name=sheet_name,
        max_rows=max_rows,
        max_columns=max_columns,
        max_cells=max_cells,
    )
    metadata = {
        "source_name": result.source_name,
        "detected_extension": result.detected_extension,
        "encoding": result.encoding,
        "separator": result.separator,
        "sheet_name": result.sheet_name,
        "archive_member": result.archive_member,
        "warnings": list(result.warnings),
    }
    return result.frame, metadata


def read_uploaded_table(
    uploaded_file: Any,
    *,
    separator: str | None = None,
    encoding: str | None = None,
    low_memory: bool = False,
    index_column: str | int | None = None,
    sheet_name: str | int | None = None,
    max_rows: int | None = None,
    max_columns: int = 10_000,
    max_cells: int = 25_000_000,
    copy: bool = True,
) -> pd.DataFrame:
    """Read an uploaded table with delimiter/encoding detection and bounded decompression.

    CSV, TSV, TXT, MAF, gzip variants, Excel/ODS and a ZIP containing exactly
    one table are supported. The uploaded stream position is restored when possible.
    """

    if uploaded_file is None:
        raise UploadReadError("No file was uploaded.")
    name = str(getattr(uploaded_file, "name", "upload"))
    try:
        if hasattr(uploaded_file, "getvalue"):
            data = bytes(uploaded_file.getvalue())
        else:
            original_position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            data = bytes(uploaded_file.read())
            if original_position is not None and hasattr(uploaded_file, "seek"):
                uploaded_file.seek(original_position)
        frame, metadata = _read_uploaded_table_cached(
            data,
            name,
            separator,
            encoding,
            bool(low_memory),
            index_column,
            sheet_name,
            max_rows,
            int(max_columns),
            int(max_cells),
        )
    except UploadReadError:
        raise
    except Exception as exc:
        raise UploadReadError(f"{Path(name).name} could not be read safely: {exc}") from exc
    if st is not None:
        st.session_state["_bio_latest_table_upload"] = metadata
        for warning in metadata.get("warnings", []):
            st.warning(str(warning))
    return frame.copy(deep=True) if copy else frame


@_cache_data(ttl=600, max_entries=64)
def _decode_uploaded_text_cached(data: bytes, encoding: str, errors: str) -> str:
    return data.decode(encoding, errors=errors)


def read_uploaded_text(
    uploaded_file: Any,
    *,
    encoding: str = "utf-8-sig",
    errors: str = "replace",
) -> str:
    return _decode_uploaded_text_cached(uploaded_file.getvalue(), encoding, errors)


def _live_timeline_html(run: WorkflowRun, *, terminal_status: str = "running") -> str:
    """Render a compact, accessible stage timeline that updates during execution."""

    level_icon = {
        "completed": "✓",
        "failed": "!",
        "cancelled": "×",
        "running": "●",
    }
    rendered: list[str] = []
    for index, event in enumerate(run.stages):
        is_last = index == len(run.stages) - 1
        if not is_last or terminal_status == "completed":
            state = "completed"
        elif terminal_status in {"failed", "cancelled"}:
            state = terminal_status
        else:
            state = "running"
        detail = html.escape(str(event.get("detail", "")))
        detail_html = f'<span class="bio-live-stage-detail">{detail}</span>' if detail else ""
        progress = event.get("progress")
        progress_html = (
            f'<span class="bio-live-stage-progress">{float(progress) * 100:.0f}%</span>'
            if progress is not None else ""
        )
        rendered.append(
            '<div class="bio-live-stage '+state+'">'
            f'<span class="bio-live-stage-dot" aria-hidden="true">{level_icon.get(state, "•")}</span>'
            '<div class="bio-live-stage-copy">'
            f'<b>{html.escape(str(event.get("label", "Stage")))}</b>{detail_html}'
            '</div>'
            f'{progress_html}</div>'
        )
    elapsed = max(0.0, time.perf_counter() - run.started_monotonic)
    return (
        '<section class="bio-live-timeline" aria-label="Live analysis timeline" aria-live="polite">'
        '<div class="bio-live-timeline-head"><span>Live analysis timeline</span>'
        f'<small>{len(run.stages)} stages · {elapsed:.1f}s</small></div>'
        + "".join(rendered)
        + '</section>'
    )


@contextmanager
def analysis_run(
    label: str,
    *,
    expanded: bool = False,
    show_progress: bool = True,
    cancel_key: str = "",
) -> Iterator[WorkflowRun]:
    """Show consistent progress, capture timing and preserve an exportable stage trail."""

    page_key = ""
    store: LiveExperienceStore | None = None
    run_id = ""
    if st is not None:
        page_key = str(st.session_state.get("_bio_active_page_key", "") or "")
        try:
            store = get_live_store()
            run_id = store.start_run(label, page_key=page_key)
        except (OSError, sqlite3.Error):
            store = None
    run = WorkflowRun(
        label=label,
        started_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        started_monotonic=time.perf_counter(),
        _store=store,
        run_id=run_id,
        page_key=page_key,
    )
    status = None
    if st is not None and hasattr(st, "status"):
        status = st.status(label, expanded=expanded)
        run._streamlit_status = status
        if show_progress and hasattr(st, "progress"):
            try:
                run._progress_widget = st.progress(0.02, text=f"{label} · preparing")
            except TypeError:  # pragma: no cover - older Streamlit compatibility.
                run._progress_widget = st.progress(0.02)
            run._detail_placeholder = st.empty()
            run._timeline_placeholder = st.empty()
        if cancel_key:
            run._cancel_key = cancel_key
            st.session_state.setdefault(cancel_key, False)
    elif st is not None:
        spinner = st.spinner(label)
        spinner.__enter__()
    else:
        spinner = None
    try:
        run.stage("Preparing inputs", progress=0.05)
        yield run
        run.finish(status="completed")
        manifest = run.manifest()
        if st is not None:
            st.session_state["_bio_latest_run"] = manifest
        if store is not None and run_id:
            try:
                store.finish_run(run_id, status="completed", elapsed_seconds=run.elapsed_seconds, manifest=manifest)
                store.notify(
                    "Analysis completed",
                    f"{label} completed in {float(run.elapsed_seconds or 0):.2f}s.",
                    level="success", source="analysis", page_key=page_key,
                    action_label="Open module", action_target=page_key, related_run_id=run_id,
                    dedupe_key=f"analysis:{run_id}:completed",
                )
            except (OSError, sqlite3.Error):
                pass
        if run._timeline_placeholder is not None:
            run._timeline_placeholder.markdown(_live_timeline_html(run, terminal_status="completed"), unsafe_allow_html=True)
        if run._progress_widget is not None:
            try:
                run._progress_widget.progress(1.0, text=f"Complete · {run.elapsed_seconds:.2f}s")
            except TypeError:
                run._progress_widget.progress(1.0)
        if run._detail_placeholder is not None:
            run._detail_placeholder.caption(
                f"Completed {len(run.stages)} stages in {run.elapsed_seconds:.2f}s"
            )
        if status is not None:
            status.update(
                label=f"{label} — complete in {run.elapsed_seconds:.2f}s",
                state="complete",
                expanded=False,
            )
    except WorkflowCancelled as exc:
        run.finish(status="cancelled", error=str(exc))
        manifest = run.manifest()
        if st is not None:
            st.session_state["_bio_latest_run"] = manifest
        if store is not None and run_id:
            try:
                store.finish_run(run_id, status="cancelled", elapsed_seconds=run.elapsed_seconds, error=str(exc), manifest=manifest)
                store.notify(
                    "Analysis cancelled", f"{label} was cancelled.", level="warning", source="analysis",
                    page_key=page_key, action_label="Open module", action_target=page_key,
                    related_run_id=run_id, dedupe_key=f"analysis:{run_id}:cancelled",
                )
            except (OSError, sqlite3.Error):
                pass
        if run._timeline_placeholder is not None:
            run._timeline_placeholder.markdown(_live_timeline_html(run, terminal_status="cancelled"), unsafe_allow_html=True)
        if run._progress_widget is not None:
            try:
                run._progress_widget.progress(run._last_progress, text="Cancelled")
            except TypeError:
                run._progress_widget.progress(run._last_progress)
        if status is not None:
            status.update(label=f"{label} — cancelled", state="error", expanded=False)
        if st is not None:
            st.warning(str(exc))
        raise
    except Exception as exc:
        run.finish(status="failed", error=str(exc))
        manifest = run.manifest()
        if st is not None:
            st.session_state["_bio_latest_run"] = manifest
        if store is not None and run_id:
            try:
                store.finish_run(run_id, status="failed", elapsed_seconds=run.elapsed_seconds, error=str(exc), manifest=manifest)
                store.notify(
                    "Analysis failed", f"{label}: {str(exc)[:240]}", level="error", source="analysis",
                    page_key=page_key, action_label="Review module", action_target=page_key,
                    related_run_id=run_id, dedupe_key=f"analysis:{run_id}:failed",
                )
            except (OSError, sqlite3.Error):
                pass
        if run._timeline_placeholder is not None:
            run._timeline_placeholder.markdown(_live_timeline_html(run, terminal_status="failed"), unsafe_allow_html=True)
        if run._progress_widget is not None:
            try:
                run._progress_widget.progress(
                    run._last_progress, text="Failed — review recovery guidance"
                )
            except TypeError:
                run._progress_widget.progress(run._last_progress)
        if status is not None:
            status.update(label=f"{label} — failed", state="error", expanded=True)
        if st is not None:
            st.error(f"{label} failed: {exc}")
            with st.expander("Recovery guidance", expanded=False):
                st.markdown(
                    "Check the file schema and selected columns, reduce very large inputs, "
                    "and rerun with the bundled example to separate input problems from environment problems."
                )
        raise
    finally:
        if status is None and st is not None and "spinner" in locals() and spinner is not None:
            spinner.__exit__(None, None, None)


def render_skeleton(
    *,
    kind: str = "card",
    rows: int = 4,
    label: str = "Loading content",
) -> None:
    """Render a layout-stable, reduced-motion-aware placeholder."""

    if st is None:  # pragma: no cover
        return
    normalized = str(kind).strip().lower()
    count = max(1, min(12, int(rows)))
    if normalized == "chart":
        body = '<div class="bio-skeleton-chart"></div>'
    elif normalized == "table":
        body = "".join('<div class="bio-skeleton-table-row"></div>' for _ in range(count))
    else:
        body = (
            '<div class="bio-skeleton-line short"></div>'
            '<div class="bio-skeleton-line"></div>'
            '<div class="bio-skeleton-block"></div>'
        )
    st.markdown(
        f'<div class="bio-skeleton" role="status" aria-label="{html.escape(label)}">{body}'
        '<span class="bio-visually-hidden">Loading…</span></div>',
        unsafe_allow_html=True,
    )


@contextmanager
def indeterminate_loader(label: str) -> Iterator[None]:
    """Consistent indeterminate state for work that cannot report a percentage."""

    if st is None:  # pragma: no cover
        yield
        return
    placeholder = st.empty()
    escaped = html.escape(label)
    placeholder.markdown(
        '<div class="bio-progress-shell" role="status" aria-live="polite">'
        f'<div class="bio-progress-label">{escaped}</div>'
        '<div class="bio-progress-indeterminate" role="progressbar" '
        f'aria-label="{escaped}" aria-valuetext="In progress"></div></div>',
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()


def render_cancel_control(run: WorkflowRun, *, label: str = "Cancel operation") -> bool:
    """Expose cooperative cancellation for staged jobs.

    The workflow must call ``run.check_cancelled()`` between expensive stages.
    """

    if st is None or not run._cancel_key:  # pragma: no cover
        return False
    clicked = st.button(label, key=f"{run._cancel_key}_button", type="secondary")
    if clicked:
        run.request_cancel()
    return clicked


def render_methodology(
    *,
    method: str,
    assumptions: Iterable[str],
    limitations: Iterable[str],
    validation: Iterable[str] = (),
    expanded: bool = False,
) -> None:
    if st is None:  # pragma: no cover
        return
    with st.expander("Method, assumptions & limitations", expanded=expanded):
        st.markdown(f"**Method:** {html.escape(str(method))}")
        assumption_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in assumptions)
        limitation_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in limitations)
        st.markdown(f"**Assumptions**<ul>{assumption_items}</ul>", unsafe_allow_html=True)
        st.markdown(f"**Limitations**<ul>{limitation_items}</ul>", unsafe_allow_html=True)
        validation_items = list(validation)
        if validation_items:
            items = "".join(f"<li>{html.escape(str(item))}</li>" for item in validation_items)
            st.markdown(f"**Recommended validation**<ul>{items}</ul>", unsafe_allow_html=True)


def render_run_manifest_download(
    run: WorkflowRun,
    *,
    filename: str,
    parameters: dict[str, Any] | None = None,
    inputs: Iterable[UploadProfile | dict[str, Any]] | None = None,
    outputs: dict[str, Any] | None = None,
    method: str = "",
    key: str,
) -> dict[str, Any]:
    payload = run.manifest(
        parameters=parameters,
        inputs=inputs,
        outputs=outputs,
        method=method,
    )
    if st is not None:
        st.download_button(
            "Download run provenance",
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            filename,
            "application/json",
            key=key,
            width="stretch",
        )
    return payload


def dataframe_profile(frame: pd.DataFrame) -> dict[str, Any]:
    """Compact, JSON-safe shape/quality summary for result manifests."""

    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "column_names": [str(column) for column in frame.columns],
    }
