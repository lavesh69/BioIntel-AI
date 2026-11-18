from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import inchi
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.rdchem import Mol

from biointel.utils.exceptions import InvalidSmilesError

_COMMON_METALS = {
    3, 4, 11, 12, 13, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
    37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 55, 56, 57,
    72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
}


@dataclass(frozen=True)
class StandardizationResult:
    original_smiles: str
    parsed_canonical_smiles: str
    parent_smiles: str
    standardized_smiles: str
    inchikey: str | None
    fragment_count: int
    removed_fragment_count: int
    original_formal_charge: int
    standardized_formal_charge: int
    tautomer_changed: bool
    transformations: list[str]
    warnings: list[str]
    submitted_fragment_smiles: list[str]
    removed_fragment_smiles: list[str]
    connectivity_key: str | None


def _parse_smiles(smiles: str) -> Mol:
    cleaned = str(smiles).strip()
    if not cleaned:
        raise InvalidSmilesError("SMILES input is empty.")
    mol = Chem.MolFromSmiles(cleaned, sanitize=False)
    if mol is None:
        raise InvalidSmilesError("RDKit could not parse the supplied SMILES string.")
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:
        raise InvalidSmilesError(f"SMILES sanitization failed: {exc}") from exc
    return mol


def _clone_result(result: StandardizationResult) -> StandardizationResult:
    return replace(
        result,
        transformations=list(result.transformations),
        warnings=list(result.warnings),
        submitted_fragment_smiles=list(result.submitted_fragment_smiles),
        removed_fragment_smiles=list(result.removed_fragment_smiles),
    )


@lru_cache(maxsize=4096)
def _standardize_cached(
    smiles: str,
    remove_fragments: bool,
    neutralize: bool,
    canonicalize_tautomer: bool,
) -> tuple[bytes, StandardizationResult]:
    original = str(smiles).strip()
    mol = _parse_smiles(original)
    parsed = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    fragment_smiles = sorted(
        Chem.MolToSmiles(item, canonical=True, isomericSmiles=True) for item in fragments
    )
    fragment_count = len(fragments)
    original_charge = int(Chem.GetFormalCharge(mol))
    transformations: list[str] = []
    warnings: list[str] = []

    working = rdMolStandardize.Cleanup(mol)
    cleaned_smiles = Chem.MolToSmiles(working, canonical=True, isomericSmiles=True)
    if cleaned_smiles != parsed:
        transformations.append("RDKit cleanup/normalization applied")

    parent = working
    if remove_fragments and fragment_count > 1:
        parent = rdMolStandardize.FragmentParent(working)
        transformations.append("Largest medicinal parent fragment selected")
        warnings.append(
            f"Input contained {fragment_count} disconnected fragments; "
            "counterions/solvents were removed for descriptor calculations."
        )
    parent_smiles = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
    parent_fragment_set = {
        Chem.MolToSmiles(item, canonical=True, isomericSmiles=True)
        for item in Chem.GetMolFrags(parent, asMols=True, sanitizeFrags=True)
    }
    removed_fragment_smiles = [
        item for item in fragment_smiles if item not in parent_fragment_set
    ]

    if neutralize:
        uncharged = rdMolStandardize.Uncharger().uncharge(parent)
        if Chem.MolToSmiles(uncharged, canonical=True, isomericSmiles=True) != parent_smiles:
            transformations.append("Neutralizable formal charges normalized")
        parent = uncharged

    pre_tautomer = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
    final_mol = parent
    if canonicalize_tautomer:
        final_mol = rdMolStandardize.TautomerEnumerator().Canonicalize(parent)
    standardized = Chem.MolToSmiles(final_mol, canonical=True, isomericSmiles=True)
    tautomer_changed = standardized != pre_tautomer
    if tautomer_changed:
        transformations.append("Canonical tautomer selected")

    removed = max(0, fragment_count - len(Chem.GetMolFrags(final_mol)))
    standardized_charge = int(Chem.GetFormalCharge(final_mol))

    if any(atom.GetAtomicNum() in _COMMON_METALS for atom in mol.GetAtoms()):
        warnings.append("Metal atom detected; standard organic-molecule rules may not apply.")
    unassigned_stereo = [
        idx
        for idx, label in Chem.FindMolChiralCenters(final_mol, includeUnassigned=True)
        if label == "?"
    ]
    if unassigned_stereo:
        warnings.append(
            f"{len(unassigned_stereo)} potentially stereogenic centre(s) are unassigned."
        )
    if not transformations:
        transformations.append("No structural transformation required")

    try:
        inchikey_value = inchi.MolToInchiKey(final_mol) or None
    except Exception:
        inchikey_value = None
        warnings.append("InChIKey generation was unavailable for this structure.")
    connectivity_key = inchikey_value.split("-", 1)[0] if inchikey_value else None

    result = StandardizationResult(
        original_smiles=original,
        parsed_canonical_smiles=parsed,
        parent_smiles=parent_smiles,
        standardized_smiles=standardized,
        inchikey=inchikey_value,
        fragment_count=fragment_count,
        removed_fragment_count=removed,
        original_formal_charge=original_charge,
        standardized_formal_charge=standardized_charge,
        tautomer_changed=tautomer_changed,
        transformations=transformations,
        warnings=warnings,
        submitted_fragment_smiles=fragment_smiles,
        removed_fragment_smiles=removed_fragment_smiles,
        connectivity_key=connectivity_key,
    )
    return final_mol.ToBinary(), result


def standardize_molecule(
    smiles: str,
    *,
    remove_fragments: bool = True,
    neutralize: bool = True,
    canonicalize_tautomer: bool = True,
) -> tuple[Mol, StandardizationResult]:
    """Return a reproducible parent structure and transparent transformation log.

    Repeated identical structures use a bounded process-local cache. A fresh RDKit
    molecule and copied result lists are returned on every call so callers cannot
    mutate cached state.
    """

    mol_binary, result = _standardize_cached(
        str(smiles).strip(),
        bool(remove_fragments),
        bool(neutralize),
        bool(canonicalize_tautomer),
    )
    return Chem.Mol(mol_binary), _clone_result(result)


def standardization_cache_info() -> dict[str, int]:
    info = _standardize_cached.cache_info()
    return {
        "hits": int(info.hits),
        "misses": int(info.misses),
        "maxsize": int(info.maxsize or 0),
        "currsize": int(info.currsize),
    }


def clear_standardization_cache() -> None:
    _standardize_cached.cache_clear()


def standardize_smiles(smiles: str, **kwargs: object) -> StandardizationResult:
    return standardize_molecule(smiles, **kwargs)[1]


def standardization_dict(result: StandardizationResult) -> dict[str, object]:
    return asdict(result)
