from __future__ import annotations

import json
import math
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

ROOT = Path(__file__).resolve().parents[2]
tolerance = 1.0e-6
golden_cases = json.loads((ROOT / "tests/scientific/golden_cases.json").read_text())


def test_sequence_golden_regression() -> None:
    case = golden_cases["sequence"]
    sequence = case["dna"]
    observed = 100.0 * (sequence.count("G") + sequence.count("C")) / len(sequence)
    assert len(sequence) == case["length"]
    assert math.isclose(observed, case["gc_percent"], rel_tol=1e-12)


def test_chemistry_golden_regression() -> None:
    case = golden_cases["chemistry"]
    molecule = Chem.MolFromSmiles(case["smiles"])
    assert molecule is not None
    assert rdMolDescriptors.CalcMolFormula(molecule) == case["formula"]
    assert math.isclose(Descriptors.MolWt(molecule), case["molecular_weight"], abs_tol=0.05)


def test_dti_scientific_boundary_regression() -> None:
    assert golden_cases["dti"]["release_eligible"] is False
    assert "never release evidence" in golden_cases["dti"]["policy"]
