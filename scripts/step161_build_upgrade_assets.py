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

from biointel.readiness_v161 import (  # noqa: E402
    development_reference_readiness,
    development_reference_summary,
    ensure_development_reference_kits,
    ensure_validation_protocols,
    portfolio_upgrade_matrix,
    portfolio_upgrade_summary,
    runtime_catalog_summary,
    runtime_recipe_catalog,
    validation_protocol_readiness,
    validation_protocol_summary,
)
from biointel.scientific_depth.profiles import MODULE_PROFILES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step 161 module upgrade assets.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    reference_paths = ensure_development_reference_kits(root)
    protocol_paths = ensure_validation_protocols(root)
    recipes = runtime_recipe_catalog()
    references = development_reference_readiness(root)
    protocols = validation_protocol_readiness(root)
    matrix = portfolio_upgrade_matrix(root, detect_runtime=False)

    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    recipes.to_csv(report_dir / "step161_runtime_recipe_catalog.csv", index=False)
    references.to_csv(report_dir / "step161_development_reference_matrix.csv", index=False)
    protocols.to_csv(report_dir / "step161_validation_protocol_matrix.csv", index=False)
    matrix.to_csv(report_dir / "step161_module_upgrade_matrix.csv", index=False)

    summary = {
        "schema": "biointel.step161.upgrade-assets.v1",
        "modules": len(MODULE_PROFILES),
        "reference_files_written": len(reference_paths),
        "validation_protocols_written": len(protocol_paths),
        "runtime_recipes": runtime_catalog_summary(recipes),
        "development_references": development_reference_summary(references),
        "validation_protocols": validation_protocol_summary(protocols),
        "module_upgrades": portfolio_upgrade_summary(matrix),
        "external_release_not_inferred": True,
    }
    (report_dir / "step161_upgrade_assets.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["module_upgrades"]["step161_10_of_10"] == len(MODULE_PROFILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
