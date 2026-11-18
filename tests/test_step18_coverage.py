from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.data.coverage_packs import (
    load_coverage_manifest,
    register_coverage_datasets,
    seed_demo_workspace,
    verify_coverage_integrity,
    write_coverage_packs,
)
from biointel.data.dataset_registry import list_datasets
from biointel.governance.governance_registry import (
    governance_portfolio_summary,
)
from biointel.portfolio.project_registry import (
    list_projects,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step18_coverage_asset_quantities() -> None:
    manifest = load_coverage_manifest(ROOT)
    totals = manifest["totals"]
    assert len(manifest["assets"]) == 9
    assert totals["sequence_records"] == 800
    assert totals["comparison_pairs"] == 180
    assert totals["molecules"] == 1000
    assert totals["external_validation_rows"] == 14000
    assert totals["lookup_starters"] == 20


def test_step18_sequence_and_molecule_files() -> None:
    sequences = pd.read_csv(ROOT / "data" / "coverage" / "sequence_library_800.csv")
    assert len(sequences) == 800
    assert sequences["sequence_type"].value_counts().to_dict() == {
        "DNA": 300,
        "Protein": 300,
        "RNA": 200,
    }

    pairs = pd.read_csv(ROOT / "data" / "coverage" / "sequence_comparison_pairs_180.csv")
    assert len(pairs) == 180
    assert pairs["sequence_type"].nunique() == 3

    molecules = pd.read_csv(ROOT / "data" / "coverage" / "molecule_analysis_library_1000.csv")
    assert len(molecules) == 1000
    assert molecules["canonical_smiles"].nunique() == 1000


def test_step18_validation_files() -> None:
    for name, rows, target in (
        (
            "external_validation_classification_5000.csv",
            5000,
            "label",
        ),
        (
            "external_validation_regression_5000.csv",
            5000,
            "p_activity",
        ),
        (
            "drift_validation_classification_2000.csv",
            2000,
            "label",
        ),
        (
            "drift_validation_regression_2000.csv",
            2000,
            "p_activity",
        ),
    ):
        frame = pd.read_csv(ROOT / "data" / "coverage" / name)
        assert len(frame) == rows
        assert {
            "canonical_smiles",
            "protein_sequence",
            target,
        } <= set(frame.columns)


def test_step18_coverage_integrity_and_registry() -> None:
    integrity = verify_coverage_integrity(ROOT)
    assert integrity["valid"] is True
    assert integrity["checked_files"] == 9
    assert integrity["errors"] == []

    records = list_datasets(
        ROOT / "reports" / "datasets.sqlite3",
        limit=5000,
    )
    coverage_records = [
        item
        for item in records
        if item.dataset_name.startswith(
            (
                "BioIntel Coverage",
                "BioIntel External Validation",
                "BioIntel Drift Validation",
                "BioIntel External Lookup",
            )
        )
    ]
    assert len(coverage_records) == 8


def test_step18_seeded_workspace() -> None:
    projects = list_projects(ROOT / "reports" / "projects.sqlite3")
    demo_projects = [item for item in projects if item.project_code.startswith("DEMO-")]
    assert len(demo_projects) >= 30
    governance = governance_portfolio_summary(ROOT / "reports" / "projects.sqlite3")
    assert governance["milestones_total"] >= 48
    assert governance["decisions_total"] >= 12
    assert governance["gates_total"] >= 60


def test_step18_navigation_and_prefilled_modules() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["data_coverage"].path.endswith("36_Data_Coverage_Center.py")
    for relative, expected in (
        (
            "pages/1_Sequence_Analyzer.py",
            "Coverage library — 800 records",
        ),
        (
            "pages/2_Sequence_Comparison.py",
            "Coverage pair library — 180 pairs",
        ),
        (
            "pages/3_Drug_SMILES_Analyzer.py",
            "Coverage molecule library — 1,000 structures",
        ),
        (
            "pages/14_External_Validation_Drift.py",
            "Coverage independent validation",
        ),
        (
            "pages/16_Batch_Sequence_Analysis.py",
            "Coverage mixed library — 800 records",
        ),
        (
            "pages/10_External_Databases.py",
            "Ready UniProt starter",
        ),
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert expected in content


def test_step18_api_and_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = TestClient(app)
    response = client.get("/data/coverage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["integrity"]["valid"] is True
    assert payload["manifest"]["totals"]["sequence_records"] == 800

    assert cli_main(["coverage-status"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["integrity"]["valid"] is True
    assert cli_payload["manifest"]["totals"]["molecules"] == 1000


def test_step18_generation_and_seed_are_repeatable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    for relative in (
        "data/packs",
        "data/libraries",
        "data/templates",
        "models",
        "reports",
        "config",
    ):
        (root / relative).mkdir(
            parents=True,
            exist_ok=True,
        )

    # Reuse required Double pack and trusted models.
    source_double = ROOT / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv"
    target_double = root / "data" / "packs" / source_double.name
    target_double.write_bytes(source_double.read_bytes())

    for model in (ROOT / "models").glob("*.joblib"):
        (root / "models" / model.name).write_bytes(model.read_bytes())
        for suffix in (".json", ".model_card.md"):
            sidecar = model.with_suffix(suffix)
            if sidecar.is_file():
                (root / "models" / sidecar.name).write_bytes(sidecar.read_bytes())

    assets = write_coverage_packs(root)
    registered = register_coverage_datasets(root)
    summary = seed_demo_workspace(root)
    assert len(assets) == 9
    assert len(registered) == 8
    assert summary["projects"] == 12
