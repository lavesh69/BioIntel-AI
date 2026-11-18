from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.external_readiness_v181 import PROFILES, TARGET_MODULES


def _frames() -> dict[tuple[str, str], pd.DataFrame | bytes]:
    patients = list(range(30))
    labels = [i % 2 == 0 for i in patients]
    predictions = [0.90 if label else 0.10 for label in labels]
    review_labels = ["positive" if label else "negative" for label in labels]
    experimental = [5 + i * 0.1 for i in range(20)]
    truth = [i % 2 == 0 for i in range(20)]
    expected = [i % 3 != 0 for i in range(12)]
    return {
        ("phenotypic_screening", "physical_instrument_qualification"): pd.DataFrame({
            "run_id": ["DEMO-R1", "DEMO-R2", "DEMO-R3"],
            "field_flatness_pct": [5.1, 6.0, 4.7], "focus_cv_pct": [5.0, 5.8, 4.5],
            "illumination_cv_pct": [4.1, 5.0, 5.6], "stage_error_um": [2.0, 3.0, 2.2],
            "passed": [True, True, True],
        }),
        ("phenotypic_screening", "multi_plate_validation"): pd.DataFrame({
            "plate_id": ["DEMO-P1", "DEMO-P2", "DEMO-P3"],
            "positive_mean": [100, 102, 98], "positive_sd": [2, 2, 2],
            "negative_mean": [0, 1, -1], "negative_sd": [2, 2, 2],
            "replicate_corr": [0.91, 0.90, 0.92], "edge_effect_pct": [5, 6, 5],
        }),
        ("phenotypic_screening", "segmentation_ground_truth"): pd.DataFrame({
            "image_id": [f"DEMO-I{i:02d}" for i in range(20)],
            "dice": [0.90] * 20, "iou": [0.82] * 20, "object_f1": [0.91] * 20,
            "reviewer_approved": [True] * 20,
        }),
        ("phenotypic_screening", "biological_replicates_external_site"): pd.DataFrame({
            "site_id": ["DEMO-S1", "DEMO-S1", "DEMO-S2", "DEMO-S2"],
            "batch_id": ["DEMO-B1", "DEMO-B2", "DEMO-B3", "DEMO-B4"],
            "replicate_corr": [0.90, 0.88, 0.89, 0.91],
            "confirmed_hit_rate": [0.80, 0.75, 0.78, 0.82],
        }),
        ("phenotypic_screening", "orthogonal_assay_confirmation"): pd.DataFrame({
            "candidate_id": [f"DEMO-C{i:02d}" for i in range(10)],
            "primary_effect": list(range(10)),
            "orthogonal_effect": [value * 1.02 for value in range(10)],
            "confirmed": [True] * 8 + [False] * 2,
        }),
        ("spatial_omics_pathology", "scanner_qualification"): pd.DataFrame({
            "scanner_id": ["DEMO-SC1", "DEMO-SC1", "DEMO-SC2"],
            "colour_delta_e": [2, 3, 2], "focus_failure_pct": [1, 1, 1],
            "tile_artifact_pct": [1, 1, 1], "registration_error_um": [5, 6, 5],
            "passed": [True, True, True],
        }),
        ("spatial_omics_pathology", "stain_site_drift_validation"): pd.DataFrame({
            "site_id": ["DEMO-S1", "DEMO-S1", "DEMO-S2", "DEMO-S2"],
            "scanner_id": ["DEMO-SC1", "DEMO-SC1", "DEMO-SC2", "DEMO-SC2"],
            "stain_batch": ["A", "B", "A", "B"],
            "embedding_shift": [0.10, 0.12, 0.11, 0.09],
            "auc_drop": [0.02, 0.03, 0.02, 0.01],
            "calibration_error": [0.02, 0.03, 0.02, 0.03],
        }),
        ("spatial_omics_pathology", "patient_external_cohort"): pd.DataFrame({
            "patient_id": [f"DEMO-P{i:02d}" for i in patients],
            "site_id": ["DEMO-S1" if i < 15 else "DEMO-S2" for i in patients],
            "prediction": predictions, "label": labels,
        }),
        ("spatial_omics_pathology", "pathologist_agreement"): pd.DataFrame({
            "case_id": [f"DEMO-C{i:02d}" for i in patients],
            "model_label": review_labels, "reviewer1_label": review_labels,
            "reviewer2_label": review_labels,
        }),
        ("spatial_omics_pathology", "prospective_clinical_validation"): pd.DataFrame({
            "case_id": [f"DEMO-PC{i:02d}" for i in patients],
            "prediction": predictions, "label": labels,
            "pre_specified_before_outcome": [True] * 30,
        }),
        ("protein_language_design", "authentic_trained_weights"): b"BIOINTEL-DEMO-WEIGHTS-NOT-A-REAL-MODEL\n",
        ("protein_language_design", "independent_sequence_benchmark"): pd.DataFrame({
            "benchmark_id": ["DEMO-B1", "DEMO-B2"], "metric_name": ["accuracy", "f1"],
            "metric_value": [0.90, 0.88], "threshold": [0.80, 0.80],
            "independent": [True, True], "identity_to_train_max": [0.50, 0.60],
        }),
        ("protein_language_design", "novelty_verification"): pd.DataFrame({
            "sequence_id": [f"DEMO-S{i:02d}" for i in range(20)],
            "sequence": ["MKTAYIAKQRQISFVKSHFS" + "A" * i for i in range(20)],
            "max_identity_to_training": [0.50] * 20, "max_kmer_jaccard": [0.40] * 20,
            "restricted_motif": [False] * 20, "duplicate": [False] * 20,
        }),
        ("protein_language_design", "structure_confirmation"): pd.DataFrame({
            "sequence_id": [f"DEMO-S{i:02d}" for i in range(10)],
            "method": ["demo-independent-model"] * 10, "plddt": [85] * 10,
            "ptm": [0.75] * 10, "independent_or_experimental": [True] + [False] * 9,
        }),
        ("protein_language_design", "wet_lab_expression"): pd.DataFrame({
            "sequence_id": [f"DEMO-S{i:02d}" for i in range(5)],
            "expression_yield_mg_l": [10] * 5, "soluble_fraction": [0.8] * 5,
            "purity_pct": [90] * 5, "activity_confirmed": [True] * 5,
        }),
        ("protein_ligand_codesign", "docking_engine_qualification"): pd.DataFrame({
            "complex_id": [f"DEMO-X{i:02d}" for i in range(20)],
            "predicted_rmsd": [1.2] * 20, "rank": [1] * 20,
            "engine_version": ["demo-pinned"] * 20, "reference_pose": ["demo-experimental"] * 20,
        }),
        ("protein_ligand_codesign", "experimental_binding_affinity"): pd.DataFrame({
            "compound_id": [f"DEMO-L{i:02d}" for i in range(20)], "target_id": ["DEMO-T"] * 20,
            "predicted_pkd": [value + 0.1 for value in experimental],
            "experimental_pkd": experimental, "assay_type": ["DEMO-SPR"] * 20,
        }),
        ("protein_ligand_codesign", "selectivity_panel"): pd.DataFrame({
            "compound_id": [f"DEMO-L{i:02d}" for i in range(10)],
            "panel_size": [8] * 10, "selectivity_pass": [True] * 8 + [False] * 2,
        }),
        ("protein_ligand_codesign", "admet_confirmation"): pd.DataFrame({
            "compound_id": [f"DEMO-L{i:02d}" for i in range(10)],
            "solubility_ok": [True] * 10, "permeability_ok": [True] * 10,
            "cytotoxicity_ok": [True] * 10, "herg_ok": [True] * 10,
            "metabolic_stability_ok": [True] * 10,
        }),
        ("protein_ligand_codesign", "prospective_assay_validation"): pd.DataFrame({
            "compound_id": [f"DEMO-L{i:02d}" for i in range(20)],
            "predicted_active": truth, "experimental_active": truth,
            "planned_before_assay": [True] * 20,
        }),
        ("strain_microbiome", "licensed_reference_database"): b"BIOINTEL-DEMO-REFERENCE-DB-NOT-LICENSED-FOR-RELEASE\n",
        ("strain_microbiome", "real_mock_community"): pd.DataFrame({
            "sample_id": ["DEMO-M1"] * 12, "strain_id": [f"DEMO-ST{i:02d}" for i in range(12)],
            "expected_present": expected, "called_present": expected,
            "expected_abundance": [i + 1 for i in range(12)],
            "estimated_abundance": [(i + 1) * 1.01 for i in range(12)],
        }),
        ("strain_microbiome", "contamination_controls"): pd.DataFrame({
            "sample_id": [f"DEMO-N{i}" for i in range(5)],
            "control_type": ["extraction_blank"] * 5, "total_reads": [100000] * 5,
            "contaminant_reads": [500, 2000, 400, 300, 1500],
            "flagged": [False, True, False, False, True],
        }),
        ("strain_microbiome", "strain_ground_truth"): pd.DataFrame({
            "sample_id": ["DEMO-G1"] * 10, "strain_id": [f"DEMO-ST{i:02d}" for i in range(10)],
            "expected_present": [True] * 10, "called_present": [True] * 10,
            "ani": [0.995] * 10, "coverage": [0.90] * 10, "ambiguous": [False] * 10,
        }),
        ("strain_microbiome", "independent_site_validation"): pd.DataFrame({
            "site_id": ["DEMO-S1", "DEMO-S1", "DEMO-S2", "DEMO-S2"],
            "sample_id": ["A", "B", "C", "D"],
            "precision": [0.92, 0.90, 0.91, 0.93], "recall": [0.90, 0.91, 0.92, 0.90],
            "abundance_corr": [0.91, 0.92, 0.90, 0.93],
        }),
    }


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_demo_evidence(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    base = project / "UserData" / "step182" / "demo_evidence"
    frames = _frames()
    written: list[str] = []
    for module_key in TARGET_MODULES:
        profile = PROFILES[module_key]
        for requirement in profile.requirements:
            folder = base / module_key / requirement.evidence_id
            folder.mkdir(parents=True, exist_ok=True)
            item = frames[(module_key, requirement.evidence_id)]
            if requirement.data_file:
                data_path = folder / requirement.data_file
                assert isinstance(item, pd.DataFrame)
                item.to_csv(data_path, index=False)
            else:
                data_path = folder / ("demo_model_weights.bin" if module_key == "protein_language_design" else "demo_reference_database.bin")
                assert isinstance(item, bytes)
                data_path.write_bytes(item)
            manifest = {
                "schema": "biointel.step182.demo-evidence-manifest.v1",
                "module_key": module_key,
                "evidence_id": requirement.evidence_id,
                "evidence_title": requirement.title,
                "source_organization": "BioIntel AI Demo Data Generator",
                "source_contact": "demo-only@example.invalid",
                "acquisition_date": "2026-07-14",
                "licence_or_permission": "Synthetic demo fixture; test and UI demonstration only",
                "provenance_record": "Deterministically generated by Step 182 from documented synthetic fixtures",
                "real_world_evidence": False,
                "synthetic_or_demo": True,
                "independent_from_development_team": False,
                "deidentified_or_nonhuman": True,
                "reviewer_name": "Demo Validator",
                "reviewer_role": "Automated synthetic-fixture validator",
                "review_signed": False,
                "review_date": "2026-07-14",
                "controlled_release_eligible": False,
                "demo_execution_eligible": True,
                "files": [{"path": data_path.name, "sha256": _digest(data_path)}],
                "notes": "DEMO ONLY. Never use this evidence for scientific, clinical, wet-lab or controlled-release claims.",
            }
            (folder / "qualification_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (folder / "README.md").write_text(
                f"# DEMO ONLY — {requirement.title}\n\n"
                f"Module: **{profile.title}**\n\n"
                "This folder contains synthetic data designed to exercise parsers, metrics, charts and acceptance gates.\n\n"
                "It is **not real evidence**, is **not independently sourced**, and cannot unlock controlled scientific release.\n\n"
                f"The synthetic fixture is shaped to demonstrate this acceptance rule: {requirement.acceptance_summary}\n",
                encoding="utf-8",
            )
            written.extend(str(path.relative_to(project)) for path in (data_path, folder / "qualification_manifest.json", folder / "README.md"))
    (project / "data" / "step182").mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "biointel.step182.demo-evidence-workspace.v1",
        "module_count": len(TARGET_MODULES),
        "demo_pack_count": sum(len(PROFILES[key].requirements) for key in TARGET_MODULES),
        "real_evidence_count": 0,
        "controlled_release_eligible": False,
        "base": str(base),
        "written_files": written,
    }
    (project / "data" / "step182" / "demo_workspace_index.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


__all__ = ["build_demo_evidence"]
