from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.bioinformatics_peak_v138.catalog import MODULES, MODULE_BY_KEY
from biointel.bioinformatics_peak_v138.contracts import CONTRACTS, contract_for, parameters_for
from biointel.bioinformatics_peak_v138.io import read_upload
from biointel.bioinformatics_peak_v138.scientific import analyse_module, demo_frame, validate_frame
from biointel.bioinformatics_peak_v138.visuals import VISUAL_PLANS, build_visuals


ROOT = Path(__file__).resolve().parents[1]


class Upload(io.BytesIO):
    def __init__(self, payload: bytes, name: str):
        super().__init__(payload)
        self.name = name

    def getvalue(self) -> bytes:
        return super().getvalue()


def test_step138_catalogue_contracts_and_visual_depth() -> None:
    assert len(MODULES) == 15
    assert set(CONTRACTS) == {m.key for m in MODULES}
    for module in MODULES:
        assert len(module.visuals) == 12
        assert len(VISUAL_PLANS[module.key]) == 12
        contract = contract_for(module.key)
        assert len(contract.capabilities) >= 7
        assert len(contract.qc_checks) >= 6
        assert len(contract.reference_assets) >= 3
        assert parameters_for(module.key)
        assert len(parameters_for(module.key, expert=True)) >= len(parameters_for(module.key))


@pytest.mark.parametrize("module", MODULES, ids=lambda module: module.key)
def test_all_modules_run_deep_qc_and_twelve_visuals(module) -> None:
    source = demo_frame(module, 120)
    audit = validate_frame(source, module)
    assert audit["valid"], audit
    bundle = analyse_module(source, module, parameters={"priority_threshold": 0.65})
    assert not bundle.result.empty
    assert bundle.summary["schema"] == "biointel.bioinformatics_peak.v138"
    assert bundle.summary["visual_count"] == 12
    assert bundle.summary["quality_status"] in {"Passed", "Review", "Blocked"}
    assert "parameter_manifest" in bundle.extras
    assert "reference_context" in bundle.extras
    assert "provenance" in bundle.extras
    assert len(bundle.quality) >= 10
    numeric = bundle.result.select_dtypes(include=[np.number]).to_numpy()
    assert not np.isinf(numeric).any()
    visuals = build_visuals(module.key, bundle)
    assert len(visuals) == 12
    assert all(v.figure is not None for v in visuals)
    assert all(v.title and v.method and v.interpretation for v in visuals)


def test_module_specific_deep_outputs() -> None:
    expected = {
        "population_gwas_peak": {"sample_qc", "variant_qc", "fine_mapping_proxy", "prs_calibration"},
        "epigenomics_peak": {"sample_qc", "motif_enrichment", "region_annotations"},
        "pharmacogenomics_peak": {"diplotype_confidence", "medication_impact", "reanalysis_queue"},
        "structural_variant_peak": {"consensus_events", "mosaic_candidates", "breakpoint_clusters"},
        "rna_splicing_peak": {"isoform_switches", "aberrant_splicing", "nmd_proxy"},
        "immune_repertoire": {"public_clonotypes", "clonality", "rarefaction"},
        "single_cell_multiome": {"cell_qc", "modality_depth", "multimodal_markers"},
        "proteogenomics_peak": {"candidate_panel_deep", "shared_candidates", "evidence_tiers"},
        "gene_regulatory_network": {"master_regulators", "perturbation_simulation", "edge_provenance"},
        "federated_genomic_discovery": {"consent_matrix", "federated_query_plan", "case_summary"},
        "viral_within_host": {"depth_qc", "primer_dropout", "mixed_infection"},
        "genome_annotation": {"annotation_conflicts", "orphan_features", "version_consistency"},
        "circular_dna_instability": {"consensus_events", "topology_summary", "sample_recurrence"},
        "environmental_edna": {"control_qc", "replicate_concordance", "surveillance_alerts"},
        "comparative_regulatory_genomics": {"species_support", "regulatory_gain_loss", "conservation_qc"},
    }
    for key, names in expected.items():
        bundle = analyse_module(demo_frame(key, 120), key)
        assert names.issubset(bundle.extras), (key, names - set(bundle.extras))


def test_upload_safety_and_special_formats() -> None:
    airr = b"sample\tclonotype\tchain\tv_gene\tj_gene\tcdr3\tcount\nS1\tC1\tTRA\tTRAV1\tTRAJ1\tCASS\t10\n"
    frame = read_upload(Upload(airr, "repertoire.airr"), "immune_repertoire")
    assert set(MODULE_BY_KEY["immune_repertoire"].required_columns).issubset(frame.columns)

    with pytest.raises(ValueError, match="PLINK"):
        read_upload(Upload(b"binary", "cohort.pgen"), "population_gwas_peak")

    with pytest.raises(ValueError, match="Scanpy/MuData"):
        read_upload(Upload(b"binary", "multiome.h5ad"), "single_cell_multiome")


def test_pages_use_step138_renderer() -> None:
    for module in MODULES:
        if module.existing_page:
            source = (ROOT / module.existing_page).read_text(encoding="utf-8")
            assert "bioinformatics_peak_v138" in source
            assert "STEP138_BIOINFORMATICS_DEEP_EXCELLENCE" in source


def test_background_analysis_job_executes_with_reproducible_artifacts(tmp_path: Path) -> None:
    from biointel.bioinformatics_peak_v138.background import stage_and_submit
    from biointel.jobs.worker import LocalWorker

    (tmp_path / "reports").mkdir()
    source = demo_frame("population_gwas_peak", 60)
    submission = stage_and_submit(
        tmp_path,
        source,
        module_key="population_gwas_peak",
        parameters={"priority_threshold": 0.70},
    )
    job_id = submission["job"]["job_id"]
    worker = LocalWorker(tmp_path, worker_id="step138-test-worker")
    run = worker.run_once()
    assert run.processed and run.status == "completed"
    record = worker.queue.get(job_id)
    assert record.status == "completed"
    assert record.result is not None
    assert Path(record.result["result_path"]).is_file()
    assert Path(record.result["manifest_path"]).is_file()
