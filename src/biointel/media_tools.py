from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def ffmpeg_executable() -> str | None:
    """Return an explicitly configured, system, or bundled local FFmpeg executable."""
    configured = os.environ.get("BIOINTEL_FFMPEG", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return str(path)
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        return str(bundled) if bundled.is_file() else None
    except (ImportError, OSError, RuntimeError):
        return None


def ffprobe_executable() -> str | None:
    configured = os.environ.get("BIOINTEL_FFPROBE", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return str(path)
    return shutil.which("ffprobe")


def media_duration(path: str | Path, *, timeout: float = 30.0) -> float:
    """Probe duration locally, using ffprobe first and bundled FFmpeg as a safe fallback."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return 0.0
    probe = ffprobe_executable()
    if probe:
        try:
            completed = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            return max(0.0, float(completed.stdout.strip() or 0))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return 0.0
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0.0
    match = _DURATION.search((completed.stderr or "") + "\n" + (completed.stdout or ""))
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return max(0.0, int(hours) * 3600 + int(minutes) * 60 + float(seconds))
