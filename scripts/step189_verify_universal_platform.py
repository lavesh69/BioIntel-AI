from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.universal_platform_v189 import PLATFORM_DIMENSIONS, TARGET_MODULES, rating_matrix, validate_module
from biointel.universal_platform_v189.platform import connect
from biointel.universal_platform_v189.generator import shared_db

def main() -> int:
    frame = rating_matrix(ROOT)
    bad = {key: list(validate_module(ROOT, key).blockers) for key in TARGET_MODULES if not validate_module(ROOT, key).qualified_10_of_10}
    db = shared_db(ROOT)
    with connect(db) as conn:
        table_counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in (
            "projects", "samples", "assets", "engines", "references_registry", "jobs", "handoffs",
            "provenance", "reviews", "metrics", "errors",
        )}
    result = {
        "schema": "biointel.step189.verification.v1",
        "status": "passed" if not bad and len(frame) == 80 and frame.qualified_10_of_10.all() else "failed",
        "modules": len(frame), "qualified": int(frame.qualified_10_of_10.sum()),
        "dimensions_passed": int(frame.dimensions_passed.sum()),
        "dimensions_total": int(frame.dimensions_total.sum()),
        "platform_dimensions_per_module": len(PLATFORM_DIMENSIONS),
        "table_counts": table_counts, "blockers": bad, "controlled_release_eligible": False,
    }
    (ROOT / "STEP189_VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
