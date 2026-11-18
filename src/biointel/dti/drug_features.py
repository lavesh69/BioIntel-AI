from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biointel.chemistry.descriptors import (
    DESCRIPTOR_ORDER,
    calculate_descriptors,
    descriptor_vector,
)
from biointel.chemistry.fingerprints import generate_morgan_fingerprint
from biointel.chemistry.smiles_validator import mol_from_validated_smiles, validate_smiles


@dataclass(frozen=True)
class DrugFeatureSet:
    """A fixed-order molecular representation for DTI modelling."""

    values: np.ndarray
    names: tuple[str, ...]
    canonical_smiles: str
    radius: int
    n_bits: int
    use_chirality: bool


def extract_drug_features(
    smiles: str,
    radius: int = 2,
    n_bits: int = 2048,
    use_chirality: bool = True,
) -> DrugFeatureSet:
    """Combine molecular descriptors and Morgan fingerprint bits."""

    validation = validate_smiles(smiles)
    mol = mol_from_validated_smiles(validation.canonical_smiles)
    descriptors = calculate_descriptors(mol)
    fingerprint = generate_morgan_fingerprint(mol, radius, n_bits, use_chirality)

    descriptor_values = np.array(descriptor_vector(descriptors), dtype=float)
    values = np.concatenate([descriptor_values, fingerprint.values.astype(float)])
    names = tuple(f"drug_{name}" for name in DESCRIPTOR_ORDER) + tuple(
        f"morgan_bit_{index}" for index in range(n_bits)
    )
    if not np.isfinite(values).all():
        raise ValueError("Drug feature extraction produced a non-finite value.")
    return DrugFeatureSet(
        values=values,
        names=names,
        canonical_smiles=validation.canonical_smiles,
        radius=radius,
        n_bits=n_bits,
        use_chirality=use_chirality,
    )
