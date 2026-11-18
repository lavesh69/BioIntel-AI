from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

PDB_TEXT = """\
ATOM      1  N   ALA A   1      11.104  13.207   9.900  1.00 20.00           N
ATOM      2  CA  ALA A   1      12.560  13.207   9.900  1.00 20.00           C
ATOM      3  N   GLY A   2      13.100  14.500  10.300  1.00 20.00           N
ATOM      4  CA  GLY A   2      14.500  14.600  10.600  1.00 20.00           C
ATOM      5  N   LYS B  10      15.100  15.500  11.300  1.00 20.00           N
ATOM      6  CA  LYS B  10      16.500  15.600  11.600  1.00 20.00           C
END
"""


def test_stage_structure_is_immutable_and_summarised(tmp_path: Path) -> None:
    from biointel.step122.protein_design import stage_protein_design_input

    staged = stage_protein_design_input(
        workspace=tmp_path / "runs",
        source_bytes=PDB_TEXT.encode(),
        filename="target.pdb",
        run_name="binder target",
    )
    assert staged["input_kind"] == "structure"
    assert staged["summary"]["atom_count"] == 6
    assert set(staged["summary"]["chains"]) == {"A", "B"}
    assert staged["input_sha256"] == sha256(Path(staged["input_path"]).read_bytes()).hexdigest()
    assert Path(staged["run_directory"], "input_manifest.json").is_file()


def test_model_asset_registration_rejects_bad_digest(tmp_path: Path) -> None:
    from biointel.step122.protein_design import register_model_asset

    asset = tmp_path / "weights"
    asset.mkdir()
    (asset / "model.pt").write_bytes(b"verified model bytes")
    with pytest.raises(ValueError, match="SHA-256"):
        register_model_asset(
            "proteinmpnn",
            asset,
            workspace=tmp_path / "runs",
            expected_sha256="0" * 64,
            license_accepted=True,
        )
    record = register_model_asset(
        "proteinmpnn",
        asset,
        workspace=tmp_path / "runs",
        license_accepted=True,
    )
    assert record["sha256"]
    assert record["license_accepted"] is True


def _fake_proteinmpnn(path: Path) -> Path:
    script = path / "proteinmpnn-fake"
    script.write_text(
        """#!/usr/bin/env python3
import sys
from pathlib import Path
if '--help' in sys.argv:
    print('ProteinMPNN fake 1.0')
    raise SystemExit(0)
args = sys.argv[1:]
out = Path(args[args.index('--out_folder') + 1])
out.joinpath('seqs').mkdir(parents=True, exist_ok=True)
out.joinpath('seqs', 'target.fa').write_text('>design_1\\nACDEFGHIK\\n>design_2\\nACDEYGHIK\\n', encoding='utf-8')
print('completed')
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_proteinmpnn_real_subprocess_output_parsing_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.step122.protein_design import (
        build_protein_design_plan,
        execute_protein_design_plan,
        register_model_asset,
        stage_protein_design_input,
    )

    workspace = tmp_path / "runs"
    staged = stage_protein_design_input(
        workspace=workspace,
        source_bytes=PDB_TEXT.encode(),
        filename="target.pdb",
        run_name="mpnn",
    )
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "v_48_020.pt").write_bytes(b"weights")
    register_model_asset("proteinmpnn", weights, workspace=workspace, license_accepted=True)
    fake = _fake_proteinmpnn(tmp_path)
    monkeypatch.setenv("BIOINTEL_TOOL_PROTEINMPNN", str(fake))

    plan = build_protein_design_plan(
        "proteinmpnn",
        run_directory=staged["run_directory"],
        input_path=staged["input_path"],
        parameters={"chains": ["A"], "fixed_positions": "1", "num_sequences": 2, "seed": 11},
    )
    assert plan.executable
    assert "--pdb_path" in plan.arguments
    assert plan.asset_status["checksum_match"] is True
    result = execute_protein_design_plan(plan, timeout_seconds=30)
    assert result.status == "completed"
    assert len(result.candidates) == 2
    assert set(result.candidates["candidate_id"]) == {"design_1", "design_2"}
    assert result.release_gate["scientific_release_ready"] is False
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["schema"] == "biointel.step122.protein_design_run_manifest.v1"
    assert manifest["manifest_sha256"]
    resumed = execute_protein_design_plan(plan, timeout_seconds=30)
    assert resumed.resumed is True
    assert len(resumed.candidates) == 2


def test_rfdiffusion_blocks_without_cuda_and_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.step122.protein_design import build_protein_design_plan, stage_protein_design_input

    workspace = tmp_path / "runs"
    staged = stage_protein_design_input(
        workspace=workspace,
        source_bytes=PDB_TEXT.encode(),
        filename="target.pdb",
        run_name="rf",
    )
    fake = _fake_proteinmpnn(tmp_path)
    monkeypatch.setenv("BIOINTEL_TOOL_RFDIFFUSION", str(fake))
    plan = build_protein_design_plan(
        "rfdiffusion",
        run_directory=staged["run_directory"],
        input_path=staged["input_path"],
        parameters={"num_designs": 2, "contigs": "A1-2/10-20", "hotspot_residues": ["A1"]},
    )
    assert not plan.executable
    assert any("model" in blocker.lower() for blocker in plan.blockers)
    assert any("cuda" in blocker.lower() for blocker in plan.blockers)


def test_colabfold_plan_requires_fasta_and_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.step122.protein_design import build_protein_design_plan, register_model_asset, stage_protein_design_input

    workspace = tmp_path / "runs"
    staged = stage_protein_design_input(
        workspace=workspace,
        sequence="ACDEFGHIKLMNPQRSTVWY",
        run_name="fold",
    )
    params = tmp_path / "colabfold-params"
    params.mkdir()
    (params / "params.bin").write_bytes(b"params")
    register_model_asset("colabfold_batch", params, workspace=workspace, license_accepted=True)
    fake = _fake_proteinmpnn(tmp_path)
    monkeypatch.setenv("BIOINTEL_TOOL_COLABFOLD_BATCH", str(fake))
    plan = build_protein_design_plan(
        "colabfold_batch",
        run_directory=staged["run_directory"],
        input_path=staged["input_path"],
        parameters={"num_models": 99, "num_recycles": 50, "seed": 8},
    )
    assert plan.executable
    assert plan.parameters["num_models"] == 5
    assert plan.parameters["num_recycles"] == 20
    assert "--random-seed" in plan.arguments


def test_protected_paths_and_page_integration(tmp_path: Path) -> None:
    from biointel.step122.protein_design import build_protein_design_plan, stage_protein_design_input

    staged = stage_protein_design_input(workspace=tmp_path / "runs", sequence="ACDEFGHIK", run_name="safe")
    outside = tmp_path / "outside.fasta"
    outside.write_text(">x\nACDEFGHIK\n")
    with pytest.raises(ValueError, match="outside"):
        build_protein_design_plan(
            "colabfold_batch",
            run_directory=staged["run_directory"],
            input_path=outside,
        )
    page = (ROOT / "pages/96_AI_Protein_Design_Lab.py").read_text(encoding="utf-8")
    assert "render_protein_design_execution_upgrade" in page
    assert "Step 122" in page
    assert "arbitrary shell arguments" in (ROOT / "src/biointel/step122/panels.py").read_text(encoding="utf-8").lower()
