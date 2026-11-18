from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import zipfile

import pandas as pd

from biointel.external_readiness_v181 import (
    PROFILES,
    TARGET_MODULES,
    build_workspaces,
    evidence_detail_matrix,
    import_bundle,
    qualification_matrix,
    validate_evidence_folder,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_pack(
    root: Path,
    module_key: str,
    evidence_id: str,
    frame: pd.DataFrame | None = None,
    data_file: str | None = None,
) -> Path:
    requirement = next(item for item in PROFILES[module_key].requirements if item.evidence_id == evidence_id)
    folder = root / "UserData" / "step181" / "evidence" / module_key / evidence_id
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    if data_file:
        path = folder / data_file
        assert frame is not None
        frame.to_csv(path, index=False)
        files.append({"path": data_file, "sha256": sha256(path.read_bytes()).hexdigest()})
    else:
        path = folder / "authentic_asset.bin"
        path.write_bytes(b"test-only-authentic-asset-fixture")
        files.append({"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()})
    manifest = {
        "schema": "biointel.step181.evidence-manifest.v1",
        "module_key": module_key,
        "evidence_id": evidence_id,
        "evidence_title": requirement.title,
        "source_organization": "Independent Test Laboratory",
        "source_contact": "quality@example.invalid",
        "acquisition_date": "2026-07-14",
        "licence_or_permission": "unit-test permission record",
        "provenance_record": "unit-test provenance record",
        "real_world_evidence": True,
        "synthetic_or_demo": False,
        "independent_from_development_team": True,
        "deidentified_or_nonhuman": True,
        "reviewer_name": "Test Reviewer",
        "reviewer_role": "Independent domain expert",
        "review_signed": True,
        "review_date": "2026-07-14",
        "files": files,
    }
    (folder / "qualification_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder


def test_step181_catalog_and_workspace_templates(tmp_path: Path):
    assert len(TARGET_MODULES) == 5
    assert sum(len(PROFILES[key].requirements) for key in TARGET_MODULES) == 25
    result = build_workspaces(tmp_path)
    assert result["evidence_pack_count"] == 25
    details = evidence_detail_matrix(tmp_path)
    assert len(details) == 25
    assert not details.qualified.any()
    summary = qualification_matrix(tmp_path)
    assert summary.weakness_remediation_workflow_rating.eq(10.0).all()
    assert not summary.controlled_release_eligible.any()


def test_step181_page_hooks_and_windows_flow():
    for key in TARGET_MODULES:
        page = ROOT / PROFILES[key].page
        text = page.read_text(encoding="utf-8-sig")
        assert "render_step181_external_readiness" in text
        assert key in text
    for filename in (
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "BUILD_STEP181_EXTERNAL_EVIDENCE_WORKSPACES_WINDOWS.bat",
        "VERIFY_STEP181_EXTERNAL_EVIDENCE_WINDOWS.bat",
        "IMPORT_STEP181_EVIDENCE_BUNDLE_WINDOWS.bat",
    ):
        assert (ROOT / filename).is_file()


def test_step181_phenotypic_real_evidence_validators(tmp_path: Path):
    _write_pack(tmp_path, "phenotypic_screening", "physical_instrument_qualification", pd.DataFrame({
        "run_id": ["R1", "R2", "R3"], "field_flatness_pct": [5, 6, 4], "focus_cv_pct": [5, 6, 4],
        "illumination_cv_pct": [4, 5, 6], "stage_error_um": [2, 3, 2], "passed": [True, True, True],
    }), "instrument_runs.csv")
    _write_pack(tmp_path, "phenotypic_screening", "multi_plate_validation", pd.DataFrame({
        "plate_id": ["P1", "P2", "P3"], "positive_mean": [100, 102, 98], "positive_sd": [2, 2, 2],
        "negative_mean": [0, 1, -1], "negative_sd": [2, 2, 2], "replicate_corr": [0.91, 0.90, 0.92],
        "edge_effect_pct": [5, 6, 5],
    }), "plate_qc.csv")
    _write_pack(tmp_path, "phenotypic_screening", "segmentation_ground_truth", pd.DataFrame({
        "image_id": [f"I{i}" for i in range(20)], "dice": [0.90] * 20, "iou": [0.82] * 20,
        "object_f1": [0.91] * 20, "reviewer_approved": [True] * 20,
    }), "segmentation_metrics.csv")
    _write_pack(tmp_path, "phenotypic_screening", "biological_replicates_external_site", pd.DataFrame({
        "site_id": ["S1", "S1", "S2", "S2"], "batch_id": ["B1", "B2", "B3", "B4"],
        "replicate_corr": [0.90, 0.88, 0.89, 0.91], "confirmed_hit_rate": [0.80, 0.75, 0.78, 0.82],
    }), "external_site_replicates.csv")
    _write_pack(tmp_path, "phenotypic_screening", "orthogonal_assay_confirmation", pd.DataFrame({
        "candidate_id": [f"C{i}" for i in range(10)], "primary_effect": list(range(10)),
        "orthogonal_effect": [value * 1.02 for value in range(10)], "confirmed": [True] * 8 + [False] * 2,
    }), "orthogonal_confirmation.csv")
    results = [validate_evidence_folder(tmp_path, "phenotypic_screening", requirement) for requirement in PROFILES["phenotypic_screening"].requirements]
    assert all(result.qualified for result in results)


def test_step181_spatial_real_evidence_validators(tmp_path: Path):
    _write_pack(tmp_path, "spatial_omics_pathology", "scanner_qualification", pd.DataFrame({
        "scanner_id": ["SC1", "SC1", "SC2"], "colour_delta_e": [2, 3, 2], "focus_failure_pct": [1, 1, 1],
        "tile_artifact_pct": [1, 1, 1], "registration_error_um": [5, 6, 5], "passed": [True, True, True],
    }), "scanner_runs.csv")
    _write_pack(tmp_path, "spatial_omics_pathology", "stain_site_drift_validation", pd.DataFrame({
        "site_id": ["S1", "S1", "S2", "S2"], "scanner_id": ["SC1", "SC1", "SC2", "SC2"],
        "stain_batch": ["A", "B", "A", "B"], "embedding_shift": [0.10, 0.12, 0.11, 0.09],
        "auc_drop": [0.02, 0.03, 0.02, 0.01], "calibration_error": [0.02, 0.03, 0.02, 0.03],
    }), "drift_metrics.csv")
    patients = list(range(30))
    labels = [index % 2 == 0 for index in patients]
    predictions = [0.9 if label else 0.1 for label in labels]
    _write_pack(tmp_path, "spatial_omics_pathology", "patient_external_cohort", pd.DataFrame({
        "patient_id": [f"P{i}" for i in patients], "site_id": ["S1" if i < 15 else "S2" for i in patients],
        "prediction": predictions, "label": labels,
    }), "patient_validation.csv")
    review_labels = ["positive" if i % 2 == 0 else "negative" for i in patients]
    _write_pack(tmp_path, "spatial_omics_pathology", "pathologist_agreement", pd.DataFrame({
        "case_id": [f"C{i}" for i in patients], "model_label": review_labels,
        "reviewer1_label": review_labels, "reviewer2_label": review_labels,
    }), "pathology_review.csv")
    _write_pack(tmp_path, "spatial_omics_pathology", "prospective_clinical_validation", pd.DataFrame({
        "case_id": [f"PC{i}" for i in patients], "prediction": predictions, "label": labels,
        "pre_specified_before_outcome": [True] * 30,
    }), "prospective_outcomes.csv")
    results = [validate_evidence_folder(tmp_path, "spatial_omics_pathology", requirement) for requirement in PROFILES["spatial_omics_pathology"].requirements]
    assert all(result.qualified for result in results)


def test_step181_protein_and_ligand_real_evidence_validators(tmp_path: Path):
    _write_pack(tmp_path, "protein_language_design", "authentic_trained_weights")
    _write_pack(tmp_path, "protein_language_design", "independent_sequence_benchmark", pd.DataFrame({
        "benchmark_id": ["B1", "B2"], "metric_name": ["accuracy", "f1"], "metric_value": [0.90, 0.88],
        "threshold": [0.80, 0.80], "independent": [True, True], "identity_to_train_max": [0.50, 0.60],
    }), "benchmark_summary.csv")
    _write_pack(tmp_path, "protein_language_design", "novelty_verification", pd.DataFrame({
        "sequence_id": [f"S{i}" for i in range(20)], "sequence": ["MKTAYIAKQRQISFVKSHFS" + "A" * i for i in range(20)],
        "max_identity_to_training": [0.50] * 20, "max_kmer_jaccard": [0.40] * 20,
        "restricted_motif": [False] * 20, "duplicate": [False] * 20,
    }), "generated_sequences.csv")
    _write_pack(tmp_path, "protein_language_design", "structure_confirmation", pd.DataFrame({
        "sequence_id": [f"S{i}" for i in range(10)], "method": ["independent-model"] * 10,
        "plddt": [85] * 10, "ptm": [0.75] * 10, "independent_or_experimental": [True] + [False] * 9,
    }), "structure_confirmation.csv")
    _write_pack(tmp_path, "protein_language_design", "wet_lab_expression", pd.DataFrame({
        "sequence_id": [f"S{i}" for i in range(5)], "expression_yield_mg_l": [10] * 5,
        "soluble_fraction": [0.8] * 5, "purity_pct": [90] * 5, "activity_confirmed": [True] * 5,
    }), "expression_results.csv")

    _write_pack(tmp_path, "protein_ligand_codesign", "docking_engine_qualification", pd.DataFrame({
        "complex_id": [f"X{i}" for i in range(20)], "predicted_rmsd": [1.2] * 20, "rank": [1] * 20,
        "engine_version": ["pinned"] * 20, "reference_pose": ["experimental"] * 20,
    }), "docking_benchmark.csv")
    experimental = [5 + i * 0.1 for i in range(20)]
    _write_pack(tmp_path, "protein_ligand_codesign", "experimental_binding_affinity", pd.DataFrame({
        "compound_id": [f"L{i}" for i in range(20)], "target_id": ["T"] * 20,
        "predicted_pkd": [value + 0.1 for value in experimental], "experimental_pkd": experimental,
        "assay_type": ["SPR"] * 20,
    }), "binding_affinity.csv")
    _write_pack(tmp_path, "protein_ligand_codesign", "selectivity_panel", pd.DataFrame({
        "compound_id": [f"L{i}" for i in range(10)], "panel_size": [8] * 10, "selectivity_pass": [True] * 8 + [False] * 2,
    }), "selectivity_panel.csv")
    _write_pack(tmp_path, "protein_ligand_codesign", "admet_confirmation", pd.DataFrame({
        "compound_id": [f"L{i}" for i in range(10)], "solubility_ok": [True] * 10, "permeability_ok": [True] * 10,
        "cytotoxicity_ok": [True] * 10, "herg_ok": [True] * 10, "metabolic_stability_ok": [True] * 10,
    }), "admet_results.csv")
    truth = [i % 2 == 0 for i in range(20)]
    _write_pack(tmp_path, "protein_ligand_codesign", "prospective_assay_validation", pd.DataFrame({
        "compound_id": [f"L{i}" for i in range(20)], "predicted_active": truth, "experimental_active": truth,
        "planned_before_assay": [True] * 20,
    }), "prospective_assay.csv")

    for module_key in ("protein_language_design", "protein_ligand_codesign"):
        results = [validate_evidence_folder(tmp_path, module_key, requirement) for requirement in PROFILES[module_key].requirements]
        assert all(result.qualified for result in results)


def test_step181_microbiome_real_evidence_validators(tmp_path: Path):
    _write_pack(tmp_path, "strain_microbiome", "licensed_reference_database")
    expected = [i % 3 != 0 for i in range(12)]
    _write_pack(tmp_path, "strain_microbiome", "real_mock_community", pd.DataFrame({
        "sample_id": ["M1"] * 12, "strain_id": [f"S{i}" for i in range(12)],
        "expected_present": expected, "called_present": expected,
        "expected_abundance": [i + 1 for i in range(12)], "estimated_abundance": [(i + 1) * 1.01 for i in range(12)],
    }), "mock_community_results.csv")
    _write_pack(tmp_path, "strain_microbiome", "contamination_controls", pd.DataFrame({
        "sample_id": [f"N{i}" for i in range(5)], "control_type": ["extraction_blank"] * 5,
        "total_reads": [100000] * 5, "contaminant_reads": [500, 2000, 400, 300, 1500],
        "flagged": [False, True, False, False, True],
    }), "contamination_controls.csv")
    _write_pack(tmp_path, "strain_microbiome", "strain_ground_truth", pd.DataFrame({
        "sample_id": ["G1"] * 10, "strain_id": [f"S{i}" for i in range(10)],
        "expected_present": [True] * 10, "called_present": [True] * 10, "ani": [0.995] * 10,
        "coverage": [0.90] * 10, "ambiguous": [False] * 10,
    }), "strain_ground_truth.csv")
    _write_pack(tmp_path, "strain_microbiome", "independent_site_validation", pd.DataFrame({
        "site_id": ["S1", "S1", "S2", "S2"], "sample_id": ["A", "B", "C", "D"],
        "precision": [0.92, 0.90, 0.91, 0.93], "recall": [0.90, 0.91, 0.92, 0.90],
        "abundance_corr": [0.91, 0.92, 0.90, 0.93],
    }), "site_validation.csv")
    results = [validate_evidence_folder(tmp_path, "strain_microbiome", requirement) for requirement in PROFILES["strain_microbiome"].requirements]
    assert all(result.qualified for result in results)


def test_step181_bundle_import_rejects_path_traversal(tmp_path: Path):
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    result = import_bundle(tmp_path, bundle, "phenotypic_screening", "physical_instrument_qualification")
    assert not result.imported
    assert any("unsafe archive path" in blocker for blocker in result.blockers)
