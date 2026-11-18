from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise, read_upload
from biointel.ui.nextgen_specialist_canvases import _PROFILES
from biointel.ui.scientific_visuals import build_scientific_visuals
from biointel.ui.workbench import _validate_analysis_outputs


class Upload:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload
        self.size = len(payload)

    def getvalue(self) -> bytes:
        return self._payload


EXPECTED_EXTRA_TABLES = {
    "digital_pathology_foundation": {"tile_level_qc", "scanner_site_drift", "slide_tumour_heatmap"},
    "long_read_epigenome": {"dmr_candidates", "region_condition_matrix", "haplotype_imbalance"},
    "single_cell_long_read_isoforms": {"dominant_isoforms", "isoform_usage_matrix", "junction_support_qc"},
    "biomedical_foundation_model_hub": {"hardware_compatibility", "licence_review_matrix", "modality_task_coverage"},
    "amr_surveillance": {"temporal_resistance_trends", "phenotype_genotype_concordance", "gene_species_matrix"},
    "spatial_medicine_tme": {"spatial_points", "gene_region_expression", "compartment_composition"},
    "gene_therapy_vector": {"construct_capacity", "promoter_vector_matrix", "safety_risk_register"},
    "cell_therapy_cart": {"construct_score_components", "antigen_domain_matrix"},
    "federated_biomedical_ai": {"site_round_metrics", "privacy_utility_frontier", "site_outlier_review"},
    "clinical_biomarker_survival": {"kaplan_meier_curves", "event_rate_summary", "patient_risk_waterfall"},
    "protein_ligand_codesign": {"pareto_candidates", "variant_ligand_matrix", "score_components"},
    "pangenome_population_medicine": {"population_allele_matrix", "reference_bias_audit"},
    "pharmacovigilance_intelligence": {"drug_event_matrix", "serious_outcome_summary"},
    "synthetic_cohort_trial": {"kaplan_meier_curves", "covariate_balance", "patient_level_simulation"},
    "autonomous_lab_planner": {"design_matrix", "resource_schedule", "risk_register"},
}


def test_step129_all_fifteen_modules_have_specialist_canvases_and_five_visuals() -> None:
    assert set(_PROFILES) == set(NEW_BIOMEDICAL_KEYS)
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        data = normalise(demo_frame(module, 120), module)
        result, summary, secondary, extras = analyse(data, module, 0.7)
        assert EXPECTED_EXTRA_TABLES[key].issubset(extras), key
        visuals = build_scientific_visuals(key, data=data, result=result, secondary=secondary, extras=extras)
        assert len(visuals) == 5, key
        assert len({visual.title for visual in visuals}) == 5, key
        assert all(not visual.data.empty for visual in visuals), key
        assert summary["advanced_table_count"] == len(extras)


def test_step129_boolean_text_is_parsed_safely() -> None:
    model = MODULE_BY_KEY["biomedical_foundation_model_hub"]
    frame = demo_frame(model, 30).head(2)
    frame["local_ready"] = ["false", "true"]
    result, *_ = analyse(normalise(frame, model), model, 0.7)
    assert result["local_ready"].tolist().count(True) == 1
    assert result["local_ready"].tolist().count(False) == 1

    pv = MODULE_BY_KEY["pharmacovigilance_intelligence"]
    cases = demo_frame(pv, 30).head(4)
    cases["serious"] = ["false", "true", "0", "1"]
    _, _, _, extras = analyse(normalise(cases, pv), pv, 0.7)
    outcome = extras["serious_outcome_summary"]
    assert outcome["serious_rate"].between(0, 1).all()


def test_step129_native_adapter_inputs_are_bounded_and_schema_compatible() -> None:
    image = Image.new("RGB", (64, 64), (170, 90, 150))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pathology = read_upload(Upload("slide.png", buffer.getvalue()), "digital_pathology_foundation")
    assert len(pathology) == 64
    assert {"slide_id", "tile_id", "tissue_fraction", "embedding_score", "tumour_probability"}.issubset(pathology)

    bedmethyl = b"chr1\t100\t101\tregion_H1\t0\t+\t100\t101\t0\t30\t75\n"
    methyl = read_upload(Upload("sample.bedmethyl", bedmethyl), "long_read_epigenome")
    assert methyl.iloc[0]["haplotype"] == "H1"
    assert np.isclose(methyl.iloc[0]["methylation_fraction"], 0.75)

    gfa = b"H\tVN:Z:1.0\nS\t1\tACGT\nS\t2\tGGGG\nP\tPOP_A\t1+,2+\t*\nP\tPOP_B\t1+\t*\n"
    population = read_upload(Upload("graph.gfa", gfa), "pangenome_population_medicine")
    assert not population.empty
    assert {"sample", "population", "path", "variant", "allele_frequency", "reference_bias"}.issubset(population)

    pdb = b"ATOM      1  CA  ALA A   1      10.000  10.000  10.000\nHETATM    2  C1  LIG A 101      11.000  10.000  10.000\n"
    pair = read_upload(Upload("complex.pdb", pdb), "protein_ligand_codesign")
    assert not pair.empty
    assert pair.iloc[0]["score_source"] == "structure_summary_proxy_requires_docking"


def test_step129_output_validation_replaces_non_finite_values() -> None:
    result = pd.DataFrame({"score": [1.0, np.inf, -np.inf]})
    extra = pd.DataFrame({"value": [np.inf]})
    clean, summary, secondary, extras = _validate_analysis_outputs(result, {"ok": True}, None, {"extra": extra})
    assert clean["score"].isna().sum() == 2
    assert extras["extra"]["value"].isna().all()
    assert summary["ok"] is True
    assert secondary is None


def test_step129_version_and_release_files() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert (root / "STEP129_RELEASE.json").exists()
    assert (root / "config/step129_nextgen_depth_visuals.json").exists()
