from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.rdchem import Mol

DESCRIPTOR_ORDER = [
    "molecular_weight",
    "exact_molecular_weight",
    "logp",
    "tpsa",
    "h_bond_donors",
    "h_bond_acceptors",
    "rotatable_bonds",
    "ring_count",
    "aromatic_ring_count",
    "heavy_atom_count",
    "formal_charge",
    "fraction_csp3",
    "heteroatom_count",
]


def _finite(value: float | int) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("A molecular descriptor produced a non-finite value.")
    return numeric


def _coerce_molecule(value: Mol | str) -> Mol:
    """Return an RDKit molecule for either a Mol or SMILES input.

    The UI historically passed SMILES strings while feature pipelines passed Mol
    instances. Accepting both prevents opaque Boost.Python argument errors and
    replaces them with an actionable validation message.
    """

    if isinstance(value, Mol):
        return Chem.Mol(value)
    if isinstance(value, str):
        smiles = value.strip()
        if not smiles:
            raise ValueError("SMILES is empty.")
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError("SMILES could not be parsed into a valid molecule.")
        return molecule
    raise TypeError("Molecular descriptors require an RDKit Mol or a SMILES string.")


def calculate_descriptors(mol: Mol | str) -> dict[str, Any]:
    """Calculate deterministic physicochemical descriptors and Lipinski summary."""

    molecule = _coerce_molecule(mol)
    descriptors: dict[str, Any] = {
        "molecular_weight": _finite(Descriptors.MolWt(molecule)),
        "exact_molecular_weight": _finite(Descriptors.ExactMolWt(molecule)),
        "logp": _finite(Descriptors.MolLogP(molecule)),
        "tpsa": _finite(rdMolDescriptors.CalcTPSA(molecule)),
        "h_bond_donors": int(Lipinski.NumHDonors(molecule)),
        "h_bond_acceptors": int(Lipinski.NumHAcceptors(molecule)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(molecule)),
        "ring_count": int(rdMolDescriptors.CalcNumRings(molecule)),
        "aromatic_ring_count": int(rdMolDescriptors.CalcNumAromaticRings(molecule)),
        "heavy_atom_count": int(molecule.GetNumHeavyAtoms()),
        "formal_charge": int(sum(atom.GetFormalCharge() for atom in molecule.GetAtoms())),
        "fraction_csp3": _finite(rdMolDescriptors.CalcFractionCSP3(molecule)),
        "heteroatom_count": int(rdMolDescriptors.CalcNumHeteroatoms(molecule)),
    }

    rules = {
        "molecular_weight_le_500": descriptors["molecular_weight"] <= 500,
        "logp_le_5": descriptors["logp"] <= 5,
        "h_bond_donors_le_5": descriptors["h_bond_donors"] <= 5,
        "h_bond_acceptors_le_10": descriptors["h_bond_acceptors"] <= 10,
    }
    descriptors["lipinski_rules"] = rules
    descriptors["lipinski_violations"] = sum(not passed for passed in rules.values())
    return descriptors


def descriptor_vector(descriptors: dict[str, Any]) -> list[float]:
    """Return descriptors in the fixed order used by downstream DTI features."""

    return [float(descriptors[name]) for name in DESCRIPTOR_ORDER]
