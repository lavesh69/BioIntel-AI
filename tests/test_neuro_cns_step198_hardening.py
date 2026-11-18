from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from biointel.neuro_cns.chemistry import (
    bbb_permeability,
    blood_csf_barrier,
    cns_adme_transporters,
    cns_drug_likeness,
    receptor_occupancy,
    simulate_brain_exposure,
)
from biointel.neuro_cns.clinical import trial_intelligence
from biointel.neuro_cns.consistency import evaluate_results
from biointel.neuro_cns.demos import (
    DEMO_AGGREGATION_SEQUENCE,
    DEMO_GPCR_SEQUENCE,
    DEMO_PROTEIN_SEQUENCE,
    DEMO_SMILES,
    binding_profile,
    cohort,
    eeg,
    omics,
    trials,
    variants,
)
from biointel.neuro_cns.genetics import prioritize_variants
from biointel.neuro_cns.imaging import load_image_payload, profile_image_array
from biointel.neuro_cns.omics import biomarker_discovery
from biointel.neuro_cns.precision import stratify_research_cohort
from biointel.neuro_cns.projects import load_project, save_project
from biointel.neuro_cns.reporting import bundle_html, bundle_json, bundle_markdown
from biointel.neuro_cns.safety import aggregation_risk, cns_side_effects, off_target_neurotoxicity
from biointel.neuro_cns.schemas import concentration_to_nm, normalize_affinity_rows
from biointel.neuro_cns.signals import analyze_neural_signals, load_signal_payload
from biointel.neuro_cns.targets import (
    brain_expression_profile,
    classify_gpcr,
    classify_ion_channel,
    disease_target_table,
    model_organism_cross_reference,
    neuroinflammation_lookup,
    pathway_mapping,
    target_tagging,
)
from biointel.neuro_cns.workflows import compound_to_clinic_workflow, disease_workflow_plan, target_to_translation_workflow


@pytest.fixture(scope="module")
def binding_rows() -> list[dict[str, object]]:
    return binding_profile().to_dict(orient="records")


@pytest.mark.parametrize(
    ("module_number", "runner"),
    [
        (1, lambda: bbb_permeability(DEMO_SMILES["Caffeine"])),
        (2, lambda: target_tagging("DRD2")),
        (3, lambda: pathway_mapping("DRD2")),
        (4, lambda: classify_ion_channel(DEMO_PROTEIN_SEQUENCE)),
        (5, lambda: classify_gpcr(DEMO_GPCR_SEQUENCE)),
        (6, lambda: disease_target_table(disease="Alzheimer disease")),
        (7, lambda: cns_drug_likeness(DEMO_SMILES["Caffeine"])),
        (9, lambda: aggregation_risk(DEMO_AGGREGATION_SEQUENCE)),
        (11, lambda: neuroinflammation_lookup("TREM2")),
        (12, lambda: blood_csf_barrier(DEMO_SMILES["Caffeine"])),
        (13, lambda: model_organism_cross_reference("DRD2")),
        (14, lambda: cns_adme_transporters(DEMO_SMILES["Caffeine"])),
        (16, lambda: receptor_occupancy(20.0, [{"target": "DRD2", "kd": 5.0, "unit": "nM"}])),
        (17, lambda: prioritize_variants(variants())),
        (18, lambda: brain_expression_profile("TREM2")),
        (19, lambda: biomarker_discovery(omics(), "group", bootstrap_iterations=20)),
        (20, lambda: analyze_neural_signals(eeg(), 256.0, "time")),
        (21, lambda: profile_image_array(np.pad(np.ones((8, 8, 4)), ((4, 4), (4, 4), (2, 2))), threshold=0.5)),
        (22, lambda: trial_intelligence(trials())),
        (23, lambda: stratify_research_cohort(cohort(), identifier_column="sample_id", cluster_count=3, bootstrap_iterations=5)),
    ],
)
def test_module_smoke_cases(module_number: int, runner) -> None:
    result = runner()
    assert result is not None, module_number
    if isinstance(result, pd.DataFrame):
        assert not result.empty, module_number


def test_binding_dependent_modules(binding_rows) -> None:
    assert off_target_neurotoxicity(binding_rows)["flag_count"] >= 1
    assert cns_side_effects(binding_rows)["coverage"]["covered_targets"] >= 1


def test_pk_multi_dose_and_occupancy_units() -> None:
    result = simulate_brain_exposure(
        initial_plasma_concentration=100,
        half_life_hours=6,
        duration_hours=48,
        passive_permeability_factor=0.8,
        efflux_ratio=0.4,
        fraction_unbound_plasma=0.1,
        fraction_unbound_brain=0.08,
        route="oral",
        absorption_half_life_hours=1.0,
        dose_count=3,
        dosing_interval_hours=12,
    )
    assert len(result["dose_times_hours"]) == 3
    assert result["peak_brain_unbound"] > 0
    occupancy = receptor_occupancy(0.02, [{"target": "DRD2", "kd": 5.0, "unit": "nM"}], concentration_unit="uM")
    assert occupancy.loc[0, "free_brain_concentration_nm"] == pytest.approx(20.0)


def test_unit_normalization_is_strict() -> None:
    assert concentration_to_nm(1, "uM") == pytest.approx(1000)
    rows = normalize_affinity_rows([{"target": "A", "kd": 2, "unit": "uM"}])
    assert rows[0]["affinity_nm"] == pytest.approx(2000)
    with pytest.raises(ValueError):
        concentration_to_nm(1, "banana")


def test_tabular_signal_loader_and_candidate_event_output() -> None:
    payload = load_signal_payload(eeg().to_csv(index=False).encode(), "recording.csv")
    assert payload["metadata"]["format"] == "tabular"
    result = analyze_neural_signals(payload["frame"], 256, "time")
    assert "candidate_events" in result
    assert result["signal_quality_grade"] in {"good", "review", "poor"}


def test_npy_image_loader_round_trip() -> None:
    import io

    source = np.arange(64, dtype=float).reshape(8, 8)
    stream = io.BytesIO()
    np.save(stream, source, allow_pickle=False)
    payload = load_image_payload(stream.getvalue(), "image.npy")
    assert payload["metadata"]["format"] == "NPY"
    assert np.array_equal(payload["array"], source)


def test_workflows_merge_modules_and_emit_consistency(binding_rows) -> None:
    compound = compound_to_clinic_workflow(
        DEMO_SMILES["Caffeine"],
        binding_rows=binding_rows,
        pk_parameters={
            "initial_plasma_concentration": 100.0,
            "half_life_hours": 6.0,
            "duration_hours": 24.0,
            "passive_permeability_factor": 0.75,
            "efflux_ratio": 0.35,
            "fraction_unbound_plasma": 0.1,
            "fraction_unbound_brain": 0.08,
        },
        free_brain_concentration=20,
        affinity_rows=[{"target": "DRD2", "kd": 5, "unit": "nM", "role": "primary"}],
    )
    assert "bbb_permeability" in compound["results"]
    assert isinstance(compound["consistency_findings"], pd.DataFrame)
    target = target_to_translation_workflow("DRD2", sequence=DEMO_GPCR_SEQUENCE)
    assert "gpcr_classifier" in target["results"]
    assert disease_workflow_plan("Epilepsy")["recommended_module_keys"]


def test_consistency_catches_low_side_effect_coverage() -> None:
    findings = evaluate_results({"cns_side_effects": {"coverage": {"coverage_fraction": 0.2}}})
    assert "LOW_SIDE_EFFECT_COVERAGE" in set(findings["rule"])


def test_project_persistence_and_report_formats(tmp_path) -> None:
    results = {"bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"])}
    path = save_project("Neuro hardening", results, metadata={"reviewer": "test"}, directory=tmp_path)
    loaded = load_project(path)
    assert loaded["results"]["bbb_permeability"]["classification"] == results["bbb_permeability"]["classification"]
    json_payload = json.loads(bundle_json(results, project_name="Test"))
    assert json_payload["schema"].endswith("v2")
    assert "Cross-module consistency" in bundle_html(results)
    assert "# BioIntel Neuro/CNS" in bundle_markdown(results)


def test_background_queue_executes_neuro_batch(tmp_path) -> None:
    from biointel.jobs.local_queue import LocalJobQueue
    from biointel.jobs.worker import LocalWorker
    from biointel.neuro_cns.jobs import submit_neuro_job

    job = submit_neuro_job(
        tmp_path,
        "bbb_permeability",
        {"compound_rows": [{"compound_id": "caffeine", "smiles": DEMO_SMILES["Caffeine"]}]},
    )
    worker = LocalWorker(tmp_path, worker_id="test-neuro-worker")
    run = worker.run_once()
    assert run.status == "completed"
    stored = LocalJobQueue(tmp_path / "reports" / "jobs.sqlite3").get(job.job_id)
    assert stored.result is not None
    assert stored.result["module_key"] == "bbb_permeability"
