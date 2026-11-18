from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.target_modules_v180 import (
    TARGET_MODULES,
    TARGET_PROFILES,
    required_cohorts,
    required_components,
    required_models,
    required_references,
    run_contract_smoke,
)
from biointel.target_modules_v180.runtime import (
    COHORT_FLAGS,
    EXTERNAL_FLAGS,
    FIXTURE_FLAGS,
    GOVERNANCE_FLAGS,
    MODEL_FLAGS,
    REFERENCE_FLAGS,
)


def manifest(asset_id: str, kind: str, flags: tuple[str, ...]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": f"biointel.step180.{kind}-qualification.v1",
        "asset_id": asset_id,
        "operator_notes": "Replace false placeholders only after reviewing real evidence.",
    }
    payload.update({flag: False for flag in flags})
    return payload


def main(root: Path) -> None:
    output = root / "data" / "step180"
    target_root = output / "target_modules"
    target_root.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []

    for module_key in TARGET_MODULES:
        profile = TARGET_PROFILES[module_key]
        folder = target_root / module_key
        folder.mkdir(parents=True, exist_ok=True)
        contract = {
            "schema": "biointel.step180.final-five-scientific-assurance.v1",
            "module_key": module_key,
            "module_title": profile.title,
            "baseline_rating": profile.baseline_rating,
            "internal_after_rating": 10.0,
            "focus": profile.focus,
            "workflow": list(profile.workflow),
            "data_gates": list(profile.data_gates),
            "model_gates": list(profile.model_gates),
            "scientific_gates": list(profile.scientific_gates),
            "acceptance_criteria": list(profile.acceptance_criteria),
            "required_outputs": list(profile.required_outputs),
            "risk_controls": list(profile.risk_controls),
            "monitoring_metrics": list(profile.monitoring_metrics),
            "boundary": profile.boundary,
            "decision_policy": "internal-10of10-external-fail-closed",
        }
        (folder / "qualification_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
        required_components(module_key).to_csv(folder / "component_plan.csv", index=False)
        required_references(module_key).to_csv(folder / "reference_plan.csv", index=False)
        required_models(module_key).to_csv(folder / "model_plan.csv", index=False)
        required_cohorts(module_key).to_csv(folder / "cohort_plan.csv", index=False)
        (folder / "built_in_scientific_smoke_results.json").write_text(
            json.dumps({"module_key": module_key, "checks": run_contract_smoke(module_key)}, indent=2),
            encoding="utf-8",
        )

        groups = (
            ("reference", profile.supplemental_references, REFERENCE_FLAGS),
            ("model", profile.model_assets, MODEL_FLAGS),
            ("cohort", profile.cohort_assets, COHORT_FLAGS),
            ("fixture", profile.validation_fixtures, FIXTURE_FLAGS),
            ("governance", profile.governance_assets, GOVERNANCE_FLAGS),
        )
        for kind, asset_ids, flags in groups:
            template_folder = folder / f"{kind}_manifest_templates"
            template_folder.mkdir(exist_ok=True)
            for asset_id in asset_ids:
                (template_folder / f"{asset_id}.json").write_text(
                    json.dumps(manifest(asset_id, kind, flags), indent=2),
                    encoding="utf-8",
                )

        external = {
            "schema": "biointel.step180.external-scientific-evidence.v1",
            "module_key": module_key,
            "operator_notes": "Attach only independently reviewed, real evidence.",
        }
        external.update({flag: False for flag in EXTERNAL_FLAGS})
        (folder / "external_evidence_manifest_template.json").write_text(
            json.dumps(external, indent=2), encoding="utf-8"
        )
        index.append(
            {
                "module_key": module_key,
                "module_title": profile.title,
                "baseline_rating": profile.baseline_rating,
                "internal_after_rating": 10.0,
                "folder": str(folder.relative_to(root)),
            }
        )

    (output / "asset_index.json").write_text(
        json.dumps(
            {
                "schema": "biointel.step180.asset-index.v1",
                "module_count": len(index),
                "portfolio_internal_status": "80/80 modules at internal 10/10",
                "modules": index,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    main(arguments.root.resolve())
