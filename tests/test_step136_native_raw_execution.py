from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from biointel.native.formats import detect_native_format, parse_native_path
from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.native_execution_v136 import (
    PROFILES,
    engine_readiness,
    execute_native_pipeline_job,
    pipeline_readiness,
    stage_for_background,
    submit_native_pipeline_job,
    streamlit_upload_types,
    validate_profiles,
)

ROOT = Path(__file__).resolve().parents[1]


class Upload:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload
        self.size = len(payload)
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._payload) - self._position
        chunk = self._payload[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def seek(self, offset: int) -> None:
        self._position = offset

    def getvalue(self) -> bytes:
        return self._payload


def test_step136_profiles_cover_exactly_the_fifteen_new_modules() -> None:
    assert set(PROFILES) == set(NEW_BIOMEDICAL_KEYS)
    assert validate_profiles() == {
        "module_count": 15,
        "missing_profiles": [],
        "extra_profiles": [],
        "duplicate_extensions": {},
        "valid": True,
    }
    for profile in PROFILES.values():
        assert profile.accepted_extensions
        assert len(profile.builtin_stages) >= 6
        assert profile.reference_assets
        assert profile.primary_outputs
        assert profile.maximum_bytes == 1024 * 1024 * 1024



def test_streamlit_upload_filters_support_compound_extensions_without_weakening_validation() -> None:
    methylation_types = streamlit_upload_types("long_read_epigenome")
    assert "bedmethyl.gz" in methylation_types
    assert "gz" in methylation_types
    pathology_types = streamlit_upload_types("digital_pathology_foundation")
    assert "ome.tif" in pathology_types
    assert "tif" in pathology_types

def test_new_native_format_detection() -> None:
    assert detect_native_format("slide.svs") == "wsi"
    assert detect_native_format("calls.bedmethyl.gz") == "bedmethyl"
    assert detect_native_format("vector.gbk") == "genbank"
    assert detect_native_format("ligands.sdf") == "sdf"
    assert detect_native_format("model.safetensors") == "model_asset"
    assert detect_native_format("cases.xml") == "safety_xml"
    assert detect_native_format("cohort.parquet") == "parquet"
    assert detect_native_format("events.jsonl") == "jsonl"
    assert detect_native_format("design.yaml") == "yaml"
    assert detect_native_format("spatial.h5") == "hdf5"
    assert detect_native_format("population.bcf") == "bcf"
    assert detect_native_format("graph.gbz") == "graph_binary"


def test_bedmethyl_genbank_sdf_and_model_assets_parse_without_execution(tmp_path: Path) -> None:
    bed = tmp_path / "calls.bedmethyl"
    bed.write_text("chr1\t10\t11\tH1_site\t0\t+\t10\t11\t0\t30\t75\n", encoding="utf-8")
    parsed = parse_native_path(bed)
    assert parsed.format_key == "bedmethyl"
    assert parsed.primary.loc[0, "coverage"] == 30
    assert parsed.primary.loc[0, "methylation_fraction"] == 0.75

    genbank = tmp_path / "vector.gbk"
    genbank.write_text(
        "LOCUS       TEST0001                  12 bp    DNA     circular\n"
        "DEFINITION  test vector.\n"
        "ACCESSION   TEST0001\n"
        "VERSION     TEST0001.1\n"
        "KEYWORDS    .\n"
        "SOURCE      synthetic construct\n"
        "  ORGANISM  synthetic construct\n"
        "FEATURES             Location/Qualifiers\n"
        "     source          1..12\n"
        "ORIGIN\n"
        "        1 acgtacgtacgt\n"
        "//\n",
        encoding="utf-8",
    )
    parsed = parse_native_path(genbank)
    assert parsed.format_key == "genbank"
    assert int(parsed.primary.loc[0, "length"]) == 12

    sdf = tmp_path / "ligands.sdf"
    sdf.write_text("LigandA\n  BioIntel\n\n  2  1  0  0  0  0            999 V2000\n$$$$\n", encoding="utf-8")
    parsed = parse_native_path(sdf)
    assert parsed.format_key == "sdf"
    assert int(parsed.primary.loc[0, "atom_count"]) == 2

    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes((2).to_bytes(8, "little") + b"{}")
    parsed = parse_native_path(checkpoint)
    assert parsed.format_key == "model_asset"
    assert parsed.primary.loc[0, "deserialised"] == False  # noqa: E712
    assert parsed.metadata["security_policy"] == "metadata_only"


def test_jsonl_yaml_xml_and_binary_placeholders_parse_safely(tmp_path: Path) -> None:
    jsonl = tmp_path / "events.jsonl"
    jsonl.write_text('{"site":"A","round":1}\n{"site":"B","round":2}\n', encoding="utf-8")
    parsed = parse_native_path(jsonl)
    assert parsed.total_records == 2
    assert set(parsed.primary["site"]) == {"A", "B"}

    yaml_path = tmp_path / "design.yaml"
    yaml_path.write_text("records:\n  - arm: control\n  - arm: treatment\n", encoding="utf-8")
    parsed = parse_native_path(yaml_path)
    assert parsed.total_records == 2

    xml_path = tmp_path / "cases.xml"
    xml_path.write_text("<root><safetyreport><caseid>1</caseid><drug>A</drug></safetyreport></root>", encoding="utf-8")
    parsed = parse_native_path(xml_path)
    assert parsed.total_records == 1
    assert "caseid" in parsed.primary.columns

    bcf = tmp_path / "population.bcf"
    bcf.write_bytes(b"BCF\x02\x02")
    parsed = parse_native_path(bcf)
    assert parsed.engine_required == "bcftools"
    assert parsed.primary.loc[0, "decode_state"] == "external_engine_required"



def test_corrupt_image_preview_returns_safe_metadata_instead_of_crashing(tmp_path: Path) -> None:
    image = tmp_path / "truncated.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    parsed = parse_native_path(image, preferred_viewer="pathology")
    assert parsed.format_key == "image"
    assert parsed.primary.loc[0, "decode_state"] == "invalid_or_truncated_image"
    assert parsed.metadata["preview_available"] is False
    assert parsed.warnings

def test_staging_job_queue_and_execution_are_checksum_bound(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    user_data = tmp_path / "userdata"
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(user_data))
    payload = (
        b"sample\tchrom\tposition\thaplotype\tmethylation_fraction\tcoverage\tregion\tcondition\n"
        b"S1\tchr1\t10\tH1\t0.75\t30\tchr1:10-11\tcase\n"
    )
    upload = Upload("methylation.tsv", payload)
    staged = stage_for_background(project, upload, "long_read_epigenome")
    staged_path = Path(staged["path"])
    assert staged_path.is_file()
    assert hashlib.sha256(staged_path.read_bytes()).hexdigest() == staged["sha256"]

    job = submit_native_pipeline_job(project, "long_read_epigenome", staged, max_records=10_000)
    assert job.job_type == "nextgen_native_pipeline"
    assert job.status == "queued"

    result = execute_native_pipeline_job(
        project,
        job.payload,
        job_id=job.job_id,
    )
    assert result["source"]["sha256"] == staged["sha256"]
    assert Path(result["manifest_path"]).is_file()
    assert result["native_parse"]["records_loaded"] == 1
    assert result["module_analysis"]["state"] == "completed"


def test_pipeline_readiness_and_engine_probe_fail_safely() -> None:
    readiness = pipeline_readiness("clinical_biomarker_survival", source_name="cohort.csv", source_head=b"patient,time,event\n")
    assert readiness["built_in_stages"] >= 6
    assert readiness["optional_engines"] == 0
    frame = engine_readiness("protein_ligand_codesign", timeout_seconds=0.1)
    assert set(["Engine", "Key", "Available", "Version"]).issubset(frame.columns)
    assert len(frame) == len(PROFILES["protein_ligand_codesign"].optional_engines)


def test_renderer_integrates_native_pipeline_only_into_existing_modules() -> None:
    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    assert "render_native_execution_v136_panel" in renderer
    assert "Native pipeline" in renderer
    page_names = {path.name for path in (ROOT / "pages").glob("*.py")}
    assert not any("Step136" in name or "Native_Raw_Data_136" in name for name in page_names)


def test_worker_supports_native_pipeline_job_type() -> None:
    worker = (ROOT / "src/biointel/jobs/worker.py").read_text(encoding="utf-8")
    assert '"nextgen_native_pipeline": self._nextgen_native_pipeline' in worker
    assert "execute_native_pipeline_job" in worker


def test_protected_pages_remain_byte_identical() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
