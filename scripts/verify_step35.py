from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.relationship_integrity import relationship_summary
from biointel.intelligence.data_intelligence import all_database_health
from biointel.quality.scorecard import build_quality_scorecard
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG


def main() -> None:
    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    health = all_database_health(ROOT)
    relationships = relationship_summary(ROOT)
    quality = build_quality_scorecard(ROOT)
    checks = {
        "version": __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "compile": compile_result.returncode == 0,
        "quality_page": PAGE_BY_KEY.get("platform_quality") is not None,
        "page_catalog": len(PAGE_CATALOG) >= 78,
        "database_health": health.get("healthy_count") == health.get("database_count"),
        "relationship_integrity": relationships.get("broken_edges", 0) == 0,
        "quality_diagnostics": bool(quality.get("dimensions")),
        "model_policy_truthful": quality["model_audit"]["release_eligible_models"] == 0,
    }
    payload = {
        "passed": all(checks.values()),
        "checks": checks,
        "database_health": {
            "healthy": health.get("healthy_count"),
            "total": health.get("database_count"),
        },
        "relationships": {
            "broken_edges": relationships.get("broken_edges", 0),
            "orphan_findings": relationships.get("orphan_findings", 0),
        },
        "quality": {
            "overall_score": quality["overall_score"],
            "group_scores": quality["group_scores"],
            "critical_blockers": [item for item in quality["blockers"] if item["score"] < 5.0],
        },
        "compile_stderr": compile_result.stderr,
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
