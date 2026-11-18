from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def normalize_root(value: str | Path) -> Path:
    raw = str(value).strip().strip('\"').strip("'")
    if not raw or raw == ".":
        return Path.cwd().resolve()
    return Path(raw).expanduser().resolve()


def verify_lock(root: Path) -> dict[str, object]:
    root = normalize_root(root)
    lock = root / "requirements.lock"
    checksum = root / "requirements.lock.sha256"
    if not lock.is_file() or not checksum.is_file():
        return {
            "valid": False,
            "root": str(root),
            "missing": [str(p.name) for p in (lock, checksum) if not p.is_file()],
            "packages": 0,
            "invalid": [],
        }
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    expected = checksum.read_text(encoding="utf-8").split()[0].lower()
    rows = [
        row.strip()
        for row in lock.read_text(encoding="utf-8").splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    ]
    invalid = [row for row in rows if "==" not in row]
    return {
        "valid": digest == expected and not invalid,
        "root": str(root),
        "sha256": digest,
        "expected_sha256": expected,
        "packages": len(rows),
        "invalid": invalid,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = verify_lock(normalize_root(args.root))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)
