from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

RELEASE_RE = re.compile(r"^STEP(?P<step>\d+)_RELEASE\.json$", re.IGNORECASE)
MARKER_RE = re.compile(r"^step(?P<step>\d+)_part(?P<part>[1-4])\.ok$", re.IGNORECASE)


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


def _release_files(root: Path) -> list[tuple[int, Path, dict[str, object] | None, str | None]]:
    rows: list[tuple[int, Path, dict[str, object] | None, str | None]] = []
    for path in sorted(root.glob("STEP*_RELEASE.json")):
        match = RELEASE_RE.match(path.name)
        if not match:
            continue
        step = int(match.group("step"))
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError("top-level JSON is not an object")
            rows.append((step, path, payload, None))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            rows.append((step, path, None, str(exc)))
    return rows


def _backup(path: Path, backup_dir: Path) -> str | None:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / path.name
    shutil.copy2(path, destination)
    return str(destination)


def repair(root: Path, *, dry_run: bool = False) -> dict[str, object]:
    root = root.resolve()
    version = _read_version(root)
    project_version = _read_project_version(root)
    if project_version != version:
        raise RuntimeError(
            f"Mixed current product metadata: VERSION={version!r}, "
            f"pyproject.toml version={project_version!r}. "
            "Extract four matching release ZIPs into one empty folder."
        )

    marker_sets = _marker_sets(root)
    complete_steps = sorted(step for step, parts in marker_sets.items() if parts == {1, 2, 3, 4})
    preferred_step = 194 if marker_sets.get(194) == {1, 2, 3, 4} else (complete_steps[-1] if complete_steps else 194)

    releases = _release_files(root)
    ignored_historical: list[dict[str, object]] = []
    matching: list[int] = []
    malformed: list[str] = []
    for step, path, payload, error in releases:
        if error:
            malformed.append(f"{path.name}: {error}")
            continue
        assert payload is not None
        declared_version = str(payload.get("version", "")).strip()
        if declared_version == version:
            matching.append(step)
        else:
            ignored_historical.append(
                {"file": path.name, "step": step, "version": declared_version, "reason": "historical-version"}
            )

    active_step = max(matching) if matching else preferred_step
    if marker_sets and marker_sets.get(active_step, set()) != {1, 2, 3, 4}:
        if complete_steps:
            active_step = complete_steps[-1]
        else:
            missing = sorted({1, 2, 3, 4} - marker_sets.get(active_step, set()))
            raise RuntimeError(
                f"Current release Step {active_step} is incomplete; missing part marker(s): {missing}. "
                "Extract all four matching ZIP parts into one empty folder."
            )

    active_path = root / f"STEP{active_step}_RELEASE.json"
    active_payload = {
        "schema": f"biointel.step{active_step}.release.v2",
        "step": active_step,
        "version": version,
        "status": "verified-internal",
        "historical_release_manifests_are_non_blocking": True,
        "current_release_detection": "VERSION + pyproject + complete release markers",
        "repaired_at": datetime.now(timezone.utc).isoformat(),
    }

    backup_dir = root / ".hotfix_backups" / f"step194-release-{time.strftime('%Y%m%d-%H%M%S')}"
    backup = None
    changed = True
    if active_path.is_file():
        try:
            existing = json.loads(active_path.read_text(encoding="utf-8-sig"))
            changed = not (
                isinstance(existing, dict)
                and int(existing.get("step", active_step)) == active_step
                and str(existing.get("version", "")).strip() == version
                and bool(existing.get("historical_release_manifests_are_non_blocking", False))
            )
        except Exception:
            changed = True
    if changed and not dry_run:
        backup = _backup(active_path, backup_dir)
        temp = active_path.with_suffix(active_path.suffix + ".tmp")
        temp.write_text(json.dumps(active_payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(active_path)

    report = {
        "schema": "biointel.step194.release-metadata-repair.v2",
        "passed": True,
        "root": str(root),
        "version": version,
        "project_version": project_version,
        "active_step": active_step,
        "active_release_file": active_path.name,
        "complete_marker_steps": complete_steps,
        "ignored_historical_manifests": ignored_historical,
        "malformed_release_manifests": malformed,
        "changed": changed and not dry_run,
        "backup": backup,
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        report_path = root / "reports" / "step194_release_metadata_repair.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair BioIntel AI current release metadata safely.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        report = repair(Path(args.root), dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
