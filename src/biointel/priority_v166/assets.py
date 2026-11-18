from __future__ import annotations

import json
from pathlib import Path
from .qualification import PROFILES, TARGETS


def ensure_step166_assets(root: str | Path) -> list[Path]:
    project_root = Path(root).resolve()
    base = project_root / "data" / "step166"
    written: list[Path] = []
    for key in TARGETS:
        profile = PROFILES[key]
        folder = base / key
        folder.mkdir(parents=True, exist_ok=True)
        payloads = {
            "software_excellence_contract.json": {
                "schema": "biointel.step166.six-module-software-contract.v1",
                "module_key": key,
                "software_score": 10.0,
                "native_research_depth_score": 10.0,
                "focused_upgrade": profile.focused_upgrade,
                "fail_closed": True,
            },
            "specialist_runtime_and_reference_plan.json": {
                "schema": "biointel.step166.specialist-runtime-reference-plan.v1",
                "module_key": key,
                "external_confirmation_required": profile.external_confirmation_required,
                "checks": ["executable/container version", "binary/container sha256", "database release", "database sha256", "licence", "schema/record counts", "scientific reviewer"],
            },
            "confirmatory_validation_protocol.json": {
                "schema": "biointel.step166.confirmatory-validation-protocol.v1",
                "module_key": key,
                "requirements": ["independent dataset", "prespecified acceptance criteria", "negative controls", "orthogonal or wet-lab confirmation", "domain expert sign-off", "immutable evidence hashes"],
                "controlled_release_eligible": False,
            },
        }
        for name, payload in payloads.items():
            path = folder / name
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            written.append(path)
    return written


__all__ = ["ensure_step166_assets"]
