from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import (
    Descriptors,
    Lipinski,
    rdFingerprintGenerator,
    rdMolDescriptors,
)

from biointel.utils.integrity_cache import verify_manifest_files
from biointel.utils.runtime_cache import load_json_cached

AA_ORDER = tuple("ACDEFGHIKLMNPQRSTVWY")
DATA_PACK_VERSION = "5.0"

SUBSTITUENTS = (
    "C",
    "CC",
    "CCC",
    "O",
    "OC",
    "N",
    "NC",
    "N(C)C",
    "F",
    "Cl",
    "Br",
    "C#N",
    "C(=O)O",
    "C(=O)N",
    "S(=O)(=O)N",
    "C(F)(F)F",
    "CO",
    "CCO",
    "C(=O)OC",
    "C1CC1",
    "C1CCCCC1",
    "SC",
    "S(=O)(=O)C",
)
SCAFFOLD_TEMPLATES = (
    "c1cc({a})ccc1{b}",
    "n1cc({a})ccc1{b}",
    "c1ncc({a})cc1{b}",
    "c1cc2ccc({a})cc2c1{b}",
)
TARGET_FAMILIES = {
    "Kinase-like": (
        ("VAIK", "HRD", "DFG"),
        "VAILKRDG",
        0.25,
    ),
    "Protease-like": (
        ("GDSGG", "HSC"),
        "GASTC",
        0.05,
    ),
    "GPCR-like": (
        ("DRY", "NPFIY"),
        "AILVFWY",
        0.15,
    ),
    "Nuclear-receptor-like": (
        ("CEGCKGFFR", "CPYCR"),
        "CEGKR",
        -0.05,
    ),
    "Transporter-like": (
        ("GGAGG", "NPQ"),
        "AILVFG",
        0.00,
    ),
    "Enzyme-like": (
        ("HGGH", "GGH"),
        "AGHDE",
        -0.10,
    ),
}


@dataclass(frozen=True)
class DataPackRecord:
    key: str
    filename: str
    title: str
    rows: int
    compounds: int
    targets: int
    task_support: tuple[str, ...]
    source_type: str
    scientific_validity: str
    description: str
    sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_molecules() -> list[dict[str, object]]:
    RDLogger.DisableLog("rdApp.*")
    unique: dict[str, dict[str, object]] = {}

    for template_index, template in enumerate(
        SCAFFOLD_TEMPLATES,
        start=1,
    ):
        for first in SUBSTITUENTS:
            for second in SUBSTITUENTS:
                smiles = template.format(
                    a=first,
                    b=second,
                )
                molecule = Chem.MolFromSmiles(smiles)
                if molecule is None:
                    continue

                canonical = Chem.MolToSmiles(
                    molecule,
                    canonical=True,
                )
                molecular_weight = float(Descriptors.MolWt(molecule))
                logp = float(Descriptors.MolLogP(molecule))
                tpsa = float(rdMolDescriptors.CalcTPSA(molecule))
                if not (
                    90.0 <= molecular_weight <= 520.0 and -1.5 <= logp <= 6.0 and tpsa <= 180.0
                ):
                    continue

                unique[canonical] = {
                    "canonical_smiles": canonical,
                    "scaffold_family": (f"synthetic_scaffold_{template_index}"),
                    "molecular_weight": round(
                        molecular_weight,
                        4,
                    ),
                    "logp": round(logp, 4),
                    "tpsa": round(tpsa, 4),
                    "h_bond_donors": int(Lipinski.NumHDonors(molecule)),
                    "h_bond_acceptors": int(Lipinski.NumHAcceptors(molecule)),
                    "rotatable_bonds": int(Lipinski.NumRotatableBonds(molecule)),
                    "ring_count": int(rdMolDescriptors.CalcNumRings(molecule)),
                    "fraction_csp3": round(
                        float(rdMolDescriptors.CalcFractionCSP3(molecule)),
                        4,
                    ),
                }

    return [unique[key] for key in sorted(unique)]


def build_molecule_library(
    count: int = 240,
    random_seed: int = 20260704,
) -> pd.DataFrame:
    candidates = _candidate_molecules()
    if len(candidates) < count:
        raise RuntimeError("Not enough valid molecules were generated.")
    rng = np.random.default_rng(random_seed)
    selected_indices = np.sort(
        rng.choice(
            len(candidates),
            size=count,
            replace=False,
        )
    )
    selected = [candidates[int(index)] for index in selected_indices]
    rows = []
    for index, item in enumerate(
        selected,
        start=1,
    ):
        rows.append(
            {
                "drug_id": f"BIOCMP{index:04d}",
                **item,
                "source": ("BioIntel deterministic synthetic " "molecule library"),
            }
        )
    return pd.DataFrame(rows)


def _synthetic_sequence(
    target_index: int,
    family: str,
    length: int,
    random_seed: int,
) -> str:
    motifs, biased_residues, _ = TARGET_FAMILIES[family]
    rng = random.Random(random_seed + target_index * 17)
    weights = [1.0 + 2.5 * (aa in biased_residues) for aa in AA_ORDER]
    sequence = [
        rng.choices(
            AA_ORDER,
            weights=weights,
            k=1,
        )[0]
        for _ in range(length)
    ]
    for motif_index, motif in enumerate(motifs):
        position = (target_index * 37 + motif_index * 83 + 20) % max(length - len(motif) - 1, 1)
        sequence[position : position + len(motif)] = list(motif)
    return "".join(sequence)


def build_protein_library(
    count: int = 24,
    random_seed: int = 20260704,
) -> pd.DataFrame:
    families = tuple(TARGET_FAMILIES)
    rows = []
    for index in range(count):
        family = families[index % len(families)]
        length = 220 + (index * 37) % 260
        sequence = _synthetic_sequence(
            index,
            family,
            length,
            random_seed,
        )
        rows.append(
            {
                "target_id": f"BIOTGT{index + 1:03d}",
                "target_family": family,
                "protein_sequence": sequence,
                "sequence_length": len(sequence),
                "source": ("BioIntel deterministic synthetic " "protein library"),
            }
        )
    return pd.DataFrame(rows)


def _latent_dataset(
    molecules: pd.DataFrame,
    proteins: pd.DataFrame,
    random_seed: int = 20260704,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_seed)
    fingerprint_generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2,
        fpSize=128,
        includeChirality=True,
    )

    fingerprint_projection = rng.normal(
        0.0,
        1.0,
        size=(128, 16),
    )
    descriptor_projection = rng.normal(
        0.0,
        1.0,
        size=(8, 16),
    )
    amino_projection = rng.normal(
        0.0,
        1.0,
        size=(20, 16),
    )
    target_biases = rng.normal(
        0.0,
        0.25,
        size=len(proteins),
    )

    drug_latents: dict[str, tuple[np.ndarray, float]] = {}
    for row in molecules.itertuples(index=False):
        molecule = Chem.MolFromSmiles(row.canonical_smiles)
        if molecule is None:
            raise RuntimeError(f"Generated invalid molecule: {row.drug_id}")
        fingerprint = np.zeros(
            128,
            dtype=float,
        )
        DataStructs.ConvertToNumpyArray(
            fingerprint_generator.GetFingerprint(molecule),
            fingerprint,
        )
        descriptor_vector = np.array(
            [
                float(row.molecular_weight) / 500.0,
                float(row.logp) / 5.0,
                float(row.tpsa) / 150.0,
                float(row.h_bond_donors) / 5.0,
                float(row.h_bond_acceptors) / 10.0,
                float(row.rotatable_bonds) / 10.0,
                float(row.ring_count) / 5.0,
                float(row.fraction_csp3),
            ],
            dtype=float,
        )
        active_bits = max(
            float(fingerprint.sum()),
            1.0,
        )
        latent = np.tanh(
            fingerprint @ fingerprint_projection / np.sqrt(active_bits)
            + descriptor_vector @ descriptor_projection
        )
        drug_bias = 0.15 * np.tanh((descriptor_vector[1] - 0.4) * 2) - 0.10 * max(
            descriptor_vector[0] - 0.9, 0.0
        )
        drug_latents[row.drug_id] = (
            latent,
            float(drug_bias),
        )

    target_latents: dict[
        str,
        tuple[np.ndarray, float],
    ] = {}
    for target_index, row in enumerate(proteins.itertuples(index=False)):
        composition = np.array(
            [
                row.protein_sequence.count(amino_acid) / len(row.protein_sequence)
                for amino_acid in AA_ORDER
            ],
            dtype=float,
        )
        latent = np.tanh(composition @ amino_projection * 4.0)
        family_shift = TARGET_FAMILIES[row.target_family][2]
        target_latents[row.target_id] = (
            latent,
            float(family_shift + target_biases[target_index]),
        )

    rows: list[dict[str, object]] = []
    raw_scores: list[float] = []
    for molecule in molecules.itertuples(index=False):
        drug_latent, drug_bias = drug_latents[molecule.drug_id]
        for protein in proteins.itertuples(index=False):
            target_latent, target_bias = target_latents[protein.target_id]
            compatibility = float(
                np.dot(
                    drug_latent,
                    target_latent,
                )
                / len(drug_latent)
            )
            noise = float(rng.normal(0.0, 0.18))
            p_activity = 6.25 + 1.65 * compatibility + 0.45 * drug_bias + target_bias + noise
            raw_scores.append(p_activity)
            rows.append(
                {
                    "drug_id": molecule.drug_id,
                    "canonical_smiles": (molecule.canonical_smiles),
                    "target_id": protein.target_id,
                    "protein_sequence": (protein.protein_sequence),
                    "target_family": (protein.target_family),
                    "activity_type": ("SYNTHETIC_AFFINITY_SCORE"),
                    "p_activity": round(
                        float(p_activity),
                        4,
                    ),
                    "source": (
                        "BioIntel deterministic synthetic " "benchmark—not experimental evidence"
                    ),
                    "data_pack_version": (DATA_PACK_VERSION),
                }
            )

    threshold = float(np.median(raw_scores))
    for row in rows:
        row["label"] = int(float(row["p_activity"]) >= threshold)
        row["classification_threshold_p_activity"] = round(threshold, 4)
    return pd.DataFrame(rows)


def build_extended_dataset(
    random_seed: int = 20260704,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    molecules = build_molecule_library(
        count=240,
        random_seed=random_seed,
    )
    proteins = build_protein_library(
        count=24,
        random_seed=random_seed,
    )
    dataset = _latent_dataset(
        molecules,
        proteins,
        random_seed=random_seed,
    )
    return molecules, proteins, dataset


def build_foundation_dataset(
    extended: pd.DataFrame,
) -> pd.DataFrame:
    selected_drugs = sorted(extended["drug_id"].unique())[:120]
    selected_targets = sorted(extended["target_id"].unique())[:16]
    return (
        extended[
            extended["drug_id"].isin(selected_drugs) & extended["target_id"].isin(selected_targets)
        ]
        .reset_index(drop=True)
        .copy()
    )


def _write_step15_data_packs(
    root: str | Path,
) -> list[DataPackRecord]:
    project_root = Path(root).resolve()
    pack_directory = project_root / "data" / "packs"
    library_directory = project_root / "data" / "libraries"
    recipe_directory = project_root / "data" / "recipes"
    for directory in (
        pack_directory,
        library_directory,
        recipe_directory,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    molecules, proteins, extended = build_extended_dataset()
    foundation = build_foundation_dataset(extended)
    batch_sample = (
        extended.sample(
            n=250,
            random_state=20260704,
        )[
            [
                "drug_id",
                "canonical_smiles",
                "target_id",
                "protein_sequence",
            ]
        ]
        .rename(columns={"drug_id": "sample_id"})
        .reset_index(drop=True)
    )

    foundation_path = pack_directory / "synthetic_foundation_dti_v2.csv"
    extended_path = pack_directory / "synthetic_extended_dti_v2.csv"
    batch_path = pack_directory / "batch_prediction_sample_250.csv"
    molecule_path = library_directory / "molecule_library_240.csv"
    protein_path = library_directory / "protein_library_24.csv"
    fasta_path = library_directory / "protein_library_24.fasta"

    foundation.to_csv(
        foundation_path,
        index=False,
    )
    extended.to_csv(
        extended_path,
        index=False,
    )
    batch_sample.to_csv(
        batch_path,
        index=False,
    )
    molecules.to_csv(
        molecule_path,
        index=False,
    )
    proteins.to_csv(
        protein_path,
        index=False,
    )
    fasta_path.write_text(
        "\n".join(
            f">{row.target_id}|{row.target_family}\n" f"{row.protein_sequence}"
            for row in proteins.itertuples(index=False)
        )
        + "\n",
        encoding="utf-8",
    )

    recipes = pd.DataFrame(
        [
            {
                "target_chembl_id": "CHEMBL203",
                "target_name": ("Epidermal growth factor receptor"),
                "suggested_activity_type": "IC50",
                "suggested_max_records": 1000,
            },
            {
                "target_chembl_id": "CHEMBL279",
                "target_name": ("Vascular endothelial growth " "factor receptor 2"),
                "suggested_activity_type": "IC50",
                "suggested_max_records": 1000,
            },
            {
                "target_chembl_id": "CHEMBL1862",
                "target_name": ("Tyrosine-protein kinase ABL"),
                "suggested_activity_type": "IC50",
                "suggested_max_records": 1000,
            },
            {
                "target_chembl_id": "CHEMBL240",
                "target_name": ("Voltage-gated inwardly rectifying " "potassium channel KCNH2"),
                "suggested_activity_type": "IC50",
                "suggested_max_records": 1000,
            },
            {
                "target_chembl_id": "CHEMBL204",
                "target_name": "Prothrombin",
                "suggested_activity_type": "Ki",
                "suggested_max_records": 1000,
            },
        ]
    )
    recipes["source"] = "Official ChEMBL target identifiers; " "live API download required"
    recipes["manual_review_required"] = True
    recipe_path = recipe_directory / "chembl_starter_targets.csv"
    recipes.to_csv(
        recipe_path,
        index=False,
    )

    records = [
        DataPackRecord(
            key="foundation_dti",
            filename=foundation_path.relative_to(project_root).as_posix(),
            title="Foundation DTI Pack",
            rows=len(foundation),
            compounds=foundation["drug_id"].nunique(),
            targets=foundation["target_id"].nunique(),
            task_support=(
                "classification",
                "regression",
            ),
            source_type="deterministic_synthetic",
            scientific_validity=("Software benchmark only; not " "experimental evidence"),
            description=(
                "Balanced medium-size pack for fast " "local training and UI demonstrations."
            ),
            sha256=_sha256(foundation_path),
        ),
        DataPackRecord(
            key="extended_dti",
            filename=extended_path.relative_to(project_root).as_posix(),
            title="Extended DTI Pack",
            rows=len(extended),
            compounds=extended["drug_id"].nunique(),
            targets=extended["target_id"].nunique(),
            task_support=(
                "classification",
                "regression",
            ),
            source_type="deterministic_synthetic",
            scientific_validity=("Software benchmark only; not " "experimental evidence"),
            description=(
                "Large balanced pack for pretrained " "models, benchmarking and batch tests."
            ),
            sha256=_sha256(extended_path),
        ),
        DataPackRecord(
            key="batch_sample",
            filename=batch_path.relative_to(project_root).as_posix(),
            title="Batch Prediction Sample",
            rows=len(batch_sample),
            compounds=batch_sample["canonical_smiles"].nunique(),
            targets=batch_sample["target_id"].nunique(),
            task_support=("prediction",),
            source_type="deterministic_synthetic",
            scientific_validity=("Software benchmark only; not " "experimental evidence"),
            description=("Ready-to-upload 250-row sample for " "batch prediction modules."),
            sha256=_sha256(batch_path),
        ),
    ]

    manifest = {
        "data_pack_version": DATA_PACK_VERSION,
        "generated_with_seed": 20260704,
        "packs": [asdict(record) for record in records],
        "libraries": {
            "molecules": {
                "filename": molecule_path.relative_to(project_root).as_posix(),
                "rows": len(molecules),
                "sha256": _sha256(molecule_path),
            },
            "proteins_csv": {
                "filename": protein_path.relative_to(project_root).as_posix(),
                "rows": len(proteins),
                "sha256": _sha256(protein_path),
            },
            "proteins_fasta": {
                "filename": fasta_path.relative_to(project_root).as_posix(),
                "records": len(proteins),
                "sha256": _sha256(fasta_path),
            },
            "chembl_recipes": {
                "filename": recipe_path.relative_to(project_root).as_posix(),
                "rows": len(recipes),
                "sha256": _sha256(recipe_path),
            },
        },
        "warning": (
            "Bundled DTI packs are deterministic "
            "synthetic benchmarks. They are not "
            "biological or clinical evidence."
        ),
    }
    (pack_directory / "data_pack_manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return records


def load_data_pack_manifest(
    root: str | Path,
) -> dict[str, object]:
    path = Path(root).resolve() / "data" / "packs" / "data_pack_manifest.json"
    default = {
        "data_pack_version": DATA_PACK_VERSION,
        "packs": [],
        "libraries": {},
        "warning": "Data packs have not been generated.",
    }
    return load_json_cached(path, default=default)


def register_bundled_data_packs(
    root: str | Path,
) -> list[dict[str, object]]:
    """Register Double, Ultra, Extended and Foundation task views."""

    from biointel.data.dataset_registry import (
        delete_dataset_record,
        list_datasets,
        register_dataset,
    )

    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "datasets.sqlite3")
    for existing in list_datasets(registry, limit=5000):
        if existing.dataset_name.startswith("BioIntel Synthetic"):
            delete_dataset_record(registry, existing.dataset_sha256)
    frames = (
        (
            "5X",
            pd.read_csv(project_root / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv"),
            "5.0",
        ),
        (
            "Double",
            pd.read_csv(project_root / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv"),
            "4.0",
        ),
        (
            "Ultra",
            pd.read_csv(project_root / "data" / "packs" / "synthetic_ultra_dti_v3.csv"),
            "3.0",
        ),
        (
            "Extended",
            pd.read_csv(project_root / "data" / "packs" / "synthetic_extended_dti_v2.csv"),
            "2.0",
        ),
        (
            "Foundation",
            pd.read_csv(project_root / "data" / "packs" / "synthetic_foundation_dti_v2.csv"),
            "2.0",
        ),
    )
    common = [
        "drug_id",
        "canonical_smiles",
        "target_id",
        "protein_sequence",
        "activity_type",
        "source",
        "data_pack_version",
    ]
    registered: list[dict[str, object]] = []
    parent_hashes: dict[str, str] = {}

    for pack_name, dataframe, pack_version in frames:
        for task_type, target_column in (
            ("classification", "label"),
            ("regression", "p_activity"),
        ):
            record = register_dataset(
                registry,
                dataframe[common + [target_column]].copy(),
                dataset_name=f"BioIntel Synthetic {pack_name} DTI",
                dataset_version=f"{pack_version}-{task_type}",
                task_type=task_type,
                source_description=(
                    "Deterministic synthetic benchmark generated " "locally by BioIntel AI"
                ),
                activity_type="SYNTHETIC_AFFINITY_SCORE",
                parent_sha256=parent_hashes.get(task_type),
                notes=("Software validation only; not experimental " "or clinical evidence."),
                metadata={
                    "compounds": int(dataframe["drug_id"].nunique()),
                    "targets": int(dataframe["target_id"].nunique()),
                    "data_pack": pack_name.lower(),
                    "source_rows": len(dataframe),
                },
            )
            parent_hashes[task_type] = record.dataset_sha256
            registered.append(asdict(record))
    return registered


def data_library_summary(
    root: str | Path,
) -> dict[str, object]:
    project_root = Path(root).resolve()
    manifest = load_data_pack_manifest(project_root)
    benchmark_path = project_root / "data" / "packs" / "model_benchmark_summary.json"
    benchmark = load_json_cached(
        benchmark_path,
        default={
            "best_models": {},
            "ranking": [],
            "warning": ("Bundled model benchmark has not been generated."),
        },
    )
    return {
        "manifest": manifest,
        "benchmark": benchmark,
    }


def verify_data_pack_integrity(
    root: str | Path,
) -> dict[str, object]:
    """Verify bundled files, re-hashing only changed signatures."""

    project_root = Path(root).resolve()
    manifest = load_data_pack_manifest(project_root)
    total_rows = 0
    items: list[dict[str, object]] = []

    for pack in manifest.get("packs", []):
        if isinstance(pack, dict):
            items.append(pack)
            total_rows += int(pack.get("rows", 0))

    libraries = manifest.get("libraries", {})
    if isinstance(libraries, dict):
        items.extend(value for value in libraries.values() if isinstance(value, dict))

    result = verify_manifest_files(
        project_root,
        items,
        cache_name=".data_pack_integrity_cache.json",
    )
    return {
        **result,
        "total_rows": total_rows,
        "data_pack_version": manifest.get(
            "data_pack_version",
            DATA_PACK_VERSION,
        ),
    }


def build_ultra_dataset(
    random_seed: int = 20260716,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the Step 16 16,000-pair synthetic benchmark."""

    molecules = build_molecule_library(
        count=400,
        random_seed=random_seed,
    )
    proteins = build_protein_library(
        count=40,
        random_seed=random_seed,
    )
    dataset = _latent_dataset(
        molecules,
        proteins,
        random_seed=random_seed,
    )
    return molecules, proteins, dataset


def _write_step16_data_packs(
    root: str | Path,
) -> list[DataPackRecord]:
    """Generate Step 15 and Step 16 packs."""

    records = _write_step15_data_packs(root)
    project_root = Path(root).resolve()
    pack_directory = project_root / "data" / "packs"
    library_directory = project_root / "data" / "libraries"
    template_directory = project_root / "data" / "templates"
    template_directory.mkdir(parents=True, exist_ok=True)

    ultra_molecules, ultra_proteins, ultra = build_ultra_dataset()
    ultra_path = pack_directory / "synthetic_ultra_dti_v3.csv"
    ultra_molecule_path = library_directory / "molecule_library_400.csv"
    ultra_protein_path = library_directory / "protein_library_40.csv"
    ultra_fasta_path = library_directory / "protein_library_40.fasta"
    batch_1000_path = pack_directory / "batch_prediction_sample_1000.csv"
    classification_template_path = template_directory / "classification_training_template.csv"
    regression_template_path = template_directory / "regression_training_template.csv"
    prediction_template_path = template_directory / "prediction_input_template.csv"

    ultra.to_csv(ultra_path, index=False)
    ultra_molecules.to_csv(ultra_molecule_path, index=False)
    ultra_proteins.to_csv(ultra_protein_path, index=False)
    ultra_fasta_path.write_text(
        "\n".join(
            f">{row.target_id}|{row.target_family}\n" f"{row.protein_sequence}"
            for row in ultra_proteins.itertuples(index=False)
        )
        + "\n",
        encoding="utf-8",
    )

    batch_1000 = (
        ultra.sample(
            n=1000,
            random_state=20260716,
        )[
            [
                "drug_id",
                "canonical_smiles",
                "target_id",
                "protein_sequence",
            ]
        ]
        .rename(columns={"drug_id": "sample_id"})
        .reset_index(drop=True)
    )
    batch_1000.to_csv(batch_1000_path, index=False)

    template_source = ultra.sample(
        n=100,
        random_state=20260717,
    ).reset_index(drop=True)
    template_source[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "label",
        ]
    ].to_csv(
        classification_template_path,
        index=False,
    )
    template_source[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "p_activity",
        ]
    ].to_csv(
        regression_template_path,
        index=False,
    )
    template_source[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
        ]
    ].rename(columns={"drug_id": "sample_id"}).to_csv(
        prediction_template_path,
        index=False,
    )

    ultra_record = DataPackRecord(
        key="ultra_dti",
        filename=ultra_path.relative_to(project_root).as_posix(),
        title="Ultra DTI Pack",
        rows=len(ultra),
        compounds=ultra["drug_id"].nunique(),
        targets=ultra["target_id"].nunique(),
        task_support=(
            "classification",
            "regression",
        ),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description=(
            "Step 16 high-data benchmark with 16,000 " "drug-target pairs for ML benchmarking."
        ),
        sha256=_sha256(ultra_path),
    )
    batch_record = DataPackRecord(
        key="batch_sample_1000",
        filename=batch_1000_path.relative_to(project_root).as_posix(),
        title="Batch Prediction Sample 1000",
        rows=len(batch_1000),
        compounds=batch_1000["canonical_smiles"].nunique(),
        targets=batch_1000["target_id"].nunique(),
        task_support=("prediction",),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description=("Ready-to-upload 1,000-row prediction input."),
        sha256=_sha256(batch_1000_path),
    )
    records.extend([ultra_record, batch_record])

    manifest_path = pack_directory / "data_pack_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_pack_version"] = "3.0"
    manifest["generated_with_seed_step16"] = 20260716
    manifest["packs"] = [asdict(record) for record in records]
    manifest["libraries"].update(
        {
            "molecules_400": {
                "filename": ultra_molecule_path.relative_to(project_root).as_posix(),
                "rows": len(ultra_molecules),
                "sha256": _sha256(ultra_molecule_path),
            },
            "proteins_40_csv": {
                "filename": ultra_protein_path.relative_to(project_root).as_posix(),
                "rows": len(ultra_proteins),
                "sha256": _sha256(ultra_protein_path),
            },
            "proteins_40_fasta": {
                "filename": ultra_fasta_path.relative_to(project_root).as_posix(),
                "records": len(ultra_proteins),
                "sha256": _sha256(ultra_fasta_path),
            },
            "classification_template": {
                "filename": classification_template_path.relative_to(project_root).as_posix(),
                "rows": 100,
                "sha256": _sha256(classification_template_path),
            },
            "regression_template": {
                "filename": regression_template_path.relative_to(project_root).as_posix(),
                "rows": 100,
                "sha256": _sha256(regression_template_path),
            },
            "prediction_template": {
                "filename": prediction_template_path.relative_to(project_root).as_posix(),
                "rows": 100,
                "sha256": _sha256(prediction_template_path),
            },
        }
    )
    manifest["warning"] = (
        "All bundled DTI packs are deterministic synthetic "
        "software benchmarks and are not biological or clinical evidence."
    )
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return records


def build_double_ultra_dataset(
    random_seed: int = 20260717,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the exact double-size 32,000-pair Step 17 pack."""

    molecules = build_molecule_library(
        count=640,
        random_seed=random_seed,
    )
    proteins = build_protein_library(
        count=50,
        random_seed=random_seed,
    )
    dataset = _latent_dataset(
        molecules,
        proteins,
        random_seed=random_seed,
    )
    return molecules, proteins, dataset


def _write_step18_data_packs(
    root: str | Path,
) -> list[DataPackRecord]:
    """Generate all packs through Step 17 Double Ultra."""

    records = _write_step16_data_packs(root)
    project_root = Path(root).resolve()
    pack_directory = project_root / "data" / "packs"
    library_directory = project_root / "data" / "libraries"
    template_directory = project_root / "data" / "templates"
    template_directory.mkdir(parents=True, exist_ok=True)

    molecules, proteins, dataset = build_double_ultra_dataset()
    dataset_path = pack_directory / "synthetic_double_ultra_dti_v4.csv"
    molecule_path = library_directory / "molecule_library_640.csv"
    protein_path = library_directory / "protein_library_50.csv"
    fasta_path = library_directory / "protein_library_50.fasta"
    batch_path = pack_directory / "batch_prediction_sample_2000.csv"
    class_template = template_directory / "double_classification_training_template_250.csv"
    reg_template = template_directory / "double_regression_training_template_250.csv"
    pred_template = template_directory / "double_prediction_input_template_250.csv"

    dataset.to_csv(dataset_path, index=False)
    molecules.to_csv(molecule_path, index=False)
    proteins.to_csv(protein_path, index=False)
    fasta_path.write_text(
        "\n".join(
            f">{row.target_id}|{row.target_family}\n" f"{row.protein_sequence}"
            for row in proteins.itertuples(index=False)
        )
        + "\n",
        encoding="utf-8",
    )

    batch = (
        dataset.sample(n=2000, random_state=20260717)[
            [
                "drug_id",
                "canonical_smiles",
                "target_id",
                "protein_sequence",
            ]
        ]
        .rename(columns={"drug_id": "sample_id"})
        .reset_index(drop=True)
    )
    batch.to_csv(batch_path, index=False)

    template = dataset.sample(n=250, random_state=20260718).reset_index(drop=True)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "label",
        ]
    ].to_csv(class_template, index=False)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "p_activity",
        ]
    ].to_csv(reg_template, index=False)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
        ]
    ].rename(
        columns={"drug_id": "sample_id"}
    ).to_csv(pred_template, index=False)

    double_record = DataPackRecord(
        key="double_ultra_dti",
        filename=dataset_path.relative_to(project_root).as_posix(),
        title="Double Ultra DTI Pack",
        rows=len(dataset),
        compounds=int(dataset["drug_id"].nunique()),
        targets=int(dataset["target_id"].nunique()),
        task_support=("classification", "regression"),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description=("Step 17 exact double-data benchmark with 32,000 " "drug-target pairs."),
        sha256=_sha256(dataset_path),
    )
    batch_record = DataPackRecord(
        key="batch_sample_2000",
        filename=batch_path.relative_to(project_root).as_posix(),
        title="Batch Prediction Sample 2000",
        rows=len(batch),
        compounds=int(batch["canonical_smiles"].nunique()),
        targets=int(batch["target_id"].nunique()),
        task_support=("prediction",),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description="Ready-to-upload 2,000-row prediction input.",
        sha256=_sha256(batch_path),
    )
    records.extend([double_record, batch_record])

    manifest_path = pack_directory / "data_pack_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_pack_version"] = "4.0"
    manifest["generated_with_seed_step17"] = 20260717
    manifest["packs"] = [asdict(record) for record in records]
    manifest["libraries"].update(
        {
            "molecules_640": {
                "filename": molecule_path.relative_to(project_root).as_posix(),
                "rows": len(molecules),
                "sha256": _sha256(molecule_path),
            },
            "proteins_50_csv": {
                "filename": protein_path.relative_to(project_root).as_posix(),
                "rows": len(proteins),
                "sha256": _sha256(protein_path),
            },
            "proteins_50_fasta": {
                "filename": fasta_path.relative_to(project_root).as_posix(),
                "records": len(proteins),
                "sha256": _sha256(fasta_path),
            },
            "double_classification_template": {
                "filename": class_template.relative_to(project_root).as_posix(),
                "rows": 250,
                "sha256": _sha256(class_template),
            },
            "double_regression_template": {
                "filename": reg_template.relative_to(project_root).as_posix(),
                "rows": 250,
                "sha256": _sha256(reg_template),
            },
            "double_prediction_template": {
                "filename": pred_template.relative_to(project_root).as_posix(),
                "rows": 250,
                "sha256": _sha256(pred_template),
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return records


def build_quintuple_ultra_dataset(
    random_seed: int = 20260719,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the exact five-times 160,000-pair Step 19 pack."""

    molecules = build_molecule_library(
        count=1000,
        random_seed=random_seed,
    )
    proteins = build_protein_library(
        count=160,
        random_seed=random_seed,
    )
    dataset = _latent_dataset(
        molecules,
        proteins,
        random_seed=random_seed,
    )
    return molecules, proteins, dataset


def write_data_packs(
    root: str | Path,
) -> list[DataPackRecord]:
    """Generate all packs through the Step 19 5X benchmark."""

    records = _write_step18_data_packs(root)
    project_root = Path(root).resolve()
    pack_directory = project_root / "data" / "packs"
    library_directory = project_root / "data" / "libraries"
    template_directory = project_root / "data" / "templates"
    template_directory.mkdir(parents=True, exist_ok=True)

    molecules, proteins, dataset = build_quintuple_ultra_dataset()
    dataset_path = pack_directory / "synthetic_5x_ultra_dti_v5.csv"
    molecule_path = library_directory / "molecule_library_1000_5x.csv"
    protein_path = library_directory / "protein_library_160.csv"
    fasta_path = library_directory / "protein_library_160.fasta"
    batch_path = pack_directory / "batch_prediction_sample_5000.csv"
    class_template = template_directory / "five_x_classification_training_template_500.csv"
    reg_template = template_directory / "five_x_regression_training_template_500.csv"
    pred_template = template_directory / "five_x_prediction_input_template_500.csv"

    dataset.to_csv(dataset_path, index=False)
    molecules.to_csv(molecule_path, index=False)
    proteins.to_csv(protein_path, index=False)
    fasta_path.write_text(
        "\n".join(
            f">{row.target_id}|{row.target_family}\n" f"{row.protein_sequence}"
            for row in proteins.itertuples(index=False)
        )
        + "\n",
        encoding="utf-8",
    )

    batch = (
        dataset.sample(
            n=5000,
            random_state=20260719,
        )[
            [
                "drug_id",
                "canonical_smiles",
                "target_id",
                "protein_sequence",
            ]
        ]
        .rename(columns={"drug_id": "sample_id"})
        .reset_index(drop=True)
    )
    batch.to_csv(batch_path, index=False)

    template = dataset.sample(
        n=500,
        random_state=20260720,
    ).reset_index(drop=True)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "label",
        ]
    ].to_csv(class_template, index=False)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
            "p_activity",
        ]
    ].to_csv(reg_template, index=False)
    template[
        [
            "drug_id",
            "canonical_smiles",
            "target_id",
            "protein_sequence",
        ]
    ].rename(
        columns={"drug_id": "sample_id"}
    ).to_csv(pred_template, index=False)

    five_x_record = DataPackRecord(
        key="five_x_ultra_dti",
        filename=dataset_path.relative_to(project_root).as_posix(),
        title="5X Ultra DTI Pack",
        rows=len(dataset),
        compounds=int(dataset["drug_id"].nunique()),
        targets=int(dataset["target_id"].nunique()),
        task_support=("classification", "regression"),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description=("Step 19 exact five-times benchmark with " "160,000 drug-target pairs."),
        sha256=_sha256(dataset_path),
    )
    batch_record = DataPackRecord(
        key="batch_sample_5000",
        filename=batch_path.relative_to(project_root).as_posix(),
        title="Batch Prediction Sample 5000",
        rows=len(batch),
        compounds=int(batch["canonical_smiles"].nunique()),
        targets=int(batch["target_id"].nunique()),
        task_support=("prediction",),
        source_type="deterministic_synthetic",
        scientific_validity=("Software benchmark only; not experimental evidence"),
        description=("Ready-to-upload 5,000-row prediction input."),
        sha256=_sha256(batch_path),
    )
    records.extend([five_x_record, batch_record])

    manifest_path = pack_directory / "data_pack_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_pack_version"] = "5.0"
    manifest["generated_with_seed_step19"] = 20260719
    manifest["packs"] = [asdict(record) for record in records]
    manifest["libraries"].update(
        {
            "molecules_1000_5x": {
                "filename": molecule_path.relative_to(project_root).as_posix(),
                "rows": len(molecules),
                "sha256": _sha256(molecule_path),
            },
            "proteins_160_csv": {
                "filename": protein_path.relative_to(project_root).as_posix(),
                "rows": len(proteins),
                "sha256": _sha256(protein_path),
            },
            "proteins_160_fasta": {
                "filename": fasta_path.relative_to(project_root).as_posix(),
                "records": len(proteins),
                "sha256": _sha256(fasta_path),
            },
            "five_x_classification_template": {
                "filename": class_template.relative_to(project_root).as_posix(),
                "rows": 500,
                "sha256": _sha256(class_template),
            },
            "five_x_regression_template": {
                "filename": reg_template.relative_to(project_root).as_posix(),
                "rows": 500,
                "sha256": _sha256(reg_template),
            },
            "five_x_prediction_template": {
                "filename": pred_template.relative_to(project_root).as_posix(),
                "rows": 500,
                "sha256": _sha256(pred_template),
            },
        }
    )
    manifest["warning"] = (
        "All bundled packs are deterministic synthetic "
        "software benchmarks, not biological or clinical evidence."
    )
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return records
