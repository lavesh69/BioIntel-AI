from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pandas as pd

from biointel.innovation.advanced_engines import workflow_dag_from_blocks
from biointel.innovation.engines import WORKFLOW_TEMPLATES
from biointel.quality10 import WorkflowRegistry, assess_quality, execute_workflow_v3, run_self_test, sha256_file
from biointel.tools.runtime import load_manifest, run_tool_audited


def test_quality_model_separates_implementation_and_external_evidence():
    assessment = assess_quality(
        input_integrity=10,
        reproducibility=10,
        execution_completion=10,
        error_handling=10,
        test_coverage=10,
        provenance=10,
        external_validation=0,
        prospective_validation=0,
        peer_review=0,
        clinical_or_regulatory=0,
        source_kind="software_qualification",
    )
    assert assessment.implementation_readiness == 10
    assert assessment.scientific_evidence_score == 0
    assert not assessment.release_eligible
    assert assessment.blockers


def test_registry_enforces_integrity(tmp_path: Path):
    registry = WorkflowRegistry(tmp_path / "runs.sqlite3")
    report = registry.integrity_report()
    assert report["healthy"]
    assert report["foreign_key_issues"] == []


def test_real_workflow_creates_hashed_artifacts_and_registry(tmp_path: Path):
    dag = workflow_dag_from_blocks(WORKFLOW_TEMPLATES["Protein engineering"])
    result = execute_workflow_v3(
        dag,
        tmp_path / "runs",
        "protein_quality10",
        parameters={"candidate_limit": 25, "fail_on_quality_gate": False},
        registry_path=tmp_path / "runs.sqlite3",
        source_kind="user_supplied",
    )
    assert result.status == "completed"
    assert len(result.steps) == 3
    assert len(result.artifacts) >= 3
    for artifact in result.artifacts:
        path = Path(artifact["path"])
        assert path.is_file()
        assert sha256_file(path) == artifact["sha256"]
    registry = WorkflowRegistry(tmp_path / "runs.sqlite3")
    integrity = registry.integrity_report()
    assert integrity["healthy"]
    assert integrity["counts"]["workflow_runs"] == 1
    assert integrity["counts"]["workflow_steps"] == 3
    assert integrity["counts"]["workflow_artifacts"] >= 3


def test_long_read_workflow_executes_qc_and_report(tmp_path: Path):
    dag = workflow_dag_from_blocks(WORKFLOW_TEMPLATES["Long-read genome assembly"])
    result = execute_workflow_v3(
        dag,
        tmp_path / "runs",
        "long_read_quality10",
        parameters={"demo_reads": 40, "max_reads": 1000, "genome_size_mb": 0.5, "fail_on_quality_gate": False},
        registry_path=tmp_path / "runs.sqlite3",
        source_kind="demo",
        synthetic=True,
    )
    assert result.status == "completed"
    roles = {artifact["role"] for artifact in result.artifacts}
    assert {"reads", "qc_table", "assembly", "quality_gate", "report"}.issubset(roles)
    qc_summary = next(Path(a["path"]) for a in result.artifacts if a["role"] == "qc_summary")
    payload = json.loads(qc_summary.read_text())
    assert payload["reads"] == 40


def test_resume_uses_verified_artifacts(tmp_path: Path):
    dag = workflow_dag_from_blocks(WORKFLOW_TEMPLATES["Protein engineering"])
    first = execute_workflow_v3(
        dag,
        tmp_path / "runs",
        "resume_quality10",
        parameters={"candidate_limit": 10, "fail_on_quality_gate": False},
        registry_path=tmp_path / "runs.sqlite3",
    )
    second = execute_workflow_v3(
        dag,
        tmp_path / "runs",
        "resume_quality10",
        parameters={"candidate_limit": 10, "fail_on_quality_gate": False},
        registry_path=tmp_path / "runs.sqlite3",
        resume=True,
    )
    assert second.run_id == first.run_id
    assert second.resumed
    assert any(step.get("resumed") for step in second.steps)


def test_audited_tool_execution_captures_logs_and_manifest(tmp_path: Path, monkeypatch):
    tool = tmp_path / "echo-tool"
    tool.write_text("#!/bin/sh\nprintf 'tool-output:%s\\n' \"$1\"\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("BIOINTEL_TOOL_ECHO_TOOL", str(tool))
    result = run_tool_audited("echo-tool", ["hello"], run_directory=tmp_path / "evidence", timeout_seconds=5)
    assert result.status == "completed"
    assert result.returncode == 0
    assert result.executable_sha256 == sha256_file(tool)
    assert "tool-output:hello" in Path(result.stdout_path).read_text()
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["status"] == "completed"
    assert manifest["command"][-1] == "hello"


def test_advanced_tool_manifest_expanded():
    manifest = load_manifest()
    ids = {item["id"] for item in manifest["tools"]}
    assert len(ids) >= 38
    assert {"flye", "hifiasm", "quast", "busco", "odgi", "vg", "minigraph", "foldseek", "nextflow"}.issubset(ids)


def test_step95_self_test(tmp_path: Path):
    report = run_self_test(tmp_path)
    assert report["status"] == "passed"
    assert all(item["passed"] for item in report["checks"])
    assert (tmp_path / "quality10_self_test.json").is_file()


def test_navigation_contains_quality_center():
    from biointel.ui.navigation import PAGE_CATALOG

    keys = {page.key for page in PAGE_CATALOG}
    assert "scientific_execution_quality" in keys


def test_distance_tree_and_layout_are_valid():
    from biointel.innovation.advanced_engines import distance_tree_newick, newick_tree_layout

    matrix = pd.DataFrame(
        [[0, 2, 7, 8], [2, 0, 6, 7], [7, 6, 0, 3], [8, 7, 3, 0]],
        index=["A", "B", "C", "D"],
        columns=["A", "B", "C", "D"],
    )
    newick = distance_tree_newick(matrix)
    assert newick.endswith(";")
    layout = newick_tree_layout(newick)
    assert set(layout) == {"nodes", "edges"}
    assert set(layout["nodes"].loc[layout["nodes"]["is_terminal"], "label"]) == {"A", "B", "C", "D"}
    assert len(layout["edges"]) == len(layout["nodes"]) - 1


def test_trio_segregation_detects_de_novo_candidate():
    from biointel.innovation.advanced_engines import trio_segregation_assessment

    frame = pd.DataFrame([
        {
            "chrom": "1",
            "pos": 100,
            "sample_genotypes": json.dumps({
                "proband": {"GT": "0/1"},
                "mother": {"GT": "0/0"},
                "father": {"GT": "0/0"},
            }),
        }
    ])
    result = trio_segregation_assessment(frame, proband="proband", mother="mother", father="father")
    assert result.loc[0, "segregation_pattern"] == "de_novo_candidate"
    assert bool(result.loc[0, "segregation_support"])
    assert not bool(result.loc[0, "mendelian_inconsistency"])
