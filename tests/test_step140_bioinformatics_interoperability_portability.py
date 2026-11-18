from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from biointel.bioinformatics_peak_v138.benchmark_center import BENCHMARK_PROFILES, BenchmarkStore, run_benchmark
from biointel.bioinformatics_peak_v138.catalog import MODULES
from biointel.bioinformatics_peak_v138.consensus import build_consensus
from biointel.bioinformatics_peak_v138.execution_peak import CheckpointStore, diagnose_failure, plan_resources
from biointel.bioinformatics_peak_v138.harmonization import harmonize_samples
from biointel.bioinformatics_peak_v138.indexed_streaming import GenomicRegion, index_status, progressive_tiles, query_region
from biointel.bioinformatics_peak_v138.interoperability import (
    categorical_variant,
    drs_object,
    htsget_request,
    sequence_identifier,
    standards_bundle,
    validate_phenopacket,
    variation_statement,
    vrs_allele,
)
from biointel.bioinformatics_peak_v138.portable_workflows import ContainerSpec, TaskSpec, default_plan, import_workflow_descriptor, workflow_pack
from biointel.bioinformatics_peak_v138.reference_diff import compare_reference_releases
from biointel.bioinformatics_peak_v138.result_versions import ResultVersionStore
from biointel.bioinformatics_peak_v138.scientific import analyse_module, demo_frame
from biointel.bioinformatics_peak_v138.uncertainty import bootstrap_summary, uncertainty_table

ROOT = Path(__file__).resolve().parents[1]


def test_all_modules_have_portable_workflow_and_benchmark_profiles() -> None:
    assert set(BENCHMARK_PROFILES) == {module.key for module in MODULES}
    for module in MODULES:
        plan = default_plan(module.key)
        manifest = plan.to_manifest()
        assert manifest["workflow_digest"].startswith("sha256:")
        assert len(plan.tasks) >= 3
        assert plan.wes_run_request()["workflow_type"] == "CWL"
        assert plan.tes_tasks()
        assert plan.trs_descriptor()["versions"][0]["verified"] is True
        pack = workflow_pack(plan)
        assert set(pack) == {"manifest", "WES", "TES", "TRS", "DRS_inputs"}


def test_container_digest_and_no_shell_task_guards() -> None:
    digest = "sha256:" + "a" * 64
    container = ContainerSpec("example/tool:1", digest)
    task = TaskSpec("x", "safe", ("tool", "--version"), container=container)
    assert task.container.digest == digest
    with pytest.raises(ValueError):
        ContainerSpec("bad", "sha256:123")
    with pytest.raises(ValueError):
        TaskSpec("x", "unsafe", ("tool", "&&", "rm"))


def test_workflow_descriptor_import_is_metadata_only() -> None:
    cwl = import_workflow_descriptor("cwlVersion: v1.2\nclass: Workflow\n", filename="main.cwl")
    nf = import_workflow_descriptor("nextflow.enable.dsl=2\nworkflow TEST { }\n", filename="main.nf")
    assert cwl["type"] == "CWL"
    assert nf["type"] == "Nextflow"
    assert "metadata-only" in nf["execution_state"]


def test_ga4gh_style_identifiers_are_deterministic() -> None:
    sequence_id = sequence_identifier("ACGT\nACGT")
    assert sequence_id.startswith("ga4gh:SQ.")
    a = vrs_allele({"chrom": "1", "position": 100, "ref": "A", "alt": "G"})
    b = vrs_allele({"chrom": "1", "position": 100, "ref": "A", "alt": "G"})
    assert a["id"] == b["id"] and a["id"].startswith("ga4gh:VA.")
    categorical = categorical_variant([a], label="test")
    statement = variation_statement(a, proposition="Research association")
    assert categorical["id"].startswith("ga4gh:CX.")
    assert statement["id"].startswith("ga4gh:VD.")


def test_phenopacket_validation_and_portable_data_manifests() -> None:
    valid = {
        "id": "packet-1",
        "subject": {"id": "subject-1"},
        "phenotypicFeatures": [{"type": {"id": "HP:0001250"}}],
        "metaData": {"createdBy": "test"},
    }
    assert validate_phenopacket(valid) == []
    invalid = {"id": "packet-2", "phenotypicFeatures": [{"type": {"id": "BAD"}}]}
    issues = validate_phenopacket(invalid)
    assert any(issue.severity == "Review" for issue in issues)
    drs = drs_object(object_id="obj", name="cohort.vcf", size=10, sha256="f" * 64, access_uri="file:///tmp/cohort.vcf")
    request = htsget_request(data_id="obj", reference_name="chr1", start=10, end=20, data_format="VCF")
    assert drs["checksums"][0]["type"] == "sha-256"
    assert request["start"] == 10


def test_standards_bundle_canonicalizes_variant_rows() -> None:
    frame = pd.DataFrame({"chrom": ["1"], "position": [100], "ref": ["A"], "alt": ["G"]})
    bundle = standards_bundle("population_gwas_peak", frame)
    assert bundle["variant_summary"]["Canonicalized"] == 1
    assert bundle["variant_records"][0]["vrs_id"].startswith("ga4gh:VA.")


def test_indexed_text_region_query_and_tiles(tmp_path: Path) -> None:
    vcf = tmp_path / "calls.vcf"
    vcf.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchr1\t50\trs1\tA\tG\t60\tPASS\t.\nchr1\t500\trs2\tC\tT\t60\tPASS\t.\n")
    region = GenomicRegion.parse("chr1:1-100")
    result = query_region(vcf, region)
    assert result["id"].tolist() == ["rs1"]
    assert index_status(vcf)["random_access_ready"] is True
    tiles = progressive_tiles(GenomicRegion("chr1", 0, 2500), tile_size=1000)
    assert [(t.start, t.end) for t in tiles] == [(0, 1000), (1000, 2000), (2000, 2500)]


def test_multi_engine_consensus_tracks_agreement_and_unique_calls() -> None:
    frame = pd.DataFrame(
        {
            "chrom": ["1", "1", "2"],
            "position": [100, 100, 300],
            "ref": ["A", "A", "C"],
            "alt": ["G", "G", "T"],
            "caller": ["A", "B", "A"],
            "quality": [80, 70, 60],
        }
    )
    bundle = build_consensus(frame, minimum_callers=2)
    assert len(bundle.consensus) == 2
    assert int(bundle.consensus.iloc[0]["caller_count"]) == 2
    assert len(bundle.unique_calls) == 1
    assert set(bundle.agreement_matrix["caller"]) == {"A", "B"}


def test_uncertainty_and_harmonization_are_deterministic() -> None:
    summary = bootstrap_summary(pd.Series([1.0, 2.0, 3.0, 4.0]), iterations=200, seed=1)
    assert summary.lower <= summary.estimate <= summary.upper
    frame = pd.DataFrame({"sample": ["s 1", "S-2"], "priority_score": [0.7, 0.9]})
    table, meta = uncertainty_table(frame, iterations=200)
    assert not table.empty and meta["overall_stability"] >= 0
    harmonized = harmonize_samples([frame, frame.copy()])
    assert harmonized.summary["samples_shared_across_sources"] == 2


def test_reference_release_diff_reports_added_removed_changed() -> None:
    old = pd.DataFrame({"id": ["A", "B"], "value": [1, 2]})
    new = pd.DataFrame({"id": ["A", "C"], "value": [3, 4]})
    diff = compare_reference_releases(old, new, key_columns=["id"])
    assert diff.summary == {"added": 1, "removed": 1, "changed": 1, "unchanged": 0, "keys": ["id"]}


def test_resource_planner_checkpoint_and_failure_intelligence(tmp_path: Path) -> None:
    interactive = plan_resources(input_bytes=1024, rows=100, columns=10)
    background = plan_resources(input_bytes=700 * 1024**2, rows=2_000_000, columns=20)
    assert interactive.mode == "Interactive"
    assert background.mode in {"Background local", "External/HPC"}
    store = CheckpointStore(tmp_path)
    store.save(run_id="run", stage="verify", status="completed", input_hash="abc", parameters={"x": 1}, output_hash="def")
    compatible = store.resume_state("run", input_hash="abc", parameters={"x": 1})
    incompatible = store.resume_state("run", input_hash="changed", parameters={"x": 1})
    assert compatible[0]["resume_compatible"] is True
    assert incompatible[0]["resume_compatible"] is False
    diagnostic = diagnose_failure("Out of memory", stage="analysis")
    assert diagnostic["category"] == "Memory" and diagnostic["recovery_id"].startswith("BIO140-")


def test_benchmark_center_requires_explicit_truth_and_saves_history(tmp_path: Path) -> None:
    frame = pd.DataFrame({"truth": [1, 0, 1, 0], "score": [0.9, 0.2, 0.8, 0.1], "group": ["A", "A", "B", "B"]})
    table, summary = run_benchmark(frame, truth_column="truth", prediction_column="score", module_key="population_gwas_peak", subgroup_column="group")
    assert summary["f1"] == 1.0
    assert set(table["stratum"]) == {"Overall", "A", "B"}
    store = BenchmarkStore(tmp_path)
    run_id = store.save("population_gwas_peak", summary)
    assert run_id >= 1
    assert len(store.history("population_gwas_peak")) == 1


def test_result_version_store_preserves_hash_and_state(tmp_path: Path) -> None:
    frame = pd.DataFrame({"id": [1, 2], "value": [3, 4]})
    store = ResultVersionStore(tmp_path)
    draft = store.save(module_key="population_gwas_peak", frame=frame, state="Draft", reason="initial", reviewer="reviewer", input_hash="abc")
    assert store.load(draft["version_id"]).equals(frame)
    locked = store.save(module_key="population_gwas_peak", frame=frame, state="Locked", reason="reviewed", reviewer="reviewer", input_hash="abc", parent_version_id=draft["version_id"])
    versions = store.list("population_gwas_peak")
    assert set(versions["state"]) == {"Draft", "Locked"}
    assert locked["result_hash"] == draft["result_hash"]


def test_step140_publication_bundle_contains_portability_and_uncertainty() -> None:
    from biointel.bioinformatics_peak_v138.publication import build_publication_bundle
    from biointel.bioinformatics_peak_v138.visuals import build_visuals
    import io
    import zipfile

    module_key = "population_gwas_peak"
    source = demo_frame(module_key, 120)
    bundle = analyse_module(source, module_key)
    payload = build_publication_bundle(module_key=module_key, source=source, bundle=bundle, visuals=build_visuals(module_key, bundle), parameters={}, include_static=False)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "interoperability/standards_bundle.json" in names
        assert "workflow/portable_workflow_pack.json" in names
        assert "validation/uncertainty_summary.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"].endswith("v140")


def test_renderer_exposes_step140_workspaces() -> None:
    text = (ROOT / "src/biointel/bioinformatics_peak_v138/renderer.py").read_text(encoding="utf-8")
    for token in (
        "Standards & validation",
        "Portable WES / TES / TRS / DRS workflow pack",
        "Indexed regional inspection",
        "Multi-engine consensus and uncertainty",
        "Gold-standard benchmark center",
        "Scientific result versioning",
        "Stage checkpoint compatibility",
        "Scientific inspection drawer",
        "Reference release difference viewer",
    ):
        assert token in text


def test_all_modules_receive_last_mile_features_and_tables() -> None:
    from biointel.bioinformatics_peak_v138.last_mile import LAST_MILE_PROFILES
    assert set(LAST_MILE_PROFILES) == {module.key for module in MODULES}
    for module in MODULES:
        bundle = analyse_module(demo_frame(module.key, 120), module.key)
        assert bundle.summary["last_mile_features"]
        assert bundle.summary["specialist_confirmations"]
        assert bundle.summary["last_mile_tables"]
        assert all(name in bundle.extras for name in bundle.summary["last_mile_tables"])


def test_last_mile_gwas_meta_analysis_and_sv_baf() -> None:
    from biointel.bioinformatics_peak_v138.last_mile import augment_bundle
    from biointel.bioinformatics_peak_v138.catalog import MODULE_BY_KEY
    from biointel.bioinformatics_peak_v138.scientific import AnalysisBundle
    empty_quality = pd.DataFrame([{"check": "test", "status": "Pass"}])
    gwas = pd.DataFrame({"variant": ["v1", "v1"], "study": ["a", "b"], "beta": [0.2, 0.3], "se": [0.1, 0.2], "gene": ["G1", "G1"], "genotype": [1, 2], "sample": ["S1", "S2"], "ancestry": ["A", "B"]})
    base = AnalysisBundle(gwas.copy(), {"metrics": {}}, {}, empty_quality)
    enhanced = augment_bundle(gwas, MODULE_BY_KEY["population_gwas_peak"], base)
    assert "last_mile_fixed_effect_meta_analysis" in enhanced.extras
    sv = pd.DataFrame({"event_id": ["e1"], "baf": [0.1], "allele_fraction": [0.2], "support": [20]})
    base_sv = AnalysisBundle(sv.copy(), {"metrics": {}}, {}, empty_quality)
    enhanced_sv = augment_bundle(sv, MODULE_BY_KEY["structural_variant_peak"], base_sv)
    assert "last_mile_baf_cnv_evidence" in enhanced_sv.extras
    assert "last_mile_mosaic_confidence" in enhanced_sv.extras
