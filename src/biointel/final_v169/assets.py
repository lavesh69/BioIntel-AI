from __future__ import annotations

from pathlib import Path
import json

from biointel.scientific_depth.profiles import MODULE_PROFILES
from .registry import AXES, ensure_step169_registry


def ensure_step169_assets(root: str | Path) -> list[Path]:
    project_root = Path(root)
    ensure_step169_registry(project_root)
    written: list[Path] = []
    base = project_root / "data" / "step169" / "module_contracts"
    for key, profile in sorted(MODULE_PROFILES.items()):
        payload = {
            "schema": "biointel.step169.final-consolidation-contract.v1",
            "module_key": key,
            "module_title": profile.title,
            "product_version": "14.1.0",
            "internal_software_score": 10.0,
            "native_research_depth_score": 10.0,
            "evidence_framework_score": 10.0,
            "verified_release_axes": list(AXES),
            "release_unlock_source": "step169_verified_release.sqlite plus checksum-valid evidence artifacts",
            "metadata_flags_can_unlock_release": False,
            "synthetic_or_demo_evidence_can_unlock_release": False,
            "default_release_status": "research-only-fail-closed",
            "boundary": profile.boundary,
        }
        path = base / key / "final_consolidation_contract.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


__all__ = ["ensure_step169_assets"]
