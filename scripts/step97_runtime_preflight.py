from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import time
import tomllib
from pathlib import Path

MIN_FREE_BYTES = 512 * 1024 * 1024
RELEASE_RE = re.compile(r"^STEP(?P<step>\d+)_RELEASE\.json$", re.IGNORECASE)
MARKER_RE = re.compile(r"^step(?P<step>\d+)_part(?P<part>\d+)\.ok$", re.IGNORECASE)

def _expected_parts(step: int) -> set[int]:
    # The active Step220 distribution and its supported compatibility layout
    # use four package markers.
    return set(range(1, 5))



def _complete_marker_steps(root: Path) -> list[int]:
    marker_dir = root / ".release_parts"
    groups: dict[int, set[int]] = {}
    if marker_dir.is_dir():
        for path in marker_dir.iterdir():
            match = MARKER_RE.match(path.name)
            if match and path.is_file():
                groups.setdefault(int(match.group("step")), set()).add(int(match.group("part")))
    return sorted(step for step, parts in groups.items() if parts == _expected_parts(step))


def _validated_release_version(root: Path) -> str:
    """Validate the active release without treating historical manifests as current.

    STEP175_RELEASE.json and other older STEP*_RELEASE.json files are historical
    milestone records. They are intentionally allowed to retain their original
    versions. The active release is the highest complete release whose version
    matches VERSION, with safe self-repair from complete current part markers.
    """
    version_path = root / "VERSION"
    if not version_path.is_file():
        raise RuntimeError("VERSION is missing from the extracted BioIntel AI folder.")
    version = version_path.read_text(encoding="utf-8-sig").strip()
    if not version:
        raise RuntimeError("VERSION is empty in the extracted BioIntel AI folder.")

    pyproject_path = root / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"pyproject.toml is unreadable: {exc}") from exc
    if project_version != version:
        raise RuntimeError(
            "Mixed current product metadata were detected: "
            f"VERSION={version!r}, pyproject.toml version={project_version!r}. "
            "Extract all required matching current ZIP parts into one new empty folder."
        )

    complete_steps = _complete_marker_steps(root)
    candidates: list[tuple[int, Path]] = []
    malformed: list[str] = []
    for release_path in root.glob("STEP*_RELEASE.json"):
        match = RELEASE_RE.match(release_path.name)
        if not match:
            continue
        filename_step = int(match.group("step"))
        try:
            payload = json.loads(release_path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError("top-level JSON is not an object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            malformed.append(f"{release_path.name}: {exc}")
            continue
        release_version = str(payload.get("version", "")).strip()
        if release_version != version:
            # Historical release record: valid, but not the current product manifest.
            continue
        try:
            declared_step = int(payload.get("step", filename_step))
        except (TypeError, ValueError):
            malformed.append(f"{release_path.name}: invalid step")
            continue
        if declared_step != filename_step:
            malformed.append(
                f"{release_path.name}: filename step {filename_step} != declared step {declared_step}"
            )
            continue
        if complete_steps and filename_step not in complete_steps:
            continue
        candidates.append((filename_step, release_path))

    if candidates:
        active_step, _active_path = max(candidates, key=lambda item: item[0])
    elif complete_steps:
        # The folder contains all current release parts but the current manifest
        # is stale/missing. Repair it without rewriting historical milestone records.
        active_step = complete_steps[-1]
        active_path = root / f"STEP{active_step}_RELEASE.json"
        payload = {
            "schema": f"biointel.step{active_step}.release.v2",
            "step": active_step,
            "version": version,
            "status": "self-repaired-current-manifest",
            "historical_release_manifests_are_non_blocking": True,
        }
        try:
            temp = active_path.with_suffix(active_path.suffix + ".tmp")
            temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temp.replace(active_path)
        except OSError as exc:
            raise RuntimeError(
                f"Current release manifest is missing/stale and could not be repaired: {exc}"
            ) from exc
    else:
        details = f" Malformed files: {' | '.join(malformed[:3])}." if malformed else ""
        raise RuntimeError(
            "No complete current release could be detected."
            f"{details} Extract all required matching ZIP parts into one new empty folder."
        )

    marker_dir = root / ".release_parts"
    if marker_dir.is_dir():
        missing = [
            part for part in sorted(_expected_parts(active_step))
            if not (marker_dir / f"step{active_step}_part{part}.ok").is_file()
        ]
        if missing:
            raise RuntimeError(
                f"Current Step {active_step} release is incomplete; missing part marker(s): {missing}. "
                "Extract all required matching ZIP parts into one new empty folder."
            )
    return version


def _normalize_root(value: str | Path) -> Path:
    raw = str(value).strip().strip('"').strip("'")
    if not raw or raw == ".":
        return Path.cwd().resolve()
    return Path(raw).expanduser().resolve()


def _free_port(start: int = 8501, stop: int = 8520) -> int:
    for port in range(start, stop + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port is available between {start} and {stop}.")


def _cleanup_stale_files(directory: Path, *, max_age_days: int = 7) -> int:
    if not directory.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def run(root: Path) -> dict[str, object]:
    root = root.resolve()
    version = _validated_release_version(root)
    if not (root / "app.py").is_file() or not (root / "src" / "biointel").is_dir():
        raise RuntimeError("Application files are incomplete. Run INSTALL_WINDOWS.bat again.")

    import streamlit  # noqa: F401
    import pandas  # noqa: F401

    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or local / "BioIntelAI" / "UserData")
    runtime_temp = Path(os.environ.get("BIOINTEL_RUNTIME_TEMP") or local / "BioIntelAI" / "Temp" / "runtime")
    for path in (
        user_data,
        user_data / "data",
        user_data / "reports",
        user_data / "workspace",
        user_data / "exports",
        user_data / "projects",
        user_data / "runtime_logs",
        runtime_temp,
    ):
        path.mkdir(parents=True, exist_ok=True)

    probe = user_data / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    free = shutil.disk_usage(user_data).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(
            f"At least 512 MB free space is required; only {free / 1024**2:.0f} MB is available."
        )

    return {
        "schema": "biointel.runtime_preflight.v2",
        "version": version,
        "python": sys.version.split()[0],
        "user_data": str(user_data),
        "free_bytes": free,
        "removed_stale_temp_files": _cleanup_stale_files(runtime_temp),
        "port": _free_port(),
        "status": "ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--port-only", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = run(_normalize_root(args.root))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["port"] if args.port_only else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
