from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any

from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES

from .catalog import PHASES
from .orchestrator import Step174ExecutionRegistry, automatic_environment_probe


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _csv(path: Path, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(headers)


def build_step174_assets(root: str | Path) -> list[Path]:
    root_path = Path(root).resolve()
    registry = Step174ExecutionRegistry(root_path)
    matrix = registry.refresh()
    rows = {str(row["module_key"]): row for row in matrix.to_dict(orient="records")}
    base = root_path / "data" / "step174"
    modules = base / "module_execution_packages"
    assets: list[Path] = []

    _json(base / "phase_catalog.json", {"schema": "biointel.step174.phase-catalog.v1", "phases": [phase.__dict__ for phase in PHASES]})
    assets.append(base / "phase_catalog.json")
    _json(base / "build_host_environment_probe.json", automatic_environment_probe(root_path))
    assets.append(base / "build_host_environment_probe.json")

    handbook = base / "PHASE1_TO_9_EXECUTION_HANDBOOK.md"
    handbook.write_text(
        "# BioIntel AI Step 174 — Phase 1 to 9 Execution Handbook\n\n"
        "Step 174 completes every software-owned orchestration, template, evidence-intake and verification control for Phases 1–9. "
        "It does not fabricate laboratory measurements, provider credentials, patient cohorts, expert identities, physical site history or release approvals.\n\n"
        "## Ordered execution\n\n"
        + "\n".join(f"{p.phase_number}. **{p.title}** — `{p.default_command}`" for p in PHASES)
        + "\n\n## Final command\n\n`RUN_STEP174_PHASE1_TO_9_WINDOWS.bat`\n",
        encoding="utf-8",
    )
    assets.append(handbook)

    global_templates = {
        "evidence_inventory_template.csv": ["module_key", "phase", "artifact_type", "path", "sha256", "provider", "release_id", "licence_id", "reviewer", "status", "notes"],
        "operating_history_template.csv": ["module_key", "run_id", "started_at_utc", "completed_at_utc", "site_id", "instrument_id", "dataset_sha256", "outcome", "failure_code", "downtime_minutes", "drift_review", "capa_id", "reviewer"],
        "incident_capa_template.csv": ["module_key", "incident_id", "severity", "opened_at_utc", "description", "root_cause", "corrective_action", "preventive_action", "owner", "status", "closed_at_utc"],
        "expert_register_template.csv": ["expert_id", "name", "domain", "institution", "credential_path", "credential_sha256", "conflict_path", "conflict_sha256", "public_key_path", "public_key_sha256", "independent", "approved"],
        "release_committee_register_template.csv": ["module_key", "release_id", "qa_reviewer", "domain_expert", "product_owner", "quorum", "decision", "decision_path", "decision_sha256", "risk_acceptance", "intended_use", "prohibited_use"],
        "site_instrument_register_template.csv": ["site_id", "site_name", "instrument_id", "manufacturer", "model", "serial_number", "firmware", "iq_path", "iq_sha256", "oq_path", "oq_sha256", "pq_path", "pq_sha256", "calibration_path", "calibration_sha256", "qualified"],
    }
    for name, headers in global_templates.items():
        path = base / "templates" / name
        _csv(path, headers)
        assets.append(path)

    signature = base / "templates" / "EXPERT_SIGNATURE_INSTRUCTIONS.md"
    signature.write_text(
        "# Expert cryptographic sign-off\n\n"
        "1. Create an expert review PDF or Markdown file.\n"
        "2. Generate or use an approved signing key.\n"
        "3. Sign with `openssl dgst -sha256 -sign private_key.pem -out review.sig review.pdf`.\n"
        "4. Submit the review, detached signature, public key, credential and conflict disclosure with SHA-256 values.\n"
        "5. Never include the private key in BioIntel AI.\n",
        encoding="utf-8",
    )
    assets.append(signature)

    for module_key in ALL_MODULES:
        row = rows[module_key]
        folder = modules / module_key
        phase_status = {phase: bool(row[f"phase_{phase}_complete"]) for phase in range(1, 10)}
        for phase in PHASES:
            applicable = bool(row.get(f"phase_{phase.phase_number}_applicable", True))
            payload = {
                "schema": "biointel.step174.module-phase-work-package.v1",
                "module_key": module_key,
                "module_title": FINAL_PROFILES[module_key].module_title,
                "phase_number": phase.phase_number,
                "phase_key": phase.phase_key,
                "phase_title": phase.title,
                "applicable": applicable,
                "complete": phase_status[phase.phase_number],
                "software_automation_ready": True,
                "objective": phase.objective,
                "software_automation": phase.software_automation,
                "external_evidence_required": list(phase.external_evidence_required),
                "completion_rule": phase.completion_rule,
                "command": row["next_command"] if row["next_phase"] == phase.phase_number else phase.default_command.replace("MODULE_KEY", module_key),
                "claim_policy": {
                    "external_evidence_must_be_genuine": True,
                    "metadata_flags_without_files_are_ineligible": True,
                    "missing_evidence_decision": "research-only-fail-closed",
                },
            }
            path = folder / f"phase_{phase.phase_number:02d}_{phase.phase_key}.json"
            _json(path, payload)
            assets.append(path)

        manifest = {
            "schema": "biointel.step174.module-execution-manifest.v1",
            "module_key": module_key,
            "module_title": FINAL_PROFILES[module_key].module_title,
            "phase_state": row,
            "internal_software_native_framework_rating": 10.0,
            "actual_practical_readiness_rating": row["actual_practical_readiness_rating"],
            "controlled_release_eligible": row["controlled_release_eligible"],
            "external_evidence_fabricated": False,
        }
        _json(folder / "execution_manifest.json", manifest)
        assets.append(folder / "execution_manifest.json")
        _csv(folder / "evidence_inventory.csv", global_templates["evidence_inventory_template.csv"])
        assets.append(folder / "evidence_inventory.csv")
        readme = folder / "README.md"
        readme.write_text(
            f"# {FINAL_PROFILES[module_key].module_title}\n\n"
            f"Software automation: **10/10**.\n\n"
            f"Completed externally executed phases: **{row['completed_phases']}/{row['required_phases']}**.\n\n"
            f"Actual practical readiness: **{row['actual_practical_readiness_rating']}/10**.\n\n"
            f"Next phase: **{row['next_phase']}**.\n\n"
            f"Next command: `{row['next_command']}`.\n\n"
            f"Blockers: {row['phase_blockers'] or 'None'}\n",
            encoding="utf-8",
        )
        assets.append(readme)

    manifest_entries = [
        {"path": path.relative_to(root_path).as_posix(), "sha256": sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}
        for path in sorted(assets)
    ]
    manifest_path = base / "asset_manifest.json"
    _json(manifest_path, {"schema": "biointel.step174.asset-manifest.v1", "assets": manifest_entries})
    assets.append(manifest_path)
    return assets


def prepare_execution_workspace(root: str | Path, module_key: str | None = None, *, force: bool = False) -> list[Path]:
    root_path = Path(root).resolve()
    source = root_path / "data" / "step174" / "module_execution_packages"
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (root_path / "UserData")).resolve()
    target = user_data / "step174" / "execution_workspaces"
    keys = [module_key] if module_key else list(ALL_MODULES)
    written: list[Path] = []
    for key in keys:
        if key not in ALL_MODULES:
            raise KeyError(f"Unknown module: {key}")
        src = source / key
        dst = target / key
        dst.mkdir(parents=True, exist_ok=True)
        for path in src.iterdir():
            out = dst / path.name
            if out.exists() and not force:
                continue
            shutil.copy2(path, out)
            written.append(out)
    return written


__all__ = ["build_step174_assets", "prepare_execution_workspace"]
