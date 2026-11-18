from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "EDUCATION_PHASE10_SOURCE_MANIFEST_SHA256.json"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    if not MANIFEST.is_file():
        print("ERROR: Phase 10 source manifest is missing.")
        return 1
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in payload.get("files", []):
        relative = str(item["path"])
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        if path.stat().st_size != int(item["size"]):
            failures.append(f"size:{relative}")
            continue
        if digest(path) != str(item["sha256"]):
            failures.append(f"sha256:{relative}")
    print(json.dumps({
        "release": payload.get("release"),
        "verified": int(payload.get("file_count", 0)) - len(failures),
        "expected": int(payload.get("file_count", 0)),
        "failed": failures[:50],
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
