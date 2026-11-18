from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.engine_platform_v196.acquisition import build_acquisition_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare BioIntel V19.6 full-engine acquisition and target-qualification bundle.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or (args.root / "engine-packs" / "v19.6-acquisition")
    payload = build_acquisition_bundle(output, root=args.root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["registered_engines"] == 76 else 1


if __name__ == "__main__":
    raise SystemExit(main())
