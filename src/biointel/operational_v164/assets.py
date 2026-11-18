from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from biointel.scientific_depth.profiles import MODULE_PROFILES

from .catalog import engine_manifest, provisioning_catalog, safe_slug
from .qualification import evidence_intake_template, model_intake_template, reference_intake_template


def ensure_step164_assets(root: str | Path, module_keys: Iterable[str] | None = None) -> list[Path]:
    project_root = Path(root).expanduser().resolve()
    keys = sorted(set(module_keys or MODULE_PROFILES))
    base = project_root / "data" / "step164"
    engine_dir = base / "engine_provisioning"
    reference_dir = base / "reference_intake_templates"
    model_dir = base / "model_intake_templates"
    evidence_dir = base / "external_evidence_templates"
    module_dir = base / "module_operational_contracts"
    for folder in (engine_dir, reference_dir, model_dir, evidence_dir, module_dir):
        folder.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    catalog = provisioning_catalog()
    for engine in catalog["engine"].astype(str).tolist():
        path = engine_dir / f"{safe_slug(engine)}.json"
        path.write_text(json.dumps(engine_manifest(engine), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)

    for module_key in keys:
        profile = MODULE_PROFILES[module_key]
        module_reference_dir = reference_dir / module_key
        module_reference_dir.mkdir(parents=True, exist_ok=True)
        references = []
        for index, reference in enumerate(profile.references, start=1):
            payload = reference_intake_template(module_key, reference, index)
            path = module_reference_dir / f"{index:02d}-{safe_slug(reference)}.json"
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
            references.append(payload["asset_id"])
        model_payload = model_intake_template(module_key)
        model_path = model_dir / f"{module_key}.json"
        model_path.write_text(json.dumps(model_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(model_path)
        evidence_payload = evidence_intake_template(module_key)
        evidence_path = evidence_dir / f"{module_key}.json"
        evidence_path.write_text(json.dumps(evidence_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(evidence_path)
        module_payload = {
            "schema": "biointel.step164.module-operational-contract.v1",
            "module_key": module_key,
            "module_title": profile.title,
            "software_owned_target": "10/10",
            "specialist_engines": [str(e).lower() for e in profile.engines if not str(e).startswith("biointel_native::")],
            "reference_asset_ids": references,
            "accepted_formats": list(profile.native_formats),
            "validation_gates": list(profile.validations),
            "optimization_controls": list(profile.optimization),
            "scientific_boundary": profile.boundary,
            "native_research_fallback_ready": True,
            "specialist_claims_fail_closed": True,
            "external_release_requires_all_real_artifacts": True,
        }
        module_path = module_dir / f"{module_key}.json"
        module_path.write_text(json.dumps(module_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(module_path)
    return written


__all__ = ["ensure_step164_assets"]
