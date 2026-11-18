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

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)")


def safe_environment() -> dict[str, str]:
    allowed = {
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PYTHONUTF8",
        "BIOINTEL_THREADS",
        "BIOINTEL_OPTIMIZED_RUNTIME",
    }
    return {key: value for key, value in os.environ.items() if key in allowed and not SECRET_NAME.search(key)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output) if args.output else root / "reports" / "step192" / "BioIntel-Step192-Support-Bundle.zip"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "schema": "biointel.step192.support-snapshot.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "cwd": str(root),
        "safe_environment": safe_environment(),
        "part_markers": {f"step192_part{i}": (root / ".release_parts" / f"step192_part{i}.ok").is_file() for i in range(1, 5)},
        "venv_python_present": (root / ".venv" / "Scripts" / "python.exe").is_file(),
    }

    candidates = [
        root / "STEP192_RELEASE.json",
        root / "STEP192_UPGRADE_SUMMARY.json",
        root / "STEP192_PACKAGE_PART_ASSIGNMENT.json",
        root / "reports" / "step192" / "wheelhouse_verification.json",
        root / "reports" / "step192" / "STEP192_RELEASE_AUDIT.json",
        root / "reports" / "step192" / "extracted_release_validation.json",
        root / "reports" / "step192" / "post_install_self_test.json",
        root / "reports" / "step145_runtime_preflight.json",
    ]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("support_snapshot.json", json.dumps(snapshot, indent=2) + "\n")
        for path in candidates:
            if path.is_file() and path.stat().st_size <= 10 * 1024 * 1024:
                archive.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"Support bundle is corrupt: {corrupt}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
