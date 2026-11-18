from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import hashlib
import json
import random
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from biointel.data.data_packs import build_molecule_library
from biointel.data.dataset_registry import (
    list_datasets,
    register_dataset,
)
from biointel.governance.governance_registry import (
    create_decision,
    create_milestone,
    upsert_gate,
)
from biointel.portfolio.project_registry import (
    create_project,
    delete_project,
    list_projects,
)
from biointel.training.model_catalog import sync_model_catalog
from biointel.utils.integrity_cache import verify_manifest_files
from biointel.utils.runtime_cache import load_json_cached

COVERAGE_PACK_VERSION = "1.0"
DNA_ALPHABET = "ACGT"
RNA_ALPHABET = "ACGU"
PROTEIN_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"


@dataclass(frozen=True)
class CoverageAsset:
    key: str
    title: str
    filename: str
    rows: int
    section: str
    description: str
    sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _random_sequence(
    alphabet: str,
    length: int,
    seed: int,
) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _mutate_sequence(
    sequence: str,
    alphabet: str,
    rate: float,
    seed: int,
) -> str:
    rng = random.Random(seed)
    chars = list(sequence)
    for index, value in enumerate(chars):
        if rng.random() < rate:
            choices = [item for item in alphabet if item != value]
            chars[index] = rng.choice(choices)
    return "".join(chars)


def _sequence_libraries() -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, object]] = []
    fasta_blocks: list[str] = []

    for index in range(300):
        length = 300 + (index * 37) % 1200
        sequence = _random_sequence(
            DNA_ALPHABET,
            length,
            18000 + index,
        )
        if length >= 180:
            sequence = sequence[:30] + "ATG" + sequence[33:-6] + "TAA"
        record_id = f"COVDNA{index + 1:04d}"
        records.append(
            {
                "record_id": record_id,
                "sequence_type": "DNA",
                "family": ("coding_like" if index % 3 == 0 else "genomic_like"),
                "sequence": sequence,
                "length": len(sequence),
                "source": "BioIntel deterministic coverage pack",
            }
        )
        fasta_blocks.append(f">{record_id}|DNA\n{sequence}")

    for index in range(200):
        length = 180 + (index * 29) % 720
        sequence = _random_sequence(
            RNA_ALPHABET,
            length,
            19000 + index,
        )
        record_id = f"COVRNA{index + 1:04d}"
        records.append(
            {
                "record_id": record_id,
                "sequence_type": "RNA",
                "family": ("transcript_like" if index % 2 == 0 else "noncoding_like"),
                "sequence": sequence,
                "length": len(sequence),
                "source": "BioIntel deterministic coverage pack",
            }
        )
        fasta_blocks.append(f">{record_id}|RNA\n{sequence}")

    protein_biases = (
        "AILVFWY",
        "GSTC",
        "DEKR",
        "PGQN",
        "ACDEFGHIKLMNPQRSTVWY",
    )
    for index in range(300):
        length = 100 + (index * 43) % 700
        bias = protein_biases[index % len(protein_biases)]
        alphabet = PROTEIN_ALPHABET + bias * 2
        sequence = _random_sequence(
            alphabet,
            length,
            20000 + index,
        )
        record_id = f"COVPRO{index + 1:04d}"
        records.append(
            {
                "record_id": record_id,
                "sequence_type": "Protein",
                "family": (
                    "membrane_like"
                    if index % 5 == 0
                    else "enzyme_like" if index % 5 == 1 else "binding_like"
                ),
                "sequence": sequence,
                "length": len(sequence),
                "source": "BioIntel deterministic coverage pack",
            }
        )
        fasta_blocks.append(f">{record_id}|Protein\n{sequence}")

    frame = pd.DataFrame(records)
    return frame, pd.DataFrame({"fasta_text": ["\n".join(fasta_blocks) + "\n"]})


def _comparison_pairs(
    sequence_library: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    rates = (0.02, 0.05, 0.10, 0.15)
    for sequence_type, alphabet in (
        ("DNA", DNA_ALPHABET),
        ("RNA", RNA_ALPHABET),
        ("Protein", PROTEIN_ALPHABET),
    ):
        subset = sequence_library[sequence_library["sequence_type"] == sequence_type].head(60)
        for pair_index, row in enumerate(
            subset.itertuples(index=False),
            start=1,
        ):
            rate = rates[(pair_index - 1) % len(rates)]
            target = _mutate_sequence(
                str(row.sequence),
                alphabet,
                rate,
                21000
                + pair_index
                + (0 if sequence_type == "DNA" else 1000)
                + (0 if sequence_type == "RNA" else 2000),
            )
            rows.append(
                {
                    "pair_id": (f"{sequence_type[:3].upper()}PAIR" f"{pair_index:03d}"),
                    "sequence_type": sequence_type,
                    "query_id": row.record_id,
                    "query_sequence": row.sequence,
                    "target_id": f"{row.record_id}_MUT",
                    "target_sequence": target,
                    "mutation_rate": rate,
                    "recommended_mode": ("global" if rate <= 0.10 else "local"),
                    "source": ("BioIntel deterministic coverage pack"),
                }
            )
    return pd.DataFrame(rows)


def _validation_assets(
    root: Path,
) -> dict[str, pd.DataFrame]:
    double_path = root / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv"
    source = pd.read_csv(double_path)
    drug_ids = sorted(source["drug_id"].unique())
    target_ids = sorted(source["target_id"].unique())

    external_drugs = set(drug_ids[-200:])
    external_targets = set(target_ids[-25:])
    external = source[
        source["drug_id"].isin(external_drugs) & source["target_id"].isin(external_targets)
    ].head(5000)

    shifted_drugs = set(drug_ids[:80])
    shifted_targets = set(target_ids[-25:])
    drift = source[
        source["drug_id"].isin(shifted_drugs) & source["target_id"].isin(shifted_targets)
    ].head(2000)

    common = [
        "drug_id",
        "canonical_smiles",
        "target_id",
        "protein_sequence",
    ]
    return {
        "external_classification": external[common + ["label"]].reset_index(drop=True),
        "external_regression": external[common + ["p_activity"]].reset_index(drop=True),
        "drift_classification": drift[common + ["label"]].reset_index(drop=True),
        "drift_regression": drift[common + ["p_activity"]].reset_index(drop=True),
    }


def _lookup_catalog() -> pd.DataFrame:
    rows = [
        ("UniProt", "Protein accession", "P69905", "Hemoglobin subunit alpha"),
        ("UniProt", "Protein accession", "P68871", "Hemoglobin subunit beta"),
        ("UniProt", "Protein accession", "P00533", "Epidermal growth factor receptor"),
        ("UniProt", "Protein accession", "P04637", "Cellular tumor antigen p53"),
        ("UniProt", "Protein accession", "P31749", "AKT1"),
        ("UniProt", "Protein accession", "P15056", "BRAF"),
        ("UniProt", "Protein accession", "P24941", "CDK2"),
        ("UniProt", "Protein accession", "P28482", "MAPK1"),
        ("ChEMBL molecule", "Molecule ID", "CHEMBL25", "Aspirin"),
        ("ChEMBL molecule", "Molecule ID", "CHEMBL521", "Caffeine"),
        ("ChEMBL molecule", "Molecule ID", "CHEMBL1201585", "Ibuprofen"),
        ("ChEMBL molecule", "Molecule ID", "CHEMBL941", "Paracetamol"),
        ("ChEMBL target", "Target ID", "CHEMBL203", "EGFR"),
        ("ChEMBL target", "Target ID", "CHEMBL279", "VEGFR2"),
        ("ChEMBL target", "Target ID", "CHEMBL1862", "ABL1"),
        ("ChEMBL target", "Target ID", "CHEMBL240", "KCNH2"),
        ("ChEMBL target", "Target ID", "CHEMBL204", "Prothrombin"),
        ("ChEMBL target", "Target ID", "CHEMBL301", "CDK2"),
        ("ChEMBL target", "Target ID", "CHEMBL4822", "BRAF"),
        ("ChEMBL target", "Target ID", "CHEMBL214", "AKT1"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "database",
            "query_type",
            "query_value",
            "description",
        ],
    )


def write_coverage_packs(
    root: str | Path,
) -> list[CoverageAsset]:
    project_root = Path(root).resolve()
    directory = project_root / "data" / "coverage"
    directory.mkdir(parents=True, exist_ok=True)

    sequences, fasta_frame = _sequence_libraries()
    pairs = _comparison_pairs(sequences)
    molecules = build_molecule_library(
        count=1000,
        random_seed=20260718,
    )
    validation = _validation_assets(project_root)
    lookups = _lookup_catalog()

    paths: dict[str, Path] = {
        "sequence_library": directory / "sequence_library_800.csv",
        "sequence_fasta": directory / "sequence_library_800.fasta",
        "comparison_pairs": directory / "sequence_comparison_pairs_180.csv",
        "molecule_library": directory / "molecule_analysis_library_1000.csv",
        "external_classification": directory / "external_validation_classification_5000.csv",
        "external_regression": directory / "external_validation_regression_5000.csv",
        "drift_classification": directory / "drift_validation_classification_2000.csv",
        "drift_regression": directory / "drift_validation_regression_2000.csv",
        "lookup_catalog": directory / "external_lookup_starters_20.csv",
    }

    sequences.to_csv(paths["sequence_library"], index=False)
    paths["sequence_fasta"].write_text(
        str(fasta_frame.iloc[0]["fasta_text"]),
        encoding="utf-8",
    )
    pairs.to_csv(paths["comparison_pairs"], index=False)
    molecules.to_csv(paths["molecule_library"], index=False)
    for key, frame in validation.items():
        frame.to_csv(paths[key], index=False)
    lookups.to_csv(paths["lookup_catalog"], index=False)

    specs = [
        (
            "sequence_library",
            "Sequence Library",
            len(sequences),
            "Sequence Analyzer / Batch Sequence",
            "300 DNA, 200 RNA and 300 protein records.",
        ),
        (
            "sequence_fasta",
            "Sequence FASTA Pack",
            len(sequences),
            "Batch Sequence",
            "Combined 800-record FASTA file.",
        ),
        (
            "comparison_pairs",
            "Sequence Comparison Pairs",
            len(pairs),
            "Sequence Comparison",
            "DNA, RNA and protein mutation pairs.",
        ),
        (
            "molecule_library",
            "Molecule Analysis Library",
            len(molecules),
            "SMILES Analyzer",
            "1,000 RDKit-valid molecular structures.",
        ),
        (
            "external_classification",
            "External Classification Validation",
            len(validation["external_classification"]),
            "External Validation",
            "5,000 labelled independent-style pairs.",
        ),
        (
            "external_regression",
            "External Regression Validation",
            len(validation["external_regression"]),
            "External Validation",
            "5,000 p_activity validation pairs.",
        ),
        (
            "drift_classification",
            "Classification Drift Sample",
            len(validation["drift_classification"]),
            "External Validation",
            "2,000 shifted-distribution labelled pairs.",
        ),
        (
            "drift_regression",
            "Regression Drift Sample",
            len(validation["drift_regression"]),
            "External Validation",
            "2,000 shifted-distribution activity pairs.",
        ),
        (
            "lookup_catalog",
            "External Lookup Starters",
            len(lookups),
            "External Databases",
            "Ready UniProt and ChEMBL identifiers.",
        ),
    ]

    assets = [
        CoverageAsset(
            key=key,
            title=title,
            filename=paths[key].relative_to(project_root).as_posix(),
            rows=rows,
            section=section,
            description=description,
            sha256=_sha256(paths[key]),
        )
        for key, title, rows, section, description in specs
    ]
    manifest = {
        "coverage_pack_version": COVERAGE_PACK_VERSION,
        "assets": [asdict(item) for item in assets],
        "totals": {
            "sequence_records": len(sequences),
            "comparison_pairs": len(pairs),
            "molecules": len(molecules),
            "external_validation_rows": sum(len(item) for item in validation.values()),
            "lookup_starters": len(lookups),
        },
        "warning": (
            "Coverage assets are deterministic demonstration data. "
            "They are not biological or clinical evidence."
        ),
    }
    (directory / "coverage_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return assets


def load_coverage_manifest(
    root: str | Path,
) -> dict[str, object]:
    path = Path(root).resolve() / "data" / "coverage" / "coverage_manifest.json"
    return load_json_cached(
        path,
        default={
            "coverage_pack_version": COVERAGE_PACK_VERSION,
            "assets": [],
            "totals": {},
            "warning": "Coverage pack is missing.",
        },
    )


def verify_coverage_integrity(
    root: str | Path,
) -> dict[str, object]:
    project_root = Path(root).resolve()
    manifest = load_coverage_manifest(project_root)
    assets = [asset for asset in manifest.get("assets", []) if isinstance(asset, dict)]
    result = verify_manifest_files(
        project_root,
        assets,
        cache_name=".coverage_integrity_cache.json",
    )
    return {
        **result,
        "totals": manifest.get("totals", {}),
        "coverage_pack_version": manifest.get(
            "coverage_pack_version",
            COVERAGE_PACK_VERSION,
        ),
    }


def register_coverage_datasets(
    root: str | Path,
) -> list[dict[str, object]]:
    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "datasets.sqlite3")
    directory = project_root / "data" / "coverage"
    if registry.exists():
        with managed_connect(registry) as connection:
            connection.execute(
                "DELETE FROM datasets WHERE dataset_name LIKE ?",
                ("BioIntel Coverage %",),
            )
            connection.execute(
                "DELETE FROM datasets WHERE dataset_name LIKE ?",
                ("BioIntel External Validation %",),
            )
            connection.execute(
                "DELETE FROM datasets WHERE dataset_name LIKE ?",
                ("BioIntel Drift Validation %",),
            )
            connection.commit()
    specs = [
        (
            "sequence_library_800.csv",
            "BioIntel Coverage Sequence Library",
            "1.0",
            "unlabelled",
        ),
        (
            "sequence_comparison_pairs_180.csv",
            "BioIntel Coverage Alignment Pairs",
            "1.0",
            "unlabelled",
        ),
        (
            "molecule_analysis_library_1000.csv",
            "BioIntel Coverage Molecule Library",
            "1.0",
            "unlabelled",
        ),
        (
            "external_validation_classification_5000.csv",
            "BioIntel External Validation Classification",
            "1.0",
            "classification",
        ),
        (
            "external_validation_regression_5000.csv",
            "BioIntel External Validation Regression",
            "1.0",
            "regression",
        ),
        (
            "drift_validation_classification_2000.csv",
            "BioIntel Drift Validation Classification",
            "1.0",
            "classification",
        ),
        (
            "drift_validation_regression_2000.csv",
            "BioIntel Drift Validation Regression",
            "1.0",
            "regression",
        ),
        (
            "external_lookup_starters_20.csv",
            "BioIntel External Lookup Starters",
            "1.0",
            "unlabelled",
        ),
    ]
    records = []
    for filename, name, version, task in specs:
        frame = pd.read_csv(directory / filename)
        record = register_dataset(
            registry,
            frame,
            dataset_name=name,
            dataset_version=version,
            task_type=task,
            source_description=("BioIntel deterministic complete-coverage pack"),
            notes=("Demonstration data only; not experimental evidence."),
            metadata={
                "coverage_pack_version": COVERAGE_PACK_VERSION,
                "filename": filename,
            },
        )
        records.append(asdict(record))
    return records


def seed_demo_workspace(
    root: str | Path,
    replace_existing_demo: bool = True,
) -> dict[str, object]:
    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "projects.sqlite3")
    if replace_existing_demo:
        for project in list_projects(registry):
            if project.project_code.startswith("DEMO-"):
                delete_project(registry, project.project_id)

    datasets = list_datasets(
        runtime_database_path(project_root, "datasets.sqlite3"),
        limit=5000,
    )
    models = [
        item for item in sync_model_catalog(project_root / "models") if item.state != "archived"
    ]
    dataset_hashes = [item.dataset_sha256 for item in datasets]
    model_files = [item.filename for item in models]

    today = date.today()
    templates = [
        ("DEMO-SEQ-01", "Sequence Library Characterisation", "Active", "High"),
        ("DEMO-ALIGN-02", "Mutation Alignment Benchmark", "Validation", "Medium"),
        ("DEMO-CHEM-03", "Molecule Descriptor Profiling", "Active", "High"),
        ("DEMO-DTI-04", "Double-Data DTI Classification", "Validation", "Critical"),
        ("DEMO-REG-05", "Activity Regression Benchmark", "Active", "High"),
        ("DEMO-EXT-06", "External Validation Programme", "Validation", "Critical"),
        ("DEMO-DRIFT-07", "Dataset Drift Monitoring", "Active", "High"),
        ("DEMO-CHEMBL-08", "ChEMBL Data Collection Pilot", "Planning", "Medium"),
        ("DEMO-BATCH-09", "Batch Prediction Operations", "Active", "Medium"),
        ("DEMO-GOV-10", "Research Governance Controls", "Completed", "Low"),
        ("DEMO-REPORT-11", "Evidence Package Readiness", "Validation", "High"),
        ("DEMO-RELEASE-12", "Local Release Qualification", "Planning", "Medium"),
    ]
    projects = []
    milestone_count = 0
    decision_count = 0
    gate_count = 0

    for index, (code, name, status, priority) in enumerate(templates):
        project = create_project(
            registry,
            project_code=code,
            name=name,
            status=status,
            priority=priority,
            objective=(
                f"Demonstrate complete data coverage and controlled "
                f"evidence for {name.lower()}."
            ),
            owner_label=("Bioinformatics team" if index % 2 == 0 else "ML validation team"),
            tags=(
                "demo",
                "coverage",
                "step18",
                status.lower(),
            ),
            target_date=(today + timedelta(days=14 + index * 9)).isoformat(),
            dataset_sha256=(
                dataset_hashes[index % len(dataset_hashes)] if dataset_hashes else None
            ),
            model_filename=(
                model_files[index % len(model_files)] if model_files and index >= 3 else None
            ),
            notes=(
                "Seeded professional demonstration project. "
                "Replace with real research evidence before use."
            ),
        )
        projects.append(project)

        statuses = (
            ("Completed", "Completed", "In Progress", "Planned")
            if status in {"Active", "Validation"}
            else (
                ("Completed", "Completed", "Completed", "Completed")
                if status == "Completed"
                else ("Completed", "In Progress", "Planned", "Planned")
            )
        )
        milestone_titles = (
            "Data intake and provenance review",
            "Quality and feature validation",
            "Model or analytical benchmark",
            "Independent evidence review",
        )
        for offset, (title, milestone_status) in enumerate(
            zip(milestone_titles, statuses, strict=True)
        ):
            create_milestone(
                registry,
                project.project_id,
                title=title,
                status=milestone_status,
                due_date=(today + timedelta(days=5 + index * 5 + offset * 8)).isoformat(),
                owner_label=project.owner_label,
                acceptance_criteria=(
                    "Required files, checksums, metrics and review notes "
                    "are recorded in the local workspace."
                ),
                evidence_reference=(f"reports/generated/{code.lower()}_evidence.json"),
                notes="Seeded Step 18 demonstration milestone.",
            )
            milestone_count += 1

        create_decision(
            registry,
            project.project_id,
            title="Adopt controlled local workflow",
            decision=(
                "Use checksum-verified local datasets and grouped "
                "evaluation splits for this demonstration project."
            ),
            status="Approved",
            context=(
                "The project requires reproducible examples without " "external authentication."
            ),
            rationale=(
                "Local deterministic data provides reliable software "
                "coverage while keeping scientific limitations explicit."
            ),
            alternatives="Manual uploads only; cloud-hosted workflow.",
            impact="Faster onboarding and reproducible module testing.",
            approver_label="Demo review board",
            evidence_reference="MILESTONE_18_STATUS.md",
        )
        decision_count += 1

        for gate_index, gate_name in enumerate(
            (
                "Data readiness",
                "Model validation",
                "External validation",
                "Reproducibility",
                "Release approval",
            )
        ):
            gate_status = (
                "Approved"
                if gate_index < 2 or status == "Completed"
                else "Conditional" if gate_index == 2 else "Pending"
            )
            upsert_gate(
                registry,
                project.project_id,
                gate_name=gate_name,
                status=gate_status,
                reviewer_label="Demo review board",
                conditions=(
                    ""
                    if gate_status == "Approved"
                    else "Replace synthetic evidence with independently reviewed real data."
                ),
                evidence_reference=(f"reports/generated/{code.lower()}_gate.json"),
                decision_date=(today.isoformat() if gate_status != "Pending" else None),
            )
            gate_count += 1

    summary = {
        "projects": len(projects),
        "milestones": milestone_count,
        "decisions": decision_count,
        "gates": gate_count,
        "dataset_records_available": len(datasets),
        "model_artifacts_available": len(models),
        "warning": ("Seeded workspace content is demonstration data only."),
    }
    output = runtime_report_path(project_root, "generated") / "complete_demo_workspace_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary
