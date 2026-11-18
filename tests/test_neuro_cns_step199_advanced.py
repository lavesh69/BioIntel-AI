from __future__ import annotations

import numpy as np
import pandas as pd

from biointel.neuro_cns.advanced import (
    ADVANCED_FEATURES,
    aggregation_mutation_engineering,
    brain_digital_twin_viewer,
    compound_optimization_board,
    dose_to_effect_simulator,
    experimental_model_selection_assistant,
    multiomics_disease_signature_builder,
    neurophysiology_review_board,
    rare_neurological_disease_board,
    safety_margin_matrix,
)
from biointel.neuro_cns.demos import DEMO_AGGREGATION_SEQUENCE, DEMO_SMILES, eeg, omics, variants
from biointel.neuro_cns.recommendations import recommendation_frame


def test_all_nine_advanced_features_are_registered() -> None:
    assert len(ADVANCED_FEATURES) == 9
    assert len({item[2] for item in ADVANCED_FEATURES}) == 9


def test_compound_optimization_board_and_pareto() -> None:
    result = compound_optimization_board([
        {"compound_id": "caffeine", "smiles": DEMO_SMILES["Caffeine"], "potency_nm": 500},
        {"compound_id": "diazepam", "smiles": DEMO_SMILES["Diazepam"], "potency_nm": 20},
        {"compound_id": "bad", "smiles": "not-a-smiles"},
    ])
    assert len(result["comparison"]) == 3
    assert result["recommended_screening_candidate"] in {"caffeine", "diazepam"}
    assert result["pareto_optimal_compounds"]


def test_safety_margin_matrix_has_exposure_context() -> None:
    result = safety_margin_matrix(20, [
        {"target": "DRD2", "kd": 5, "unit": "nM"},
        {"target": "HTR2A", "kd": 50, "unit": "nM"},
    ], primary_targets=["DRD2"])
    assert result["free_brain_concentration_nm"] == 20
    assert set(result["matrix"]["role"]) == {"primary", "off_target"}


def test_aggregation_mutation_engineering_is_fail_closed() -> None:
    sequence = "A" + DEMO_AGGREGATION_SEQUENCE[1:]
    result = aggregation_mutation_engineering(sequence, ["A1T", "Z999A"])
    assert result["mutation_comparison"].iloc[0]["error"] is None
    assert result["mutation_comparison"].iloc[1]["error"]


def test_model_selection_and_rare_disease_board() -> None:
    model = experimental_model_selection_assistant("TREM2", disease="Alzheimer disease")
    assert len(model["ranked_models"]) == 6
    board = rare_neurological_disease_board(variants(), phenotype_terms=["seizure"], disease="Epilepsy")
    assert not board["variant_board"].empty
    assert "board_score" in board["variant_board"]


def test_dose_to_effect_builds_time_window() -> None:
    result = dose_to_effect_simulator(
        {
            "initial_plasma_concentration": 100.0,
            "half_life_hours": 6.0,
            "duration_hours": 24.0,
            "passive_permeability_factor": 0.8,
            "efflux_ratio": 0.3,
            "fraction_unbound_plasma": 0.1,
            "fraction_unbound_brain": 0.08,
        },
        [{"target": "DRD2", "kd": 5, "unit": "nM"}, {"target": "HTR2A", "kd": 60, "unit": "nM"}],
        primary_targets=["DRD2"],
    )
    assert "inside_effect_window" in result["dose_to_effect_curve"]
    assert not result["target_occupancy_long"].empty


def test_multiomics_signature_builder_cross_validates() -> None:
    result = multiomics_disease_signature_builder(omics(), "group", maximum_features=4)
    assert 0.5 <= result["cross_validated_auc"] <= 1.0
    assert len(result["selected_signature_features"]) <= 4


def test_neurophysiology_review_board_and_digital_twin() -> None:
    signal = neurophysiology_review_board(eeg(), 256.0, "time")
    assert "channel_review_board" in signal
    volume = np.zeros((12, 12, 8), dtype=float)
    volume[3:9, 4:10, 2:7] = 2.0
    twin = brain_digital_twin_viewer(volume, threshold=1.0, overlay_points=[{"x": 5, "y": 5, "z": 4, "label": "focus"}])
    assert twin["surface_point_count"] > 0
    assert len(twin["overlay_points"]) == 1


def test_recommendations_cover_all_modules() -> None:
    frame = recommendation_frame()
    assert len(frame) == 41
    assert frame["module"].nunique() == 41


def test_advanced_results_feed_consistency_rules() -> None:
    from biointel.neuro_cns.consistency import evaluate_results

    findings = evaluate_results({
        "advanced_safety_margin": {"high_off_target_count": 2},
        "advanced_dose_effect": {"time_inside_effect_window_hours": 0.0},
        "advanced_multiomics_signature": {"cross_validated_auc": 0.58},
        "advanced_neurophysiology_review": {"signal_quality_grade": "poor"},
        "advanced_brain_digital_twin": {"surface_point_count": 0},
    })
    rules = set(findings["rule"].astype(str))
    assert {"HIGH_OFF_TARGET_OCCUPANCY", "NO_SIMULATED_EFFECT_WINDOW", "WEAK_INTERNAL_SIGNATURE", "POOR_SIGNAL_QUALITY", "EMPTY_DIGITAL_TWIN_SURFACE"} <= rules


def test_advanced_background_job_executes(tmp_path) -> None:
    from biointel.jobs.local_queue import LocalJobQueue
    from biointel.jobs.worker import LocalWorker
    from biointel.neuro_cns.jobs import submit_neuro_job

    job = submit_neuro_job(
        tmp_path,
        "advanced_compound_optimization",
        {"compound_rows": [{"compound_id": "caffeine", "smiles": DEMO_SMILES["Caffeine"]}]},
    )
    worker = LocalWorker(tmp_path, worker_id="step199-neuro-worker")
    run = worker.run_once()
    assert run.status == "completed"
    stored = LocalJobQueue(tmp_path / "reports" / "jobs.sqlite3").get(job.job_id)
    assert stored.result["module_key"] == "advanced_compound_optimization"
