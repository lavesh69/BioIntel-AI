from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from step206_contract import (
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_NAME,
    RELEASE_STEP,
    active_record_path,
    user_data_directory,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET_VALUE = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)(\s*[:=]\s*)([^\s,;]+)")
BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")


def redact(text: str) -> str:
    home = str(Path.home())
    local = os.environ.get("LOCALAPPDATA", "")
    value = text.replace(home, "%USERPROFILE%") if home else text
    if local:
        value = value.replace(local, "%LOCALAPPDATA%")
    value = SECRET_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)
    return BEARER.sub("Bearer <redacted>", value)


def safe_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def add_text(archive: zipfile.ZipFile, arcname: str, text: str) -> None:
    archive.writestr(arcname, redact(text)[-250_000:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    user_data = user_data_directory()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(args.output).resolve() if args.output else user_data / "reports" / f"BioIntel-Step{RELEASE_STEP}-Support-Bundle-{stamp}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "schema": f"biointel.step{RELEASE_STEP}.sanitized-support-bundle.v2",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "release_step": RELEASE_STEP,
        "release_version": PRODUCT_VERSION,
        "platform": platform.platform(),
        "python": sys.version,
        "python_bits": 64 if sys.maxsize > 2**32 else 32,
        "root": str(root),
        "active_install": safe_json(active_record_path()),
        "part_markers": {
            f"step{RELEASE_STEP}_part{part}": (
                root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok"
            ).is_file()
            for part in range(1, PART_COUNT + 1)
        },
        "privacy": "No project datasets, uploaded biomedical files, evidence packages, workspace files, or database contents are included.",
    }

    metadata = [
        root / RELEASE_NAME,
        root / "VERSION",
        root / "CURRENT_RELEASE.md",
        user_data / "reports" / f"step{RELEASE_STEP}-install.json",
        user_data / "reports" / f"step{RELEASE_STEP}-install-run-verification.json",
        user_data / "reports" / f"step{RELEASE_STEP}-native-startup-smoke.json",
        user_data / "reports" / f"step{RELEASE_STEP}-streamlit-startup-check.json",
        user_data / "reports" / f"step{RELEASE_STEP}-release-gate.json",
        user_data / "runtime_logs" / "biointel-runtime-status.json",
        user_data / "runtime_logs" / "biointel-running.json",
        user_data / "runtime_logs" / f"step{RELEASE_STEP}-runtime-preflight.json",
    ]
    logs = sorted(
        (path for path in (user_data / "runtime_logs").glob(f"*step{RELEASE_STEP}*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:12]
    logs += sorted(
        (path for path in (user_data / "runtime_logs").glob("biointel-*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:12]

    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        add_text(archive, "support_snapshot.json", json.dumps(snapshot, indent=2) + "\n")
        for path in metadata + logs:
            if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            prefix = "application" if root in path.parents else "local-runtime"
            add_text(archive, f"{prefix}/{path.name}", content)
    os.replace(temporary, output)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Support bundle CRC failed: {bad}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
