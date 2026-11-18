from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.engine_platform_v196.packs import build_pack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--engines-json", type=Path, required=True)
    parser.add_argument("--licences-json", type=Path)
    args = parser.parse_args()
    engines = json.loads(args.engines_json.read_text(encoding="utf-8"))
    licences = json.loads(args.licences_json.read_text(encoding="utf-8")) if args.licences_json else []
    path = build_pack(args.source, args.destination, pack_id=args.pack_id, pack_version=args.pack_version, platform=args.platform, engines=engines, licence_records=licences)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
