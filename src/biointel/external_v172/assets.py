from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import ALL_MODULES, PROFILES
from .registry import Step172Registry


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_step172_assets(root: str | Path) -> list[Path]:
    root = Path(root).resolve()
    base = root / "data" / "step172"
    written: list[Path] = []
    for key in ALL_MODULES:
        p = PROFILES[key]
        module_dir = base / "module_packages" / key
        requirements = {
            "schema": "biointel.step172.module-confirmation-requirements.v1",
            **p.__dict__,
            "completion_inferred": False,
            "claim_boundary": "No external outcome, signature, qualification or operating history is inferred from software completion.",
        }
        written.append(_write(module_dir / "requirements.json", requirements))
        written.append(_write(module_dir / "prospective_protocol_template.json", {
            "schema": "biointel.step172.prospective-protocol.v1", "module_key": key,
            "protocol_id": "", "path": "", "sha256": "", "preregistered_reference": "",
            "locked_before_execution": False, "acceptance_thresholds_locked": False,
            "blinding_plan": "", "adjudication_plan": "", "deviation_policy": "",
        }))
        written.append(_write(module_dir / "site_qualification_template.json", {
            "schema": "biointel.step172.site-qualification.v1", "module_key": key,
            "sites": [{"site_id": "", "organization": "", "country": "", "independent": False,
                       "qualification_path": "", "qualification_sha256": "", "qa_approved": False}],
        }))
        written.append(_write(module_dir / "instrument_qualification_template.json", {
            "schema": "biointel.step172.instrument-qualification.v1", "module_key": key,
            "required": p.requires_instrument_qualification,
            "instruments": [{"instrument_id": "", "manufacturer": "", "model": "", "serial_number": "", "firmware": "",
                             "iq_path": "", "iq_sha256": "", "oq_path": "", "oq_sha256": "",
                             "pq_path": "", "pq_sha256": "", "calibration_path": "", "calibration_sha256": "", "qualified": False}],
        }))
        written.append(_write(module_dir / "confirmation_evidence_template.json", {
            "schema": "biointel.step172.confirmation-evidence.v1", "module_key": key,
            "allowed_types": ["wet_lab", "prospective", "orthogonal"],
            "confirmations": [{"type": "", "batch_id": "", "site_id": "", "instrument_id": "",
                               "evidence_path": "", "evidence_sha256": "", "data_manifest_path": "", "data_manifest_sha256": "",
                               "sample_count": 0, "biological_replicates": 0, "technical_replicates": 0,
                               "controls_complete": False, "independent": False, "blinded": False,
                               "adjudicated": False, "acceptance_passed": False}],
        }))
        written.append(_write(module_dir / "expert_signoff_template.json", {
            "schema": "biointel.step172.expert-signoff.v1", "module_key": key,
            "experts": [{"name": "", "role": "", "organization": "", "independent": False,
                         "credential_path": "", "credential_sha256": "", "conflict_disclosure_path": "", "conflict_disclosure_sha256": "",
                         "review_path": "", "review_sha256": "", "signature_path": "", "signature_sha256": "",
                         "public_key_path": "", "public_key_sha256": "", "approved": False}],
            "signature_verification": "OpenSSL SHA-256 detached signature verification is required for controlled release.",
        }))
        written.append(_write(module_dir / "physical_qualification_template.json", {
            "schema": "biointel.step172.physical-qualification.v1", "module_key": key,
            "report_path": "", "report_sha256": "", "windows_tested": False,
            "gpu_tested": False, "instrument_tested": False, "antivirus_tested": False,
            "sleep_resume_tested": False, "network_loss_tested": False, "recovery_tested": False,
            "large_file_tested": False,
        }))
        written.append(_write(module_dir / "operating_history_template.json", {
            "schema": "biointel.step172.operating-history.v1", "module_key": key,
            "report_path": "", "report_sha256": "", "runs": 0, "failures": 0,
            "unresolved_critical_incidents": 0, "drift_review_complete": False,
        }))
        written.append(_write(module_dir / "formal_release_review_template.json", {
            "schema": "biointel.step172.formal-release-review.v1", "module_key": key,
            "decision_path": "", "decision_sha256": "", "decision": "pending", "intended_use": "research-only",
            "quorum": 0, "independent_qa_approval": False, "domain_expert_approval": False,
            "product_owner_approval": False, "risk_acceptance_documented": False,
        }))
        written.append(_write(module_dir / "confirmation_manifest_template.json", {
            "schema": "biointel.step172.confirmation-submission.v1", "module_key": key,
            "protocol": {}, "sites": [], "instruments": [], "confirmations": [], "experts": [],
            "physical_qualification": {}, "operating_history": {}, "release_review": {},
        }))
    registry = Step172Registry(root)
    registry.matrix(refresh=True)
    written.append(_write(base / "STEP172_ASSET_INDEX.json", {
        "schema": "biointel.step172.asset-index.v1", "modules": len(ALL_MODULES),
        "assets_per_module": 10, "assets": len(written),
        "software_framework_score": 10.0,
        "actual_external_evidence_is_not_bundled_or_inferred": True,
    }))
    return written


__all__ = ["build_step172_assets"]
