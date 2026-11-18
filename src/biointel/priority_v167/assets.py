from __future__ import annotations

from pathlib import Path
import json
from .qualification import PROFILES, TARGETS


def ensure_step167_assets(root: str | Path) -> list[Path]:
    project_root = Path(root)
    base = project_root / "data" / "step167"
    written: list[Path] = []
    for key in TARGETS:
        profile = PROFILES[key]
        module_dir = base / key
        module_dir.mkdir(parents=True, exist_ok=True)
        payloads = {
            "software_contract.json": {
                "schema": "biointel.step167.priority-module-software-contract.v1",
                "module_key": key,
                "software_score": 10.0,
                "native_research_depth_score": 10.0,
                "focused_upgrade": profile.focused_upgrade,
                "claim_boundary": "research-only-fail-closed",
            },
            "specialist_reference_plan.json": {
                "schema": "biointel.step167.specialist-reference-plan.v1",
                "module_key": key,
                "required_external_confirmation": profile.external_confirmation_required,
                "requirements": ["version lock", "SHA-256 or OCI digest", "licence record", "scientific smoke test", "reference release manifest"],
            },
            "validation_protocol.json": {
                "schema": "biointel.step167.validation-protocol.v1",
                "module_key": key,
                "required_evidence": ["independent cohort", "negative controls", "uncertainty analysis", "prospective or orthogonal confirmation", "domain-expert sign-off"],
                "release_eligible_without_evidence": False,
            },
        }
        for filename, payload in payloads.items():
            path = module_dir / filename
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            written.append(path)
    return written


__all__ = ["ensure_step167_assets"]
