from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from biointel.expansion.catalog import EXPANSION_MODULES, MODULE_BY_KEY
from biointel.expansion.io_formats import read_scientific_upload
from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise

ROOT = Path(__file__).resolve().parents[1]


class Upload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def test_step103_release_metadata_and_versions_are_synchronised():
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text()
    release = json.loads((ROOT / "STEP103_RELEASE.json").read_text())
    assert release["version"] == "10.3.0"
    assert release["upgraded_module_count"] == 21


def test_all_modules_execute_advanced_analysis_and_produce_manifest_metrics():
    for module in EXPANSION_MODULES:
        data = _normalise(_demo_frame(module, 96), module)
        result, summary, _, extras = _analyse_detailed(data, module, 0.70)
        assert not result.empty, module.key
        assert summary["advanced_engine"] == "biointel.scientific_expansion.v2"
        assert summary["result_records"] == len(result)
        assert summary["advanced_table_count"] == len(extras)


def test_fasta_converters_create_module_ready_tables():
    protein = b">protein_1\nMKWVTFISLLLLFSSAYSRGVFRRDTHKSEIAHRFKDLGE\n"
    for key in ("immunoinformatics_vaccine", "antibody_biologics", "proteogenomics_neoantigen"):
        module = MODULE_BY_KEY[key]
        frame = read_scientific_upload(Upload("protein.fasta", protein), key)
        assert not frame.empty
        normalised = _normalise(frame, module)
        assert set(module.columns).issubset(normalised.columns)


def test_genome_editing_fasta_discovers_spcas9_guides():
    dna = b">target\nAAACCCGGGTTTAAACCCGGAGGTTTCCCAAAGGGTTTCCCGG\n"
    frame = read_scientific_upload(Upload("target.fna", dna), "genome_editing_safety")
    assert not frame.empty
    assert frame["guide"].str.len().eq(20).all()
    assert frame["pam"].str.endswith("GG").all()


def test_vcf_and_bed_imports_are_transparent_and_schema_compatible():
    vcf = b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n1\t12345\trs123\tA\tG\t99\tPASS\tGENE=CYP2C19\tGT\t0/1\n"
    pgx = read_scientific_upload(Upload("sample.vcf", vcf), "pharmacogenomics")
    assert pgx.iloc[0]["gene"] == "CYP2C19"
    assert pgx.iloc[0]["evidence_level"] == "Uncurated"

    bed = b"chr1\t100\t250\tpeak_1\t12.5\nchr2\t300\t480\tpeak_2\t9.0\n"
    epi = read_scientific_upload(Upload("peaks.bed", bed), "epigenomics_chromatin")
    assert epi["region"].str.contains(":").all()
    assert len(epi) == 2


def test_microscopy_image_import_generates_object_measurements():
    image = np.zeros((96, 96), dtype=np.uint8)
    image[10:30, 10:30] = 240
    image[55:82, 58:84] = 220
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    frame = read_scientific_upload(Upload("cells.png", buffer.getvalue()), "bioimage_microscopy")
    assert len(frame) >= 2
    assert {"area", "intensity", "circularity"}.issubset(frame.columns)
