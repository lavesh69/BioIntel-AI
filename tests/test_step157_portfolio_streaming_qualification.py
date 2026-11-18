from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from biointel.native.engine_plans_step157 import STEP157_PLAN_REQUIREMENTS, build_step157_plan
from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, plan_catalog
from biointel.scientific_depth import (
    portfolio_readiness_matrix,
    profile_tabular_file,
    readiness_summary,
)
from biointel.validation.target_qualification import qualify_target


ROOT = Path(__file__).resolve().parents[1]


def test_step157_engine_and_plan_coverage() -> None:
    assert len(ENGINE_REGISTRY) >= 76
    assert len(plan_catalog()) >= 78
    assert len(STEP157_PLAN_REQUIREMENTS) == 12
    required = {
        "fastqc_run",
        "multiqc_report",
        "fastp_trim",
        "cutadapt_trim",
        "snpeff_annotate",
        "interproscan_annotate",
        "hmmsearch_scan",
        "blastp_search",
        "mosdepth_coverage",
        "picard_collect_alignment_metrics",
        "salmon_quant",
        "kallisto_quant",
    }
    assert required <= set(plan_catalog()["Plan"])


def test_step157_fastp_plan_is_path_bounded(tmp_path: Path) -> None:
    reads1 = tmp_path / "R1.fastq.gz"
    reads2 = tmp_path / "R2.fastq.gz"
    reads1.write_bytes(b"reads1")
    reads2.write_bytes(b"reads2")
    payload = build_step157_plan(
        "fastp_trim",
        executable="fastp",
        workdir=tmp_path,
        parameters={"reads1": reads1, "reads2": reads2, "threads": 4},
    )
    assert payload["command"][0] == "fastp"
    assert "--detect_adapter_for_pe" in payload["command"]
    assert payload["resources"]["shell"] is False
    outside = tmp_path.parent / "outside.fastq.gz"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError):
        build_step157_plan(
            "fastp_trim",
            executable="fastp",
            workdir=tmp_path,
            parameters={"reads1": outside},
        )


def test_public_engine_plan_dispatches_step157(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reads = tmp_path / "reads.fastq.gz"
    reads.write_bytes(b"reads")
    # Detection is intentionally not required for protected plan construction.
    plan = build_engine_plan("fastqc_run", workdir=tmp_path, reads=[reads], threads=2)
    assert plan.engine_key == "fastqc"
    assert plan.plan_key == "fastqc_run"
    assert str(reads) in plan.inputs
    assert plan.resources["execution_policy"] == "explicit-user-action-only"


def test_streaming_profile_covers_complete_file_and_hash(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "sample_id": [f"S{i}" for i in range(25_000)],
            "value": list(range(25_000)),
            "group": ["A", "B"] * 12_500,
        }
    )
    source = tmp_path / "large table.csv"
    frame.to_csv(source, index=False)
    checkpoint = tmp_path / "profile.checkpoint.json"
    result = profile_tabular_file(
        source,
        chunk_rows=5_000,
        checkpoint_path=checkpoint,
        expected_columns=("sample_id", "value", "group", "required_missing"),
    )
    assert result.completed
    assert result.rows == 25_000
    assert result.chunks == 5
    assert result.missing_expected_columns == ("required_missing",)
    assert result.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert checkpoint.is_file()
    assert len(result.bundle()) > 500
    profile = pd.DataFrame(result.column_profile).set_index("column")
    assert profile.loc["value", "mean"] == pytest.approx(12_499.5)


def test_streaming_profile_hash_changes_after_late_row_edit(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    pd.DataFrame({"x": range(20_000)}).to_csv(source, index=False)
    first = profile_tabular_file(source, chunk_rows=5_000, checkpoint_path=tmp_path / "a.json")
    frame = pd.read_csv(source)
    frame.loc[len(frame) - 1, "x"] = -999
    frame.to_csv(source, index=False)
    second = profile_tabular_file(source, chunk_rows=5_000, checkpoint_path=tmp_path / "b.json")
    assert first.source_sha256 != second.source_sha256
    assert pd.DataFrame(second.column_profile).set_index("column").loc["x", "minimum"] == -999


def test_readiness_matrix_separates_implementation_and_external_evidence() -> None:
    matrix = portfolio_readiness_matrix(ROOT, detect_runtime=False)
    summary = readiness_summary(matrix)
    assert len(matrix) == 80
    assert summary["implementation_complete"] == 80
    assert summary["external_evidence_complete"] == 0
    assert summary["release_eligible"] == 0
    assert matrix.internal_implementation_score.eq(100).all()
    assert matrix.external_evidence_score.eq(0).all()
    assert matrix.blockers.str.contains("External evidence pending").all()


def test_target_qualification_core_checks_without_package_manifest(tmp_path: Path) -> None:
    # Use the real source root so the isolated subprocess can import BioIntel.
    report = qualify_target(ROOT, verify_manifest=False)
    assert report.passed
    indexed = {check.key: check for check in report.checks}
    assert indexed["path_with_spaces"].passed
    assert indexed["sqlite_integrity"].passed
    assert indexed["sqlite_foreign_keys"].passed
    assert indexed["core_python_import"].passed


def test_step157_command_center_exposes_honest_axes_and_streaming() -> None:
    source = (ROOT / "pages" / "227_Scientific_Readiness_Command_Center.py").read_text(encoding="utf-8")
    assert "Step 157 honest 10/10 readiness matrix" in source
    assert "Full-file streaming integrity profiler" in source
    assert "implementation-complete" in source.lower()
    assert "external scientific evidence" in source.lower()
    assert "profile_tabular_file" in source


def test_step157_windows_qualification_launcher_is_path_safe() -> None:
    source = (ROOT / "RUN_STEP157_TARGET_QUALIFICATION_WINDOWS.bat").read_text(encoding="utf-8")
    assert 'set "PROJECT_ROOT=%~dp0"' in source
    assert '"%PROJECT_ROOT%\\scripts\\step157_target_qualification.py"' in source
    assert "--ui" in source
