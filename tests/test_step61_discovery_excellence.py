from __future__ import annotations

import pandas as pd

from biointel.chemistry.admet import profile_admet, profile_dict
from biointel.chemistry.medicinal_chemistry import profile_medicinal_chemistry
from biointel.chemistry.similarity_search import (
    compare_molecules,
    greedy_diverse_subset,
    similarity_search,
)
from biointel.chemistry.standardization import standardize_molecule, standardize_smiles
from biointel.discovery.workflow import rank_discovery_hits, score_target_priority
from biointel.ui.navigation import PAGE_BY_KEY


def test_salt_standardization_retains_provenance_and_removes_counterion():
    result = standardize_smiles("CC(=O)[O-].[Na+]")
    assert result.original_smiles == "CC(=O)[O-].[Na+]"
    assert result.standardized_smiles == "CC(=O)O"
    assert result.fragment_count == 2
    assert result.removed_fragment_count == 1
    assert result.warnings


def test_medicinal_chemistry_profile_has_expanded_rules_and_catalogs():
    mol, _ = standardize_molecule("CC(=O)OC1=CC=CC=C1C(=O)O")
    profile = profile_medicinal_chemistry(mol)
    assert 0 <= profile.qed <= 1
    assert 1 <= profile.synthetic_accessibility_heuristic <= 10
    assert len(profile.rules) >= 8
    assert {item.name for item in profile.rules} >= {"Lipinski rule of five", "Veber", "Ghose", "Egan", "Muegge"}


def test_admet_is_explicit_about_unavailable_endpoint_models():
    result = profile_admet("CC(=O)OC1=CC=CC=C1C(=O)O")
    payload = profile_dict(result)
    assert 0 <= result.developability_score <= 100
    assert result.risk_score == 100 - result.developability_score
    assert result.methodology["validated_endpoint_model"] is False
    not_assessed = [row for row in result.endpoint_summary if row["status"] == "not assessed"]
    assert any(row["endpoint"] == "hERG" for row in not_assessed)
    assert any(row["endpoint"] == "CYP3A4 inhibition/substrate" for row in not_assessed)
    assert payload["standardization"]["standardized_smiles"] == result.standardized_smiles


def test_admet_recommends_hbond_and_flexibility_actions():
    # A polar flexible chain deliberately outside common oral-property windows.
    result = profile_admet("OCC(O)C(O)C(O)C(O)C(O)COCCOCCOCCO")
    joined = " ".join(result.recommendations).lower()
    assert "hydrogen-bond" in joined or "rotatable" in joined or "polar surface" in joined
    assert result.modifiable_liabilities


def test_similarity_search_standardizes_and_reports_invalid_rows():
    library = pd.DataFrame(
        {
            "name": ["ethanol", "propanol", "invalid", "sodium acetate"],
            "smiles": ["CCO", "CCCO", "not_smiles", "CC(=O)[O-].[Na+]"],
        }
    )
    hits, failures = similarity_search("CCO", library, top_n=10)
    assert hits.iloc[0]["name"] == "ethanol"
    assert bool(hits.iloc[0]["exact_structure"])
    assert len(failures) == 1
    assert failures.iloc[0]["name"] == "invalid"


def test_pair_similarity_includes_scaffold_and_mcs():
    result = compare_molecules("c1ccccc1O", "c1ccccc1N")
    assert 0 <= result.tanimoto <= 1
    assert result.same_scaffold is True
    assert result.mcs_atoms >= 6


def test_greedy_diversity_returns_requested_size():
    frame = pd.DataFrame(
        {
            "name": ["a", "b", "c", "d"],
            "standardized_smiles": ["CCO", "CCCO", "c1ccccc1", "CC(=O)O"],
        }
    )
    subset = greedy_diverse_subset(frame, size=3)
    assert len(subset) == 3
    assert subset["name"].nunique() == 3


def test_target_priority_is_bounded_and_transparent():
    score = score_target_priority(
        "PTGS2",
        disease_relevance=80,
        genetic_evidence=60,
        pathway_evidence=70,
        tractability=90,
        safety_window=55,
        experimental_validation=50,
    )
    assert 0 <= score.total_score <= 100
    assert score.target_id == "PTGS2"
    assert score.methodology["type"] == "user-evidence weighted prioritisation"


def test_multi_objective_hit_ranking_is_deterministic():
    frame = pd.DataFrame(
        {
            "compound_id": ["A", "B", "C"],
            "developability_score": [90, 70, 80],
            "qed": [0.7, 0.9, 0.6],
            "risk_score": [10, 30, 20],
            "synthetic_accessibility_heuristic": [2.0, 6.0, 3.0],
        }
    )
    ranked = rank_discovery_hits(frame, id_column="compound_id")
    assert ranked["hit_rank"].tolist() == [1, 2, 3]
    assert ranked.iloc[0]["compound_id"] == "A"
    assert ranked["multi_objective_score"].is_monotonic_decreasing


def test_discovery_navigation_is_unified():
    assert PAGE_BY_KEY["discovery_command_center"].category == "Discovery"
    for key in [
        "drug_analyzer",
        "chembl_builder",
        "dti_features",
        "dti_predictor",
        "structural_bioinformatics",
        "admet_discovery",
        "pathway_network",
    ]:
        assert PAGE_BY_KEY[key].category == "Discovery"
