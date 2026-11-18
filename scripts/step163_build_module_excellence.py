from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.excellence_v163 import ensure_step163_assets, module_excellence_matrix, module_excellence_summary  # noqa: E402
from biointel.readiness_v161 import runtime_recipe_catalog  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step 163 all-module excellence assets.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    written = ensure_step163_assets(root)

    runtime_dir = root / "data" / "step163" / "specialist_runtime_lock_contracts"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime = runtime_recipe_catalog()
    runtime_paths = []
    for row in runtime.to_dict(orient="records"):
        engine = str(row["engine"])
        payload = {
            "schema": "biointel.step163.specialist-runtime-lock-contract.v1",
            "engine": engine,
            "label": row["label"],
            "category": row["category"],
            "modules": [value.strip() for value in str(row["modules"]).split(",") if value.strip()],
            "execution_backends": [value.strip() for value in str(row["execution_backends"]).split(",") if value.strip()],
            "install_strategy": row["install_strategy"],
            "package_hint": row["package_hint"],
            "licence_class": row["licence_class"],
            "manual_action_required": bool(row["manual_action_required"]),
            "model_or_database_required": bool(row["model_or_database_required"]),
            "checksum_required": True,
            "version_probe_required": True,
            "environment_lock_required": True,
            "container_digest_or_binary_hash_required": True,
            "runtime_self_test_required": True,
            "scientific_smoke_test_required": True,
            "bundled_in_core_package": False,
            "installed_and_qualified": False,
        }
        path = runtime_dir / f"{engine}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        runtime_paths.append(path)

    matrix = module_excellence_matrix(root)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    matrix_path = reports / "step163_module_excellence_matrix.csv"
    matrix.to_csv(matrix_path, index=False)
    summary = module_excellence_summary(matrix)
    summary.update(
        {
            "module_asset_files": len(written),
            "specialist_runtime_lock_contracts": len(runtime_paths),
            "all_module_asset_files_checksum_bound": True,
        }
    )
    summary_path = reports / "step163_module_excellence_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    all_paths = sorted(written + runtime_paths + [matrix_path, summary_path])
    manifest = {
        "schema": "biointel.step163.asset-manifest.v1",
        "files": [
            {"path": str(path.relative_to(root)).replace("\\", "/"), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in all_paths
        ],
    }
    manifest["file_count"] = len(manifest["files"])
    manifest_path = reports / "step163_asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "asset_manifest_files": manifest["file_count"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
