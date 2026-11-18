from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem.rdchem import Mol

from biointel.utils.exceptions import InvalidSmilesError


@dataclass(frozen=True)
class SmilesValidationResult:
    """Validated representation of a SMILES string."""

    original_smiles: str
    canonical_smiles: str
    atom_count: int
    bond_count: int


def validate_smiles(smiles: str) -> SmilesValidationResult:
    """Validate, sanitize and canonicalize a SMILES string.

    Raises:
        InvalidSmilesError: If the input is blank or RDKit cannot parse/sanitize it.
    """

    cleaned = smiles.strip()
    if not cleaned:
        raise InvalidSmilesError("SMILES input is empty.")

    mol = Chem.MolFromSmiles(cleaned, sanitize=False)
    if mol is None:
        raise InvalidSmilesError("RDKit could not parse the supplied SMILES string.")

    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # RDKit exposes several sanitizer exception types
        raise InvalidSmilesError(f"SMILES sanitization failed: {exc}") from exc

    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    return SmilesValidationResult(
        original_smiles=cleaned,
        canonical_smiles=canonical,
        atom_count=mol.GetNumAtoms(),
        bond_count=mol.GetNumBonds(),
    )


def mol_from_validated_smiles(smiles: str) -> Mol:
    """Return a sanitized RDKit molecule or raise a readable project exception."""

    result = validate_smiles(smiles)
    mol = Chem.MolFromSmiles(result.canonical_smiles)
    if mol is None:  # defensive; canonical SMILES was just validated
        raise InvalidSmilesError("Validated SMILES could not be reconstructed.")
    return mol
