from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, plan_catalog
from biointel.scientific_depth.native_integrity import (
    build_complete_result_bundle,
    full_frame_sha256,
    manifest_table_payload,
    parse_scientific_bool,
    ranked_numeric_features,
)
from biointel.scientific_depth.native_workflows import (
    native_input_template,
    native_portfolio_manifest,
    native_workflow_catalog,
    run_native_workflow,
)
from biointel.scientific_depth.profiles import MODULE_PROFILES
from biointel.scientific_depth.toolchain_readiness import reference_readiness
from biointel.release_hygiene import audit_runtime_residue, clean_runtime_residue


def test_safe_boolean_parser_blocks_truthy_string_trap() -> None:
    for value in ("False", "false", "NO", "0", "off", "", None, pd.NA):
        assert parse_scientific_bool(value) is False
    for value in ("True", "yes", "1", "on", 1, True):
        assert parse_scientific_bool(value) is True
    assert parse_scientific_bool("unreviewed") is False


def test_full_frame_hash_covers_rows_beyond_old_10k_boundary() -> None:
    first = pd.DataFrame({"value": np.arange(10_020), "label": ["x"] * 10_020})
    second = first.copy()
    second.loc[10_019, "value"] = -999
    assert full_frame_sha256(first) != full_frame_sha256(second)


def test_numeric_selection_is_ranked_not_first_column_order() -> None:
    frame = pd.DataFrame({f"constant_{index:03d}": [index] * 30 for index in range(120)})
    frame["informative_last"] = np.arange(30, dtype=float)
    selected, audit = ranked_numeric_features(frame, limit=10)
    assert "informative_last" in selected
    assert not audit.empty
    assert int(audit.loc[audit.feature == "informative_last", "selection_rank"].iloc[0]) == 1


def test_complete_table_bundle_preserves_full_rows_and_declares_preview() -> None:
    table = pd.DataFrame({"row_id": np.arange(5_125), "value": np.arange(5_125) * 2})
    previews, artifacts = manifest_table_payload({"large": table}, preview_limit=5_000)
    assert len(previews["large"]) == 5_000
    assert artifacts[0]["rows"] == 5_125
    assert artifacts[0]["preview_complete"] is False
    payload = build_complete_result_bundle({"table_artifacts": artifacts}, {"large": table})
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        restored = pd.read_csv(archive.open("tables/large.csv"))
        assert len(restored) == 5_125
        assert "manifest.json" in archive.namelist()


def test_reference_readiness_rejects_filename_only_false_positive(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "reference_packs"
    folder.mkdir(parents=True)
    (folder / "genome_annotation_model_reference.csv").write_text("fake,asset\n1,2\n", encoding="utf-8")
    frame = reference_readiness(tmp_path, ["population_gwas"])
    assert not frame.empty
    assert not frame["local_candidate_detected"].any()
    assert not frame["qualified_for_use"].any()
    assert frame["detection_policy"].str.contains("filename-only matches prohibited", regex=False).all()


def test_all_profile_engines_are_registered_or_biointel_native() -> None:
    missing: dict[str, list[str]] = {}
    for module_key, profile in MODULE_PROFILES.items():
        unknown = [engine for engine in profile.engines if not engine.startswith("biointel_native::") and engine.lower() not in ENGINE_REGISTRY]
        if unknown:
            missing[module_key] = unknown
    assert missing == {}


def test_new_external_adapter_plans_are_safe_and_bounded(tmp_path: Path) -> None:
    reads1 = tmp_path / "r1.fastq"
    reads2 = tmp_path / "r2.fastq"
    peptides = tmp_path / "peptides.txt"
    graph = tmp_path / "graph.gfa"
    fasta = tmp_path / "protein.fasta"
    jsonl = tmp_path / "parsed.jsonl"
    model = tmp_path / "dorado_model"
    pod5 = tmp_path / "pod5"
    database = tmp_path / "kraken_db"
    for path in (reads1, reads2, peptides, graph, fasta, jsonl):
        path.write_text("demo\n", encoding="utf-8")
    for path in (model, pod5, database):
        path.mkdir()
    cases = {
        "bowtie2_align": {"reads1": reads1, "reads2": reads2, "index_prefix": tmp_path / "idx"},
        "kraken2_classify": {"database": database, "reads1": reads1, "reads2": reads2},
        "netmhcpan_predict": {"peptides": peptides, "allele": "HLA-A02:01", "peptide_length": 9},
        "dorado_basecall": {"model": model, "reads": pod5, "device": "auto"},
        "vg_stats": {"graph": graph},
        "odgi_stats": {"graph": graph},
        "graphaligner_align": {"graph": graph, "reads": reads1},
        "proteinmpnn_design": {"jsonl": jsonl, "num_seq_per_target": 5, "sampling_temp": 0.1},
        "colabfold_predict": {"fasta": fasta, "num_recycle": 3, "num_models": 5},
    }
    for key, arguments in cases.items():
        plan = build_engine_plan(key, workdir=tmp_path, **arguments)
        assert plan.command
        assert plan.cwd == str(tmp_path.resolve())
        assert all(Path(item).is_relative_to(tmp_path.resolve()) for item in plan.inputs)
    assert len(plan_catalog()) >= 41


def test_step154_has_dedicated_operational_families() -> None:
    catalog = native_workflow_catalog()
    assert len(catalog) == 80
    assert catalog.family.nunique() >= 49
    expected = {
        "background_job_engine": "job-orchestration",
        "collaboration_review_v2": "collaboration-review",
        "data_lakehouse_v2": "data-lakehouse",
        "evidence_citation_engine": "evidence-citation",
        "plugin_marketplace_core": "plugin-security",
        "provenance_ledger_v2": "provenance-ledger",
        "reference_lifecycle_v2": "reference-lifecycle",
        "unified_report_builder": "report-governance",
        "workflow_builder_core": "workflow-orchestration",
    }
    actual = dict(zip(catalog.module_key, catalog.family))
    assert {key: actual[key] for key in expected} == expected
    manifest = native_portfolio_manifest()
    assert manifest["complete_result_bundle_available"] is True
    assert "first-column" in manifest["numeric_feature_selection"]


def test_platform_security_negative_case_fails_closed() -> None:
    frame = pd.DataFrame(
        {
            "plugin_id": ["P-001"],
            "publisher": ["untrusted"],
            "signature_valid": ["False"],
            "isolated_environment": ["False"],
            "permissions_reviewed": ["False"],
        }
    )
    result = run_native_workflow("plugin_marketplace_core", frame)
    assert result.status == "fail"
    assert (result.checks.status == "fail").any()


def test_gwas_workflow_generates_sample_qc_pca_and_relatedness() -> None:
    result = run_native_workflow("population_gwas", native_input_template("population_gwas", demonstration=True))
    assert {"variant_qc", "sample_qc", "ancestry_pca", "relatedness_flags"}.issubset(result.tables)
    assert not result.tables["sample_qc"].empty
    assert not result.tables["ancestry_pca"].empty
    assert "PC1" in result.tables["ancestry_pca"].columns


def test_metabolomics_workflow_adds_drift_correction_artifacts() -> None:
    result = run_native_workflow("metabolomics_lipidomics", native_input_template("metabolomics_lipidomics", demonstration=True))
    assert "feature_qc" in result.tables
    assert "drift_correction_models" in result.tables
    assert "drift_corrected_intensities" in result.tables


def test_release_hygiene_removes_sqlite_sidecars_and_bytecode(tmp_path: Path) -> None:
    (tmp_path / "data.sqlite-wal").write_text("runtime", encoding="utf-8")
    (tmp_path / "data.sqlite-shm").write_text("runtime", encoding="utf-8")
    cache = tmp_path / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-313.pyc").write_bytes(b"bytecode")
    assert audit_runtime_residue(tmp_path)
    report = clean_runtime_residue(tmp_path)
    assert report.clean
    assert audit_runtime_residue(tmp_path) == []
