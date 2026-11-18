from biointel.chemistry.fingerprints import generate_morgan_fingerprint, tanimoto_similarity
from biointel.chemistry.smiles_validator import mol_from_validated_smiles


def test_morgan_fingerprint_size_and_binary_values():
    fingerprint = generate_morgan_fingerprint(mol_from_validated_smiles("CCO"), n_bits=512)
    assert len(fingerprint.values) == 512
    assert set(fingerprint.values).issubset({0, 1})


def test_identical_molecules_have_similarity_one():
    mol = mol_from_validated_smiles("CCO")
    first = generate_morgan_fingerprint(mol, n_bits=256)
    second = generate_morgan_fingerprint(mol, n_bits=256)
    assert tanimoto_similarity(first, second) == 1.0
