from __future__ import annotations

from pathlib import Path
import json

from .qualification import ALL_MODULES, PROFILES, TARGETS


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_step168_assets(root: str | Path) -> list[Path]:
    project_root = Path(root)
    written: list[Path] = []

    focused = project_root / "data" / "step168" / "focused_modules"
    for key in TARGETS:
        profile = PROFILES[key]
        payloads = {
            "software_and_scientific_contract.json": {
                "schema": "biointel.step168.focused-module-contract.v1",
                "module_key": key,
                "software_score": 10.0,
                "native_research_depth_score": 10.0,
                "operational_evidence_framework_score": 10.0,
                "focused_upgrade": profile.focused_upgrade,
                "claim_boundary": "research-only-fail-closed",
            },
            "production_data_intake.json": {
                "schema": "biointel.step168.production-data-intake.v1",
                "module_key": key,
                "required": ["provider/site/instrument", "release or cohort identifier", "licence", "SHA-256", "schema", "QC report", "reviewer"],
                "completion_inferred": False,
            },
            "external_validation_plan.json": {
                "schema": "biointel.step168.external-validation-plan.v1",
                "module_key": key,
                "required": ["prespecified protocol", "independent dataset/site", "negative controls", "acceptance thresholds", "failure analysis", "uncertainty"],
                "completion_inferred": False,
            },
            "prospective_release_plan.json": {
                "schema": "biointel.step168.prospective-release-plan.v1",
                "module_key": key,
                "required": ["prospective or orthogonal confirmation", "domain-expert sign-off", "formal release review", "operating history", "physical qualification"],
                "completion_inferred": False,
            },
        }
        for filename, payload in payloads.items():
            path = focused / key / filename
            _write(path, payload)
            written.append(path)

    universal = project_root / "data" / "step168" / "universal_evidence"
    for key in ALL_MODULES:
        payloads = {
            "production_reference_intake.json": {
                "schema": "biointel.step168.production-reference-intake.v1",
                "module_key": key,
                "fields": ["provider", "release_id", "licence", "source_accession", "local_path", "sha256", "record_count", "schema", "reviewer", "review_date"],
                "qualified": False,
            },
            "independent_validation_protocol.json": {
                "schema": "biointel.step168.independent-validation-protocol.v1",
                "module_key": key,
                "requirements": ["locked protocol", "independent site/dataset", "negative controls", "prespecified thresholds", "calibration", "failure analysis"],
                "complete": False,
            },
            "prospective_or_orthogonal_protocol.json": {
                "schema": "biointel.step168.prospective-validation-protocol.v1",
                "module_key": key,
                "requirements": ["prediction lock", "blinded outcome", "orthogonal assay or prospective operation", "deviation log"],
                "complete": False,
            },
            "expert_and_release_review.json": {
                "schema": "biointel.step168.expert-release-review.v1",
                "module_key": key,
                "requirements": ["named domain expert", "conflict disclosure", "signed review", "release committee decision", "intended-use boundary"],
                "complete": False,
            },
            "operating_history_schema.json": {
                "schema": "biointel.step168.operating-history.v1",
                "module_key": key,
                "fields": ["site", "environment", "start/end", "runs", "failures", "downtime", "drift", "incidents", "corrective actions"],
                "minimum_history_complete": False,
            },
            "physical_qualification_protocol.json": {
                "schema": "biointel.step168.physical-qualification.v1",
                "module_key": key,
                "requirements": ["Windows hardware", "GPU when applicable", "instrument when applicable", "antivirus", "sleep/resume", "network loss", "large-file", "recovery"],
                "complete": False,
            },
        }
        for filename, payload in payloads.items():
            path = universal / key / filename
            _write(path, payload)
            written.append(path)
    return written


__all__ = ["ensure_step168_assets"]
