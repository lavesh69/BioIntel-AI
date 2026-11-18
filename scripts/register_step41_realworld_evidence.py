from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.realworld import (  # noqa: E402
    OperationalArtifact,
    OperationalAttestation,
    RealWorldEvidenceRegistry,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register authentic Step 41 external operating evidence from JSON."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "reports" / "realworld_evidence.sqlite3"
    )
    args = parser.parse_args()
    raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    registry = RealWorldEvidenceRegistry(args.database)
    record = registry.register_evidence(
        payload=dict(raw["study"]),
        artifacts=[OperationalArtifact(**item) for item in raw.get("artifacts", [])],
        metrics=[dict(item) for item in raw.get("metrics", [])],
        attestations=[OperationalAttestation(**item) for item in raw.get("attestations", [])],
        entities=[dict(item) for item in raw.get("entities", [])],
    )
    print(
        json.dumps(
            {
                "record": record.__dict__,
                "summary": registry.summary(),
                "integrity": registry.verify_integrity(),
            },
            indent=2,
            default=list,
        )
    )
    return 0 if record.release_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
