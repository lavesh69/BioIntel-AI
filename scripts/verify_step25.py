from __future__ import annotations

import argparse
import compileall
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.curation import normalize_activity_value
from biointel.data.evidence_registry import registry_summary
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--core-only", action="store_true", help="Skip optional runtime dependency diagnostics."
    )
    args = parser.parse_args()
    assert __version__ == "3.3.0"
    assert len(PAGE_CATALOG) >= 71, len(PAGE_CATALOG)
    less = normalize_activity_value(100, "nM", "<")
    greater = normalize_activity_value(100, "nM", ">")
    assert less.p_activity_lower_bound is not None and less.p_activity_upper_bound is None
    assert greater.p_activity_upper_bound is not None and greater.p_activity_lower_bound is None
    assert compileall.compile_dir(SRC, quiet=1)
    models = sorted((ROOT / "models").glob("*.joblib"))
    loaded = []
    for model in models:
        artifact = load_model_artifact(model, trusted_root=ROOT / "models")
        loaded.append({"name": model.name, "task": artifact.metadata.task_type})
    databases = all_database_health(ROOT)
    assert databases["database_count"] >= 13
    assert databases["healthy_count"] == databases["database_count"]
    evidence = registry_summary(ROOT / "reports" / "evidence.sqlite3")
    assert evidence["counts"]["evidence_licenses"] >= 5
    if args.core_only:
        diagnostics = {"PASS": 0, "WARN": 1, "FAIL": 0, "total": 0, "overall": "CORE_ONLY"}
    else:
        checks = run_diagnostics(ROOT)
        diagnostics = diagnostic_summary(checks)
    payload = {
        "version": __version__,
        "page_catalog": len(PAGE_CATALOG),
        "models_loaded": len(loaded),
        "databases": databases,
        "evidence": evidence,
        "diagnostics": diagnostics,
        "censored_activity_direction": "verified",
        "models": loaded,
    }
    output = ROOT / "reports" / "generated" / "step25_release_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if diagnostics["FAIL"]:
        raise SystemExit(f"Diagnostics reported {diagnostics['FAIL']} failure(s).")


if __name__ == "__main__":
    main()
