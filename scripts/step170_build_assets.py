from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.runtime_v170 import engine_catalog, engine_manifest, licence_catalog, provisioning_commands, reference_catalog, reference_manifest


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    data = root / "data" / "step170"
    reports = root / "reports"
    reports.mkdir(exist_ok=True)

    engines = engine_catalog()
    references = reference_catalog()
    licences = licence_catalog()
    plan = provisioning_commands(root)

    for row in engines.to_dict(orient="records"):
        _write_json(data / "engine_manifests" / f"{row['engine']}.json", engine_manifest(str(row["engine"])))
    for row in references.to_dict(orient="records"):
        _write_json(data / "reference_catalog" / f"{row['reference_id']}.json", reference_manifest(str(row["reference_id"])))
    for row in licences.to_dict(orient="records"):
        _write_json(data / "license_catalog" / f"{row['licence_id']}.json", {"schema": "biointel.step170.licence-policy.v1", **row})
    _write_json(data / "environment" / "step170-provisioning-plan.json", plan)

    environment_lines = [
        "name: biointel-step170",
        "channels:",
        "  - conda-forge",
        "  - bioconda",
        "dependencies:",
        "  - python=3.11",
    ]
    environment_lines.extend(f"  - {pkg}" for pkg in plan["conda_packages"])
    if plan["pip_packages"]:
        environment_lines.append("  - pip")
        environment_lines.append("  - pip:")
        environment_lines.extend(f"      - {pkg}" for pkg in plan["pip_packages"])
    (data / "environment" / "step170-linux-64.yml").write_text("\n".join(environment_lines) + "\n", encoding="utf-8")
    tsv_lines = ["engine\tconda_packages\tpip_packages\tmanual_distribution"]
    for row in engines.to_dict(orient="records"):
        tsv_lines.append("\t".join([
            str(row["engine"]),
            str(row.get("conda_packages") or "").replace("\t", " "),
            str(row.get("pip_packages") or "").replace("\t", " "),
            "1" if bool(row.get("manual_distribution")) else "0",
        ]))
    (data / "environment" / "step170-install-plan.tsv").write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")

    manual = plan["manual_installations"]
    for item in manual:
        _write_json(data / "manual_install" / f"{item['engine']}.json", {
            "schema": "biointel.step170.manual-install-intake.v1",
            **item,
            "operator_fields": {
                "release_id": "",
                "local_path": "",
                "executable_sha256": "",
                "licence_text_path": "",
                "licence_text_sha256": "",
                "model_weight_paths": [],
                "model_weight_sha256": [],
                "smoke_test_output": "",
                "qualified_by": "",
                "qualified_at_utc": "",
            },
            "status": "operator-action-required",
        })

    engines.to_csv(reports / "step170_engine_catalog.csv", index=False)
    references.to_csv(reports / "step170_reference_catalog.csv", index=False)
    licences.to_csv(reports / "step170_licence_catalog.csv", index=False)
    payload = {
        "schema": "biointel.step170.asset-build.v1",
        "engine_manifests": int(len(engines)),
        "reference_manifests": int(len(references)),
        "licence_policies": int(len(licences)),
        "automatic_conda_packages": len(plan["conda_packages"]),
        "automatic_pip_packages": len(plan["pip_packages"]),
        "manual_provider_installations": len(manual),
        "environment_file": "data/step170/environment/step170-linux-64.yml",
        "software_assets_complete": len(engines) == 53,
        "external_installations_not_claimed": True,
        "licences_not_auto_accepted": True,
        "large_reference_assets_not_bundled": True,
    }
    _write_json(reports / "step170_asset_build.json", payload)
    print(json.dumps(payload, indent=2))
    return 0 if payload["software_assets_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
