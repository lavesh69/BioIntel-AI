from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_readiness_v181 import import_bundle


def main(root: Path, bundle: Path, module_key: str, evidence_id: str) -> int:
    result = import_bundle(root, bundle, module_key, evidence_id)
    print(f"IMPORTED={result.imported}")
    print(f"DESTINATION={result.destination}")
    for blocker in result.blockers:
        print(f"BLOCKER={blocker}")
    return 0 if result.imported else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.root.resolve(), args.bundle.resolve(), args.module, args.evidence))
