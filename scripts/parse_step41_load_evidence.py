from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize k6/Locust output into Step 41 high-load evidence metrics."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/step41/load_evidence.json"))
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    metrics = raw.get("metrics", raw)
    normalized = {
        "schema": "biointel.step41.load-evidence.v1",
        "total_requests": int(
            metrics.get("http_reqs", {})
            .get("values", {})
            .get("count", metrics.get("total_requests", 0))
        ),
        "error_rate_percent": float(
            metrics.get("http_req_failed", {})
            .get("values", {})
            .get("rate", metrics.get("error_rate_percent", 0))
        )
        * (100 if "http_req_failed" in metrics else 1),
        "p95_latency_ms": float(
            metrics.get("http_req_duration", {})
            .get("values", {})
            .get("p(95)", metrics.get("p95_latency_ms", 0))
        ),
        "source": str(args.input),
        "classification": "measured_output_requires_external_attestation_for_10_of_10_evidence",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(normalized, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
