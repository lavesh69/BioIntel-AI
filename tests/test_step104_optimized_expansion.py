from __future__ import annotations

import io
import json
import os
import time
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from biointel.nextgen.catalog import MODULE_BY_KEY, NEXTGEN_MODULES, PLATFORM_MODULES, SCIENTIFIC_MODULES
from biointel.nextgen.scientific import analyse, demo_frame, normalise, read_upload
from biointel.nextgen.services import NextGenStore, ProvenanceLedger, build_report_bundle, inspect_file_bytes
from biointel.ui.navigation import PAGE_BY_KEY

ROOT = Path(__file__).resolve().parents[1]


class Upload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


def test_step104_catalog_navigation_and_pages_are_complete():
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert json.loads((ROOT / "STEP104_RELEASE.json").read_text())["version"] == "10.4.0"
    assert len(NEXTGEN_MODULES) == 44
    assert len(SCIENTIFIC_MODULES) == 29
    assert len(PLATFORM_MODULES) == 15
    assert (ROOT / "pages/163_Step104_Scientific_and_Platform_Expansion_Hub.py").is_file()
    assert PAGE_BY_KEY["step104_expansion_hub"].path.endswith("163_Step104_Scientific_and_Platform_Expansion_Hub.py")
    for module in NEXTGEN_MODULES:
        page = PAGE_BY_KEY[module.key]
        assert (ROOT / page.path).is_file(), page.path


def test_all_fourteen_scientific_demo_engines_execute():
    for module in SCIENTIFIC_MODULES:
        data = normalise(demo_frame(module, 120), module)
        result, summary, _secondary, _extras = analyse(data, module, 0.7)
        assert not data.empty, module.key
        assert not result.empty, module.key
        assert summary["schema"] == "biointel.nextgen.scientific.v1"
        assert summary["input_records"] == len(data)
        assert summary["result_records"] == len(result)


def test_scientific_raw_imports_are_bounded_and_transparent():
    vcf = b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n1\t100\trs1\tA\tG\t99\tPASS\tGENE=GENE1\tGT\t0/1\n"
    gwas = read_upload(Upload("cohort.vcf", vcf), "population_gwas")
    assert gwas.iloc[0]["variant"] == "rs1"
    assert gwas.iloc[0]["genotype"] == 1

    fasta = b">p1\nMKWVTFISLLLLFSSAYSRGVFRR\n"
    protein = read_upload(Upload("protein.fasta", fasta), "protein_language_design")
    assert protein.iloc[0]["sequence_id"] == "p1"
    assert protein.iloc[0]["sequence"].startswith("MKW")

    image = np.zeros((96, 96), dtype=np.uint8)
    image[10:30, 10:30] = 240
    image[55:82, 58:84] = 220
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    organoids = read_upload(Upload("organoids.png", buffer.getvalue()), "organoid_3d")
    assert len(organoids) >= 2
    assert {"area", "viability", "circularity"}.issubset(organoids.columns)


def test_file_inspector_checks_format_hash_and_archive_safety():
    report = inspect_file_bytes(b">seq\nACGT\n", "x.fasta")
    assert report.detected_format == "FASTA"
    assert report.sha256
    import gzip
    compressed = inspect_file_bytes(gzip.compress(b">seq\nACGT\n"), "x.fasta.gz")
    assert "FASTA" in compressed.detected_format
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../unsafe.txt", "x")
    unsafe = inspect_file_bytes(buffer.getvalue(), "unsafe.zip")
    assert any("unsafe" in risk.lower() for risk in unsafe.risks)


def test_platform_services_persist_validate_and_recover(tmp_path: Path):
    store = NextGenStore(tmp_path)
    project = store.create_project("P", "D")
    asset = store.attach_asset(project["project_id"], b"abc", "input.txt", module_key="test")
    assert asset["sha256"]
    snapshot = store.create_snapshot(project["project_id"], "S")
    assert snapshot["manifest_sha256"]

    valid = {"nodes": [{"id": "a", "output_type": "table"}, {"id": "b", "input_type": "table"}], "edges": [{"source": "a", "target": "b", "output_type": "table", "input_type": "table"}]}
    assert store.validate_workflow(valid)["valid"]
    cyclic = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}
    assert not store.validate_workflow(cyclic)["valid"]
    workflow = store.save_workflow("W", valid)
    assert workflow["version"] == 1

    queue = store.job_queue()
    job = queue.submit("test", {"bounded": True})
    assert queue.get(job.job_id).status == "queued"
    claimed = queue.claim_next(worker_id="pytest")
    assert claimed is not None
    queue.complete(claimed.job_id, {"ok": True})
    assert queue.get(claimed.job_id).status == "completed"

    ledger = ProvenanceLedger(tmp_path)
    ledger.append("test", {"asset": asset["sha256"]})
    assert ledger.verify()["valid"]


def test_reference_model_instrument_review_lake_benchmark_and_plugin_services(tmp_path: Path):
    store = NextGenStore(tmp_path)
    state = tmp_path / "workspace" / "step104"
    reference = state / "reference.db"
    reference.write_bytes(b"reference")
    store.register_reference("DB", "1", reference)
    assert bool(store.verify_references().iloc[0]["checksum_match"])

    model = state / "model.bin"
    model.write_bytes(b"model")
    registered = store.register_model("M", "1", model, metrics={"auc": 0.8})
    assert registered["status"] == "registered"
    import pytest
    with pytest.raises(ValueError):
        store.set_model_status(registered["model_id"], "deployed")
    assert store.set_model_status(registered["model_id"], "approved", reviewer="QA")["status"] == "approved"
    assert store.set_model_status(registered["model_id"], "deployed")["status"] == "deployed"

    inbox = state / "inbox"
    inbox.mkdir()
    instrument_file = inbox / "sample-S01.csv"
    instrument_file.write_text("x\n1\n")
    os.utime(instrument_file, (time.time() - 10, time.time() - 10))
    connector = store.add_connector("I", inbox, patterns=["*.csv"], stability_seconds=2)
    assert store.scan_connector(connector["connector_id"])["imported"] == 1

    review = store.create_review("result.csv", "v1", "R")
    store.add_review_comment(review["review_id"], "R", "Reviewed")
    assert store.decide_review(review["review_id"], "approved")["locked"] == 1

    index_result = store.index_folder(state, max_files=100, max_hash_bytes=50_000_000)
    assert index_result["indexed_or_updated"] > 0
    assert not store.search_files().empty

    benchmark = store.register_benchmark("B", "1", {"expected": {"accuracy": 0.9}, "tolerances": {"accuracy": 0.02}})
    assert store.run_benchmark(benchmark["benchmark_id"], {"accuracy": 0.91})["status"] == "passed"

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("plugin.json", json.dumps({"name": "safe", "version": "1", "permissions": []}))
        bundle.writestr("module.py", "x=1")
    inspection = store.inspect_plugin(archive.getvalue(), "safe.zip")
    assert inspection["safe_to_register"]
    registered_plugin = store.register_plugin_inspection(inspection)
    assert registered_plugin["status"] == "inspected"
    installed = store.install_plugin_archive(archive.getvalue(), inspection, trust_unverified=True)
    assert installed["status"] == "installed_disabled"
    assert store.set_plugin_status(installed["plugin_id"], "enabled")["status"] == "enabled"


def test_unified_report_bundle_contains_four_formats():
    bundle = build_report_bundle("Report", [{"heading": "Methods", "body": "Bounded test"}], {"schema": "test"})
    assert bundle["html"].startswith(b"<!doctype html>")
    assert bundle["docx"].startswith(b"PK")
    assert bundle["pdf"].startswith(b"%PDF")
    assert json.loads(bundle["manifest"])["schema"] == "test"


def test_annotation_h5ad_and_sequence_specific_import_hardening(tmp_path: Path):
    import h5py

    gtf = b'chr1\tsource\ttranscript\t100\t500\t.\t+\t.\tgene_id "GENE1"; transcript_id "TX1";\n'
    annotation = read_upload(Upload("annotation.gtf", gtf), "rna_isoform_splicing")
    assert annotation.iloc[0]["gene"] == "GENE1"
    assert annotation.iloc[0]["transcript"] == "TX1"

    h5ad_path = tmp_path / "atlas.h5ad"
    with h5py.File(h5ad_path, "w") as h5:
        obs = h5.create_group("obs")
        obs.create_dataset("_index", data=np.array([b"cell1", b"cell2"]))
        obs.create_dataset("cell_type", data=np.array([b"T cell", b"B cell"]))
        obs.create_dataset("confidence", data=np.array([0.92, 0.84]))
        obs.create_dataset("batch", data=np.array([b"A", b"B"]))
    atlas = read_upload(Upload("atlas.h5ad", h5ad_path.read_bytes()), "cell_atlas_mapping")
    assert atlas["cell"].tolist() == ["cell1", "cell2"]
    assert atlas["reference_label"].tolist() == ["T cell", "B cell"]
    assert np.allclose(atlas["similarity"], [0.92, 0.84])

    enzyme_raw = read_upload(Upload("enzymes.fasta", b">E1\nMKWVTFISLLLLFSSAYSRGVFRR\n"), "enzyme_pathway_design")
    enzyme = normalise(enzyme_raw, MODULE_BY_KEY["enzyme_pathway_design"])
    assert enzyme[["activity", "stability", "flux"]].notna().all().all()
    assert enzyme.iloc[0]["score_source"] == "sequence_composition_proxy"

    virus = read_upload(Upload("virus.fasta", b">ref\nACGTACGT\n>sample\nACGTTCGT\n"), "virology_evolution")
    assert len(virus) == 1
    assert int(virus.iloc[0]["position"]) == 5
    assert virus.iloc[0]["ref"] == "A" and virus.iloc[0]["alt"] == "T"
