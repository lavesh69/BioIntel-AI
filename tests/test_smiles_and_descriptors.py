import math

import pytest

from biointel.chemistry.descriptors import calculate_descriptors
from biointel.chemistry.smiles_validator import mol_from_validated_smiles, validate_smiles
from biointel.utils.exceptions import InvalidSmilesError


def test_valid_smiles_is_canonicalized():
    result = validate_smiles("CCO")
    assert result.canonical_smiles == "CCO"
    assert result.atom_count == 3


def test_invalid_smiles_is_rejected():
    with pytest.raises(InvalidSmilesError):
        validate_smiles("C1(CC")


def test_descriptors_are_finite():
    values = calculate_descriptors(mol_from_validated_smiles("CC(=O)O"))
    assert values["molecular_weight"] > 0
    assert math.isfinite(values["logp"])
    assert isinstance(values["lipinski_violations"], int)
