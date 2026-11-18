from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_study_design_families_and_randomization() -> None:
    from biointel.study_design import calculate_design, build_randomization_schedule, simulate_power

    continuous = calculate_design("two_group_continuous", effect_size=0.5, dropout_fraction=0.1)
    assert continuous.total_sample_size > continuous.complete_case_total > 0
    proportions = calculate_design("two_proportions", proportion_1=0.4, proportion_2=0.6)
    assert proportions.total_sample_size > 0
    survival = calculate_design("survival", hazard_ratio=0.7, event_fraction=0.65)
    assert survival.assumptions["required_events"] > 0
    cluster = calculate_design("cluster_randomized", effect_size=0.5, cluster_size=20, intraclass_correlation=0.05)
    assert cluster.assumptions["design_effect"] > 1
    simulation = simulate_power("two_group_continuous", total_sample_size=128, simulations=200, seed=7)
    assert 0 <= simulation["estimated_power"] <= 1
    schedule = build_randomization_schedule([f"P{x}" for x in range(20)], ["Control", "Treatment"], seed=42)
    assert len(schedule) == 20
    assert set(schedule["assigned_group"]) == {"Control", "Treatment"}


def test_bioinformatics_upgrade_engines() -> None:
    from biointel.bioinformatics import (
        batch_sequence_profile,
        build_transcriptomics_design,
        extended_fastq_qc,
        protein_feature_track,
        vcf_quality_summary,
    )

    profile = batch_sequence_profile(">a\nATGAAATAG\n>b\nMKWVTFISLLFLFSSAYSRG", motifs=["ATG"])
    assert len(profile) == 2
    assert profile.loc[profile["record_id"] == "a", "motif_hit_count"].iloc[0] == 1
    fastq = "@r1\nACGT\n+\nIIII\n@r2\nACGT\n+\nIIII\n"
    qc = extended_fastq_qc(fastq)
    assert qc["summary"]["reads_profiled"] == 2
    assert len(qc["per_cycle"]) == 4
    vcf = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n1\t10\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\n"
    summary = vcf_quality_summary(vcf)
    assert summary["summary"]["variants_loaded"] == 1
    metadata = pd.DataFrame({"sample": ["S1", "S2", "S3", "S4"], "group": ["A", "A", "B", "B"], "batch": ["X", "Y", "X", "Y"]})
    design = build_transcriptomics_design(metadata, sample_column="sample", group_column="group", reference_group="A", batch_column="batch")
    assert "Treatment(reference='A')" in design["formula"]
    track = protein_feature_track("MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE")
    assert len(track) == 40


def test_reference_lifecycle_register_verify_activate_and_rollback() -> None:
    from biointel.reference_lifecycle import ReferenceLifecycleManager

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = root / "first.fa"
        second = root / "second.fa"
        first.write_text(">one\nACGT\n", encoding="utf-8")
        second.write_text(">two\nACGTACGT\n", encoding="utf-8")
        manager = ReferenceLifecycleManager(root)
        v1 = manager.register_path("Genome", "v1", first, license_name="test")
        v2 = manager.register_path("Genome", "v2", second, license_name="test")
        assert manager.verify(v1["reference_id"])["checksum_match"]
        manager.activate(v1["reference_id"])
        manager.activate(v2["reference_id"])
        rolled = manager.rollback("Genome")
        assert rolled["version"] == "v1"
        manifest = manager.export_manifest()
        assert len(manifest["references"]) == 2
        assert len(manifest["manifest_sha256"]) == 64


def test_step112_pages_and_navigation_present() -> None:
    assert (ROOT / "pages/121_Biostatistics_Power_and_Experimental_Design_Studio.py").is_file()
    assert (ROOT / "pages/153_Reference_Database_Lifecycle_Manager_2.py").is_file()
    assert (ROOT / "pages/167_Bioinformatics_Feature_Upgrade_Center.py").is_file()
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    assert "bioinformatics_upgrade_center" in navigation
    assert "Reference Database Lifecycle Manager" in navigation


def test_step112_version() -> None:
    version = tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split("."))
    assert version >= (11, 2, 0)
