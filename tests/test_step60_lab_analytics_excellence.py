from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from biointel.biotech.assays_advanced import (
    bioprocess_advanced_metrics,
    bioprocess_sensor_metrics,
    elisa_hook_effect_screen,
    elisa_parallelism_recovery_qc,
    fit_elisa_calibration,
    fit_enzyme_model,
    melt_curve_qc,
    qpcr_control_qc,
    qpcr_group_statistics,
    qpcr_reference_gene_stability,
    qpcr_standard_curve,
)
from biointel.biotech.experimental_design import (
    cluster_adjusted_sample_size,
    correlation_sample_size,
    equivalence_sample_size,
    noninferiority_sample_size,
    one_way_anova_sample_size,
    paired_sample_size,
    plate_randomization,
    randomized_assignment,
    repeated_measures_sample_size,
    two_proportion_sample_size,
)
from biointel.biotech.lab_schema import apply_column_mapping, infer_column_mapping, plate_map_audit
from biointel.genomics.codon_advanced import codon_adaptation_index, optimize_protein_advanced
from biointel.genomics.design_advanced import (
    NUCLEASES,
    base_editing_window,
    deletion_guide_pairs,
    design_primer_pairs_advanced,
    find_crispr_guides_advanced,
    in_silico_pcr,
    multiplex_compatibility,
)
from biointel.microbiology.metagenomics import (
    approximate_ani,
    beta_diversity,
    diversity_metrics,
    kmer_profile,
)
from biointel.projects.metagenomics_advanced import (
    contamination_screen,
    covariate_adjusted_clr_association,
    faith_phylogenetic_diversity,
    functional_profile_summary,
    multiplicative_zero_replacement,
    nmds_ordination,
    pcoa_diagnostics,
    restricted_permanova,
    unifrac_distance,
)
from biointel.projects.metagenomics_pipeline import bray_curtis_distance, relative_abundance
from biointel.projects.metagenomics_raw_reads import (
    build_raw_read_plan,
    execute_raw_read_plan,
    plan_table,
)

ROOT = Path(__file__).resolve().parents[1]


def test_schema_mapping_and_plate_audit() -> None:
    raw = pd.DataFrame({"Sample ID": ["S1", "S2"], "Ct Target": [22.0, 23.0], "Ref Ct": [18.0, 18.2], "Well Position": ["A01", "H12"]})
    mapping = infer_column_mapping(raw, "qpcr")
    assert mapping["sample"] == "Sample ID"
    mapped = apply_column_mapping(raw, mapping, required=["sample", "target_ct", "reference_ct"])
    assert set(["sample", "target_ct", "reference_ct", "well"]).issubset(mapped.columns)
    audit = plate_map_audit(mapped, plate_format=96)
    assert audit["valid_wells"] == 2
    assert audit["edge_wells"] == 2


def test_qpcr_standard_curve_and_group_statistics() -> None:
    concentrations = np.array([1, 10, 100, 1000], dtype=float)
    ct = 35 - 3.321928 * np.log10(concentrations)
    result = qpcr_standard_curve(concentrations, ct)
    assert 95 <= result["efficiency_percent"] <= 105
    expression = pd.DataFrame({"group": ["A", "A", "A", "B", "B", "B"], "relative_expression": [1.0, 1.1, 0.9, 2.0, 2.2, 1.8]})
    summary, tests = qpcr_group_statistics(expression, group_column="group", reference_group="A", bootstrap_iterations=200)
    assert len(summary) == 2
    assert tests.iloc[0]["fold_change_of_means"] > 1.5


def test_melt_curve_detects_single_peak() -> None:
    temperature = np.linspace(65, 95, 301)
    fluorescence = 1 / (1 + np.exp((temperature - 82) / 0.45))
    result = melt_curve_qc(temperature, fluorescence)
    assert result["peak_count"] == 1
    assert 81 < result["primary_tm"] < 83


def test_elisa_model_selection_and_qc() -> None:
    concentration = np.repeat(np.array([0.25, 0.5, 1, 2, 4, 8], dtype=float), 3)
    response = 0.05 + 2.0 / (1 + (1.5 / concentration) ** 1.2)
    standards = pd.DataFrame({"concentration": concentration, "absorbance": response + np.tile([-0.01, 0, 0.01], 6)})
    result = fit_elisa_calibration(standards, candidate_models=("4PL", "5PL", "log-linear"))
    assert result["selected_model"] in {"4PL", "5PL"}
    assert result["fit_table"]["r_squared"].max() > 0.99


def test_advanced_enzyme_models_and_bioprocess_rates() -> None:
    substrate = np.array([0.05, 0.1, 0.25, 0.5, 1, 2, 5], dtype=float)
    velocity = 12 * substrate / (0.4 + substrate + substrate**2 / 8)
    fit = fit_enzyme_model(substrate, velocity, model="substrate_inhibition")
    assert fit["r_squared"] > 0.99
    process = pd.DataFrame({"time": [0, 1, 2, 3, 4], "biomass": [0.2, 0.35, 0.65, 1.1, 1.4], "substrate": [20, 18, 14, 8, 4], "product": [0, 0.1, 0.5, 1.4, 2.2]})
    trajectory, summary = bioprocess_advanced_metrics(process)
    assert "specific_productivity" in trajectory
    assert summary["maximum_volumetric_productivity"] > 0


def test_expanded_experimental_design_and_plate_randomization() -> None:
    assert paired_sample_size(0.8)["pairs"] > 0
    assert one_way_anova_sample_size(0.4, 3)["total"] % 3 == 0
    assert two_proportion_sample_size(0.2, 0.5)["total"] > 0
    assignment = randomized_assignment([f"S{i}" for i in range(24)], ["A", "B"], blind_labels=True)
    assert set(assignment["group"]) == {"A", "B"}
    plate = plate_randomization([f"S{i}" for i in range(20)], controls={"Blank": 2})
    assert plate["well"].is_unique
    assert len(plate) == 22


def test_advanced_primer_crispr_and_codon_workflows() -> None:
    sequence = ("ATGCGTACGTTAGCGGCGTACCTGACTGCGTACGATCGTACGGCATGCTAGCGTACGATCGTACGGC" * 5)
    pairs = design_primer_pairs_advanced(sequence, minimum_product=70, maximum_product=220, minimum_tm=45, maximum_tm=75, maximum_pairs=20)
    assert pairs
    assert all(pair.product_size >= 70 for pair in pairs)
    target = "ACGT" * 20 + "TGG" + "GCTA" * 20 + "TTTA" + "ACGT" * 20
    for nuclease in NUCLEASES:
        guides = find_crispr_guides_advanced(target, nuclease=nuclease)
        assert isinstance(guides, list)
    optimized = optimize_protein_advanced("MKWVTFISLLFLFSSAYSR", host="cho", avoid_motifs=["GAATTC"], candidates=3)
    assert len(optimized) == 3
    assert optimized[0].cai_proxy > 0
    assert codon_adaptation_index(optimized[0].optimized_dna, host="cho") > 0


def test_microbiology_strict_validation_and_k31() -> None:
    assert kmer_profile("ACGT" * 20, k=31)
    with pytest.raises(ValueError, match="Negative abundance"):
        diversity_metrics(pd.DataFrame({"taxon": ["A", "B"], "S1": [1, -1]}))
    frame = pd.DataFrame({"taxon": ["A", "B", "C"], "S1": [10, 0, 3], "S2": [0, 7, 3]})
    distance = beta_diversity(frame)
    assert distance.shape == (2, 2)
    ani = approximate_ani("ACGT" * 30, "ACGT" * 29 + "ACGA", k=15)
    assert ani["containment_a_in_b"] > 0


def test_advanced_metagenomics_design_controls() -> None:
    counts = pd.DataFrame({"taxon": ["T1", "T2", "T3", "T4"], "A1": [100, 5, 0, 2], "A2": [90, 7, 0, 3], "B1": [10, 80, 1, 2], "B2": [12, 75, 1, 4], "N1": [2, 2, 50, 1]})
    relative = relative_abundance(counts)
    replaced = multiplicative_zero_replacement(relative)
    assert np.allclose(replaced.drop(columns="taxon").sum(axis=0), 1.0)
    metadata = pd.DataFrame({"sample": ["A1", "A2", "B1", "B2", "N1"], "group": ["A", "A", "B", "B", "A"], "batch": ["X", "Y", "X", "Y", "X"], "sample_type": ["biological", "biological", "biological", "biological", "negative"]})
    distance = bray_curtis_distance(counts)
    permanova = restricted_permanova(distance, metadata, strata_column="batch", permutations=19)
    assert 0 <= permanova.permutation_p_value <= 1
    nmds, diagnostics = nmds_ordination(distance, random_state=7)
    assert len(nmds) == 5
    assert diagnostics["stress"] >= 0
    contaminants = contamination_screen(relative, metadata)
    assert "contaminant_flag" in contaminants
    association = covariate_adjusted_clr_association(relative, metadata, reference_group="A", comparison_group="B", covariates=["batch"])
    assert "fdr_q_value" in association


def test_functional_profile_and_raw_read_plan() -> None:
    profile = pd.DataFrame({"feature": ["K1", "K2", "K3"], "pathway": ["P1", "P1", "P2"], "S1": [2, 3, 1], "S2": [1, 4, 5]})
    feature, pathway = functional_profile_summary(profile)
    assert len(feature) == 3
    assert len(pathway) == 2
    plan = build_raw_read_plan(sample_id="S-1", read_1="R1.fastq.gz", read_2="R2.fastq.gz", kraken_database="db", threads=8)
    table = plan_table(plan)
    assert table[0]["executable"] == "fastp"
    assert any(row["executable"] == "kraken2" for row in table)


def test_lab_pages_expose_step60_controls() -> None:
    primer = (ROOT / "pages" / "58_Primer_CRISPR_Codon_Studio.py").read_text()
    wet = (ROOT / "pages" / "64_Wet_Lab_Biotechnology.py").read_text()
    micro = (ROOT / "pages" / "65_Microbiology_Metagenomics.py").read_text()
    meta = (ROOT / "pages" / "82_Metagenomics_Pipeline.py").read_text()
    assert "Nearest-neighbour Tm" in primer
    assert "Column mapping and schema audit" in wet
    assert "Negative abundance" not in micro  # handled by strict backend error, not clipping text
    assert "Restricted-permutation strata" in meta
    assert "raw-read pipeline plan" in meta.lower()


def test_qpcr_reference_stability_and_control_qc() -> None:
    long = pd.DataFrame(
        {
            "sample": ["S1", "S1", "S2", "S2", "S3", "S3"],
            "gene": ["GAPDH", "ACTB"] * 3,
            "ct": [18.0, 18.2, 18.4, 18.5, 17.9, 18.1],
        }
    )
    stability = qpcr_reference_gene_stability(long, candidate_genes=["GAPDH", "ACTB"])
    assert set(stability["gene"]) == {"GAPDH", "ACTB"}
    controls = pd.DataFrame({"role": ["ntc", "ntc", "positive"], "ct": [np.nan, 39.5, 22.0]})
    qc = qpcr_control_qc(controls)
    assert set(qc["qc_status"]) == {"Pass"}


def test_sensor_and_extended_design_functions() -> None:
    process = pd.DataFrame(
        {
            "time": [0, 1, 2],
            "our": [1.0, 2.0, 3.0],
            "cer": [0.8, 1.8, 2.7],
            "do": [7.0, 5.0, 3.0],
            "oxygen_saturation": [8.0, 8.0, 8.0],
            "kla": [20, 20, 20],
            "feed": [0, 2, 2],
        }
    )
    enriched, summary = bioprocess_sensor_metrics(process)
    assert "respiratory_quotient" in enriched
    assert summary["maximum_oxygen_transfer_rate"] == 100.0
    assert noninferiority_sample_size(0.5)["total"] > 0
    assert equivalence_sample_size(0.5)["total"] > 0
    assert correlation_sample_size(0.4)["participants"] > 0
    assert repeated_measures_sample_size(0.5, measurements=4)["pairs"] > 0
    assert cluster_adjusted_sample_size(100, average_cluster_size=10, intracluster_correlation=0.05)["clusters"] > 0


def test_primer_panel_multiplex_and_editing_plans() -> None:
    sequence = "ACGT" * 40 + "TGG" + "TGCA" * 40
    pairs = design_primer_pairs_advanced(sequence, minimum_product=60, maximum_product=220, minimum_tm=45, maximum_tm=75, maximum_pairs=8)
    assert pairs
    products = in_silico_pcr(pairs[:2], [sequence])
    assert isinstance(products, list)
    compatibility = multiplex_compatibility(pairs[:3])
    assert isinstance(compatibility, list)
    guides = find_crispr_guides_advanced(sequence, nuclease="SpCas9")
    if guides:
        audit = base_editing_window(guides[0], editor="CBE")
        assert audit["editor"] == "CBE"
        deletion = deletion_guide_pairs(guides, target_start=40, target_end=120)
        assert isinstance(deletion, list)


def test_phylogenetic_diversity_unifrac_and_pcoa_diagnostics() -> None:
    abundance = pd.DataFrame(
        {
            "taxon": ["Taxon_A", "Taxon_B", "Taxon_C", "Taxon_D"],
            "S1": [10, 5, 0, 0],
            "S2": [0, 0, 8, 4],
            "S3": [5, 2, 3, 1],
        }
    )
    tree = "((Taxon_A:0.1,Taxon_B:0.1):0.05,(Taxon_C:0.1,Taxon_D:0.1):0.05);"
    faith = faith_phylogenetic_diversity(abundance, tree)
    assert len(faith) == 3
    unweighted = unifrac_distance(abundance, tree, weighted=False)
    weighted = unifrac_distance(abundance, tree, weighted=True)
    assert unweighted.loc["S1", "S2"] > 0
    assert weighted.loc["S1", "S2"] > 0
    coordinates, eigen, diagnostics = pcoa_diagnostics(unweighted)
    assert len(coordinates) == 3
    assert not eigen.empty
    assert "negative_axes" in diagnostics


def test_lab_template_pack_is_complete() -> None:
    template_dir = ROOT / "data" / "lab_templates"
    required = {
        "LAB_ANALYTICS_TEMPLATE_PACK.zip",
        "qpcr_wide_template.csv",
        "elisa_plate_template.csv",
        "enzyme_kinetics_template.csv",
        "bioprocess_timeseries_template.csv",
        "metagenomics_metadata_template.csv",
        "phylogenetic_tree_template.nwk",
    }
    assert required.issubset({path.name for path in template_dir.iterdir()})
    assert (template_dir / "LAB_ANALYTICS_TEMPLATE_PACK.zip").stat().st_size > 1000


@pytest.mark.parametrize(
    "page",
    [
        "pages/58_Primer_CRISPR_Codon_Studio.py",
        "pages/64_Wet_Lab_Biotechnology.py",
        "pages/65_Microbiology_Metagenomics.py",
        "pages/82_Metagenomics_Pipeline.py",
    ],
)
def test_step60_lab_pages_render_without_exceptions(page: str) -> None:
    app = AppTest.from_file(str(ROOT / page), default_timeout=180).run()
    assert not app.exception, page
    assert len(app.markdown) > 0, page


def test_elisa_parallelism_recovery_and_hook_screen() -> None:
    quantified = pd.DataFrame(
        {
            "name": ["S1", "S1", "S2"],
            "estimated_concentration": [100, 105, 50],
            "dilution_factor": [10, 20, 10],
            "expected_concentration": [100, 100, 40],
        }
    )
    parallel, recovery = elisa_parallelism_recovery_qc(quantified)
    assert parallel.loc[parallel["sample"] == "S1", "parallelism_status"].iloc[0] == "Pass"
    assert not recovery.empty
    standards = pd.DataFrame({"concentration": [1, 2, 4, 8, 16], "absorbance": [0.1, 0.3, 0.8, 1.5, 1.0]})
    hook = elisa_hook_effect_screen(standards)
    assert hook["hook_flag"]


def test_raw_read_executor_reports_unavailable_tools_without_shell() -> None:
    plan = build_raw_read_plan(sample_id="S1", read_1="missing.fastq.gz", threads=1)
    result = execute_raw_read_plan(plan, stop_on_error=True, timeout_seconds=1)
    assert result
    assert result[0]["status"] in {"unavailable", "failed"}
