from __future__ import annotations

import hashlib
import json
from pathlib import Path

from biointel.operational_v164 import (
    ensure_step164_assets,
    operational_matrix,
    provisioning_catalog,
    qualify_evidence_manifest,
    qualify_model_manifest,
    qualify_reference_manifest,
    reference_intake_template,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step164_assets_cover_all_modules_and_external_engines() -> None:
    written = ensure_step164_assets(ROOT)
    matrix = operational_matrix(ROOT, detect_runtime=False)
    catalog = provisioning_catalog()
    assert len(matrix) == len(MODULE_PROFILES) == 80
    assert (matrix["software_owned_score"] == 10.0).all()
    assert len(catalog) >= 53
    assert catalog["software_recipe_complete"].astype(bool).all()
    assert len(written) >= 400


def test_reference_manifest_requires_real_asset_and_matching_checksum(tmp_path: Path) -> None:
    asset = tmp_path / "reference.tsv"
    asset.write_text("id\tvalue\nA\t1\n", encoding="utf-8")
    payload = reference_intake_template("amr_surveillance", "Pinned AMR database", 1)
    payload.update(
        {
            "provider": "Test provider",
            "provider_release_id": "2026-07",
            "licence_identifier": "CC-BY-4.0",
            "licence_reviewed": True,
            "source_url_or_accession": "ACC-001",
            "local_relative_path": asset.name,
            "expected_sha256": _sha256(asset),
            "record_count": 1,
            "schema_or_format": "TSV",
            "schema_validation_passed": True,
            "scientific_reviewer": "Reviewer",
            "review_date": "2026-07-14",
            "production_qualified": True,
        }
    )
    result = qualify_reference_manifest(tmp_path, payload)
    assert result["production_qualified"] is True
    payload["expected_sha256"] = "0" * 64
    assert qualify_reference_manifest(tmp_path, payload)["production_qualified"] is False


def test_model_and_evidence_intake_fail_closed_without_artifacts(tmp_path: Path) -> None:
    model = qualify_model_manifest(tmp_path, {"model_id": "missing", "production_eligible": True, "task_matches_module": True})
    evidence = qualify_evidence_manifest(tmp_path, {"study_id": "missing", "release_review_complete": True})
    assert model["production_model_eligible"] is False
    assert evidence["release_review_complete"] is False


def test_step164_native_result_contains_operational_gate() -> None:
    for module_key in ["amr_surveillance", "protein_ligand_codesign", "clinical_trial_biomarker", "background_job_engine"]:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
        )
        assert result.status in {"pass", "review"}
        assert result.summary["step164_software_owned_operational_score"] == 10.0
        assert "step164_operational_readiness_gate" in result.tables
        assert "step164_required_evidence_checklist" in result.tables
        assert result.summary["step164_real_world_release_eligible"] is False


def test_step164_release_metadata() -> None:
    payload = json.loads((ROOT / "STEP164_RELEASE.json").read_text(encoding="utf-8"))
    assert payload["product_version"] == "13.6.0"
    assert payload["scientific_modules"] == 80
    assert payload["software_owned_operational_10of10"] == 80
    assert (ROOT / "pages/233_Operational_Readiness_10of10_Center.py").is_file()
