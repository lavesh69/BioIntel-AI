from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from biointel.bioinformatics_peak_v138.catalog import MODULES, MODULE_BY_KEY
from biointel.bioinformatics_peak_v138.comparison import compare_frames
from biointel.bioinformatics_peak_v138.engine_queue import compatible_auto_plans, engine_plan_parameters
from biointel.bioinformatics_peak_v138.native_profiles import NATIVE_PROFILES, profile_for
from biointel.bioinformatics_peak_v138.native_runtime import prepare_native_input
from biointel.bioinformatics_peak_v138.publication import build_publication_bundle
from biointel.bioinformatics_peak_v138.reference_registry import ReferenceRegistry
from biointel.bioinformatics_peak_v138.review_store import ReviewStore
from biointel.bioinformatics_peak_v138.scientific import analyse_module, demo_frame
from biointel.bioinformatics_peak_v138.visuals import build_visuals
from biointel.native.engines import ENGINE_REGISTRY
from biointel.native.formats import parse_native_path


ROOT = Path(__file__).resolve().parents[1]


class Upload(io.BytesIO):
    def __init__(self, payload: bytes, name: str):
        super().__init__(payload)
        self.name = name
        self.size = len(payload)

    def getvalue(self) -> bytes:
        return super().getvalue()


def test_all_fifteen_modules_have_native_peak_profiles() -> None:
    assert set(NATIVE_PROFILES) == {module.key for module in MODULES}
    for module in MODULES:
        profile = profile_for(module.key)
        assert profile.accepted_extensions
        assert len(profile.reference_assets) >= 4
        assert len(profile.native_features) >= 4
        assert profile.comparison_identifiers
        assert all(engine in ENGINE_REGISTRY for engine in profile.engines)


def test_native_gwas_vcf_is_checksum_bound_and_analysis_ready(tmp_path: Path) -> None:
    vcf = b"""##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n1\t100\trs1\tA\tG\t60\tPASS\tAF=0.2;DP=100\tGT\t0/1\n"""
    bundle = prepare_native_input(tmp_path, Upload(vcf, "cohort.vcf"), module_key="population_gwas_peak")
    assert Path(bundle.staged_path).is_file()
    assert Path(bundle.manifest_path).is_file()
    assert bundle.parse_result.sha256
    assert bundle.analysis_ready
    assert set(MODULE_BY_KEY["population_gwas_peak"].required_columns).issubset(bundle.analysis_frame.columns)
    manifest = json.loads(Path(bundle.manifest_path).read_text())
    assert manifest["analysis_ready"] is True
    assert manifest["sha256"] == bundle.parse_result.sha256


def test_native_bed_gff_and_bedpe_normalization(tmp_path: Path) -> None:
    epi = prepare_native_input(tmp_path, Upload(b"chr1\t10\t100\tpeak1\t12\n", "peaks.bed"), module_key="epigenomics_peak")
    assert epi.analysis_ready
    assert {"sample", "region", "condition", "signal"}.issubset(epi.analysis_frame.columns)

    gff = b"chr1\tsource\tgene\t10\t100\t.\t+\t.\tID=gene1;Name=GENE1\n"
    annotation = prepare_native_input(tmp_path, Upload(gff, "annotation.gff3"), module_key="genome_annotation")
    assert annotation.analysis_ready
    assert annotation.analysis_frame.loc[0, "feature_id"] == "gene1"

    bedpe = b"chr1\t10\t20\tchr2\t30\t40\tevent1\t9\t+\t-\n"
    sv = prepare_native_input(tmp_path, Upload(bedpe, "events.bedpe"), module_key="structural_variant_peak")
    assert sv.analysis_ready
    assert sv.analysis_frame.loc[0, "event_type"] == "TRANSLOCATION"
    assert sv.analysis_frame.loc[0, "partner_chrom"] == "chr2"


def test_binary_native_assets_never_deserialise_unsafely(tmp_path: Path) -> None:
    pgen = tmp_path / "cohort.pgen"
    pgen.write_bytes(b"\x6c\x1b\x01binary-genotype-placeholder")
    parsed = parse_native_path(pgen)
    assert parsed.format_key == "plink_binary"
    assert parsed.engine_required == "plink2"
    assert parsed.primary.loc[0, "decode_state"] == "external_engine_required"
    assert parsed.sha256

    bigwig = tmp_path / "signal.bw"
    bigwig.write_bytes(b"\x26\xfc\x8f\x88binary-bigwig-placeholder")
    parsed_bw = parse_native_path(bigwig)
    assert parsed_bw.format_key == "bigwig"
    assert parsed_bw.engine_required == "deeptools"
    assert parsed_bw.primary.loc[0, "decode_state"] == "external_engine_required"


def test_auto_engine_plan_is_protected_and_path_bound(tmp_path: Path) -> None:
    vcf = b"""##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\t100\trs1\tA\tG\t60\tPASS\tAF=0.2\n"""
    bundle = prepare_native_input(tmp_path, Upload(vcf, "calls.vcf"), module_key="structural_variant_peak")
    plans = compatible_auto_plans("structural_variant_peak", bundle.staged_path)
    assert any(plan.plan_key == "bcftools_stats" for plan in plans)
    plan = next(plan for plan in plans if plan.plan_key == "bcftools_stats")
    parameters = engine_plan_parameters(plan, bundle.staged_path)
    assert Path(parameters["vcf"]).resolve() == Path(bundle.staged_path).resolve()
    assert Path(parameters["output"]).parent == Path(bundle.staged_path).parent


def test_reference_registry_pins_and_rechecks_sha256(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_root = tmp_path / "references"
    asset_root.mkdir()
    asset = asset_root / "reference.fa"
    asset.write_text(">chr1\nACGT\n")
    monkeypatch.setenv("BIOINTEL_REFERENCE_ASSETS_DIR", str(asset_root))
    registry = ReferenceRegistry(tmp_path)
    requirement = profile_for("population_gwas_peak").reference_assets[0]
    registry.bind("population_gwas_peak", requirement, "reference.fa", pin_checksum=True)
    table = registry.table("population_gwas_peak")
    assert table.loc[table["Reference asset"] == requirement, "Status"].iloc[0] == "Verified"
    asset.write_text(">chr1\nACGTA\n")
    table = registry.table("population_gwas_peak")
    assert table.loc[table["Reference asset"] == requirement, "Status"].iloc[0] == "Checksum mismatch"


def test_review_snapshot_comparison_and_audit_queue(tmp_path: Path) -> None:
    module_key = "population_gwas_peak"
    source = demo_frame(module_key, 80)
    bundle = analyse_module(source, module_key)
    store = ReviewStore(tmp_path)
    snapshot = store.save_snapshot(
        module_key=module_key,
        input_sha256=store.frame_sha(source),
        result=bundle.result,
        summary=bundle.summary,
        parameters={"priority_threshold": 0.7},
    )
    loaded = store.load_snapshot_frame(snapshot.run_id)
    assert len(loaded) == len(bundle.result)
    changed = bundle.result.copy()
    changed.loc[0, "priority_score"] = min(1.0, float(changed.loc[0, "priority_score"]) + 0.1)
    comparison = compare_frames(changed, loaded, identifier_candidates=profile_for(module_key).comparison_identifiers)
    assert comparison.summary["overlap_records"] > 0
    key = str(changed.loc[0, "variant"])
    decision = store.upsert_decision(
        module_key=module_key,
        run_id=snapshot.run_id,
        record_key=key,
        record=changed.iloc[0].to_dict(),
        status="Needs confirmation",
        reason="Independent cohort confirmation required",
        reviewer="Test reviewer",
    )
    assert decision["status"] == "Needs confirmation"
    assert store.summary(module_key)["Needs confirmation"] == 1
    assert len(store.decisions(module_key)) == 1


def test_publication_bundle_contains_all_figure_assets() -> None:
    module_key = "viral_within_host"
    source = demo_frame(module_key, 80)
    bundle = analyse_module(source, module_key)
    visuals = build_visuals(module_key, bundle)
    payload = build_publication_bundle(
        module_key=module_key,
        source=source,
        bundle=bundle,
        visuals=visuals,
        parameters={"priority_threshold": 0.7},
        include_static=False,
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "methods.md" in names
        assert "report.html" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["figures"]) == 12
        for figure in manifest["figures"]:
            assert figure["data_path"] in names
            assert figure["plotly_json_path"] in names
            assert figure["interactive_html_path"] in names


def test_renderer_and_pages_expose_step139_peak_workflows() -> None:
    renderer = (ROOT / "src/biointel/bioinformatics_peak_v138/renderer.py").read_text(encoding="utf-8")
    for token in ("Review & compare", "Native & engines", "Publication-grade figure package", "Queue verified engine plan", "Linked visual filters"):
        assert token in renderer
    for module in MODULES:
        if module.existing_page:
            page = (ROOT / module.existing_page).read_text(encoding="utf-8")
            assert "bioinformatics_peak_v138" in page
