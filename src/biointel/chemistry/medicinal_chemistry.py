from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import QED, Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from rdkit.Chem.rdchem import Mol
from rdkit.Chem.Scaffolds import MurckoScaffold


@dataclass(frozen=True)
class RuleResult:
    name: str
    passed: bool
    failed_criteria: list[str]
    interpretation: str


@dataclass(frozen=True)
class AlertMatch:
    catalog: str
    description: str
    atom_indices: list[int]


@dataclass(frozen=True)
class MedicinalChemistryProfile:
    molecular_weight: float
    exact_molecular_weight: float
    logp: float
    tpsa: float
    hbd: int
    hba: int
    rotatable_bonds: int
    ring_count: int
    aromatic_rings: int
    fraction_csp3: float
    formal_charge: int
    heavy_atoms: int
    carbon_atoms: int
    heteroatoms: int
    molar_refractivity: float
    qed: float
    molecular_complexity: float
    synthetic_accessibility_heuristic: float
    scaffold_smiles: str
    esol_style_log_s: float
    solubility_class: str
    aggregation_risk: str
    rules: list[RuleResult]
    alerts: list[AlertMatch]


def _rule(name: str, checks: list[tuple[bool, str]], interpretation: str) -> RuleResult:
    failed = [label for passed, label in checks if not passed]
    return RuleResult(name, not failed, failed, interpretation)


def _sa_heuristic(mol: Mol) -> float:
    """Transparent 1–10 synthesis-complexity heuristic, not the Ertl SA score."""
    heavy = mol.GetNumHeavyAtoms()
    rings = rdMolDescriptors.CalcNumRings(mol)
    aromatic = rdMolDescriptors.CalcNumAromaticRings(mol)
    spiro = rdMolDescriptors.CalcNumSpiroAtoms(mol)
    bridge = rdMolDescriptors.CalcNumBridgeheadAtoms(mol)
    stereo = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    macro = sum(1 for ring in mol.GetRingInfo().AtomRings() if len(ring) >= 8)
    score = (
        1.0
        + max(0, heavy - 15) * 0.035
        + rings * 0.18
        + aromatic * 0.08
        + spiro * 0.5
        + bridge * 0.45
        + stereo * 0.25
        + macro * 0.8
    )
    return round(min(10.0, max(1.0, score)), 3)


@lru_cache(maxsize=1)
def _filter_catalogs() -> tuple[tuple[str, FilterCatalog], ...]:
    definitions = (
        ("PAINS", FilterCatalogParams.FilterCatalogs.PAINS),
        ("BRENK", FilterCatalogParams.FilterCatalogs.BRENK),
        ("NIH", FilterCatalogParams.FilterCatalogs.NIH),
        ("ZINC", FilterCatalogParams.FilterCatalogs.ZINC),
    )
    built: list[tuple[str, FilterCatalog]] = []
    for name, enum_value in definitions:
        params = FilterCatalogParams()
        params.AddCatalog(enum_value)
        built.append((name, FilterCatalog(params)))
    return tuple(built)


def _catalog_matches(mol: Mol) -> list[AlertMatch]:
    found: list[AlertMatch] = []
    for name, catalog in _filter_catalogs():
        for match in catalog.GetMatches(mol):
            atom_indices: list[int] = []
            for pair in match.GetFilterMatches(mol):
                atom_indices.extend(int(item.target) for item in pair.atomPairs)
            found.append(
                AlertMatch(
                    catalog=name,
                    description=match.GetDescription(),
                    atom_indices=sorted(set(atom_indices)),
                )
            )
    # deterministic de-duplication across catalogs/descriptions
    unique: dict[tuple[str, str], AlertMatch] = {}
    for item in found:
        unique[(item.catalog, item.description)] = item
    return sorted(unique.values(), key=lambda x: (x.catalog, x.description))


def _profile_medicinal_chemistry_uncached(mol: Mol) -> MedicinalChemistryProfile:
    mw = float(Descriptors.MolWt(mol))
    exact_mw = float(Descriptors.ExactMolWt(mol))
    logp = float(Crippen.MolLogP(mol))
    tpsa = float(rdMolDescriptors.CalcTPSA(mol))
    hbd = int(Lipinski.NumHDonors(mol))
    hba = int(Lipinski.NumHAcceptors(mol))
    rot = int(Lipinski.NumRotatableBonds(mol))
    rings = int(rdMolDescriptors.CalcNumRings(mol))
    aromatic = int(rdMolDescriptors.CalcNumAromaticRings(mol))
    fsp3 = float(rdMolDescriptors.CalcFractionCSP3(mol))
    charge = int(Chem.GetFormalCharge(mol))
    heavy = int(mol.GetNumHeavyAtoms())
    carbon = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6)
    hetero = int(rdMolDescriptors.CalcNumHeteroatoms(mol))
    mr = float(Crippen.MolMR(mol))
    qed_value = float(QED.qed(mol))
    complexity = float(Descriptors.BertzCT(mol))
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
    aromatic_proportion = aromatic / max(1, rings)
    # Delaney-inspired transparent descriptor heuristic; not an assay-calibrated model.
    log_s = 0.16 - 1.5 * logp - 0.01 * mw + 0.5 * rot - 1.5 * aromatic_proportion
    if log_s >= -2:
        solubility = "higher predicted solubility"
    elif log_s >= -4:
        solubility = "moderate predicted solubility"
    elif log_s >= -6:
        solubility = "low predicted solubility"
    else:
        solubility = "very low predicted solubility"

    aggregation = "higher" if logp > 4 and aromatic >= 3 and abs(charge) <= 1 else "lower/uncertain"
    rules = [
        _rule(
            "Lipinski rule of five",
            [(mw <= 500, "MW > 500"), (logp <= 5, "LogP > 5"), (hbd <= 5, "HBD > 5"), (hba <= 10, "HBA > 10")],
            "Oral drug-likeness heuristic.",
        ),
        _rule(
            "Veber",
            [(rot <= 10, "Rotatable bonds > 10"), (tpsa <= 140, "TPSA > 140 Å²")],
            "Passive permeability/oral-bioavailability heuristic.",
        ),
        _rule(
            "Lead-like",
            [(250 <= mw <= 350, "MW outside 250–350"), (logp <= 3.5, "LogP > 3.5"), (rot <= 7, "Rotatable bonds > 7")],
            "Conservative lead-optimization starting-space heuristic.",
        ),
        _rule(
            "Rule of three",
            [(mw <= 300, "MW > 300"), (logp <= 3, "LogP > 3"), (hbd <= 3, "HBD > 3"), (hba <= 3, "HBA > 3"), (rot <= 3, "Rotatable bonds > 3"), (tpsa <= 60, "TPSA > 60 Å²")],
            "Fragment-like chemical-space heuristic.",
        ),
        _rule(
            "Ghose",
            [(160 <= mw <= 480, "MW outside 160–480"), (-0.4 <= logp <= 5.6, "LogP outside −0.4–5.6"), (40 <= mr <= 130, "Molar refractivity outside 40–130"), (20 <= heavy <= 70, "Heavy atoms outside 20–70")],
            "Drug-like property-window heuristic.",
        ),
        _rule(
            "Egan",
            [(logp <= 5.88, "LogP > 5.88"), (tpsa <= 131.6, "TPSA > 131.6 Å²")],
            "Absorption/permeation property-window heuristic.",
        ),
        _rule(
            "Muegge",
            [(200 <= mw <= 600, "MW outside 200–600"), (-2 <= logp <= 5, "LogP outside −2–5"), (tpsa <= 150, "TPSA > 150 Å²"), (rings <= 7, "Rings > 7"), (carbon > 4, "Carbon atoms ≤ 4"), (hetero > 1, "Heteroatoms ≤ 1"), (rot <= 15, "Rotatable bonds > 15"), (hbd <= 5, "HBD > 5"), (hba <= 10, "HBA > 10")],
            "Broad drug-like chemical-space heuristic.",
        ),
        _rule(
            "Pfizer 3/75 liability screen",
            [((not (logp > 3 and tpsa < 75)), "LogP > 3 and TPSA < 75 Å²")],
            "Simple lipophilicity/polarity liability flag; not a toxicity prediction.",
        ),
    ]

    return MedicinalChemistryProfile(
        molecular_weight=round(mw, 3),
        exact_molecular_weight=round(exact_mw, 3),
        logp=round(logp, 3),
        tpsa=round(tpsa, 3),
        hbd=hbd,
        hba=hba,
        rotatable_bonds=rot,
        ring_count=rings,
        aromatic_rings=aromatic,
        fraction_csp3=round(fsp3, 3),
        formal_charge=charge,
        heavy_atoms=heavy,
        carbon_atoms=carbon,
        heteroatoms=hetero,
        molar_refractivity=round(mr, 3),
        qed=round(qed_value, 3),
        molecular_complexity=round(complexity, 3),
        synthetic_accessibility_heuristic=_sa_heuristic(mol),
        scaffold_smiles=scaffold,
        esol_style_log_s=round(log_s, 3),
        solubility_class=solubility,
        aggregation_risk=aggregation,
        rules=rules,
        alerts=_catalog_matches(mol),
    )


def _clone_profile(result: MedicinalChemistryProfile) -> MedicinalChemistryProfile:
    return replace(
        result,
        rules=[
            replace(item, failed_criteria=list(item.failed_criteria)) for item in result.rules
        ],
        alerts=[replace(item, atom_indices=list(item.atom_indices)) for item in result.alerts],
    )


@lru_cache(maxsize=4096)
def _profile_canonical_smiles(canonical_smiles: str) -> MedicinalChemistryProfile:
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:  # pragma: no cover - generated from an existing valid molecule
        raise ValueError("Canonical SMILES could not be reconstructed")
    return _profile_medicinal_chemistry_uncached(mol)


def profile_medicinal_chemistry(mol: Mol) -> MedicinalChemistryProfile:
    """Profile a molecule with bounded duplicate-structure caching.

    The canonical isomeric representation is the cache key. A defensive copy of
    list-bearing fields prevents callers from mutating process-local cached state.
    """

    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    return _clone_profile(_profile_canonical_smiles(canonical))


def medicinal_chemistry_cache_info() -> dict[str, int]:
    info = _profile_canonical_smiles.cache_info()
    return {
        "hits": int(info.hits),
        "misses": int(info.misses),
        "maxsize": int(info.maxsize or 0),
        "currsize": int(info.currsize),
    }


def clear_medicinal_chemistry_cache() -> None:
    _profile_canonical_smiles.cache_clear()


def medicinal_chemistry_dict(result: MedicinalChemistryProfile) -> dict[str, object]:
    return asdict(result)
