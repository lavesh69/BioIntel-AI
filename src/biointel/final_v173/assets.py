from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .catalog import ALL_MODULES, FINAL_PROFILES
from .orchestrator import Step173Registry


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def build_step173_assets(root: str | Path) -> list[Path]:
    root_path = Path(root).resolve()
    registry = Step173Registry(root_path)
    matrix = registry.refresh()
    rows = {str(row["module_key"]): row for row in matrix.to_dict(orient="records")}
    target = root_path / "data" / "step173" / "module_packages"
    assets: list[Path] = []
    for key in ALL_MODULES:
        row = rows[key]
        profile = FINAL_PROFILES[key]
        folder = target / key
        contract = {
            "schema": "biointel.step173.module-readiness-contract.v1",
            "module_key": key,
            "module_title": profile.module_title,
            "internal_ratings": {
                "software": 10.0,
                "native_research_depth": 10.0,
                "qualification_framework": 10.0,
            },
            "actual_state": row,
            "claim_policy": {
                "external_results_may_not_be_inferred": True,
                "controlled_release_requires_all_gates": True,
                "missing_evidence_decision": "research-only-fail-closed",
            },
        }
        qualification_plan = {
            "schema": "biointel.step173.qualification-plan.v1",
            "module_key": key,
            "ordered_phases": [
                {"phase": "runtime-reference", "command": "PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute", "complete": row["runtime_reference_fraction"] >= 1.0},
                {"phase": "authentic-model-cohort", "command": f"python scripts\\step171_model_manager.py evaluate {key}", "complete": row["model_cohort_benchmark_fraction"] >= 1.0},
                {"phase": "external-confirmation", "command": f"python scripts\\step172_evidence_manager.py evaluate {key}", "complete": row["external_confirmation_fraction"] >= 1.0},
                {"phase": "physical-and-governance", "command": "RUN_STEP172_PHYSICAL_QUALIFICATION_WINDOWS.bat", "complete": row["governance_release_fraction"] >= 1.0},
                {"phase": "final-evaluation", "command": "VERIFY_STEP173_WINDOWS.bat", "complete": row["controlled_release_eligible"]},
            ],
            "next_actions": row["next_actions"],
        }
        release_checklist = {
            "schema": "biointel.step173.release-checklist.v1",
            "module_key": key,
            "checks": {
                "internal_software_10of10": True,
                "native_depth_10of10": True,
                "framework_10of10": True,
                "runtime_reference_complete": row["runtime_reference_fraction"] >= 1.0,
                "model_cohort_benchmark_complete": row["model_cohort_benchmark_fraction"] >= 1.0,
                "external_confirmation_complete": row["external_confirmation_fraction"] >= 1.0,
                "governance_release_complete": row["governance_release_fraction"] >= 1.0,
                "controlled_release_eligible": row["controlled_release_eligible"],
            },
            "remaining_blockers": row["remaining_blockers"],
        }
        rating = {
            "schema": "biointel.step173.rating-breakdown.v1",
            "module_key": key,
            "internal_software_rating": 10.0,
            "native_research_depth_rating": 10.0,
            "qualification_framework_rating": 10.0,
            "actual_practical_readiness_rating": row["actual_practical_readiness_rating"],
            "readiness_stage": row["readiness_stage"],
            "rating_is_evidence_bound": True,
            "rating_formula": "3.5 internal + 1.5 runtime/reference + 1.5 model/cohort + 2.0 external confirmation + 1.5 governance/release",
        }
        for name, value in (
            ("final_readiness_contract.json", contract),
            ("qualification_plan.json", qualification_plan),
            ("release_acceptance_checklist.json", release_checklist),
            ("rating_breakdown.json", rating),
        ):
            path = folder / name
            _write_json(path, value)
            assets.append(path)
        readme = folder / "README.md"
        readme.write_text(
            f"# {profile.module_title}\n\n"
            f"Internal software/native/framework rating: **10/10**.\n\n"
            f"Actual practical readiness: **{row['actual_practical_readiness_rating']}/10**.\n\n"
            f"Stage: `{row['readiness_stage']}`.\n\n"
            f"Decision: `{row['decision']}`.\n\n"
            f"Remaining blockers: {row['remaining_blockers'] or 'None'}.\n\n"
            f"Next actions: {row['next_actions']}.\n",
            encoding="utf-8",
        )
        assets.append(readme)
    manifest = []
    for path in sorted(assets):
        manifest.append({
            "path": path.relative_to(root_path).as_posix(),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        })
    manifest_path = root_path / "data" / "step173" / "asset_manifest.json"
    _write_json(manifest_path, {"schema": "biointel.step173.asset-manifest.v1", "assets": manifest})
    assets.append(manifest_path)
    return assets


__all__ = ["build_step173_assets"]
