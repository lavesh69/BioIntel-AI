from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.coverage_packs import (  # noqa: E402
    register_coverage_datasets,
    seed_demo_workspace,
    verify_coverage_integrity,
    write_coverage_packs,
)


def main() -> None:
    assets = write_coverage_packs(ROOT)
    registered = register_coverage_datasets(ROOT)
    workspace = seed_demo_workspace(ROOT)
    integrity = verify_coverage_integrity(ROOT)
    print(
        json.dumps(
            {
                "assets": len(assets),
                "registered_datasets": len(registered),
                "workspace": workspace,
                "integrity": integrity,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
