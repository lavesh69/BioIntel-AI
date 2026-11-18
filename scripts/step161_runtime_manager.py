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

from biointel.readiness_v161 import runtime_detection_matrix, runtime_recipe_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Step 161 specialist runtime provisioning.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--fail-if-recipes-missing", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    engines = args.engine or None
    recipes = runtime_recipe_catalog(engines)
    detected = runtime_detection_matrix(engines)
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    recipes.to_csv(report_dir / "step161_runtime_recipes.csv", index=False)
    detected.to_csv(report_dir / "step161_runtime_detection.csv", index=False)
    payload = {
        "schema": "biointel.step161.runtime-manager.v1",
        "engines": int(len(recipes)),
        "complete_recipes": int(recipes["recipe_complete"].astype(bool).sum()),
        "installed": int(detected["installed"].astype(bool).sum()),
        "manual_action_required": int(recipes["manual_action_required"].astype(bool).sum()),
        "all_provisioning_paths_ready": bool(not recipes.empty and recipes["recipe_complete"].astype(bool).all()),
        "installed_status_is_environment_specific": True,
        "no_automatic_acceptance_of_external_licences": True,
    }
    (report_dir / "step161_runtime_manager.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.fail_if_recipes_missing and not payload["all_provisioning_paths_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
