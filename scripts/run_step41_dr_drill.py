from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local disaster-recovery restore rehearsal and emit measured evidence."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/step41/dr_drill.json"))
    args = parser.parse_args()
    source = args.database.resolve()
    if not source.is_file():
        raise SystemExit(f"Database not found: {source}")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="biointel-dr-") as folder:
        restored = Path(folder) / source.name
        shutil.copy2(source, restored)
        db = sqlite3.connect(restored)
        try:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            db.close()
        source_sha = digest(source)
        restored_sha = digest(restored)
    elapsed = time.perf_counter() - started
    payload = {
        "schema": "biointel.step41.dr-drill.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "source": str(source),
        "source_sha256": source_sha,
        "restored_sha256": restored_sha,
        "restore_checksum_match": source_sha == restored_sha,
        "sqlite_integrity": integrity,
        "rto_minutes": elapsed / 60.0,
        "rpo_minutes": 0.0,
        "classification": "local_rehearsal_not_external_operating_history",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["restore_checksum_match"] and integrity == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
