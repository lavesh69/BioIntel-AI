from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from biointel.neuro_cns.chemistry import (
    bbb_reference_validation,
    cns_drug_adme_workflow,
    receptor_occupancy_kinetics,
    simulate_brain_exposure_population,
)
from biointel.neuro_cns.clinical import trial_intelligence
from biointel.neuro_cns.demos import (
    DEMO_GPCR_SEQUENCE,
    DEMO_SMILES,
    binding_profile,
    cohort,
    eeg,
    omics,
    roi_timeseries,
    trials,
    variants,
)
from biointel.neuro_cns.genetics import variant_interpretation_workflow
from biointel.neuro_cns.imaging import connectivity_from_timeseries, volume_qc_workflow
from biointel.neuro_cns.ingestion import iter_tabular_chunks, read_tabular_bytes
from biointel.neuro_cns.omics import biomarker_discovery_workflow
from biointel.neuro_cns.precision import precision_neurology_workflow
from biointel.neuro_cns.safety import off_target_safety_workflow
from biointel.neuro_cns.signals import neural_signal_workflow
from biointel.neuro_cns.targets import expression_atlas_analysis, sequence_topology_track, target_mechanism_workflow
from biointel.neuro_cns.visuals import (
    chemistry_figures,
    connectivity_figures,
    expression_atlas_figures,
    imaging_slice_figures,
    omics_figures,
    pk_figures,
    precision_figures,
    safety_figures,
    sequence_topology_figure,
    signal_figures,
    target_evidence_graph_figure,
    trial_figures,
    variant_figures,
)

ROOT = Path(__file__).resolve().parents[1]


def test_expression_atlas_accepts_versioned_uploaded_long_form_data() -> None:
    atlas = pd.DataFrame({
        "gene": ["TREM2", "TREM2", "TREM2", "SNCA"],
        "region": ["cortex", "hippocampus", "cortex", "striatum"],
        "cell_type": ["microglia", "microglia", "astrocyte", "neuron"],
        "condition": ["control", "control", "disease", "control"],
        "expression": [8.0, 4.0, 3.0, 2.0],
    })
    result = expression_atlas_analysis("TREM2", atlas, source_name="unit atlas", source_version="2026-07")
    assert result["found"] is True
    assert result["matched_rows"] == 3
    assert result["provenance"]["source_version"] == "2026-07"
    assert result["top_region"] == "cortex"
    assert "regional" in expression_atlas_figures(result)


def test_omics_workflow_is_leakage_aware_and_calibrated() -> None:
    frame = omics().copy()
    frame["batch"] = ["A", "B"] * (len(frame) // 2)
    result = biomarker_discovery_workflow(frame, "group", batch_column="batch", permutation_iterations=3, bootstrap_iterations=10)
    assert result["model_metrics"]["cross_validation_folds"] >= 3
    assert 0.5 <= result["model_metrics"]["direction_adjusted_roc_auc"] <= 1.0
    assert not result["calibration_table"].empty
    assert "volcano" in omics_figures(result)


def test_neurogenetics_expands_multiallelic_and_keeps_research_boundary() -> None:
    frame = variants().copy()
    frame.loc[0, "alt"] = "T,G"
    frame["genome_build"] = "GRCh38"
    frame["phenotype"] = "seizure;epilepsy"
    result = variant_interpretation_workflow(frame, phenotype_terms=["epilepsy"])
    assert result["build_detection"]["genome_build"] == "GRCh38"
    assert result["input_summary"]["expanded_allele_rows"] >= len(frame) + 1
    assert "clinical diagnosis" in result["scientific_boundary"].lower() or "research" in result["scientific_boundary"].lower()
    assert isinstance(variant_figures(result), dict)


def test_signal_workflow_produces_qc_spectrogram_and_erp() -> None:
    frame = eeg(seconds=4)
    frame["event"] = ""
    for event_time in (1.0, 2.0, 3.0):
        frame.loc[(frame["time"] - event_time).abs().idxmin(), "event"] = "stim"
    result = neural_signal_workflow(frame, sampling_rate_hz=256.0, time_column="time", event_column="event", reference_mode="average", run_ica_review=True)
    assert not result["channel_summary"].empty
    assert not result["spectrogram"].empty
    assert not result["evoked_response"].empty
    assert "waveform" in signal_figures(result)


def test_imaging_qc_and_connectivity_network_outputs() -> None:
    rng = np.random.default_rng(12)
    volume = rng.normal(size=(12, 10, 8))
    atlas = np.zeros_like(volume, dtype=int)
    atlas[:6] = 1
    atlas[6:] = 2
    result = volume_qc_workflow(volume, metadata={"orientation_codes": ["R", "A", "S"], "voxel_spacing_mm": [1.0, 1.0, 1.5]}, atlas_labels=atlas)
    assert result["orientation_qc"]["orientation_codes"] == ["R", "A", "S"]
    assert len(result["orthogonal_slices"]) == 3
    assert isinstance(imaging_slice_figures(result), dict)
    connectivity = connectivity_from_timeseries(roi_timeseries(), "time", threshold_absolute=0.2)
    assert connectivity["network_summary"]["node_count"] == 4
    assert "matrix" in connectivity_figures(connectivity)


def test_precision_workflow_reports_consensus_and_confound_review() -> None:
    frame = cohort()
    frame["site"] = ["A", "B", "C"] * (len(frame) // 3)
    result = precision_neurology_workflow(frame, identifier_column="sample_id", subgroup_column="site", confound_columns=["site"], consensus_iterations=5)
    assert not result["consensus_matrix"].empty
    assert not result["seed_stability"].empty
    assert "clusters" in precision_figures(result)


def test_adme_bbb_reference_pk_and_occupancy_workflows() -> None:
    smiles = DEMO_SMILES["Caffeine"]
    reference = pd.DataFrame({"smiles": list(DEMO_SMILES.values())})
    adme = cns_drug_adme_workflow(smiles, reference_frame=reference)
    assert adme["bbb_screen"]["classification"]
    assert adme["reference_chemical_space"]["valid_reference_compounds"] >= 1
    assert "mpo" in chemistry_figures(adme)

    labelled = pd.DataFrame({"id": ["a", "b", "c", "d"], "smiles": list(DEMO_SMILES.values()), "bbb_label": [1, 1, 1, 0]})
    validation = bbb_reference_validation(labelled, id_column="id")
    assert validation["validation_metrics"]["evaluated_rows"] == 4

    parameters = {
        "initial_plasma_concentration": 100.0,
        "half_life_hours": 8.0,
        "duration_hours": 24.0,
        "passive_permeability_factor": 1.0,
        "efflux_ratio": 1.5,
        "fraction_unbound_plasma": 0.2,
        "fraction_unbound_brain": 0.1,
        "effective_threshold": 5.0,
        "route": "oral",
        "absorption_half_life_hours": 1.0,
        "dose_count": 2,
        "dosing_interval_hours": 12.0,
    }
    population = simulate_brain_exposure_population(parameters, simulations=10)
    exposure = population["percentile_curve"][["time_hours", "brain_unbound_p50"]].rename(columns={"brain_unbound_p50": "brain_unbound"})
    occupancy = receptor_occupancy_kinetics(exposure, [{"target": "DRD2", "kd": 5.0, "kon": 0.1, "koff": 0.5, "role": "primary"}])
    figures = pk_figures(population, occupancy)
    assert {"exposure", "occupancy"} <= set(figures)


def test_target_pathway_gpcr_topology_and_evidence_graph() -> None:
    evidence = pd.DataFrame([
        {"entity": "dopamine signaling", "entity_type": "pathway", "relationship": "participates_in", "direction": "supporting", "source": "PMID:demo"},
        {"entity": "dopamine signaling", "entity_type": "pathway", "relationship": "participates_in", "direction": "opposing", "source": "PMID:demo2"},
    ])
    result = target_mechanism_workflow("DRD2", sequence=DEMO_GPCR_SEQUENCE, evidence_frame=evidence)
    topology = result["sequence_topology"]
    assert topology["protein_class_review"] == "gpcr"
    assert topology["gpcr_classification"]["confidence_score"] >= topology["ion_channel_classification"]["confidence_score"]
    assert not result["evidence_graph"]["conflicting_evidence"].empty
    assert len(target_evidence_graph_figure(result["evidence_graph"]).data) >= 1
    assert len(sequence_topology_figure(topology).data) >= 1


def test_off_target_workflow_separates_unknown_and_visualizes_coverage() -> None:
    rows = binding_profile().to_dict(orient="records") + [{"target_id": "UNKNOWN_X", "binding_score": 0.9}]
    result = off_target_safety_workflow(rows, primary_target="DRD2", free_brain_concentration=20.0)
    assert len(result["unmatched_or_unknown_targets"]) == 1
    assert result["off_target_flags"]["primary_target_excluded"] is True
    figures = safety_figures(result)
    assert "coverage" in figures
    assert "side_effects" in figures


def test_trial_intelligence_tracks_provenance_endpoints_and_optional_links() -> None:
    frame = trials().copy()
    frame.loc[0, "trial_id"] = "NCT00000001"
    frame["sponsor"] = ["A", "B", "C"]
    frame["evidence_date"] = ["2026-07-01", "2026-06-01", "2025-01-01"]
    result = trial_intelligence(frame, source_name="unit registry export", source_version="2026-07")
    assert result["source_provenance"]["live_provider_connected"] is False
    assert result["source_provenance"]["source_version"] == "2026-07"
    assert result["normalized_trials"]["registry_url"].notna().any()
    assert not result["endpoint_summary"].empty
    assert "phase" in trial_figures(result)


def test_large_tabular_upload_is_staged_and_chunk_iterable(tmp_path: Path) -> None:
    data = ("a,b\n" + "\n".join(f"{index},{index + 1}" for index in range(2500))).encode()
    payload = read_tabular_bytes(data, "large.csv", interactive_limit_bytes=100, stage_directory=tmp_path, preview_rows=150)
    assert payload.preview_only is True
    assert payload.staged_path is not None
    assert payload.preview_rows == 150
    chunks = list(iter_tabular_chunks(payload, chunksize=1000))
    assert sum(len(chunk) for chunk in chunks) == 2500


def test_step205_ui_connects_new_workflows_and_visuals() -> None:
    source = (ROOT / "src/biointel/neuro_cns/ui.py").read_text(encoding="utf-8")
    required_tokens = {
        "expression_atlas_analysis(",
        "biomarker_discovery_workflow(",
        "variant_interpretation_workflow(",
        "neural_signal_workflow(",
        "volume_qc_workflow(",
        "precision_neurology_workflow(",
        "bbb_reference_validation(",
        "cns_drug_adme_workflow(",
        "simulate_brain_exposure_population(",
        "receptor_occupancy_kinetics(",
        "target_mechanism_workflow(",
        "off_target_safety_workflow(",
        "trial_intelligence(",
        "sequence_topology_figure(",
    }
    missing = sorted(token for token in required_tokens if token not in source)
    assert not missing
