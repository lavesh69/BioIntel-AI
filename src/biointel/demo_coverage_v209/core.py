from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DemoBundle:
    page_key: str
    title: str
    category: str
    family: str
    archive_name: str
    content: bytes
    file_names: tuple[str, ...]
    sha256: str


def _seed(page_key: str) -> int:
    return int(hashlib.sha256(page_key.encode("utf-8")).hexdigest()[:8], 16)


def demo_family(page_key: str, title: str, category: str) -> str:
    text = f"{page_key} {title}".lower().replace("-", "_")
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("sequence", ("sequence", "genome", "annotation", "primer", "crispr", "pangenome", "phylog", "long_read", "variant", "gwas", "rare_disease", "amr", "virolog")),
        ("single_cell", ("single_cell", "cell_atlas", "perturb", "trajectory", "multiome")),
        ("spatial_image", ("spatial", "pathology", "image", "microscopy", "histology", "organoid", "phenotypic")),
        ("omics", ("omics", "transcript", "proteom", "metabol", "lipid", "glyco", "epigen", "expression", "biomarker")),
        ("microbiome", ("microbi", "metagenom", "pathogen", "environment", "edna", "one_health")),
        ("compound", ("drug", "compound", "admet", "docking", "ligand", "chembl", "dti", "developability")),
        ("protein", ("protein", "antibody", "enzyme", "vaccine", "neoantigen", "host_pathogen", "cell_therapy")),
        ("neuro_signal", ("eeg", "meg", "sleep", "movement", "autonomic", "speech", "digital_neurology")),
        ("neuro_clinical", ("neuro", "cns", "brain", "stroke", "epilep", "cognitive", "rehabil", "polypharmacy")),
        ("lab_process", ("bioprocess", "fermentation", "wet_lab", "experiment", "synthetic_biology", "gene_therapy")),
    )
    for family, tokens in groups:
        if any(token in text for token in tokens):
            return family
    return {
        "Neuro/CNS": "neuro_clinical",
        "Bioinformatics": "omics",
        "Discovery": "compound",
        "Lab Analytics": "lab_process",
    }.get(category, "tabular")


def _sequence_assets(rng: np.random.Generator) -> dict[str, bytes]:
    bases = np.array(list("ACGT"))
    records = []
    fasta = []
    for index in range(12):
        sequence = "".join(rng.choice(bases, size=180 + index * 3).tolist())
        sample_id = f"SEQ-{index + 1:03d}"
        records.append({"sample_id": sample_id, "group": "case" if index % 2 else "control", "genome_build": "GRCh38", "sequence_length": len(sequence)})
        fasta.extend([f">{sample_id} synthetic_demo", sequence])
    return {
        "demo_metadata.csv": pd.DataFrame(records).to_csv(index=False).encode("utf-8"),
        "demo_sequences.fasta": ("\n".join(fasta) + "\n").encode("utf-8"),
    }


def _single_cell_assets(rng: np.random.Generator) -> dict[str, bytes]:
    matrix = rng.poisson(0.45, size=(80, 24)).astype(int)
    matrix[:4] *= 7
    genes = ["MT-ND1", "MT-CO1", *[f"GENE_{i:02d}" for i in range(22)]]
    frame = pd.DataFrame(matrix, columns=genes)
    frame.insert(0, "cell_id", [f"CELL-{i + 1:03d}" for i in range(len(frame))])
    metadata = pd.DataFrame({"cell_id": frame["cell_id"], "batch": np.where(np.arange(len(frame)) < 40, "B1", "B2"), "condition": np.where(np.arange(len(frame)) % 2, "case", "control")})
    return {"demo_count_matrix.csv": frame.to_csv(index=False).encode(), "demo_cell_metadata.csv": metadata.to_csv(index=False).encode()}


def _spatial_assets(rng: np.random.Generator) -> dict[str, bytes]:
    n = 120
    x = rng.uniform(0, 20, n)
    y = rng.uniform(0, 20, n)
    frame = pd.DataFrame({"spot_id": [f"SPOT-{i + 1:03d}" for i in range(n)], "x": x, "y": y, "value": np.sin(x / 4) + np.cos(y / 5) + rng.normal(0, 0.15, n), "region": np.where(x < 10, "region_A", "region_B")})
    image = np.clip(rng.normal(0.45, 0.12, (64, 64)), 0, 1)
    output = io.BytesIO()
    np.save(output, image, allow_pickle=False)
    return {"demo_spatial_table.csv": frame.to_csv(index=False).encode(), "demo_image_array.npy": output.getvalue()}


def _omics_assets(rng: np.random.Generator) -> dict[str, bytes]:
    n = 48
    frame: dict[str, Any] = {"sample_id": [f"S-{i + 1:03d}" for i in range(n)], "group": np.where(np.arange(n) % 2, "case", "control"), "batch": np.where(np.arange(n) < 24, "B1", "B2")}
    for index in range(30):
        shift = 0.8 if index < 5 else 0.0
        frame[f"feature_{index + 1:02d}"] = rng.normal(shift * (np.arange(n) % 2), 1.0, n)
    return {"demo_feature_matrix.csv": pd.DataFrame(frame).to_csv(index=False).encode()}


def _microbiome_assets(rng: np.random.Generator) -> dict[str, bytes]:
    samples = [f"S-{i + 1:02d}" for i in range(18)] + ["NEG-01", "NEG-02"]
    metadata = pd.DataFrame({"sample_id": samples, "is_negative_control": [False] * 18 + [True, True], "batch": ["B1"] * 10 + ["B2"] * 10})
    rows = []
    for sample in samples:
        negative = sample.startswith("NEG")
        for taxon_index in range(20):
            taxon = f"Taxon_{taxon_index + 1:02d}"
            abundance = int(rng.poisson(18 if negative and taxon_index < 2 else 3))
            rows.append({"sample_id": sample, "taxon": taxon, "abundance": abundance})
    return {"demo_abundance_long.csv": pd.DataFrame(rows).to_csv(index=False).encode(), "demo_sample_metadata.csv": metadata.to_csv(index=False).encode()}


def _compound_assets(rng: np.random.Generator) -> dict[str, bytes]:
    smiles = ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "CN1CCC[C@H]1c2cccnc2", "CCN(CC)CCCC(C)Nc1ncc2ccccc2n1"]
    rows = []
    for index in range(24):
        rows.append({"compound_id": f"CMP-{index + 1:03d}", "smiles": smiles[index % len(smiles)], "potency_nm": round(float(10 ** rng.uniform(0.5, 3.0)), 3), "solubility_um": round(float(10 ** rng.uniform(-0.5, 2.0)), 3), "clearance": round(float(rng.uniform(0.1, 1.0)), 4), "toxicity_flag": bool(index % 11 == 0)})
    return {"demo_compounds.csv": pd.DataFrame(rows).to_csv(index=False).encode()}


def _protein_assets(rng: np.random.Generator) -> dict[str, bytes]:
    amino = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
    rows = []
    fasta = []
    for index in range(10):
        sequence = "".join(rng.choice(amino, size=120 + index).tolist())
        identifier = f"PROT-{index + 1:03d}"
        rows.append({"candidate_id": identifier, "target": "DEMO_TARGET", "activity_nm": round(float(10 ** rng.uniform(0, 3)), 2), "source": "synthetic_demo"})
        fasta.extend([f">{identifier} synthetic_demo", sequence])
    return {"demo_candidates.csv": pd.DataFrame(rows).to_csv(index=False).encode(), "demo_proteins.fasta": ("\n".join(fasta) + "\n").encode()}


def _neuro_signal_assets(rng: np.random.Generator) -> dict[str, bytes]:
    fs = 128.0
    seconds = 12
    time = np.arange(int(fs * seconds)) / fs
    frame = pd.DataFrame({"time": time})
    for index, frequency in enumerate((6.0, 10.0, 18.0, 24.0)):
        frame[f"channel_{index + 1}"] = np.sin(2 * np.pi * frequency * time) + rng.normal(0, 0.15, len(time))
    events = pd.DataFrame({"event_id": ["EV-001", "EV-002"], "start_seconds": [3.0, 8.0], "label": ["synthetic_marker", "synthetic_marker"]})
    return {"demo_neural_signal.csv": frame.to_csv(index=False).encode(), "demo_event_markers.csv": events.to_csv(index=False).encode()}


def _neuro_clinical_assets(rng: np.random.Generator) -> dict[str, bytes]:
    rows = []
    for subject in range(18):
        slope = rng.normal(0.35, 0.12)
        for month in (0, 6, 12, 18, 24):
            rows.append({"subject_id": f"N-{subject + 1:03d}", "time_months": month, "group": "cohort_A" if subject % 2 else "cohort_B", "cognitive_score": 30 - slope * month / 12 + rng.normal(0, 0.35), "imaging_marker": slope * month / 12 + rng.normal(0, 0.08), "fluid_marker": 1 + slope * 0.4 * month / 12 + rng.normal(0, 0.07)})
    return {"demo_neuro_cohort.csv": pd.DataFrame(rows).to_csv(index=False).encode()}


def _lab_process_assets(rng: np.random.Generator) -> dict[str, bytes]:
    rows = []
    for batch in ("BATCH-A", "BATCH-B"):
        for hour in np.linspace(0, 48, 49):
            biomass = 0.1 * np.exp(0.11 * hour) / (1 + 0.1 * (np.exp(0.11 * hour) - 1))
            rows.append({"batch": batch, "time_hours": hour, "biomass": biomass + rng.normal(0, 0.01), "product": max(0.0, 0.8 * (biomass - 0.1)) + rng.normal(0, 0.01), "ph": 7.0 - 0.009 * hour + rng.normal(0, 0.02), "dissolved_oxygen": 82 - 1.1 * hour + rng.normal(0, 1.5)})
    return {"demo_process_timeseries.csv": pd.DataFrame(rows).to_csv(index=False).encode()}


_BUILDERS = {
    "sequence": _sequence_assets,
    "single_cell": _single_cell_assets,
    "spatial_image": _spatial_assets,
    "omics": _omics_assets,
    "microbiome": _microbiome_assets,
    "compound": _compound_assets,
    "protein": _protein_assets,
    "neuro_signal": _neuro_signal_assets,
    "neuro_clinical": _neuro_clinical_assets,
    "lab_process": _lab_process_assets,
    "tabular": _omics_assets,
}


def build_demo_bundle(page_key: str, title: str, category: str) -> DemoBundle:
    if not page_key.strip() or not title.strip() or not category.strip():
        raise ValueError("Page key, title and category are required.")
    family = demo_family(page_key, title, category)
    rng = np.random.default_rng(_seed(page_key))
    assets = _BUILDERS[family](rng)
    manifest = {
        "schema": "biointel.module-demo.v209.v1",
        "page_key": page_key,
        "title": title,
        "category": category,
        "family": family,
        "source_kind": "deterministic_synthetic_demo_input",
        "generated_at_utc": "deterministic-at-download",
        "clinical_release_eligible": False,
        "scientific_boundary": "These files are synthetic input examples for software testing and format guidance. They are not clinical, patient, experimental or validated reference results.",
        "files": sorted(assets),
    }
    readme = f"""# BioIntel AI — {title} demo input\n\nThis bundle contains **deterministic synthetic input data** for the `{page_key}` module.\n\n- Category: {category}\n- Input family: {family}\n- No patient or confidential data\n- No online result\n- No clinical, regulatory or wet-lab validation claim\n\nUse the files to test upload, validation, visualization and report flows. Replace synthetic rows with appropriately governed project data before scientific use.\n"""
    assets = {**assets, "manifest.json": json.dumps(manifest, indent=2).encode("utf-8"), "README.md": readme.encode("utf-8")}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in sorted(assets.items()):
            archive.writestr(name, content)
    content = buffer.getvalue()
    safe_key = "".join(character if character.isalnum() or character in "-_" else "-" for character in page_key)
    return DemoBundle(
        page_key=page_key,
        title=title,
        category=category,
        family=family,
        archive_name=f"BioIntel-{safe_key}-Synthetic-Demo.zip",
        content=content,
        file_names=tuple(sorted(assets)),
        sha256=hashlib.sha256(content).hexdigest(),
    )


__all__ = ["DemoBundle", "demo_family", "build_demo_bundle"]
