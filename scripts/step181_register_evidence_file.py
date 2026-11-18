from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_readiness_v181 import PROFILES, sha256_file


def main(root: Path, module_key: str, evidence_id: str, filename: str) -> int:
    if module_key not in PROFILES:
        print("Unknown module key")
        return 2
    if not any(item.evidence_id == evidence_id for item in PROFILES[module_key].requirements):
        print("Unknown evidence ID for module")
        return 2
    pure = PurePosixPath(filename.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        print("Unsafe evidence filename")
        return 2
    folder = root / "UserData" / "step181" / "evidence" / module_key / evidence_id
    target = folder / pure
    manifest_path = folder / "qualification_manifest.json"
    if not target.is_file() or not manifest_path.is_file():
        print("Evidence file or qualification_manifest.json is missing")
        return 1
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    files = payload.setdefault("files", [])
    record = {"path": pure.as_posix(), "sha256": sha256_file(target)}
    files[:] = [item for item in files if str(item.get("path", "")).replace("\\", "/") != pure.as_posix()]
    files.append(record)
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--module", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.root.resolve(), args.module, args.evidence, args.file))
