from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from biointel.chemistry.chemical_space import (
    activity_cliffs,
    butina_clusters,
    chemical_space_embedding,
    consensus_similarity,
    similarity_matrix,
)
from biointel.chemistry.medicinal_chemistry import (
    clear_medicinal_chemistry_cache,
    medicinal_chemistry_cache_info,
    profile_medicinal_chemistry,
)
from biointel.chemistry.standardization import (
    clear_standardization_cache,
    standardization_cache_info,
    standardize_molecule,
)
from biointel.discovery.registry import SCHEMA_VERSION, connect, create_project, list_projects
from biointel.engineering.isolated_tests import run_test_files_isolated
from biointel.engineering.runtime_optimizer import optimize_database_fleet


def test_standardization_cache_is_fast_and_defensive() -> None:
    clear_standardization_cache()
    first_mol, first = standardize_molecule("CC(=O)[O-].[Na+]")
    first.transformations.append("caller mutation")
    second_mol, second = standardize_molecule("CC(=O)[O-].[Na+]")
    info = standardization_cache_info()
    assert info["misses"] == 1
    assert info["hits"] >= 1
    assert "caller mutation" not in second.transformations
    assert first_mol is not second_mol
    assert second.standardized_smiles == "CC(=O)O"


def test_medicinal_chemistry_cache_is_defensive() -> None:
    clear_medicinal_chemistry_cache()
    mol, _ = standardize_molecule("CCO")
    first = profile_medicinal_chemistry(mol)
    first.rules[0].failed_criteria.append("caller mutation")
    second = profile_medicinal_chemistry(mol)
    info = medicinal_chemistry_cache_info()
    assert info["misses"] == 1
    assert info["hits"] >= 1
    assert "caller mutation" not in second.rules[0].failed_criteria


def test_discovery_registry_schema_initializes_once(tmp_path: Path) -> None:
    database = tmp_path / "discovery.sqlite3"
    with connect(database) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
    project_id = create_project("Optimization", path=database)
    projects = list_projects(path=database)
    assert project_id in set(projects["project_id"])
    with sqlite3.connect(database) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION


def test_chemical_space_optimized_paths() -> None:
    frame = pd.DataFrame(
        {
            "compound_id": ["ethanol", "propanol", "benzene"],
            "standardized_smiles": ["CCO", "CCCO", "c1ccccc1"],
            "p_activity": [5.0, 7.0, 4.0],
        }
    )
    matrix = similarity_matrix(frame)
    assert matrix.shape == (3, 3)
    assert float(matrix.loc["ethanol", "ethanol"]) == 1.0
    clusters = butina_clusters(frame, similarity_threshold=0.2)
    assert len(clusters) == 3
    embedding = chemical_space_embedding(frame)
    assert set(["PC1", "PC2"]).issubset(embedding.columns)
    cliffs = activity_cliffs(frame, similarity_threshold=0.2, activity_difference=1.0)
    assert isinstance(cliffs, pd.DataFrame)
    consensus = consensus_similarity("CCO", "CCCO")
    assert len(consensus["fingerprints"]) == 5


def test_chemical_space_rejects_duplicate_identifiers() -> None:
    frame = pd.DataFrame(
        {"compound_id": ["same", "same"], "standardized_smiles": ["CCO", "CCCO"]}
    )
    try:
        similarity_matrix(frame)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Duplicate identifiers should be rejected")


def test_isolated_test_runner_terminates_cleanly(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text("def test_ok():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    report = run_test_files_isolated(
        tmp_path,
        ["tests/test_ok.py"],
        timeout_seconds=30,
        max_workers=1,
    )
    assert report["passed_files"] == 1
    assert report["timed_out_files"] == 0


def test_database_fleet_optimizer(tmp_path: Path) -> None:
    database = tmp_path / "fleet.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records(value INTEGER)")
        connection.executemany("INSERT INTO records(value) VALUES(?)", [(1,), (2,), (3,)])
        connection.commit()
    report = optimize_database_fleet(tmp_path)
    assert report["database_count"] == 1
    assert report["optimized_databases"] == 1
    assert report["failed_databases"] == 0
