from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_step120_capability_specs_cover_weakest_modules() -> None:
    from biointel.scientific_depth.capability import CAPABILITY_SPECS

    expected = {
        "flow_cytometry",
        "epigenomics_chromatin",
        "metabolomics_lipidomics",
        "bioimage_microscopy",
        "spatial_omics_pathology",
        "glycomics_glycoproteomics",
        "proteogenomics_neoantigen",
        "population_gwas",
        "structural_variant_repeat",
        "rna_isoform_splicing",
        "pharmacogenomics",
        "docking_dynamics",
        "antibody_biologics",
        "immunoinformatics_vaccine",
        "single_cell_trajectory",
        "cell_atlas_mapping",
        "genome_editing_safety",
    }
    assert expected.issubset(CAPABILITY_SPECS)
    for key in expected:
        spec = CAPABILITY_SPECS[key]
        assert len(spec.stages) >= 6, key
        assert any(stage.mode == "external-validation" for stage in spec.stages), key
        assert spec.release_blockers, key
        assert spec.evidence_boundary, key


def test_capability_assessment_never_silently_passes_external_validation() -> None:
    from biointel.scientific_depth.capability import assess_capability

    data = pd.DataFrame(
        {
            "feature": ["M1", "M2"],
            "group": ["A", "B"],
            "intensity": [100.0, 200.0],
        }
    )
    engines = pd.DataFrame(
        {
            "engine": ["msconvert", "openms"],
            "available": [True, True],
        }
    )
    assessment = assess_capability("metabolomics_lipidomics", data, engines)
    assert assessment is not None
    assert assessment.tier in {"A", "B"}
    assert assessment.release_ready is False
    statuses = set(assessment.stage_table["status"])
    assert "external-validation" in statuses
    assert any("independent" in blocker.lower() for blocker in assessment.blockers)


def test_capability_assessment_blocks_missing_required_schema() -> None:
    from biointel.scientific_depth.capability import assess_capability

    assessment = assess_capability("population_gwas", pd.DataFrame({"sample": ["S1"]}), pd.DataFrame())
    assert assessment is not None
    assert assessment.tier == "C"
    assert assessment.blocked >= 1
    assert any("missing columns" in blocker.lower() for blocker in assessment.blockers)


def test_flow_compensation_recovers_true_signal() -> None:
    from biointel.biotech.flow_cytometry import apply_compensation

    true = np.array([[100.0, 20.0], [50.0, 80.0], [10.0, 120.0]])
    spill = np.array([[1.0, 0.10], [0.05, 1.0]])
    observed = true @ spill.T
    events = pd.DataFrame(observed, columns=["FITC-A", "PE-A"])
    matrix = pd.DataFrame(spill, index=["FITC-A", "PE-A"], columns=["FITC-A", "PE-A"])
    compensated, provenance = apply_compensation(events, ["FITC-A", "PE-A"], matrix)
    assert np.allclose(compensated[["FITC-A", "PE-A"]].to_numpy(), true, atol=1e-8)
    assert provenance["condition_number"] < 10


def test_flow_compensation_rejects_unstable_matrix() -> None:
    from biointel.biotech.flow_cytometry import validate_compensation_matrix

    matrix = pd.DataFrame([[1.0, 1.0], [1.0, 1.0]], columns=["A", "B"], index=["A", "B"])
    with pytest.raises(ValueError, match="singular|unstable"):
        validate_compensation_matrix(matrix, ["A", "B"])


def test_flow_gating_qc_and_control_thresholds() -> None:
    from biointel.biotech.flow_cytometry import (
        fmo_threshold,
        flow_qc,
        gate_audit_table,
        rectangular_gate,
        singlet_gate,
    )

    rng = np.random.default_rng(42)
    n = 2_000
    area = rng.normal(1000, 80, n)
    height = area * rng.normal(1.0, 0.05, n)
    height[:80] *= 1.8
    events = pd.DataFrame(
        {
            "event_id": [f"E{i}" for i in range(n)],
            "Time": np.arange(n),
            "FSC-A": area,
            "FSC-H": height,
            "FITC-A": rng.lognormal(4.0, 0.5, n),
            "PE-A": rng.lognormal(4.3, 0.5, n),
        }
    )
    qc = flow_qc(events, event_id_column="event_id", time_column="Time", channels=["FSC-A", "FSC-H", "FITC-A", "PE-A"])
    assert qc.summary["events"] == n
    singlets = singlet_gate(events, "FSC-A", "FSC-H")
    assert 0 < len(singlets.events) < n
    rectangle = rectangular_gate(
        singlets.events,
        "FITC-A",
        "PE-A",
        x_min=0,
        x_max=float(singlets.events["FITC-A"].quantile(0.95)),
        y_min=0,
        y_max=float(singlets.events["PE-A"].quantile(0.95)),
    )
    audit = gate_audit_table([singlets, rectangle])
    assert len(audit) == 2
    control = pd.DataFrame({"FITC-A": rng.lognormal(2.0, 0.2, 500)})
    threshold = fmo_threshold(control, "FITC-A")
    assert threshold > 0


def test_new_protected_engine_plans_are_path_bounded(tmp_path: Path) -> None:
    from biointel.native.engines import build_engine_plan, plan_catalog

    bam = tmp_path / "sample.bam"
    bam.write_bytes(b"BAM")
    control = tmp_path / "control.bam"
    control.write_bytes(b"BAM")
    pheno = tmp_path / "pheno.tsv"
    pheno.write_text("#FID\tIID\tphenotype\nF1\tS1\t1\n", encoding="utf-8")
    vcf = tmp_path / "variants.vcf"
    vcf.write_text("##fileformat=VCFv4.2\n", encoding="utf-8")
    ref = tmp_path / "ref.fa"
    ref.write_text(">chr1\nACGT\n", encoding="utf-8")
    query = tmp_path / "antibody.fasta"
    query.write_text(">ab\nEVQLVESGGGLVQPGGSLRLSCAAS\n", encoding="utf-8")
    for name in ("V", "D", "J"):
        (tmp_path / name).write_text("db", encoding="utf-8")
    spectra = tmp_path / "run.mzML"
    spectra.write_text("<mzML/>", encoding="utf-8")
    database = tmp_path / "proteins.fasta"
    database.write_text(">P1\nPEPTIDE\n", encoding="utf-8")
    params = tmp_path / "comet.params"
    params.write_text("database_name = proteins.fasta\n", encoding="utf-8")
    bed_a = tmp_path / "a.bed"
    bed_b = tmp_path / "b.bed"
    bed_a.write_text("chr1\t1\t10\n", encoding="utf-8")
    bed_b.write_text("chr1\t5\t20\n", encoding="utf-8")

    plans = [
        build_engine_plan("macs2_callpeak", workdir=tmp_path, treatment=bam, control=control),
        build_engine_plan("deeptools_bamcoverage", workdir=tmp_path, alignment=bam),
        build_engine_plan("plink2_glm", workdir=tmp_path, pfile_prefix=tmp_path / "cohort", phenotype=pheno),
        build_engine_plan("whatshap_phase", workdir=tmp_path, vcf=vcf, alignment=bam, reference=ref),
        build_engine_plan("igblast_germline", workdir=tmp_path, query=query, db_v=tmp_path / "V", db_d=tmp_path / "D", db_j=tmp_path / "J"),
        build_engine_plan("comet_search", workdir=tmp_path, spectra=spectra, database=database, params=params),
        build_engine_plan("openms_featurefinder_metabo", workdir=tmp_path, mzml=spectra),
        build_engine_plan("bedtools_intersect", workdir=tmp_path, a=bed_a, b=bed_b),
    ]
    assert len(plans) == 8
    assert all(plan.command and plan.cwd for plan in plans)
    assert set(plan.plan_key for plan in plans).issubset(set(plan_catalog()["Plan"]))


def test_advanced_analysis_adds_honest_evidence_boundaries() -> None:
    from biointel.expansion.catalog import MODULE_BY_KEY
    from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise

    expected_columns = {
        "metabolomics_lipidomics": {"identification_level", "identification_release_blocked", "result_scope"},
        "docking_dynamics": {"redocking_validation_pass", "experimental_affinity_confirmed", "result_scope"},
        "pharmacogenomics": {"reference_build_present", "guideline_version_present", "clinical_action_blocked"},
    }
    for key, columns in expected_columns.items():
        module = MODULE_BY_KEY[key]
        data = _normalise(_demo_frame(module, 96), module)
        result, _, _, _ = _analyse_detailed(data, module, 0.70)
        assert columns.issubset(result.columns), key


def test_bioimage_statistics_use_images_as_independent_units() -> None:
    from biointel.expansion.catalog import MODULE_BY_KEY
    from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise

    module = MODULE_BY_KEY["bioimage_microscopy"]
    data = _normalise(_demo_frame(module, 128), module)
    _, _, _, extras = _analyse_detailed(data, module, 0.70)
    audit = extras["analysis_unit_audit"]
    assert audit.iloc[0]["analysis_unit"] == "image"
    assert bool(audit.iloc[0]["pseudoreplication_prevented"])
    stats = extras["condition_statistics"]
    if not stats.empty:
        assert set(stats["analysis_unit"]) == {"image"}


def test_wet_lab_page_contains_real_flow_workflow() -> None:
    source = (ROOT / "pages/64_Wet_Lab_Biotechnology.py").read_text(encoding="utf-8")
    for token in ("Flow cytometry", "compensation", "FMO", "singlet_gate", "flow_qc"):
        assert token in source
