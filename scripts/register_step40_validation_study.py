from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.scientific.validation_depth import SiteAttestation, ValidationEvidenceRegistry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register a hash-verified Step 40 validation study from JSON."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "reports" / "validation_evidence.sqlite3"
    )
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    registry = ValidationEvidenceRegistry(args.database)
    sites = [SiteAttestation(**item) for item in payload.get("sites", [])]
    study = registry.register_study(
        payload=payload["study"],
        sites=sites,
        outcomes=payload.get("outcomes", []),
        metrics=payload.get("metrics", []),
        reviews=payload.get("reviews", []),
        metadata=payload.get("metadata", {}),
    )
    print(
        json.dumps(
            {
                "study": study.__dict__,
                "summary": registry.summary(),
                "integrity": registry.verify_integrity(),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
