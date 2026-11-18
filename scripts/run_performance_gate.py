from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def evaluate_performance(metrics: dict, threshold: dict) -> dict:
    checks = {
        "p95": float(metrics["p95_ms"]) <= float(threshold["p95_ms"]),
        "errors": float(metrics["error_rate"]) <= float(threshold["error_rate"]),
        "requests": int(metrics.get("requests", 0)) >= int(threshold.get("minimum_requests", 0)),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "threshold": threshold,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", required=True)
    p.add_argument("--profile", default="load")
    a = p.parse_args()
    policy = yaml.safe_load(Path("config/performance_thresholds.yaml").read_text())
    metrics = json.loads(Path(a.metrics).read_text())
    result = evaluate_performance(metrics, policy[a.profile])
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
