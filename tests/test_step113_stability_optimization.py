from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile

import pandas as pd
import pytest


class _Upload(BytesIO):
    def __init__(self, data: bytes, name: str = "upload.bin") -> None:
        super().__init__(data)
        self.name = name
        self.type = "application/octet-stream"
        self.size = len(data)


def test_study_design_allocation_and_repeated_measure_stability() -> None:
    from biointel.study_design import calculate_design, simulate_power

    simulation = simulate_power(
        "two_group_continuous",
        total_sample_size=101,
        effect_size=0.4,
        simulations=100,
        seed=4,
    )
    assert simulation["n_group_1"] + simulation["n_group_2"] == 101

    two_visits = calculate_design(
        "repeated_measures",
        effect_size=0.4,
        measurements=2,
        repeated_measure_correlation=0.5,
    )
    six_visits = calculate_design(
        "repeated_measures",
        effect_size=0.4,
        measurements=6,
        repeated_measure_correlation=0.5,
    )
    assert six_visits.total_sample_size <= two_visits.total_sample_size

    cluster = calculate_design(
        "cluster_randomized",
        effect_size=0.5,
        cluster_size=12,
        intraclass_correlation=0.05,
        allocation_ratio=1.5,
    )
    assert all(size % 12 == 0 for size in cluster.group_sizes.values())
    assert cluster.total_sample_size == sum(cluster.group_sizes.values())

    with pytest.raises(ValueError, match="Allocation ratio"):
        calculate_design("two_group_continuous", effect_size=0.5, allocation_ratio=0)


def test_randomization_rejects_empty_samples() -> None:
    from biointel.study_design import build_randomization_schedule

    with pytest.raises(ValueError, match="sample"):
        build_randomization_schedule([], ["A", "B"])


def test_bioinformatics_edge_cases_are_safe() -> None:
    from biointel.bioinformatics import (
        build_transcriptomics_design,
        extended_fastq_qc,
        protein_feature_track,
        vcf_quality_summary,
    )

    short_track = protein_feature_track("MKWVT", window=19)
    assert len(short_track) == 5

    metadata = pd.DataFrame({"sample": ["S1", "S2"], "group": ["A", "B"]})
    with pytest.raises(ValueError, match="Batch column"):
        build_transcriptomics_design(
            metadata,
            sample_column="sample",
            group_column="group",
            reference_group="A",
            batch_column="missing_batch",
        )

    fastq = "@r1\nACGTAC\n+\nIIIIII\n@broken\nACGT\n+\nIII\n@r2\nACGTAC\n+\nIIIIII\n"
    qc = extended_fastq_qc(fastq, maximum_distinct_kmers=2, kmer_size=2)
    assert qc["summary"]["malformed_records"] == 1
    assert qc["summary"]["kmer_capacity_reached"] is True

    vcf = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\tS2\n"
        "1\tbad\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\t0/0\n"
        "1\t10\t.\tA\tG,T\t50\tPASS\t.\tGT\t0/2\t2/2\n"
    )
    summary = vcf_quality_summary(vcf)
    assert summary["summary"]["malformed_records_skipped"] == 1
    alt_t = summary["variants"].loc[summary["variants"]["alt"] == "T"].iloc[0]
    assert int(alt_t["alternate_carrier_samples"]) == 2
    assert int(alt_t["alternate_homozygous_samples"]) == 1


def test_reference_lifecycle_activation_replacement_and_safe_storage() -> None:
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
        manager.activate(v1["reference_id"])
        assert manager.verify(v1["reference_id"])["status"] == "active"
        manager.activate(v2["reference_id"])
        assert manager.get_reference(v1["reference_id"])["status"] == "verified"

        changed = root / "changed.fa"
        changed.write_text(">different\nAAAA\n", encoding="utf-8")
        with pytest.raises(ValueError, match="already registered"):
            manager.register_path("Genome", "v1", changed, license_name="test")
        replaced = manager.register_path(
            "Genome",
            "v1",
            changed,
            license_name="test",
            replace_existing=True,
            copy_into_managed_storage=True,
        )
        assert replaced["sha256"] == sha256(changed.read_bytes()).hexdigest()
        assert Path(replaced["local_path"]).resolve().is_relative_to(manager.asset_root.resolve())

        traversal = manager.register_path(
            "Other DB",
            "../../unsafe/version",
            first,
            license_name="test",
            copy_into_managed_storage=True,
        )
        assert Path(traversal["local_path"]).resolve().is_relative_to(manager.asset_root.resolve())


def test_reference_download_file_url_is_atomic_and_checksum_safe() -> None:
    from biointel.reference_lifecycle import ReferenceLifecycleManager

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.bin"
        source.write_bytes(b"abcdefgh" * 1024)
        manager = ReferenceLifecycleManager(root)
        expected = sha256(source.read_bytes()).hexdigest()
        plan = manager.create_download_plan(
            "Test DB",
            "v1",
            source.as_uri(),
            expected_size_bytes=source.stat().st_size,
            license_name="test",
            license_accepted=True,
            checksum_expected=expected,
        )
        part = Path(plan["target_path"] + ".part")
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(b"partial-corrupt")
        result = manager.execute_download(plan["plan_id"], max_download_bytes=1_000_000)
        assert Path(result["target_path"]).read_bytes() == source.read_bytes()
        assert not part.exists()

        bad_plan = manager.create_download_plan(
            "Test DB",
            "v2",
            source.as_uri(),
            expected_size_bytes=source.stat().st_size,
            license_name="test",
            license_accepted=True,
            checksum_expected="0" * 64,
        )
        with pytest.raises(ValueError, match="checksum"):
            manager.execute_download(bad_plan["plan_id"], max_download_bytes=1_000_000)
        assert not Path(bad_plan["target_path"]).exists()
        assert not Path(bad_plan["target_path"] + ".part").exists()


def test_streamlit_upload_staging_is_atomic_and_bounded() -> None:
    from biointel.ui.workflow import stage_streamlit_upload

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "asset.bin"
        upload = _Upload(b"abc" * 100, "asset.bin")
        result = stage_streamlit_upload(upload, target, max_bytes=1000, chunk_size=17)
        assert target.read_bytes() == b"abc" * 100
        assert result["size_bytes"] == 300
        assert result["sha256"] == sha256(b"abc" * 100).hexdigest()

        oversized = _Upload(b"x" * 50, "too-big.bin")
        with pytest.raises(ValueError, match="maximum"):
            stage_streamlit_upload(oversized, target, max_bytes=10)
        assert target.read_bytes() == b"abc" * 100
