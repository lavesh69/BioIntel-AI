from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.authenticity_v162 import (  # noqa: E402
    build_legacy_model_authenticity_registry,
    build_provider_contracts,
    build_public_benchmark_suite,
    portfolio_authenticity_matrix,
    portfolio_authenticity_summary,
    verify_public_benchmark_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step 162 authentic-model and source assets.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    benchmarks = build_public_benchmark_suite(root)
    legacy = build_legacy_model_authenticity_registry(root)
    providers = build_provider_contracts(root)
    verification = verify_public_benchmark_suite(root)
    matrix = portfolio_authenticity_matrix(root)
    summary = portfolio_authenticity_summary(matrix)

    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    verification.to_csv(report_dir / "step162_public_benchmark_verification.csv", index=False)
    matrix.to_csv(report_dir / "step162_module_authenticity_matrix.csv", index=False)
    payload = {
        "schema": "biointel.step162.authenticity-assets.v1",
        "public_benchmark_models_built": len(benchmarks),
        "public_benchmark_models_verified": int(verification["passed"].astype(bool).sum()),
        "legacy_models_audited": len(legacy),
        "synthetic_models_quarantined": int(legacy["synthetic_demo"].astype(bool).sum()) if not legacy.empty else 0,
        "provider_source_contracts": len(providers),
        "provider_source_descriptors_verified": int(providers["source_descriptor_verified"].astype(bool).sum()),
        "provider_local_snapshots_verified": int(providers["local_snapshot_checksum_verified"].astype(bool).sum()),
        "module_authenticity": summary,
        "domain_models_release_eligible": 0,
        "external_claims_not_inferred": True,
    }
    (report_dir / "step162_authenticity_assets.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["public_benchmark_models_verified"] == len(benchmarks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
