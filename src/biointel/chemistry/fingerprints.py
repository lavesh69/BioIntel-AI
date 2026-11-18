from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rdkit import DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.rdchem import Mol


@dataclass(frozen=True)
class MorganFingerprint:
    """Morgan fingerprint plus reproducibility metadata."""

    values: np.ndarray
    radius: int
    n_bits: int
    use_chirality: bool

    @property
    def on_bits(self) -> int:
        return int(self.values.sum())

    @property
    def density(self) -> float:
        return self.on_bits / self.n_bits if self.n_bits else 0.0


def generate_morgan_fingerprint(
    mol: Mol,
    radius: int = 2,
    n_bits: int = 2048,
    use_chirality: bool = True,
) -> MorganFingerprint:
    """Generate a fixed-length Morgan bit vector as a NumPy array."""

    if radius < 0:
        raise ValueError("Fingerprint radius must be non-negative.")
    if n_bits <= 0:
        raise ValueError("Fingerprint size must be positive.")

    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=radius,
        fpSize=n_bits,
        includeChirality=use_chirality,
    )
    bit_vector = generator.GetFingerprint(mol)
    array = np.zeros((n_bits,), dtype=np.uint8)
    DataStructs.ConvertToNumpyArray(bit_vector, array)
    return MorganFingerprint(array, radius, n_bits, use_chirality)


def tanimoto_similarity(first: MorganFingerprint, second: MorganFingerprint) -> float:
    """Calculate Tanimoto similarity for compatible binary fingerprints."""

    if first.n_bits != second.n_bits:
        raise ValueError("Fingerprints must have the same size.")
    intersection = int(np.logical_and(first.values, second.values).sum())
    union = int(np.logical_or(first.values, second.values).sum())
    return float(intersection / union) if union else 1.0
