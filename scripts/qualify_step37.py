from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi.testclient import TestClient

from biointel import __version__
from biointel.api.main import app
from biointel.engineering import build_engineering_readiness, run_engineering_gates
from biointel.intelligence.data_intelligence import all_database_health
from biointel.quality.capability_readiness import build_target_capability_readiness
from biointel.quality.scorecard import build_quality_scorecard

ROOT = Path(__file__).resolve().parents[1]


def _junit_summary(directory: Path) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in sorted(directory.glob("*.xml")):
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        for suite in suites:
            for key in totals:
                totals[key] += int(float(suite.attrib.get(key, 0)))
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return totals


def _semantic_manifest() -> dict[str, object]:
    root = ROOT / "visual" / "semantic_baselines"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    mismatches: list[str] = []
    for name, item in manifest["scenarios"].items():
        for suffix, field in (("json", "json_sha256"), ("png", "png_sha256")):
            path = root / f"{name}.{suffix}"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item[field]:
                mismatches.append(f"{name}.{suffix}")
    return {
        "scenarios": len(manifest["scenarios"]),
        "valid": not mismatches,
        "mismatches": mismatches,
    }


def _api_smoke() -> dict[str, object]:
    client = TestClient(app)
    routes = [
        "/live",
        "/ready",
        "/quality/scorecard",
        "/quality/capability-readiness",
        "/quality/engineering-readiness",
        "/quality/engineering-gates",
    ]
    statuses = {route: client.get(route).status_code for route in routes}
    return {"passed": all(value == 200 for value in statuses.values()), "statuses": statuses}


def main() -> int:
    engineering = build_engineering_readiness(ROOT)
    capability = build_target_capability_readiness(ROOT)
    gates = run_engineering_gates(ROOT)
    database = all_database_health(ROOT)
    quality = build_quality_scorecard(ROOT)
    tests = _junit_summary(ROOT / "reports" / "step37")
    coverage_path = ROOT / "reports" / "step37" / "coverage.json"
    coverage = (
        json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {}
    )
    semantic = _semantic_manifest()
    api = _api_smoke()
    report = {
        "schema": "biointel.step37-qualification.v1",
        "step": 37,
        "version": __version__,
        "engineering": engineering,
        "unified_capability": {
            "implementation_average": capability["implementation_average"],
            "complete": capability["all_implementation_targets_complete"],
            "capability_count": len(capability["capabilities"]),
            "engineering_control_count": capability["engineering_control_count"],
        },
        "gates": gates,
        "tests": tests,
        "coverage_percent": round(float(coverage.get("totals", {}).get("percent_covered", 0.0)), 2),
        "semantic_visual": semantic,
        "api_smoke": api,
        "databases": {
            "count": database["database_count"],
            "healthy": database["healthy_count"],
            "health_percent": database["health_percent"],
        },
        "evidence_based_platform_score": quality["overall_score"],
        "browser_execution_boundary": (
            "Playwright cross-browser and screenshot CI is implemented. This managed local runtime blocks Chromium navigation "
            "to localhost by administrator policy, so browser journeys remain CI-qualified rather than locally certified."
        ),
    }
    report["passed"] = all(
        [
            engineering["all_targets_complete"],
            capability["all_implementation_targets_complete"],
            gates["passed"],
            tests["failures"] == 0,
            tests["errors"] == 0,
            report["coverage_percent"] >= 85.0,
            semantic["valid"],
            api["passed"],
            database["healthy_count"] == database["database_count"],
        ]
    )
    output = ROOT / "reports" / "step37_qualification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
