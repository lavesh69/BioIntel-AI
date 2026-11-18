from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.bioinformatics_peak_v137.catalog import MODULES, MODULE_BY_KEY, NEW_MODULE_KEYS
from biointel.bioinformatics_peak_v137.io import read_upload
from biointel.bioinformatics_peak_v137.scientific import analyse_module, demo_frame, validate_frame
from biointel.bioinformatics_peak_v137.visuals import VISUAL_PLANS, build_visuals
from biointel.ui.navigation import PAGE_BY_KEY, catalogue_integrity


ROOT = Path(__file__).resolve().parents[1]


class Upload(io.BytesIO):
    def __init__(self, payload: bytes, name: str):
        super().__init__(payload)
        self.name = name

    def getvalue(self) -> bytes:  # pragma: no cover - mirrors Streamlit upload API
        return super().getvalue()


def test_catalogue_has_all_fifteen_specialist_modules() -> None:
    assert len(MODULES) == 15
    assert len(MODULE_BY_KEY) == 15
    assert len(NEW_MODULE_KEYS) == 8
    assert all(len(module.visuals) == 8 for module in MODULES)
    assert all(len(VISUAL_PLANS[module.key]) == 8 for module in MODULES)


@pytest.mark.parametrize("module", MODULES, ids=lambda module: module.key)
def test_demo_analysis_and_eight_visuals_are_stable(module) -> None:
    source = demo_frame(module, 120)
    audit = validate_frame(source, module)
    assert audit["valid"], audit
    bundle = analyse_module(source, module)
    assert not bundle.result.empty
    assert bundle.summary["module"] == module.key
    assert bundle.summary["visual_count"] == 8
    assert not np.isinf(bundle.result.select_dtypes(include=[np.number]).to_numpy()).any()
    visuals = build_visuals(module.key, bundle)
    assert len(visuals) == 8
    assert all(visual.figure is not None for visual in visuals)
    assert all(visual.title for visual in visuals)


def test_validation_blocks_missing_required_and_duplicate_columns() -> None:
    module = MODULE_BY_KEY["population_gwas_peak"]
    frame = pd.DataFrame([["S1", "S1"]], columns=["sample", "sample"])
    audit = validate_frame(frame, module)
    assert not audit["valid"]
    assert audit["duplicate_columns"]
    assert "variant" in audit["missing_required"]


def test_special_format_importers_are_bounded_and_schema_aware() -> None:
    vcf = b"""##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n1\t100\trs1\tA\tG\t60\tPASS\tAF=0.2;DP=100\tGT\t0/1\n"""
    gwas = read_upload(Upload(vcf, "tiny.vcf"), "population_gwas_peak")
    assert set(["sample", "variant", "chrom", "position", "genotype"]).issubset(gwas.columns)

    bed = b"chr1\t10\t100\tpeak1\t12\n"
    epi = read_upload(Upload(bed, "peaks.bed"), "epigenomics_peak")
    assert set(MODULE_BY_KEY["epigenomics_peak"].required_columns).issubset(epi.columns)

    gff = b"chr1\tsource\tgene\t10\t100\t.\t+\t.\tID=gene1;ortholog_group=OG1\n"
    annotation = read_upload(Upload(gff, "annotation.gff3"), "genome_annotation")
    assert set(MODULE_BY_KEY["genome_annotation"].required_columns).issubset(annotation.columns)


def test_new_pages_are_curated_and_existing_pages_are_upgraded() -> None:
    expected_pages = {
        "immune_repertoire_peak": "pages/197_Immune_Repertoire_Studio.py",
        "single_cell_multiome_peak": "pages/198_Single_Cell_Multiome_Regulatory_Network_Studio.py",
        "gene_regulatory_network_peak": "pages/199_Gene_Regulatory_Network_TF_Activity_Studio.py",
        "federated_genomic_discovery_peak": "pages/200_Federated_Genomic_Discovery_Phenopacket_Studio.py",
        "genome_annotation_peak": "pages/201_Genome_Annotation_Comparative_Annotation_Studio.py",
        "circular_dna_instability_peak": "pages/202_Circular_DNA_Mobile_Elements_Genome_Instability_Studio.py",
        "environmental_edna_peak": "pages/203_Environmental_Genomics_eDNA_Surveillance_Studio.py",
        "comparative_regulatory_genomics_peak": "pages/204_Comparative_Regulatory_Genomics_Studio.py",
    }
    for key, relative in expected_pages.items():
        assert PAGE_BY_KEY[key].path == relative
        assert (ROOT / relative).is_file()

    for module in MODULES:
        if module.existing_page:
            source = (ROOT / module.existing_page).read_text(encoding="utf-8")
            assert "STEP137_BIOINFORMATICS_PEAK_EXPANSION" in source
            assert module.key in source

    integrity = catalogue_integrity(ROOT)
    assert integrity["healthy"], integrity
