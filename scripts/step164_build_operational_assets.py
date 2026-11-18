from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.operational_v164 import ensure_step164_assets, operational_matrix, provisioning_catalog, runtime_inventory  # noqa: E402
from biointel.scientific_depth import MODULE_PROFILES  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step 164 operational qualification assets.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--probe-runtime", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    written = ensure_step164_assets(root)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    catalog = provisioning_catalog()
    catalog.to_csv(reports / "step164_engine_provisioning_catalog.csv", index=False)
    inventory = runtime_inventory() if args.probe_runtime else catalog.copy()
    if not args.probe_runtime:
        inventory["installed"] = False
        inventory["detected_path"] = "Not probed during asset build"
        inventory["detected_version"] = "Not probed during asset build"
    inventory.to_csv(reports / "step164_runtime_inventory.csv", index=False)
    matrix = operational_matrix(root, detect_runtime=args.probe_runtime)
    matrix.to_csv(reports / "step164_operational_readiness_matrix.csv", index=False)

    manifest_rows = []
    for path in sorted(written):
        manifest_rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": _sha256(path)})
    manifest = {
        "schema": "biointel.step164.asset-manifest.v1",
        "modules": len(MODULE_PROFILES),
        "engines": int(len(catalog)),
        "generated_assets": len(written),
        "files": manifest_rows,
    }
    (reports / "step164_asset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "schema": "biointel.step164.operational-summary.v1",
        "modules": int(len(matrix)),
        "software_owned_10of10": int((matrix["software_owned_score"] == 10.0).sum()),
        "engine_recipes_complete": int(catalog["software_recipe_complete"].astype(bool).sum()),
        "engine_recipes_total": int(len(catalog)),
        "runtime_probe_performed": bool(args.probe_runtime),
        "engines_installed": int(inventory["installed"].astype(bool).sum()) if "installed" in inventory else 0,
        "production_references_qualified": int(matrix["production_references_qualified"].sum()),
        "real_world_release_eligible": int(matrix["real_world_release_eligible"].astype(bool).sum()),
        "external_evidence_not_inferred": True,
    }
    (reports / "step164_operational_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
