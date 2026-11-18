from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RELEASE_RE = re.compile(r"^STEP(?P<step>\d+)_RELEASE\.json$", re.IGNORECASE)
PART_COUNT = 5
MARKER_RE = re.compile(r"^step(?P<step>\d+)_part(?P<part>[1-5])\.ok$", re.IGNORECASE)
EXPECTED_STEP = 196
EXPECTED_VERSION = "15.5.0"


def _read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.is_file():
        raise RuntimeError("VERSION file is missing.")
    version = path.read_text(encoding="utf-8-sig").strip()
    if not version:
        raise RuntimeError("VERSION file is empty.")
    return version


def _read_project_version(root: Path) -> str:
    path = root / "pyproject.toml"
    if not path.is_file():
        raise RuntimeError("pyproject.toml is missing.")
    try:
        with path.open("rb") as handle:
            version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"pyproject.toml is unreadable: {exc}") from exc
    if not version:
        raise RuntimeError("pyproject.toml does not declare project.version.")
    return version


def _marker_sets(root: Path) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    directory = root / ".release_parts"
    if not directory.is_dir():
        return result
    for path in directory.iterdir():
        match = MARKER_RE.match(path.name)
        if match and path.is_file():
            result.setdefault(int(match.group("step")), set()).add(int(match.group("part")))
    return result


def _load_release(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path.name} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object.")
    return payload


def _report_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local / "BioIntelAI" / "UserData" / "reports" / "step196-release-metadata-check.json"


def inspect_release(root: Path) -> dict[str, Any]:
    """Validate current release metadata without mutating protected package files."""
    root = root.resolve()
    version = _read_version(root)
    project_version = _read_project_version(root)
    if version != EXPECTED_VERSION or project_version != EXPECTED_VERSION:
        raise RuntimeError(
            f"Mixed current product metadata: VERSION={version!r}, pyproject={project_version!r}; "
            f"expected {EXPECTED_VERSION!r}. Extract all five matching Step 196 ZIPs into one new empty folder."
        )

    markers = _marker_sets(root)
    missing_parts = sorted(set(range(1, PART_COUNT + 1)) - markers.get(EXPECTED_STEP, set()))
    if missing_parts:
        raise RuntimeError(
            f"Step {EXPECTED_STEP} is incomplete; missing part marker(s): {missing_parts}. "
            "Extract all five matching ZIPs into one new empty folder."
        )

    active_path = root / f"STEP{EXPECTED_STEP}_RELEASE.json"
    payload = _load_release(active_path)
    declared_step = int(payload.get("step", 0) or 0)
    declared_version = str(payload.get("version", "")).strip()
    declared_part_count = int(payload.get("part_count", 0) or 0)
    if (
        declared_step != EXPECTED_STEP
        or declared_version != EXPECTED_VERSION
        or declared_part_count != PART_COUNT
    ):
        raise RuntimeError(
            f"{active_path.name} does not match the active package: "
            f"step={declared_step}, version={declared_version!r}, part_count={declared_part_count}."
        )

    historical: list[dict[str, Any]] = []
    malformed: list[str] = []
    for path in sorted(root.glob("STEP*_RELEASE.json")):
        match = RELEASE_RE.match(path.name)
        if not match or path == active_path:
            continue
        try:
            row = _load_release(path)
            historical.append(
                {
                    "file": path.name,
                    "step": int(match.group("step")),
                    "version": str(row.get("version", "")).strip(),
                    "status": "historical-non-blocking",
                }
            )
        except Exception as exc:
            malformed.append(f"{path.name}: {exc}")

    return {
        "schema": "biointel.step196.release-metadata-check.v3",
        "passed": True,
        "root": str(root),
        "version": version,
        "project_version": project_version,
        "active_step": EXPECTED_STEP,
        "active_release_file": active_path.name,
        "complete_current_markers": True,
        "historical_release_manifests": historical,
        "malformed_historical_manifests": malformed,
        "package_files_modified": False,
        "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate BioIntel AI current release metadata without changing signed package files."
    )
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--dry-run", action="store_true", help="Retained for backward compatibility; validation is always read-only.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        report = inspect_release(Path(args.root))
        report_path = _report_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
