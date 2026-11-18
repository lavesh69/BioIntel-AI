from __future__ import annotations

import numpy as np

from biointel.neuro_cns.catalog import MODULES, MODULE_BY_KEY, WORKSPACES
from biointel.neuro_cns.chemistry import bbb_batch, bbb_permeability, receptor_occupancy
from biointel.neuro_cns.demos import (
    DEMO_GPCR_SEQUENCE,
    DEMO_PROTEIN_SEQUENCE,
    DEMO_SMILES,
    binding_profile,
    cohort,
    eeg,
    omics,
)
from biointel.neuro_cns.omics import biomarker_discovery
from biointel.neuro_cns.precision import stratify_research_cohort
from biointel.neuro_cns.safety import cns_side_effects, off_target_neurotoxicity
from biointel.neuro_cns.signals import analyze_neural_signals
from biointel.neuro_cns.targets import classify_gpcr, classify_ion_channel, target_tagging


def test_catalog_contains_41_unique_neuro_modules() -> None:
    assert len(MODULES) == 41
    assert len(MODULE_BY_KEY) == 41
    assert len({module.number for module in MODULES}) == 41
    assert len(WORKSPACES) == 5


def test_bbb_screen_is_deterministic_and_batch_isolates_invalid_rows() -> None:
    first = bbb_permeability(DEMO_SMILES["Caffeine"], "caffeine")
    second = bbb_permeability(DEMO_SMILES["Caffeine"], "caffeine")
    assert first == second
    frame = bbb_batch(
        [
            {"compound_id": "valid", "smiles": DEMO_SMILES["Caffeine"]},
            {"compound_id": "invalid", "smiles": "not-a-smiles"},
        ]
    )
    assert len(frame) == 2
    assert frame.loc[0, "error"] is None
    assert isinstance(frame.loc[1, "error"], str)


def test_target_and_sequence_classifiers_fail_open_to_explicit_uncertainty() -> None:
    assert target_tagging("DRD2")["is_neuro_relevant"] is True
    assert target_tagging("UNLISTED_TARGET")["is_neuro_relevant"] is False
    assert classify_ion_channel(DEMO_PROTEIN_SEQUENCE)["is_ion_channel"] is True
    assert classify_gpcr(DEMO_GPCR_SEQUENCE)["is_neuro_gpcr"] is True


def test_neurotoxicity_and_side_effect_coverage_are_bounded_by_input() -> None:
    rows = binding_profile().to_dict(orient="records")
    flags = off_target_neurotoxicity(rows)
    effects = cns_side_effects(rows)
    assert flags["flag_count"] >= 1
    assert 0 < effects["coverage"]["coverage_fraction"] < 1
    assert effects["excluded_targets"]


def test_receptor_occupancy_matches_mass_action_equation() -> None:
    result = receptor_occupancy(20.0, [{"target": "DRD2", "kd": 5.0}])
    assert result.loc[0, "occupancy_percent"] == 80.0


def test_neural_signal_demo_detects_alpha_dominant_channel() -> None:
    result = analyze_neural_signals(eeg(), 256.0, "time")
    summary = result["channel_summary"].set_index("channel")
    assert summary.loc["Fz", "alpha_relative"] > 0.8


def test_biomarker_and_precision_workflows_return_ranked_outputs() -> None:
    biomarkers = biomarker_discovery(omics(), "group")
    assert not biomarkers.empty
    assert biomarkers.iloc[0]["exploratory_rank_score"] >= biomarkers.iloc[-1]["exploratory_rank_score"]
    stratified = stratify_research_cohort(cohort(), identifier_column="sample_id", cluster_count=3)
    assert len(stratified["assignments"]) == len(cohort())
    assert stratified["quality_metrics"]["clusters"] == 3
    assert np.isfinite(stratified["quality_metrics"]["inertia"])
