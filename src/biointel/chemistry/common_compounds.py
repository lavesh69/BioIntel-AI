from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from rdkit import Chem, RDConfig

from biointel.chemistry.descriptors import calculate_descriptors
from biointel.chemistry.smiles_validator import validate_smiles

DIRECTORY_FILENAME = "common_compound_directory_5000.csv"
DIRECTORY_SIZE = 5000


@dataclass(frozen=True)
class CommonCompoundRecord:
    compound_key: str
    common_name: str
    aliases: str
    canonical_smiles: str
    name_type: str
    source: str
    source_identifier: str
    molecular_formula: str
    molecular_weight: float
    logp: float
    tpsa: float
    lipinski_violations: int
    chemistry_category: str


# Curated, high-confidence common names. The remaining directory records are
# explicitly labelled registry/screening names rather than being presented as
# approved drugs or experimentally validated compounds.
CURATED_COMMON_COMPOUNDS: tuple[tuple[str, str, str], ...] = (
    ("Aspirin", "acetylsalicylic acid; ASA", "CC(=O)OC1=CC=CC=C1C(=O)O"),
    ("Caffeine", "1,3,7-trimethylxanthine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O"),
    ("Ibuprofen", "2-(4-isobutylphenyl)propionic acid", "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"),
    ("Paracetamol", "acetaminophen; APAP", "CC(=O)NC1=CC=C(C=C1)O"),
    ("Naproxen", "naproxen free acid", "COc1ccc2cc(ccc2c1)[C@@H](C)C(=O)O"),
    ("Ketoprofen", "ketoprofen free acid", "CC(C(=O)O)c1cccc(c1)C(=O)c2ccccc2"),
    ("Diclofenac", "diclofenac free acid", "O=C(O)Cc1ccccc1Nc2c(Cl)cccc2Cl"),
    ("Metformin", "dimethylbiguanide", "CN(C)C(=N)N=C(N)N"),
    ("Salicylic acid", "2-hydroxybenzoic acid", "O=C(O)c1ccccc1O"),
    ("Benzoic acid", "benzene carboxylic acid", "O=C(O)c1ccccc1"),
    ("Acetic acid", "ethanoic acid; vinegar acid", "CC(=O)O"),
    ("Citric acid", "2-hydroxypropane-1,2,3-tricarboxylic acid", "O=C(O)CC(O)(CC(=O)O)C(=O)O"),
    ("Lactic acid", "2-hydroxypropanoic acid", "CC(O)C(=O)O"),
    ("Urea", "carbamide", "NC(=O)N"),
    ("Creatinine", "2-amino-1-methyl-5H-imidazol-4-one", "CN1C(=O)N=C(N)C1"),
    ("Dopamine", "3,4-dihydroxyphenethylamine", "NCCc1ccc(O)c(O)c1"),
    ("Serotonin", "5-hydroxytryptamine; 5-HT", "NCCc1c[nH]c2ccc(O)cc12"),
    ("Adrenaline", "epinephrine", "CNCC(O)c1ccc(O)c(O)c1"),
    ("Noradrenaline", "norepinephrine", "NCC(O)c1ccc(O)c(O)c1"),
    ("Histamine", "2-(1H-imidazol-4-yl)ethanamine", "NCCc1ncc[nH]1"),
    ("Melatonin", "N-acetyl-5-methoxytryptamine", "COc1ccc2[nH]cc(CCNC(C)=O)c2c1"),
    ("Nicotinamide", "niacinamide; vitamin B3 amide", "NC(=O)c1cccnc1"),
    ("Niacin", "nicotinic acid; vitamin B3", "O=C(O)c1cccnc1"),
    ("Adenine", "6-aminopurine", "Nc1ncnc2ncnc12"),
    ("Thymine", "5-methyluracil", "CC1=CN(C(=O)NC1=O)"),
    ("Uracil", "pyrimidine-2,4-diol", "O=C1NC=CC(=O)N1"),
    ("Guanine", "2-amino-6-oxypurine", "Nc1nc2[nH]cnc2c(=O)[nH]1"),
    ("Ethanol", "ethyl alcohol", "CCO"),
    ("Methanol", "methyl alcohol", "CO"),
    ("Acetone", "propanone", "CC(=O)C"),
    ("Glycerol", "glycerin; propane-1,2,3-triol", "OCC(O)CO"),
    ("Ethylene glycol", "ethane-1,2-diol", "OCCO"),
    ("Propylene glycol", "propane-1,2-diol", "CC(O)CO"),
    ("Formaldehyde", "methanal", "C=O"),
    ("Hydrogen peroxide", "peroxide", "OO"),
    ("Phenol", "hydroxybenzene", "Oc1ccccc1"),
    ("Aniline", "aminobenzene", "Nc1ccccc1"),
    ("Toluene", "methylbenzene", "Cc1ccccc1"),
    ("Benzene", "benzol", "c1ccccc1"),
    ("Catechol", "benzene-1,2-diol", "Oc1ccccc1O"),
    ("Resorcinol", "benzene-1,3-diol", "Oc1cccc(O)c1"),
    ("Hydroquinone", "benzene-1,4-diol", "Oc1ccc(O)cc1"),
    ("Biphenyl", "diphenyl", "c1ccc(-c2ccccc2)cc1"),
    ("Naphthalene", "naphthalin", "c1ccc2ccccc2c1"),
    ("Anthracene", "paranaphthalene", "c1ccc2cc3ccccc3cc2c1"),
    ("Vanillin", "4-hydroxy-3-methoxybenzaldehyde", "COc1cc(C=O)ccc1O"),
    ("Cinnamic acid", "3-phenylprop-2-enoic acid", "O=C(O)/C=C/c1ccccc1"),
    ("Benzocaine", "ethyl 4-aminobenzoate", "CCOC(=O)c1ccc(N)cc1"),
    ("Procaine", "novocaine", "O=C(OCCN(CC)CC)c1ccc(N)cc1"),
    ("Lidocaine", "lignocaine", "CCN(CC)CC(=O)NC1=C(C)C=CC=C1C"),
    ("Nicotine", "3-(1-methylpyrrolidin-2-yl)pyridine", "CN1CCC[C@H]1c2cccnc2"),
    ("Menthol", "peppermint camphor", "CC(C)C1CCC(C)CC1O"),
    ("Camphor", "bornan-2-one", "CC1(C)C2CCC1(C)C(=O)C2"),
    ("Quercetin", "quercetol", "O=c1c(O)c(-c2ccc(O)c(O)c2)oc2cc(O)cc(O)c12"),
    ("Resveratrol", "3,5,4'-trihydroxystilbene", "Oc1ccc(/C=C/c2cc(O)cc(O)c2)cc1"),
    ("Ascorbic acid", "vitamin C", "OC[C@H]1OC(=O)C(O)=C1O"),
    ("Glucose", "dextrose", "OC[C@H]1O[C@H](O)[C@@H](O)[C@H](O)[C@H]1O"),
    ("Fructose", "fruit sugar", "OCC(=O)[C@H](O)[C@@H](O)[C@@H](O)CO"),
    ("Xylitol", "wood sugar alcohol", "OC[C@H](O)[C@@H](O)[C@H](O)CO"),
    ("Sorbitol", "glucitol", "OC[C@H](O)[C@@H](O)[C@@H](O)[C@H](O)CO"),
)


def _category(molecular_weight: float, logp: float, violations: int) -> str:
    if violations == 0 and molecular_weight <= 500:
        return "drug-like descriptor profile"
    if molecular_weight <= 250 and logp < 1:
        return "small polar compound"
    if molecular_weight <= 500 and logp <= 3:
        return "medium balanced compound"
    if logp > 3:
        return "lipophilic compound"
    return "general screening compound"


def _record(
    *,
    compound_key: str,
    common_name: str,
    aliases: str,
    smiles: str,
    name_type: str,
    source: str,
    source_identifier: str,
) -> CommonCompoundRecord | None:
    try:
        validation = validate_smiles(smiles)
        mol = Chem.MolFromSmiles(validation.canonical_smiles)
        if mol is None:
            return None
        descriptors = calculate_descriptors(mol)
    except Exception:
        return None
    formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
    return CommonCompoundRecord(
        compound_key=compound_key,
        common_name=common_name,
        aliases=aliases,
        canonical_smiles=validation.canonical_smiles,
        name_type=name_type,
        source=source,
        source_identifier=source_identifier,
        molecular_formula=formula,
        molecular_weight=round(float(descriptors["molecular_weight"]), 6),
        logp=round(float(descriptors["logp"]), 6),
        tpsa=round(float(descriptors["tpsa"]), 6),
        lipinski_violations=int(descriptors["lipinski_violations"]),
        chemistry_category=_category(
            float(descriptors["molecular_weight"]),
            float(descriptors["logp"]),
            int(descriptors["lipinski_violations"]),
        ),
    )


def _nci_rows() -> Iterable[tuple[str, str]]:
    path = Path(RDConfig.RDDataDir) / "NCI" / "first_5K.smi"
    if not path.is_file():
        return ()
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def build_common_compound_directory(
    project_root: str | Path,
    *,
    limit: int = DIRECTORY_SIZE,
) -> pd.DataFrame:
    root = Path(project_root).resolve()
    records: list[CommonCompoundRecord] = []
    seen_smiles: set[str] = set()

    for index, (name, aliases, smiles) in enumerate(
        CURATED_COMMON_COMPOUNDS,
        start=1,
    ):
        item = _record(
            compound_key=f"COMMON-{index:04d}",
            common_name=name,
            aliases=aliases,
            smiles=smiles,
            name_type="curated_common_name",
            source="BioIntel curated common-name starter set",
            source_identifier=f"COMMON-{index:04d}",
        )
        if item is None or item.canonical_smiles in seen_smiles:
            continue
        seen_smiles.add(item.canonical_smiles)
        records.append(item)

    for smiles, identifier in _nci_rows():
        if len(records) >= limit:
            break
        item = _record(
            compound_key=f"NCI-{int(identifier):05d}",
            common_name=f"NCI screening compound {int(identifier):05d}",
            aliases=f"NCI {identifier}; NSC screening entry {identifier}",
            smiles=smiles,
            name_type="registry_screening_name",
            source="RDKit bundled NCI first-5K screening set",
            source_identifier=str(identifier),
        )
        if item is None or item.canonical_smiles in seen_smiles:
            continue
        seen_smiles.add(item.canonical_smiles)
        records.append(item)

    coverage_path = root / "data" / "coverage" / "molecule_analysis_library_1000.csv"
    if coverage_path.is_file() and len(records) < limit:
        coverage = pd.read_csv(coverage_path)
        for row in coverage.itertuples(index=False):
            if len(records) >= limit:
                break
            item = _record(
                compound_key=f"BIOINTEL-{row.drug_id}",
                common_name=f"BioIntel reference compound {row.drug_id}",
                aliases=f"BioIntel {row.drug_id}; reference molecule {row.drug_id}",
                smiles=str(row.canonical_smiles),
                name_type="reference_registry_name",
                source="BioIntel molecule coverage library",
                source_identifier=str(row.drug_id),
            )
            if item is None or item.canonical_smiles in seen_smiles:
                continue
            seen_smiles.add(item.canonical_smiles)
            records.append(item)

    if len(records) < limit:
        raise RuntimeError(
            f"Only {len(records)} unique valid molecules were available; " f"{limit} are required."
        )

    frame = pd.DataFrame(record.__dict__ for record in records[:limit])
    frame.insert(1, "directory_rank", range(1, len(frame) + 1))
    return frame


def write_common_compound_directory(
    project_root: str | Path,
) -> Path:
    root = Path(project_root).resolve()
    output = root / "data" / "chemistry" / DIRECTORY_FILENAME
    output.parent.mkdir(parents=True, exist_ok=True)
    build_common_compound_directory(root).to_csv(output, index=False)
    return output


def load_common_compound_directory(
    project_root: str | Path,
) -> pd.DataFrame:
    path = Path(project_root).resolve() / "data" / "chemistry" / DIRECTORY_FILENAME
    if not path.is_file():
        write_common_compound_directory(project_root)
    return pd.read_csv(path, low_memory=False)


def search_common_compounds(
    dataframe: pd.DataFrame,
    query: str,
    *,
    name_type: str = "all",
    limit: int = 250,
) -> pd.DataFrame:
    filtered = dataframe
    if name_type != "all":
        filtered = filtered[filtered["name_type"] == name_type]
    cleaned = query.strip()
    if cleaned:
        mask = (
            filtered["common_name"].str.contains(cleaned, case=False, na=False)
            | filtered["aliases"].str.contains(cleaned, case=False, na=False)
            | filtered["source_identifier"]
            .astype(str)
            .str.contains(
                cleaned,
                case=False,
                na=False,
            )
            | filtered["molecular_formula"].str.contains(
                cleaned,
                case=False,
                na=False,
            )
        )
        filtered = filtered[mask]
    return filtered.head(max(1, min(int(limit), 1000))).reset_index(drop=True)
