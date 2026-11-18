from __future__ import annotations

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


def murcko_scaffold_smiles(smiles: str) -> str:
    """Return canonical Bemis-Murcko scaffold or an acyclic fallback."""

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError("Cannot calculate scaffold for invalid SMILES.")

    scaffold = MurckoScaffold.GetScaffoldForMol(molecule)
    if scaffold.GetNumAtoms() == 0:
        return "ACYCLIC:" + Chem.MolToSmiles(molecule, canonical=True)
    return Chem.MolToSmiles(scaffold, canonical=True)
