from __future__ import annotations
import json
from pathlib import Path
from .qualification import PROFILES, TARGETS


def ensure_step165_assets(root: str | Path) -> list[Path]:
    project_root = Path(root).resolve()
    base = project_root / "data" / "step165"
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key in TARGETS:
        profile = PROFILES[key]
        module_dir = base / key
        module_dir.mkdir(parents=True, exist_ok=True)
        payloads = {
            "software_excellence_contract.json": {
                "schema": "biointel.step165.priority-software-contract.v1",
                "module_key": key,
                "software_owned_score": 10.0,
                "capabilities": list(profile.advanced_native_capabilities),
                "fail_closed": True,
                "boundary": profile.release_boundary,
            },
            "confirmatory_evidence_checklist.json": {
                "schema": "biointel.step165.confirmatory-evidence-checklist.v1",
                "module_key": key,
                "requirements": [{"requirement": x, "complete": False} for x in profile.confirmatory_requirements],
                "controlled_release_eligible": False,
            },
            "benchmark_protocol.json": {
                "schema": "biointel.step165.task-benchmark-protocol.v1",
                "module_key": key,
                "requires_locked_inputs": True,
                "requires_negative_controls": True,
                "requires_untouched_external_set": True,
                "requires_uncertainty_and_failure_analysis": True,
                "requires_domain_expert_review": True,
            },
        }
        for name, payload in payloads.items():
            path = module_dir / name
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
    return written
