from __future__ import annotations

from dataclasses import asdict, dataclass

from rdkit import Chem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions
from rdkit.Chem.MolStandardize import rdMolStandardize

from biointel.chemistry.standardization import standardize_molecule

IONIZABLE_ALERTS = {
    "carboxylic_acid": "[CX3](=O)[OX2H1]",
    "sulfonic_acid": "S(=O)(=O)[OX2H1]",
    "phosphoric_acid": "P(=O)([OX2H1])[OX2H1]",
    "phenol": "[cX3][OX2H1]",
    "primary_or_secondary_amine": "[NX3;H1,H2;!$(NC=O)]",
    "tertiary_amine": "[NX3;H0;!$(N-*=[O,N,S])]",
    "amidine_or_guanidine": "[NX3][CX3](=[NX2])[NX3]",
}


def _compile_ionizable_patterns() -> tuple[tuple[str, Chem.Mol], ...]:
    compiled: list[tuple[str, Chem.Mol]] = []
    for name, smarts in IONIZABLE_ALERTS.items():
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None:
            compiled.append((name, pattern))
    return tuple(compiled)


_IONIZABLE_PATTERNS = _compile_ionizable_patterns()


@dataclass(frozen=True)
class MolecularPreparationResult:
    mode: str
    requested_ph: float | None
    submitted_smiles: str
    standardized_parent_smiles: str
    parent_inchikey: str | None
    state_smiles: list[str]
    tautomer_count: int
    stereoisomer_count: int
    ionizable_groups: list[str]
    exact_microspecies_assigned: bool
    transformations: list[str]
    warnings: list[str]
    methodology: dict[str, object]


def _unique_smiles(molecules) -> list[str]:
    values = {
        Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        for mol in molecules
        if mol is not None
    }
    return sorted(values)


def prepare_molecular_states(
    smiles: str,
    *,
    mode: str = "neutral_parent",
    ph: float | None = None,
    max_tautomers: int = 32,
    max_stereoisomers: int = 32,
) -> MolecularPreparationResult:
    allowed = {
        "submitted_form",
        "neutral_parent",
        "tautomer_ensemble",
        "stereoisomer_ensemble",
        "assay_context",
        "physiological_context",
    }
    if mode not in allowed:
        raise ValueError("Unsupported molecular preparation mode")
    if ph is not None and not 0 <= float(ph) <= 14:
        raise ValueError("pH must be between 0 and 14")
    original_mol, original_std = standardize_molecule(
        smiles,
        remove_fragments=False,
        neutralize=False,
        canonicalize_tautomer=False,
    )
    parent_mol, parent_std = standardize_molecule(smiles)
    warnings = list(parent_std.warnings)
    transformations = list(parent_std.transformations)

    ionizable = [
        name
        for name, pattern in _IONIZABLE_PATTERNS
        if parent_mol.HasSubstructMatch(pattern)
    ]

    states = [parent_mol]
    tautomer_count = 1
    stereoisomer_count = 1
    if mode == "submitted_form":
        states = [original_mol]
        transformations = ["Submitted molecular form preserved"]
    if mode in {"tautomer_ensemble", "assay_context", "physiological_context"}:
        enumerator = rdMolStandardize.TautomerEnumerator()
        enumerator.SetMaxTautomers(max(1, int(max_tautomers)))
        tautomers = list(enumerator.Enumerate(parent_mol))
        tautomer_count = len(tautomers)
        states = tautomers or states
        transformations.append(f"Enumerated up to {max_tautomers} tautomers")
    if mode == "stereoisomer_ensemble":
        options = StereoEnumerationOptions(
            onlyUnassigned=True,
            unique=True,
            maxIsomers=max(1, int(max_stereoisomers)),
        )
        stereoisomers = list(EnumerateStereoisomers(parent_mol, options=options))
        stereoisomer_count = len(stereoisomers)
        states = stereoisomers or states
        transformations.append(f"Enumerated up to {max_stereoisomers} unassigned stereoisomers")

    exact_microspecies = False
    requested_ph = float(ph) if ph is not None else (7.4 if mode == "physiological_context" else None)
    if mode in {"assay_context", "physiological_context"}:
        warnings.append(
            "Ionizable groups were detected, but exact pH-dependent microspecies were not assigned because no qualified pKa/protonation model is installed."
        )
        if requested_ph is None:
            warnings.append("Provide assay pH to document the intended molecular-state context.")
    if ionizable:
        warnings.append("Review protonation and permeability at the experimental pH.")
    state_smiles = _unique_smiles(states)
    return MolecularPreparationResult(
        mode=mode,
        requested_ph=requested_ph,
        submitted_smiles=original_std.parsed_canonical_smiles,
        standardized_parent_smiles=parent_std.standardized_smiles,
        parent_inchikey=parent_std.inchikey,
        state_smiles=state_smiles,
        tautomer_count=tautomer_count,
        stereoisomer_count=stereoisomer_count,
        ionizable_groups=ionizable,
        exact_microspecies_assigned=exact_microspecies,
        transformations=transformations,
        warnings=sorted(set(warnings)),
        methodology={
            "type": "deterministic RDKit preparation with transparent ensembles",
            "pka_model": "not installed",
            "warning": "Assay-relevant microspecies require a qualified pKa/protonation model or experimental assignment.",
        },
    )


def preparation_dict(result: MolecularPreparationResult) -> dict[str, object]:
    return asdict(result)
