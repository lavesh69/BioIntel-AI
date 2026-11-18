from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd
import pytest
from scipy.io import mmwrite
from scipy.sparse import csr_matrix

from biointel.projects.cancer_genomics import standardize_variant_columns
from biointel.projects.metagenomics_pipeline import normalize_abundance_input
from biointel.projects.single_cell import parse_10x_mtx_bundle
from biointel.transcriptomics.expression import collapse_duplicate_genes
from biointel.ui.workflow import WorkflowRun, profile_upload, read_uploaded_table


class FakeUpload:
    def __init__(self, name: str, payload: bytes, content_type: str = "application/octet-stream") -> None:
        self.name = name
        self.type = content_type
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def _make_10x_zip(*, unsafe: bool = False) -> bytes:
    matrix_buffer = BytesIO()
    matrix = csr_matrix(np.array([[1, 0, 2, 0, 3, 1], [0, 4, 0, 1, 0, 2]], dtype=int))
    mmwrite(matrix_buffer, matrix)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        prefix = "../" if unsafe else "filtered_feature_bc_matrix/"
        archive.writestr(prefix + "matrix.mtx", matrix_buffer.getvalue())
        archive.writestr(prefix + "features.tsv", "ENSG1\tGeneA\tGene Expression\nENSG2\tGeneA\tGene Expression\n")
        archive.writestr(prefix + "barcodes.tsv", "\n".join(f"Cell{i}" for i in range(1, 7)) + "\n")
    return output.getvalue()


def test_upload_profile_records_identity_and_limits() -> None:
    payload = b"gene,sample\nA,1\n"
    profile = profile_upload(
        "../../matrix.csv",
        payload,
        allowed_extensions=["csv"],
        soft_limit_mb=0.000001,
        hard_limit_mb=1,
    )
    assert profile.filename == "matrix.csv"
    assert profile.extension == ".csv"
    assert profile.allowed is True
    assert profile.within_soft_limit is False
    assert profile.within_hard_limit is True
    assert len(profile.sha256) == 64
    assert profile.warnings


def test_upload_profile_rejects_unsupported_and_empty_file() -> None:
    profile = profile_upload("payload.exe", b"", allowed_extensions=["csv"])
    assert profile.allowed is False
    assert profile.size_bytes == 0
    assert any("empty" in warning.lower() for warning in profile.warnings)


def test_workflow_manifest_is_machine_readable() -> None:
    run = WorkflowRun("Test workflow", "2026-07-06T00:00:00+00:00", 0.0)
    run.stage("Validated", progress=0.5)
    run.status = "completed"
    run.completed_at_utc = "2026-07-06T00:00:01+00:00"
    run.elapsed_seconds = 1.0
    manifest = run.manifest(parameters={"seed": 42}, outputs={"rows": 3}, method="deterministic")
    assert manifest["manifest_schema"] == "biointel.interactive_run.v1"
    assert manifest["status"] == "completed"
    assert manifest["parameters"]["seed"] == 42
    assert manifest["outputs"]["rows"] == 3
    assert manifest["stages"][0]["progress"] == 0.5


def test_maf_upload_uses_tab_separator() -> None:
    upload = FakeUpload("variants.maf", b"Hugo_Symbol\tStart_Position\nTP53\t7579472\n")
    frame = read_uploaded_table(upload)
    assert list(frame.columns) == ["Hugo_Symbol", "Start_Position"]
    assert frame.loc[0, "Hugo_Symbol"] == "TP53"


def test_10x_bundle_parses_and_makes_duplicate_gene_names_unique() -> None:
    frame = parse_10x_mtx_bundle(_make_10x_zip())
    assert frame.shape == (2, 7)
    assert frame["gene"].tolist() == ["GeneA", "GeneA__2"]
    assert frame.drop(columns="gene").to_numpy().sum() == 14


def test_10x_bundle_rejects_zip_slip_and_dense_limit() -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        parse_10x_mtx_bundle(_make_10x_zip(unsafe=True))
    with pytest.raises(ValueError, match="dense interactive limit"):
        parse_10x_mtx_bundle(_make_10x_zip(), maximum_dense_cells=5)


def test_maf_standardization_maps_columns_consequence_and_vaf() -> None:
    maf = pd.DataFrame(
        {
            "Tumor_Sample_Barcode": ["S1"],
            "Hugo_Symbol": ["TP53"],
            "Chromosome": ["17"],
            "Start_Position": [7579472],
            "Reference_Allele": ["C"],
            "Tumor_Seq_Allele2": ["T"],
            "Variant_Classification": ["Missense_Mutation"],
            "t_ref_count": [80],
            "t_alt_count": [20],
            "FILTER": ["PASS"],
        }
    )
    standardized = standardize_variant_columns(maf)
    assert standardized.loc[0, "sample"] == "S1"
    assert standardized.loc[0, "gene"] == "TP53"
    assert standardized.loc[0, "consequence"] == "missense_variant"
    assert standardized.loc[0, "depth"] == 100
    assert standardized.loc[0, "vaf"] == pytest.approx(0.2)


def test_abundance_input_detection_for_counts_fraction_and_percent() -> None:
    counts = pd.DataFrame(
        {
            "taxon": ["A", "B"],
            "S1": [10, 30],
            "S2": [20, 20],
            "S3": [15, 25],
            "S4": [5, 35],
        }
    )
    normalized, report = normalize_abundance_input(counts)
    assert report["detected_input_kind"] == "raw_counts"
    assert report["supports_classical_rarefaction"] is True
    assert normalized["S1"].sum() == 40

    fraction = counts.copy()
    for sample in ["S1", "S2", "S3", "S4"]:
        fraction[sample] = fraction[sample] / fraction[sample].sum()
    normalized, report = normalize_abundance_input(fraction)
    assert report["detected_input_kind"] == "relative_fraction"
    assert report["supports_classical_rarefaction"] is False
    assert normalized["S1"].sum() == pytest.approx(1.0)

    percent = fraction.copy()
    percent[["S1", "S2", "S3", "S4"]] *= 100
    normalized, report = normalize_abundance_input(percent)
    assert report["detected_input_kind"] == "relative_percent"
    assert normalized["S2"].sum() == pytest.approx(1.0)


def test_duplicate_gene_collapse_is_explicit_and_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "gene": ["TP53", "TP53", "EGFR"],
            "S1": [1, 2, 3],
            "S2": [4, 5, 6],
        }
    )
    collapsed, report = collapse_duplicate_genes(frame, method="sum")
    assert report["duplicate_gene_ids"] == 1
    assert report["output_rows"] == 2
    tp53 = collapsed.loc[collapsed["gene"] == "TP53"].iloc[0]
    assert tp53["S1"] == 3
    assert tp53["S2"] == 9


def test_upload_profile_rejects_spoofed_binary_container() -> None:
    profile = profile_upload("evidence.zip", b"not-a-zip", allowed_extensions=["zip"])
    assert profile.allowed is False
    assert any("signature" in warning.lower() for warning in profile.warnings)


def test_10x_bundle_rejects_suspicious_compression_ratio() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("matrix.mtx", b"0" * (2 * 1024 * 1024))
        archive.writestr("features.tsv", "ENSG1\tGeneA\n")
        archive.writestr("barcodes.tsv", "Cell1\n")
    with pytest.raises(ValueError, match="suspiciously compressed"):
        parse_10x_mtx_bundle(output.getvalue(), maximum_compression_ratio=2.0)
