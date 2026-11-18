from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import verify_data_pack_integrity  # noqa: E402
from biointel.training.model_artifact import (  # noqa: E402
    clear_model_artifact_cache,
    load_model_artifact,
    load_model_artifact_cached,
)
from biointel.utils.integrity_cache import clear_integrity_cache  # noqa: E402
from biointel.utils.runtime_cache import (  # noqa: E402
    clear_runtime_caches,
    read_csv_cached,
)


def timed(function):
    started = time.perf_counter()
    value = function()
    return value, time.perf_counter() - started


def main() -> None:
    data_path = ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv"
    model_path = ROOT / "models" / "packv5_5x_classification_extra_trees.joblib"

    clear_integrity_cache(ROOT, cache_name=".data_pack_integrity_cache.json")
    _, integrity_cold = timed(lambda: verify_data_pack_integrity(ROOT))
    integrity_result, integrity_warm = timed(lambda: verify_data_pack_integrity(ROOT))

    clear_model_artifact_cache()
    _, model_uncached = timed(lambda: load_model_artifact(model_path, trusted_root=ROOT / "models"))
    clear_model_artifact_cache()
    _, model_cache_fill = timed(
        lambda: load_model_artifact_cached(model_path, trusted_root=ROOT / "models")
    )
    _, model_cached = timed(
        lambda: load_model_artifact_cached(model_path, trusted_root=ROOT / "models")
    )

    clear_runtime_caches()
    full, full_csv_seconds = timed(lambda: pd.read_csv(data_path, low_memory=False))
    preview, preview_seconds = timed(lambda: read_csv_cached(data_path, nrows=100))

    report = {
        "benchmark_version": "1.0",
        "integrity": {
            "cold_seconds": round(integrity_cold, 6),
            "warm_seconds": round(integrity_warm, 6),
            "speedup": round(integrity_cold / max(integrity_warm, 1e-9), 2),
            "reused_hashes": integrity_result["reused_hashes"],
        },
        "model_loading": {
            "uncached_seconds": round(model_uncached, 6),
            "cache_fill_seconds": round(model_cache_fill, 6),
            "cached_seconds": round(model_cached, 6),
            "warm_speedup": round(model_uncached / max(model_cached, 1e-9), 2),
        },
        "five_x_page": {
            "full_rows": len(full),
            "preview_rows": len(preview),
            "full_csv_seconds": round(full_csv_seconds, 6),
            "preview_seconds": round(preview_seconds, 6),
            "full_dataframe_mb": round(full.memory_usage(deep=True).sum() / (1024 * 1024), 2),
            "preview_dataframe_mb": round(preview.memory_usage(deep=True).sum() / (1024 * 1024), 4),
        },
    }
    output = ROOT / "reports" / "generated" / "step20_optimization_benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
