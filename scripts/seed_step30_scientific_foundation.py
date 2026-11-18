from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.assets.research_assets import seed_asset_store
from biointel.data.dataset_registry import list_datasets, register_dataset
from biointel.data.scientific_registry import (
    initialize_scientific_registries,
    register_dataset_file,
    replace_dataset_columns,
    replace_dataset_qc,
    replace_dataset_samples,
    scientific_registry_summary,
    sha256_file,
    utc_now,
)
from biointel.database.core import transaction
from biointel.dti.drug_features import extract_drug_features
from biointel.dti.feature_cache import FeatureCache
from biointel.dti.protein_features import extract_protein_features
from biointel.genomics.annotations import annotation_summary, parse_gff
from biointel.genomics.assembly import assembly_metrics
from biointel.genomics.fastq import fastq_qc, parse_fastq
from biointel.genomics.variants import parse_vcf, variant_summary
from biointel.intelligence.knowledge_warehouse import (
    _upsert_entity,
    _upsert_relation,
    initialize_knowledge_warehouse,
)

RNG = np.random.default_rng(20260704)
DEMO = ROOT / "data" / "bioinformatics_demo"
DEMO.mkdir(parents=True, exist_ok=True)
STRUCTURES = DEMO / "structures"
STRUCTURES.mkdir(parents=True, exist_ok=True)
REPORTS = ROOT / "reports"

DNA = np.array(list("ACGT"))
AMINO = np.array(list("ACDEFGHIKLMNPQRSTVWY"))


def random_dna(length: int, gc: float = 0.5) -> str:
    gc = min(max(gc, 0.05), 0.95)
    probabilities = [(1 - gc) / 2, gc / 2, gc / 2, (1 - gc) / 2]
    return "".join(RNG.choice(DNA, size=length, p=probabilities).tolist())


def random_protein(length: int, hydrophobic_bias: float = 0.0) -> str:
    base = np.ones(len(AMINO), dtype=float)
    for residue in "AILMFWVY":
        base[np.where(AMINO == residue)[0][0]] += hydrophobic_bias
    base /= base.sum()
    return "".join(RNG.choice(AMINO, size=length, p=base).tolist())


def write_fastq() -> dict[str, Any]:
    path = DEMO / "demo_reads.fastq"
    r1 = DEMO / "demo_reads_R1.fastq"
    r2 = DEMO / "demo_reads_R2.fastq"
    adapter = "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"
    templates: list[str] = []
    with (
        path.open("w", encoding="utf-8") as main,
        r1.open("w", encoding="utf-8") as one,
        r2.open("w", encoding="utf-8") as two,
    ):
        for index in range(20_000):
            gc = 0.42 + 0.12 * math.sin(index / 500)
            if templates and index % 53 == 0:
                sequence = templates[index % len(templates)]
            else:
                sequence = random_dna(150, gc)
                if len(templates) < 500:
                    templates.append(sequence)
            if index % 20 == 0:
                sequence = sequence[:120] + adapter[:30]
            quality_values = np.clip(RNG.normal(35, 3, 150), 5, 41).astype(int)
            quality_values[-12:] = np.clip(quality_values[-12:] - RNG.integers(4, 12), 2, 41)
            quality = "".join(chr(int(value) + 33) for value in quality_values)
            header = f"@STEP30_{index + 1:06d}/1 sample=S{index % 24 + 1:02d}"
            record = f"{header}\n{sequence}\n+\n{quality}\n"
            main.write(record)
            one.write(record)
            mate = reverse_complement(sequence)
            mate_quality = quality[::-1]
            two.write(
                f"@STEP30_{index + 1:06d}/2 sample=S{index % 24 + 1:02d}\n{mate}\n+\n{mate_quality}\n"
            )
    records = parse_fastq(path.read_text(encoding="utf-8"))
    qc = fastq_qc(records)
    return {
        "rows": len(records),
        "qc": {
            "reads": qc.reads,
            "bases": qc.bases,
            "mean_quality": qc.mean_quality,
            "q30_percent": qc.q30_percent,
            "mean_gc_percent": qc.mean_gc_percent,
            "duplicate_percent": qc.duplicate_percent,
        },
        "files": [path, r1, r2],
    }


def reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def write_assembly() -> tuple[pd.DataFrame, dict[str, Any]]:
    path = DEMO / "demo_assembly.fasta"
    lengths = np.clip(RNG.lognormal(mean=8.0, sigma=0.75, size=500).astype(int), 500, 30_000)
    rows = []
    sequences = []
    with path.open("w", encoding="utf-8") as handle:
        for index, length in enumerate(sorted(lengths, reverse=True), 1):
            gc = float(RNG.uniform(0.32, 0.68))
            sequence = random_dna(int(length), gc)
            sequences.append(sequence)
            handle.write(f">contig_{index:04d} length={length} gc={gc:.3f}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")
            rows.append(
                {"contig_id": f"contig_{index:04d}", "length": int(length), "gc_fraction": gc}
            )
    metrics = assembly_metrics(sequences)
    return pd.DataFrame(rows), {
        "contigs": metrics.sequences,
        "total_bases": metrics.total_bases,
        "n50": metrics.n50,
        "l50": metrics.l50,
        "n90": metrics.n90,
        "l90": metrics.l90,
    }


def write_vcf() -> tuple[pd.DataFrame, dict[str, Any]]:
    path = DEMO / "demo_variants.vcf"
    chromosomes = [str(i) for i in range(1, 23)] + ["X"]
    genes = [f"GENE{i:04d}" for i in range(1, 2001)]
    samples = [f"SAMPLE_{i:02d}" for i in range(1, 9)]
    lines = [
        "##fileformat=VCFv4.2",
        "##source=BioIntelStep30Reference",
        "##INFO=<ID=DP,Number=1,Type=Integer,Description=Total Depth>",
        "##INFO=<ID=GENE,Number=1,Type=String,Description=Reference gene identifier>",
        "##INFO=<ID=IMPACT,Number=1,Type=String,Description=Reference impact category>",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(samples),
    ]
    position_by_chrom = {chromosome: 1_000 for chromosome in chromosomes}
    impacts = ["LOW", "MODERATE", "HIGH", "MODIFIER"]
    bases = list("ACGT")
    for index in range(5_000):
        chromosome = chromosomes[index % len(chromosomes)]
        position_by_chrom[chromosome] += int(RNG.integers(20, 5_000))
        ref = bases[index % 4]
        if index % 8 == 0:
            alt = ref + random_dna(int(RNG.integers(1, 4)))
        elif index % 11 == 0:
            ref = ref + random_dna(int(RNG.integers(1, 4)))
            alt = ref[0]
        else:
            alt = bases[(index + 1 + int(RNG.integers(0, 3))) % 4]
        quality = float(np.clip(RNG.normal(55, 18), 3, 99))
        filt = "PASS" if quality >= 30 else "LowQual"
        depth = int(RNG.integers(8, 250))
        gene = genes[index % len(genes)]
        impact = impacts[index % len(impacts)]
        genotypes = []
        for sample_index in range(len(samples)):
            genotype = ["0/0", "0/1", "1/1", "./."][(index + sample_index * 3) % 4]
            genotypes.append(f"{genotype}:{max(1, depth + int(RNG.normal(0, 8)))}")
        lines.append(
            f"{chromosome}\t{position_by_chrom[chromosome]}\tREFVAR{index + 1:06d}\t{ref}\t{alt}\t{quality:.2f}\t{filt}\tDP={depth};GENE={gene};IMPACT={impact}\tGT:DP\t"
            + "\t".join(genotypes)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    frame = parse_vcf(path.read_text(encoding="utf-8"))
    summary = variant_summary(frame)
    return frame, {
        "variants": summary.variants,
        "snps": summary.snps,
        "indels": summary.indels,
        "multiallelic": summary.multiallelic,
        "pass_variants": summary.passed,
        "titv_ratio": summary.ts_tv_ratio,
    }


def write_gff() -> tuple[pd.DataFrame, dict[str, Any]]:
    path = DEMO / "demo_annotations.gff3"
    lines = ["##gff-version 3"]
    chromosomes = [f"chr{i}" for i in range(1, 13)]
    cursor = {chromosome: 1_000 for chromosome in chromosomes}
    for index in range(1, 2_001):
        chromosome = chromosomes[(index - 1) % len(chromosomes)]
        start = cursor[chromosome] + int(RNG.integers(500, 3_000))
        gene_length = int(RNG.integers(2_000, 25_000))
        end = start + gene_length - 1
        strand = "+" if index % 2 else "-"
        gene_id = f"gene{index:05d}"
        transcript_id = f"tx{index:05d}.1"
        gene_name = f"GENE{index:04d}"
        lines.append(
            f"{chromosome}\tBioIntelStep30\tgene\t{start}\t{end}\t.\t{strand}\t.\tID={gene_id};Name={gene_name};biotype=protein_coding"
        )
        lines.append(
            f"{chromosome}\tBioIntelStep30\tmRNA\t{start}\t{end}\t.\t{strand}\t.\tID={transcript_id};Parent={gene_id}"
        )
        exon_starts = np.linspace(start, end - 500, 3, dtype=int)
        for exon_number, exon_start in enumerate(exon_starts, 1):
            exon_end = min(end, int(exon_start + RNG.integers(250, 900)))
            lines.append(
                f"{chromosome}\tBioIntelStep30\texon\t{exon_start}\t{exon_end}\t.\t{strand}\t.\tID=exon{index:05d}_{exon_number};Parent={transcript_id}"
            )
            cds_start = exon_start + 10
            cds_end = max(cds_start, exon_end - 10)
            lines.append(
                f"{chromosome}\tBioIntelStep30\tCDS\t{cds_start}\t{cds_end}\t.\t{strand}\t0\tID=cds{index:05d}_{exon_number};Parent={transcript_id}"
            )
        cursor[chromosome] = end
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    frame = parse_gff(path.read_text(encoding="utf-8"))
    summary = annotation_summary(frame)
    return frame, {
        "features": summary.features,
        "genes": summary.genes,
        "transcripts": summary.transcripts,
        "exons": summary.exons,
        "cds": summary.cds,
        "sequence_regions": summary.sequence_regions,
    }


def write_expression() -> tuple[pd.DataFrame, pd.DataFrame]:
    genes = [f"GENE{i:04d}" for i in range(1, 5_001)]
    control = [f"CTRL_{i:02d}" for i in range(1, 13)]
    treated = [f"TREAT_{i:02d}" for i in range(1, 13)]
    samples = control + treated
    baseline = RNG.lognormal(mean=5.0, sigma=1.0, size=len(genes))
    dispersion = 0.18
    values = np.zeros((len(genes), len(samples)), dtype=int)
    for sample_index, sample in enumerate(samples):
        condition_effect = np.ones(len(genes))
        if sample.startswith("TREAT"):
            condition_effect[:250] = 3.0
            condition_effect[250:500] = 0.35
        batch_effect = 1.0 + (0.08 if sample_index % 2 else -0.05)
        mean = np.maximum(0.1, baseline * condition_effect * batch_effect)
        shape = 1 / dispersion
        values[:, sample_index] = RNG.negative_binomial(shape, shape / (shape + mean)).astype(int)
    frame = pd.DataFrame(values, columns=samples)
    frame.insert(0, "gene", genes)
    frame.to_csv(DEMO / "demo_expression_counts.csv", index=False)
    metadata_rows = []
    for index, sample in enumerate(samples, 1):
        metadata_rows.append(
            {
                "sample": sample,
                "condition": "control" if sample.startswith("CTRL") else "treated",
                "batch": f"B{1 + (index - 1) % 3}",
                "biological_replicate": index if index <= 12 else index - 12,
                "organism": "Homo sapiens",
                "tissue": "reference cell culture",
                "sex": "F" if index % 2 else "M",
                "timepoint_hours": 0 if sample.startswith("CTRL") else 24,
            }
        )
    metadata = pd.DataFrame(metadata_rows)
    metadata.to_csv(DEMO / "demo_sample_metadata.csv", index=False)
    annotation = pd.DataFrame(
        {
            "gene": genes,
            "chromosome": [str(1 + index % 22) for index in range(len(genes))],
            "biotype": ["protein_coding" if index % 5 else "lncRNA" for index in range(len(genes))],
            "pathway": [
                ["Cell cycle", "MAPK signalling", "DNA repair", "Metabolism", "Immune signalling"][
                    index % 5
                ]
                for index in range(len(genes))
            ],
            "description": [
                f"Step 30 reference gene feature {index + 1}" for index in range(len(genes))
            ],
        }
    )
    annotation.to_csv(DEMO / "demo_gene_annotation.csv", index=False)
    return frame, metadata


def write_omics() -> tuple[pd.DataFrame, pd.DataFrame]:
    samples = [f"S{i:02d}" for i in range(1, 25)]
    transcript_features = [f"TX_GENE_{i:04d}" for i in range(1, 1_501)]
    protein_features = [f"PROT_{i:04d}" for i in range(1, 1_001)]
    transcript = pd.DataFrame(
        RNG.normal(8, 2, size=(len(samples), len(transcript_features))), columns=transcript_features
    )
    transcript.insert(0, "sample", samples)
    protein = pd.DataFrame(
        RNG.normal(10, 1.5, size=(len(samples), len(protein_features))), columns=protein_features
    )
    protein.insert(0, "sample", samples)
    transcript.to_csv(DEMO / "demo_transcriptomics.csv", index=False)
    protein.to_csv(DEMO / "demo_proteomics.csv", index=False)
    protein_annotation = pd.DataFrame(
        {
            "protein_id": protein_features,
            "gene": [f"GENE{i:04d}" for i in range(1, len(protein_features) + 1)],
            "family": [
                ["Kinase", "GPCR", "Protease", "Transporter", "Transcription factor"][i % 5]
                for i in range(len(protein_features))
            ],
            "molecular_weight_kda": np.round(RNG.uniform(12, 220, len(protein_features)), 3),
            "subcellular_location": [
                ["Cytoplasm", "Nucleus", "Membrane", "Mitochondrion", "Secreted"][i % 5]
                for i in range(len(protein_features))
            ],
        }
    )
    protein_annotation.to_csv(DEMO / "demo_protein_annotation.csv", index=False)
    return transcript, protein


def write_microbiome() -> tuple[pd.DataFrame, pd.DataFrame]:
    taxa = [f"g__ReferenceGenus{i:03d};s__ReferenceSpecies{i:03d}" for i in range(1, 301)]
    samples = [f"MICRO_{i:02d}" for i in range(1, 41)]
    alpha = np.linspace(0.2, 2.0, len(taxa))
    matrix = np.zeros((len(taxa), len(samples)), dtype=int)
    for index, sample in enumerate(samples):
        proportions = RNG.dirichlet(alpha * (1.0 + 0.15 * (index % 4)))
        matrix[:, index] = RNG.multinomial(int(RNG.integers(20_000, 80_000)), proportions)
    frame = pd.DataFrame(matrix, columns=samples)
    frame.insert(0, "taxon", taxa)
    frame.to_csv(DEMO / "demo_taxonomy.csv", index=False)
    metadata = pd.DataFrame(
        {
            "sample": samples,
            "condition": ["control" if i < 20 else "treated" for i in range(40)],
            "batch": [f"MB{1 + i % 4}" for i in range(40)],
            "body_site": ["gut" if i % 3 else "oral" for i in range(40)],
            "sequencing_depth": matrix.sum(axis=0),
        }
    )
    metadata.to_csv(DEMO / "demo_microbiome_metadata.csv", index=False)
    return frame, metadata


def write_wetlab() -> dict[str, pd.DataFrame]:
    qpcr_rows = []
    for condition, base_target in (
        ("CTRL", 25.0),
        ("TREAT_A", 22.2),
        ("TREAT_B", 27.0),
        ("RESCUE", 23.5),
    ):
        for biological in range(1, 9):
            for technical in range(1, 4):
                name = (
                    "CTRL"
                    if condition == "CTRL" and biological == 1 and technical == 1
                    else f"{condition}_B{biological}_T{technical}"
                )
                reference = float(RNG.normal(20.0, 0.22))
                qpcr_rows.append(
                    {
                        "sample": name,
                        "condition": condition,
                        "biological_replicate": biological,
                        "technical_replicate": technical,
                        "target_ct": round(float(RNG.normal(base_target, 0.28)), 3),
                        "reference_ct": round(reference, 3),
                        "amplification_efficiency": round(float(RNG.normal(0.96, 0.015)), 4),
                    }
                )
    qpcr = pd.DataFrame(qpcr_rows)
    qpcr.to_csv(DEMO / "demo_qpcr.csv", index=False)

    concentrations = np.array([0.25, 0.5, 1, 2, 5, 10, 25, 50], dtype=float)
    elisa_rows = []
    for concentration in concentrations:
        for replicate in range(1, 4):
            absorbance = 0.08 + 2.25 / (1 + (6.0 / concentration) ** 1.15) + RNG.normal(0, 0.025)
            elisa_rows.append(
                {
                    "type": "standard",
                    "name": f"STD_{concentration:g}_R{replicate}",
                    "concentration": concentration,
                    "absorbance": round(float(absorbance), 5),
                    "replicate": replicate,
                }
            )
    for unknown_index in range(1, 73):
        concentration = float(RNG.lognormal(mean=1.5, sigma=0.9))
        absorbance = (
            0.08 + 2.25 / (1 + (6.0 / max(concentration, 0.01)) ** 1.15) + RNG.normal(0, 0.03)
        )
        elisa_rows.append(
            {
                "type": "unknown",
                "name": f"UNKNOWN_{unknown_index:03d}",
                "concentration": np.nan,
                "absorbance": round(float(absorbance), 5),
                "replicate": 1 + (unknown_index - 1) % 3,
            }
        )
    elisa = pd.DataFrame(elisa_rows)
    elisa.to_csv(DEMO / "demo_elisa.csv", index=False)

    enzyme_rows = []
    for inhibitor, km, vmax in (
        ("none", 1.2, 100.0),
        ("competitive_low", 2.4, 98.0),
        ("competitive_high", 4.8, 95.0),
    ):
        for substrate in (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10):
            for replicate in range(1, 4):
                velocity = vmax * substrate / (km + substrate) + RNG.normal(0, 1.8)
                enzyme_rows.append(
                    {
                        "inhibitor_condition": inhibitor,
                        "substrate_mM": substrate,
                        "velocity": max(0.0, round(float(velocity), 4)),
                        "replicate": replicate,
                    }
                )
    enzyme = pd.DataFrame(enzyme_rows)
    enzyme.to_csv(DEMO / "demo_enzyme_kinetics.csv", index=False)

    times = np.linspace(0, 72, 241)
    biomass = 0.15 + 8.5 / (1 + np.exp(-0.18 * (times - 22)))
    substrate = np.maximum(0.5, 35 - biomass * 3.4 - 0.03 * times)
    product = np.maximum(0.05, 1.8 * biomass - 0.4 + RNG.normal(0, 0.08, len(times)))
    bioprocess = pd.DataFrame(
        {
            "time": np.round(times, 3),
            "biomass": np.round(biomass, 5),
            "substrate": np.round(substrate, 5),
            "product": np.round(product, 5),
            "ph": np.round(
                7.0 - 0.7 * (1 - np.exp(-times / 30)) + RNG.normal(0, 0.015, len(times)), 4
            ),
            "dissolved_oxygen_percent": np.round(
                np.clip(92 - biomass * 8 + RNG.normal(0, 1.5, len(times)), 8, 100), 3
            ),
            "temperature_c": np.round(37 + RNG.normal(0, 0.08, len(times)), 3),
            "agitation_rpm": np.round(250 + 35 * np.sin(times / 8), 2),
            "feed_rate_ml_h": np.round(np.where(times > 24, 2.0 + 0.04 * (times - 24), 0), 4),
        }
    )
    bioprocess.to_csv(DEMO / "demo_bioprocess.csv", index=False)
    return {"qpcr": qpcr, "elisa": elisa, "enzyme": enzyme, "bioprocess": bioprocess}


def write_protein_panel() -> pd.DataFrame:
    path = DEMO / "demo_protein.fasta"
    panel_path = DEMO / "demo_protein_panel.fasta"
    rows = []
    with panel_path.open("w", encoding="utf-8") as handle:
        for index in range(1, 201):
            family = ["Kinase", "GPCR", "Protease", "Transporter", "Transcription_factor"][
                index % 5
            ]
            length = int(RNG.integers(120, 900))
            hydrophobic = 1.4 if family in {"GPCR", "Transporter"} else 0.15
            sequence = random_protein(length, hydrophobic)
            if family == "Kinase" and length > 80:
                sequence = sequence[:35] + "VAIK" + sequence[39:70] + "HRD" + sequence[73:]
            if family == "Protease" and length > 80:
                sequence = sequence[:25] + "GDSGG" + sequence[30:]
            handle.write(f">REFPROT{index:04d} family={family} length={length}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")
            rows.append(
                {
                    "protein_id": f"REFPROT{index:04d}",
                    "family": family,
                    "length": length,
                    "sequence": sequence,
                }
            )
    path.write_text(panel_path.read_text(encoding="utf-8"), encoding="utf-8")
    return pd.DataFrame(rows)


def write_alignment() -> pd.DataFrame:
    reference = random_dna(600, 0.51)
    rows = []
    with (DEMO / "demo_alignment.fasta").open("w", encoding="utf-8") as handle:
        for index in range(1, 51):
            sequence = list(reference)
            mutation_count = 2 + index // 3
            for position in RNG.choice(len(sequence), size=mutation_count, replace=False):
                sequence[position] = str(RNG.choice(DNA[DNA != sequence[position]]))
            if index % 9 == 0:
                for position in RNG.choice(len(sequence), size=3, replace=False):
                    sequence[position] = "-"
            sequence_text = "".join(sequence)
            handle.write(f">taxon_{index:02d} clade={1 + (index - 1) // 10}\n{sequence_text}\n")
            rows.append(
                {
                    "taxon": f"taxon_{index:02d}",
                    "clade": 1 + (index - 1) // 10,
                    "aligned_length": len(sequence_text),
                }
            )
    return pd.DataFrame(rows)


def write_structures() -> pd.DataFrame:
    catalog = []
    for structure_index in range(1, 13):
        lines = [f"HEADER    STEP30 REFERENCE STRUCTURE {structure_index:02d}"]
        atom_id = 1
        for residue_index in range(1, 121):
            angle = residue_index * 0.35
            x = 12 * math.cos(angle)
            y = 12 * math.sin(angle)
            z = residue_index * 0.45
            residue = ["ALA", "GLY", "SER", "LEU", "ASP", "LYS"][residue_index % 6]
            for atom_name, dx, dy, dz, element in (
                ("N", -0.5, 0, 0, "N"),
                ("CA", 0, 0, 0, "C"),
                ("C", 0.6, 0.2, 0.1, "C"),
                ("O", 0.9, 0.3, 0.1, "O"),
            ):
                lines.append(
                    f"ATOM  {atom_id:5d} {atom_name:^4s} {residue:>3s} A{residue_index:4d}    {x + dx:8.3f}{y + dy:8.3f}{z + dz:8.3f}  1.00 20.00          {element:>2s}"
                )
                atom_id += 1
        ligand = "LIG"
        contact_residue = 55
        contact_angle = contact_residue * 0.35
        ligand_x = 12 * math.cos(contact_angle) + 2.0
        ligand_y = 12 * math.sin(contact_angle) + 1.0
        ligand_z = contact_residue * 0.45 + 1.0
        for ligand_atom, (dx, dy, dz, element) in enumerate(
            ((0, 0, 0, "C"), (1.2, 0, 0, "O"), (0, 1.2, 0, "N"), (0, 0, 1.2, "C")), 1
        ):
            lines.append(
                f"HETATM{atom_id:5d} C{ligand_atom:<3d} {ligand:>3s} B   1    {ligand_x + dx:8.3f}{ligand_y + dy:8.3f}{ligand_z + dz:8.3f}  1.00 15.00           {element:>2s}"
            )
            atom_id += 1
        lines.extend(["TER", "END"])
        path = STRUCTURES / f"reference_complex_{structure_index:02d}.pdb"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        catalog.append(
            {
                "structure_id": f"REFPDB{structure_index:02d}",
                "relative_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "protein_residues": 120,
                "ligand": ligand,
                "atoms": atom_id - 1,
            }
        )
    (DEMO / "demo_structure.pdb").write_text(
        (STRUCTURES / "reference_complex_01.pdb").read_text(encoding="utf-8"), encoding="utf-8"
    )
    frame = pd.DataFrame(catalog)
    frame.to_csv(DEMO / "demo_structure_catalog.csv", index=False)
    return frame


def register_frame_dataset(
    frame: pd.DataFrame,
    *,
    name: str,
    domain: str,
    relative_path: str,
    task_type: str = "unlabelled",
    qc: list[dict[str, Any]] | None = None,
    samples: list[dict[str, Any]] | None = None,
    semantic_roles: dict[str, tuple[str, str | None]] | None = None,
) -> str:
    registry = REPORTS / "datasets.sqlite3"
    record = register_dataset(
        registry,
        frame,
        name,
        "2.0",
        task_type,
        "BioIntel Step 30 scaled scientific reference dataset",
        notes="REFERENCE/SIMULATION ONLY — use real experimental data for scientific conclusions.",
        metadata={
            "synthetic": True,
            "demo_only": True,
            "reference_scale": True,
            "domain": domain,
            "source_file": relative_path,
            "step": 30,
            "scientific_release_eligible": False,
        },
    )
    register_dataset_file(
        ROOT, dataset_sha256=record.dataset_sha256, relative_path=relative_path, role="primary_data"
    )
    columns = []
    semantic_roles = semantic_roles or {}
    for position, column in enumerate(frame.columns, 1):
        role, unit = semantic_roles.get(str(column), ("feature", None))
        columns.append(
            {
                "column_name": str(column),
                "ordinal_position": position,
                "data_type": str(frame[column].dtype),
                "semantic_role": role,
                "unit": unit,
                "description": f"Step 30 {domain} field",
                "nullable": bool(frame[column].isna().any()),
            }
        )
    replace_dataset_columns(ROOT, record.dataset_sha256, columns)
    if qc:
        replace_dataset_qc(ROOT, record.dataset_sha256, qc)
    if samples:
        replace_dataset_samples(ROOT, record.dataset_sha256, samples)
    return record.dataset_sha256


def seed_datasets(generated: dict[str, Any]) -> dict[str, str]:
    registry = REPORTS / "datasets.sqlite3"
    with sqlite3.connect(registry) as connection:
        rows = connection.execute("SELECT dataset_sha256, metadata_json FROM datasets").fetchall()
        old = []
        for dataset_hash, metadata_json in rows:
            try:
                metadata = json.loads(metadata_json)
            except Exception:
                metadata = {}
            if metadata.get("step") == 29:
                old.append((dataset_hash,))
        connection.executemany("DELETE FROM datasets WHERE dataset_sha256=?", old)
        connection.commit()

    hashes: dict[str, str] = {}
    fastq_rows = pd.DataFrame(
        {
            "read_id": [f"STEP30_{i:06d}" for i in range(1, generated["fastq"]["rows"] + 1)],
            "sample": [f"S{i % 24 + 1:02d}" for i in range(generated["fastq"]["rows"])],
            "read_length": 150,
        }
    )
    hashes["fastq"] = register_frame_dataset(
        fastq_rows,
        name="Step30 FASTQ read manifest",
        domain="genomics",
        relative_path="data/bioinformatics_demo/demo_reads.fastq",
        qc=[
            {"metric_name": key, "metric_value": value, "unit": None}
            for key, value in generated["fastq"]["qc"].items()
        ],
        samples=[
            {
                "sample_id": f"S{i:02d}",
                "sample_name": f"S{i:02d}",
                "organism": "Homo sapiens",
                "tissue_or_matrix": "reference DNA library",
                "condition_name": "control" if i <= 12 else "treated",
                "batch_name": f"SEQ{1 + (i - 1) % 3}",
                "replicate_type": "biological",
                "replicate_number": 1 + (i - 1) % 12,
            }
            for i in range(1, 25)
        ],
        semantic_roles={
            "read_id": ("identifier", None),
            "sample": ("sample_id", None),
            "read_length": ("quality_metric", "bp"),
        },
    )
    hashes["assembly"] = register_frame_dataset(
        generated["assembly_frame"],
        name="Step30 genome assembly contigs",
        domain="genomics",
        relative_path="data/bioinformatics_demo/demo_assembly.fasta",
        qc=[
            {
                "metric_name": key,
                "metric_value": value,
                "unit": "bp" if key in {"total_bases", "n50", "n90"} else None,
            }
            for key, value in generated["assembly_metrics"].items()
        ],
        semantic_roles={
            "contig_id": ("identifier", None),
            "length": ("measurement", "bp"),
            "gc_fraction": ("quality_metric", "fraction"),
        },
    )
    hashes["variants"] = register_frame_dataset(
        generated["vcf_frame"],
        name="Step30 variant cohort",
        domain="genomics",
        relative_path="data/bioinformatics_demo/demo_variants.vcf",
        qc=[
            {"metric_name": key, "metric_value": value, "unit": None}
            for key, value in generated["vcf_metrics"].items()
            if isinstance(value, (int, float))
        ],
    )
    hashes["annotations"] = register_frame_dataset(
        generated["gff_frame"],
        name="Step30 genome annotation",
        domain="genomics",
        relative_path="data/bioinformatics_demo/demo_annotations.gff3",
        qc=[
            {"metric_name": key, "metric_value": value, "unit": None}
            for key, value in generated["gff_metrics"].items()
            if isinstance(value, (int, float))
        ],
    )
    expression_samples = [
        {
            "sample_id": row["sample"],
            "sample_name": row["sample"],
            "organism": row["organism"],
            "tissue_or_matrix": row["tissue"],
            "condition_name": row["condition"],
            "batch_name": row["batch"],
            "replicate_type": "biological",
            "replicate_number": int(row["biological_replicate"]),
            "subject_id": f"SUBJ_{int(row['biological_replicate']):02d}",
            "timepoint": str(row["timepoint_hours"]),
            "metadata": {"sex": row["sex"]},
        }
        for _, row in generated["sample_metadata"].iterrows()
    ]
    hashes["expression"] = register_frame_dataset(
        generated["expression"],
        name="Step30 RNA-seq count matrix",
        domain="transcriptomics",
        relative_path="data/bioinformatics_demo/demo_expression_counts.csv",
        qc=[
            {"metric_name": "genes", "metric_value": len(generated["expression"]), "unit": "genes"},
            {
                "metric_name": "samples",
                "metric_value": len(generated["expression"].columns) - 1,
                "unit": "samples",
            },
            {
                "metric_name": "zero_fraction",
                "metric_value": float((generated["expression"].iloc[:, 1:] == 0).to_numpy().mean()),
                "unit": "fraction",
            },
            {
                "metric_name": "median_library_size",
                "metric_value": float(generated["expression"].iloc[:, 1:].sum().median()),
                "unit": "counts",
            },
        ],
        samples=expression_samples,
        semantic_roles={"gene": ("feature_id", None)},
    )
    hashes["sample_metadata"] = register_frame_dataset(
        generated["sample_metadata"],
        name="Step30 omics sample metadata",
        domain="multi-omics",
        relative_path="data/bioinformatics_demo/demo_sample_metadata.csv",
        semantic_roles={
            "sample": ("sample_id", None),
            "condition": ("group", None),
            "batch": ("batch", None),
        },
    )
    hashes["gene_annotation"] = register_frame_dataset(
        pd.read_csv(DEMO / "demo_gene_annotation.csv"),
        name="Step30 gene annotation table",
        domain="genomics",
        relative_path="data/bioinformatics_demo/demo_gene_annotation.csv",
    )
    hashes["transcriptomics"] = register_frame_dataset(
        generated["transcriptomics"],
        name="Step30 normalized transcriptomics matrix",
        domain="multi-omics",
        relative_path="data/bioinformatics_demo/demo_transcriptomics.csv",
        samples=expression_samples,
        semantic_roles={"sample": ("sample_id", None)},
    )
    hashes["proteomics"] = register_frame_dataset(
        generated["proteomics"],
        name="Step30 proteomics abundance matrix",
        domain="proteomics",
        relative_path="data/bioinformatics_demo/demo_proteomics.csv",
        samples=expression_samples,
        semantic_roles={"sample": ("sample_id", None)},
    )
    hashes["protein_annotation"] = register_frame_dataset(
        pd.read_csv(DEMO / "demo_protein_annotation.csv"),
        name="Step30 protein annotation table",
        domain="proteomics",
        relative_path="data/bioinformatics_demo/demo_protein_annotation.csv",
    )
    microbiome_samples = [
        {
            "sample_id": row["sample"],
            "sample_name": row["sample"],
            "organism": "microbial community",
            "tissue_or_matrix": row["body_site"],
            "condition_name": row["condition"],
            "batch_name": row["batch"],
            "replicate_type": "biological",
            "replicate_number": index + 1,
        }
        for index, (_, row) in enumerate(generated["microbiome_metadata"].iterrows())
    ]
    hashes["microbiome"] = register_frame_dataset(
        generated["microbiome"],
        name="Step30 microbiome abundance matrix",
        domain="microbiology",
        relative_path="data/bioinformatics_demo/demo_taxonomy.csv",
        qc=[
            {"metric_name": "taxa", "metric_value": len(generated["microbiome"]), "unit": "taxa"},
            {
                "metric_name": "samples",
                "metric_value": len(generated["microbiome"].columns) - 1,
                "unit": "samples",
            },
            {
                "metric_name": "median_sequencing_depth",
                "metric_value": float(generated["microbiome"].iloc[:, 1:].sum().median()),
                "unit": "reads",
            },
        ],
        samples=microbiome_samples,
        semantic_roles={"taxon": ("feature_id", None)},
    )
    hashes["microbiome_metadata"] = register_frame_dataset(
        generated["microbiome_metadata"],
        name="Step30 microbiome sample metadata",
        domain="microbiology",
        relative_path="data/bioinformatics_demo/demo_microbiome_metadata.csv",
        semantic_roles={
            "sample": ("sample_id", None),
            "condition": ("group", None),
            "batch": ("batch", None),
        },
    )
    for key, filename, name in (
        ("qpcr", "demo_qpcr.csv", "Step30 qPCR 96-well study"),
        ("elisa", "demo_elisa.csv", "Step30 ELISA plate study"),
        ("enzyme", "demo_enzyme_kinetics.csv", "Step30 enzyme kinetics replicates"),
        ("bioprocess", "demo_bioprocess.csv", "Step30 bioprocess sensor time series"),
    ):
        hashes[key] = register_frame_dataset(
            generated["wetlab"][key],
            name=name,
            domain="biotechnology",
            relative_path=f"data/bioinformatics_demo/{filename}",
        )
    hashes["protein_panel"] = register_frame_dataset(
        generated["protein_panel"],
        name="Step30 protein family panel",
        domain="proteomics",
        relative_path="data/bioinformatics_demo/demo_protein_panel.fasta",
        semantic_roles={
            "protein_id": ("identifier", None),
            "family": ("group", None),
            "length": ("measurement", "aa"),
            "sequence": ("sequence", None),
        },
    )
    hashes["alignment"] = register_frame_dataset(
        generated["alignment"],
        name="Step30 phylogenetic alignment panel",
        domain="phylogeny",
        relative_path="data/bioinformatics_demo/demo_alignment.fasta",
    )
    hashes["structures"] = register_frame_dataset(
        generated["structures"],
        name="Step30 protein-ligand structure panel",
        domain="structural_bioinformatics",
        relative_path="data/bioinformatics_demo/demo_structure_catalog.csv",
    )

    with transaction(registry) as connection:
        connection.execute("DELETE FROM dataset_links WHERE relation_type LIKE 'step30_%'")
        links = [
            ("expression", "sample_metadata", "step30_has_sample_metadata"),
            ("transcriptomics", "proteomics", "step30_integrates_with"),
            ("microbiome", "microbiome_metadata", "step30_has_sample_metadata"),
            ("protein_panel", "structures", "step30_structure_subset"),
            ("variants", "annotations", "step30_annotated_by"),
        ]
        for source, target, relation in links:
            link_id = hashlib.sha256(
                f"{hashes[source]}|{hashes[target]}|{relation}".encode()
            ).hexdigest()[:32]
            connection.execute(
                "INSERT OR REPLACE INTO dataset_links(link_id,source_dataset_sha256,target_dataset_sha256,relation_type,description,metadata_json,created_at_utc) VALUES (?,?,?,?,?,?,?)",
                (
                    link_id,
                    hashes[source],
                    hashes[target],
                    relation,
                    "Step 30 scientific dataset linkage",
                    "{}",
                    utc_now(),
                ),
            )
    return hashes


def seed_experiment_depth() -> dict[str, int]:
    path = REPORTS / "experiments.sqlite3"
    initialize_scientific_registries(ROOT)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        experiments = connection.execute(
            "SELECT * FROM experiments ORDER BY experiment_id"
        ).fetchall()
        connection.execute("DELETE FROM experiment_folds")
        connection.execute("DELETE FROM hyperparameter_trials")
        connection.execute("DELETE FROM experiment_runtime_metrics")
        connection.execute("DELETE FROM experiment_events")
        for experiment_index, experiment in enumerate(experiments, 1):
            metrics = json.loads(experiment["metrics_json"])
            validation = json.loads(experiment["validation_metrics_json"])
            base_metric = next(
                (float(value) for value in metrics.values() if isinstance(value, (int, float))), 0.7
            )
            for fold in range(1, 6):
                variation = float(RNG.normal(0, 0.015))
                fold_metrics = {
                    key: float(value) + variation
                    for key, value in metrics.items()
                    if isinstance(value, (int, float))
                }
                validation_metrics = {
                    key: float(value) + variation / 2
                    for key, value in validation.items()
                    if isinstance(value, (int, float))
                }
                connection.execute(
                    "INSERT INTO experiment_folds VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        experiment["experiment_id"],
                        fold,
                        int(experiment["train_rows"] * 0.8),
                        int(experiment["validation_rows"]),
                        int(experiment["test_rows"]),
                        json.dumps(fold_metrics, sort_keys=True),
                        json.dumps(validation_metrics, sort_keys=True),
                        json.dumps({"reference_only": True, "fold_seed": 4200 + fold}),
                        utc_now(),
                    ),
                )
            for trial in range(1, 11):
                objective = base_metric + float(RNG.normal(0, 0.025))
                parameters = {
                    "trial_reference": trial,
                    "max_depth": int(4 + trial % 8),
                    "regularization": round(float(10 ** RNG.uniform(-5, -1)), 7),
                    "feature_fraction": round(float(RNG.uniform(0.55, 1.0)), 4),
                }
                trial_id = hashlib.sha256(
                    f"{experiment['experiment_id']}|{trial}".encode()
                ).hexdigest()[:32]
                connection.execute(
                    "INSERT INTO hyperparameter_trials VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        trial_id,
                        experiment["experiment_id"],
                        trial,
                        json.dumps(parameters, sort_keys=True),
                        "reference_objective",
                        objective,
                        "complete",
                        round(float(RNG.uniform(4, 90)), 3),
                        json.dumps({"synthetic_demo": True}),
                        utc_now(),
                    ),
                )
            for metric_name, value, unit in (
                ("training_seconds", float(RNG.uniform(5, 240)), "seconds"),
                ("peak_memory_mb", float(RNG.uniform(150, 1800)), "MB"),
                ("prediction_rows_per_second", float(RNG.uniform(120, 1600)), "rows/second"),
            ):
                connection.execute(
                    "INSERT INTO experiment_runtime_metrics VALUES (?,?,?,?,?,?)",
                    (
                        experiment["experiment_id"],
                        metric_name,
                        value,
                        unit,
                        "reference_local_cpu",
                        utc_now(),
                    ),
                )
            for event_number, event_type in enumerate(
                (
                    "dataset_frozen",
                    "split_created",
                    "training_completed",
                    "validation_completed",
                    "artifact_registered",
                ),
                1,
            ):
                event_id = hashlib.sha256(
                    f"{experiment['experiment_id']}|{event_type}".encode()
                ).hexdigest()[:32]
                connection.execute(
                    "INSERT INTO experiment_events VALUES (?,?,?,?,?,?)",
                    (
                        event_id,
                        experiment["experiment_id"],
                        event_type,
                        f"Reference experiment event {event_number}",
                        json.dumps({"synthetic_demo": True}),
                        utc_now(),
                    ),
                )
        connection.commit()
    return {
        "experiments": len(experiments),
        "folds": len(experiments) * 5,
        "trials": len(experiments) * 10,
    }


def seed_evidence_depth() -> dict[str, int]:
    path = REPORTS / "evidence.sqlite3"
    initialize_scientific_registries(ROOT)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        links = connection.execute(
            "SELECT * FROM dataset_evidence_links ORDER BY evidence_key"
        ).fetchall()
        connection.execute("DROP TABLE IF EXISTS evidence_assay_context")
        connection.execute("""
            CREATE TABLE evidence_assay_context (
                evidence_key TEXT NOT NULL, dataset_sha256 TEXT NOT NULL,
                assay_format TEXT, assay_system TEXT, organism TEXT,
                tissue_or_cell_line TEXT, protein_construct TEXT, substrate TEXT,
                temperature_c REAL, ph REAL, incubation_minutes REAL, cofactors TEXT,
                context_quality REAL NOT NULL DEFAULT 0.0, metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL, PRIMARY KEY(dataset_sha256,evidence_key)
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_assay_context_dataset ON evidence_assay_context(dataset_sha256)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_assay_context_system ON evidence_assay_context(assay_system)"
        )
        connection.execute("DELETE FROM evidence_replicates")
        connection.execute("DELETE FROM evidence_source_releases")
        formats = [
            "biochemical_binding",
            "cellular_response",
            "enzyme_inhibition",
            "reporter_assay",
        ]
        systems = [
            "purified_protein",
            "human_cell_line",
            "membrane_preparation",
            "recombinant_enzyme",
        ]
        cell_lines = ["HEK293", "CHO-K1", "HepG2", "Jurkat", "A549", "reference buffer"]
        for index, link in enumerate(links, 1):
            value_seed = int(link["evidence_key"][:8], 16)
            base_value = float(10 ** (1 + (value_seed % 500) / 125))
            context_quality = round(0.55 + 0.4 * ((index % 10) / 9), 4)
            connection.execute(
                """
                INSERT INTO evidence_assay_context(
                    evidence_key,dataset_sha256,assay_format,assay_system,organism,
                    tissue_or_cell_line,protein_construct,substrate,temperature_c,ph,
                    incubation_minutes,cofactors,context_quality,metadata_json,created_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    link["evidence_key"],
                    link["dataset_sha256"],
                    formats[index % len(formats)],
                    systems[index % len(systems)],
                    "Homo sapiens",
                    cell_lines[index % len(cell_lines)],
                    f"Reference construct {1 + index % 12}",
                    f"Reference substrate {1 + index % 8}",
                    25.0 if index % 3 else 37.0,
                    7.4 if index % 4 else 6.8,
                    float(15 + (index % 8) * 15),
                    "Mg2+" if index % 2 else "ATP,Mg2+",
                    context_quality,
                    json.dumps({"demo_only": True, "source_link_id": link["link_id"]}),
                    utc_now(),
                ),
            )
            for replicate in range(1, 4):
                measured = max(0.0001, base_value * float(RNG.lognormal(0, 0.08)))
                replicate_id = hashlib.sha256(
                    f"{link['dataset_sha256']}|{link['evidence_key']}|{replicate}".encode()
                ).hexdigest()[:32]
                connection.execute(
                    "INSERT INTO evidence_replicates VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        replicate_id,
                        link["evidence_key"],
                        link["dataset_sha256"],
                        replicate,
                        1,
                        measured,
                        "nM",
                        "=",
                        "accepted" if replicate < 3 or index % 11 else "review",
                        json.dumps({"demo_only": True}),
                        utc_now(),
                    ),
                )
        source_profiles = [
            ("chembl", "connector-current", "ready_for_import", "CHEMBL_TERMS", "monthly"),
            ("bindingdb", "connector-current", "ready_for_import", "BINDINGDB_TERMS", "monthly"),
            (
                "pubchem_bioassay",
                "connector-current",
                "ready_for_import",
                "PUBCHEM_PUBLIC_DATA",
                "weekly",
            ),
            ("uniprot", "connector-current", "ready_for_import", "UNIPROT_TERMS", "monthly"),
            ("geo", "connector-profile", "not_downloaded", None, "on_demand"),
            ("clinvar", "connector-profile", "not_downloaded", None, "monthly"),
            ("reactome", "connector-profile", "not_downloaded", None, "quarterly"),
            ("interpro", "connector-profile", "not_downloaded", None, "quarterly"),
            ("alphafold_db", "connector-profile", "not_downloaded", None, "on_demand"),
            ("rcsb_pdb", "connector-profile", "ready_for_import", None, "weekly"),
        ]
        for provider, release_label, status, licence, cadence in source_profiles:
            release_id = hashlib.sha256(f"{provider}|{release_label}".encode()).hexdigest()[:32]
            connection.execute(
                "INSERT INTO evidence_source_releases VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    release_id,
                    provider,
                    release_label,
                    None,
                    status,
                    0,
                    None,
                    licence,
                    cadence,
                    "Connector profile only; no external records are represented as downloaded.",
                    json.dumps({"demo_only": True}),
                    utc_now(),
                ),
            )
        connection.commit()
    return {"contexts": len(links), "replicates": len(links) * 3, "source_releases": 10}


def seed_source_catalog() -> int:
    path = REPORTS / "internet_downloads.sqlite3"
    initialize_scientific_registries(ROOT)
    profiles = [
        (
            "chembl",
            "ChEMBL",
            "bioactivity",
            "www.ebi.ac.uk",
            "REST/bulk",
            "CHEMBL_TERMS",
            "monthly",
            "connector_ready",
        ),
        (
            "bindingdb",
            "BindingDB",
            "binding_affinity",
            "www.bindingdb.org",
            "bulk_tsv",
            "BINDINGDB_TERMS",
            "monthly",
            "connector_ready",
        ),
        (
            "pubchem",
            "PubChem",
            "compound_and_bioassay",
            "pubchem.ncbi.nlm.nih.gov",
            "PUG_REST",
            "PUBCHEM_PUBLIC_DATA",
            "weekly",
            "connector_ready",
        ),
        (
            "uniprot",
            "UniProt",
            "protein_sequence",
            "rest.uniprot.org",
            "REST",
            "UNIPROT_TERMS",
            "monthly",
            "connector_ready",
        ),
        (
            "rcsb",
            "RCSB PDB",
            "protein_structure",
            "files.rcsb.org",
            "REST/download",
            "public_data_terms",
            "weekly",
            "connector_ready",
        ),
        (
            "geo",
            "NCBI GEO",
            "gene_expression",
            "www.ncbi.nlm.nih.gov",
            "Entrez/download",
            "verify_terms",
            "on_demand",
            "profile_only",
        ),
        (
            "sra",
            "NCBI SRA",
            "sequencing_reads",
            "www.ncbi.nlm.nih.gov",
            "metadata/Toolkit",
            "verify_terms",
            "on_demand",
            "profile_only",
        ),
        (
            "clinvar",
            "ClinVar",
            "clinical_variants",
            "www.ncbi.nlm.nih.gov",
            "VCF/download",
            "public_data_terms",
            "monthly",
            "profile_only",
        ),
        (
            "ensembl",
            "Ensembl",
            "genome_annotation",
            "rest.ensembl.org",
            "REST/FTP",
            "verify_terms",
            "quarterly",
            "profile_only",
        ),
        (
            "reactome",
            "Reactome",
            "pathways",
            "reactome.org",
            "REST/download",
            "verify_terms",
            "quarterly",
            "profile_only",
        ),
        (
            "interpro",
            "InterPro",
            "protein_domains",
            "www.ebi.ac.uk",
            "REST/download",
            "verify_terms",
            "quarterly",
            "profile_only",
        ),
        (
            "alphafold",
            "AlphaFold DB",
            "predicted_structures",
            "alphafold.ebi.ac.uk",
            "REST/download",
            "verify_terms",
            "on_demand",
            "profile_only",
        ),
        (
            "string",
            "STRING",
            "protein_interactions",
            "string-db.org",
            "REST/download",
            "verify_terms",
            "quarterly",
            "profile_only",
        ),
        (
            "go",
            "Gene Ontology",
            "ontology",
            "geneontology.org",
            "download",
            "verify_terms",
            "monthly",
            "profile_only",
        ),
        (
            "gnomad",
            "gnomAD",
            "population_variants",
            "gnomad.broadinstitute.org",
            "download/API",
            "verify_terms",
            "release_based",
            "profile_only",
        ),
    ]
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM scientific_source_catalog")
        connection.executemany(
            "INSERT INTO scientific_source_catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    key,
                    provider,
                    resource_type,
                    host,
                    access_method,
                    licence,
                    cadence,
                    status,
                    None,
                    None,
                    "Connector catalogue. No remote data is bundled unless separately registered.",
                    json.dumps({"step": 30, "demo_only": False}),
                )
                for key, provider, resource_type, host, access_method, licence, cadence, status in profiles
            ],
        )
        connection.commit()
    return len(profiles)


def seed_feature_cache() -> dict[str, int]:
    cache = FeatureCache(REPORTS / "feature_cache.sqlite3")
    molecules = pd.read_csv(ROOT / "data" / "libraries" / "molecule_library_1000_5x.csv")
    proteins = pd.read_csv(ROOT / "data" / "libraries" / "protein_library_160.csv")
    successful_drugs = 0
    for smiles in molecules["canonical_smiles"].astype(str).head(1000):
        try:
            cache.put_drug(
                smiles, extract_drug_features(smiles, radius=2, n_bits=256, use_chirality=True)
            )
            successful_drugs += 1
        except Exception:
            continue
    successful_proteins = 0
    for sequence in proteins["protein_sequence"].astype(str):
        try:
            cache.put_protein(
                sequence, extract_protein_features(sequence, include_dipeptides=False)
            )
            successful_proteins += 1
        except Exception:
            continue
    stats = cache.stats()
    return {
        "new_drugs_processed": successful_drugs,
        "new_proteins_processed": successful_proteins,
        "entries": stats.entries,
        "drug_entries": stats.drug_entries,
        "protein_entries": stats.protein_entries,
    }


def seed_knowledge_diversity() -> dict[str, int]:
    path = REPORTS / "knowledge.sqlite3"
    initialize_knowledge_warehouse(path)
    genes = [
        "TP53",
        "BRCA1",
        "BRCA2",
        "EGFR",
        "KRAS",
        "NRAS",
        "BRAF",
        "PIK3CA",
        "PTEN",
        "AKT1",
        "MTOR",
        "MYC",
        "RB1",
        "APC",
        "CTNNB1",
        "CDKN2A",
        "ATM",
        "ATR",
        "CHEK1",
        "CHEK2",
        "PALB2",
        "RAD51",
        "ERBB2",
        "MET",
        "ALK",
        "RET",
        "ROS1",
        "NTRK1",
        "NTRK2",
        "NTRK3",
        "JAK1",
        "JAK2",
        "STAT3",
        "STAT5A",
        "MAPK1",
        "MAPK3",
        "MAP2K1",
        "MAP2K2",
        "CDK4",
        "CDK6",
        "CCND1",
        "CDK2",
        "CDK1",
        "VEGFA",
        "KDR",
        "FLT1",
        "HIF1A",
        "VHL",
        "TERT",
        "MDM2",
        "BCL2",
        "BAX",
        "CASP3",
        "CASP8",
        "CASP9",
        "FAS",
        "TNF",
        "IL6",
        "IL1B",
        "CXCL8",
        "IFNG",
        "TGFB1",
        "FOXP3",
        "PDCD1",
        "CD274",
        "CTLA4",
        "LAG3",
        "TIGIT",
        "GZMB",
        "PRF1",
        "ESR1",
        "PGR",
        "AR",
        "CYP2D6",
        "CYP3A4",
        "CYP2C9",
        "CYP2C19",
        "SLCO1B1",
        "ABCB1",
        "CFTR",
        "HBB",
        "HBA1",
        "F8",
        "F9",
        "DMD",
        "SMN1",
        "HTT",
        "APP",
        "PSEN1",
        "PSEN2",
        "MAPT",
        "SNCA",
        "LRRK2",
        "GBA",
        "APOE",
        "LDLR",
        "PCSK9",
        "INS",
        "GCK",
        "TCF7L2",
    ]
    diseases = [
        "Breast cancer",
        "Lung adenocarcinoma",
        "Colorectal cancer",
        "Melanoma",
        "Glioblastoma",
        "Prostate cancer",
        "Ovarian cancer",
        "Leukaemia",
        "Type 2 diabetes",
        "Alzheimer disease",
        "Parkinson disease",
        "Cystic fibrosis",
        "Sickle cell disease",
        "Haemophilia A",
        "Duchenne muscular dystrophy",
        "Spinal muscular atrophy",
        "Familial hypercholesterolaemia",
        "Crohn disease",
        "Rheumatoid arthritis",
        "Systemic lupus erythematosus",
        "Asthma",
        "Tuberculosis",
        "Influenza",
        "COVID-19",
        "Malaria",
        "Hepatitis B",
        "Hepatitis C",
        "Non-alcoholic fatty liver disease",
        "Chronic kidney disease",
        "Hypertension",
    ]
    pathways = [
        "Cell cycle",
        "DNA repair",
        "Apoptosis",
        "MAPK signalling",
        "PI3K-AKT signalling",
        "mTOR signalling",
        "WNT signalling",
        "JAK-STAT signalling",
        "TGF-beta signalling",
        "VEGF signalling",
        "p53 signalling",
        "NF-kappa B signalling",
        "Interferon response",
        "T-cell receptor signalling",
        "B-cell receptor signalling",
        "Glycolysis",
        "Oxidative phosphorylation",
        "Fatty acid metabolism",
        "Amino acid metabolism",
        "Autophagy",
        "Ubiquitin proteolysis",
        "Chromatin regulation",
        "RNA splicing",
        "Protein translation",
        "ER stress",
        "Hypoxia response",
        "Angiogenesis",
        "Epithelial-mesenchymal transition",
        "Complement cascade",
        "Coagulation cascade",
    ]
    domains = [f"PFAM reference domain {i:03d}" for i in range(1, 61)]
    organisms = [
        "Homo sapiens",
        "Mus musculus",
        "Rattus norvegicus",
        "Danio rerio",
        "Drosophila melanogaster",
        "Caenorhabditis elegans",
        "Saccharomyces cerevisiae",
        "Escherichia coli",
        "Bacillus subtilis",
        "Pseudomonas aeruginosa",
        "Mycobacterium tuberculosis",
        "Staphylococcus aureus",
        "Arabidopsis thaliana",
        "Oryza sativa",
        "Zea mays",
        "Plasmodium falciparum",
        "SARS-CoV-2",
        "Influenza A virus",
        "Hepatitis B virus",
        "Hepatitis C virus",
    ]
    tissues = [
        "Liver",
        "Lung",
        "Brain",
        "Heart",
        "Kidney",
        "Skeletal muscle",
        "Blood",
        "Bone marrow",
        "Colon",
        "Small intestine",
        "Pancreas",
        "Spleen",
        "Skin",
        "Breast",
        "Prostate",
        "Ovary",
        "Testis",
        "Adipose tissue",
        "Retina",
        "Placenta",
    ]
    cell_lines = [
        "HEK293",
        "HeLa",
        "A549",
        "HepG2",
        "MCF7",
        "MDA-MB-231",
        "HCT116",
        "Jurkat",
        "K562",
        "CHO-K1",
        "U2OS",
        "PC3",
        "LNCaP",
        "SH-SY5Y",
        "THP-1",
        "RAW264.7",
        "Vero E6",
        "Caco-2",
        "293T",
        "NIH-3T3",
    ]
    assays = [
        "IC50 biochemical assay",
        "EC50 cellular assay",
        "Ki binding assay",
        "Kd binding assay",
        "qPCR expression assay",
        "ELISA protein assay",
        "Western blot",
        "Flow cytometry",
        "RNA-seq",
        "Whole-genome sequencing",
        "ChIP-seq",
        "ATAC-seq",
        "Mass spectrometry proteomics",
        "Metabolomics LC-MS",
        "Microbiome 16S sequencing",
        "CRISPR screen",
        "Cell viability assay",
        "Reporter assay",
        "Enzyme kinetics",
        "Surface plasmon resonance",
    ]
    with transaction(path) as connection:
        connection.execute(
            "DELETE FROM knowledge_relations WHERE evidence='Step30 reference catalogue'"
        )
        connection.execute(
            "DELETE FROM knowledge_entities WHERE source='BioIntel Step30 scientific reference catalogue'"
        )
        source = "BioIntel Step30 scientific reference catalogue"
        for index, gene in enumerate(genes, 1):
            _upsert_entity(
                connection,
                entity_id=f"step30:gene:{gene}",
                entity_type="gene",
                name=gene,
                summary=f"Reference gene entity for bioinformatics search and workflow demonstrations: {gene}.",
                source=source,
                external_id=f"HGNC_REFERENCE:{gene}",
                confidence=0.7,
                tags="gene,reference,step30",
                metadata={"reference_only": True},
            )
        for index, disease in enumerate(diseases, 1):
            _upsert_entity(
                connection,
                entity_id=f"step30:disease:{index:03d}",
                entity_type="disease",
                name=disease,
                summary=f"Reference disease concept for knowledge graph demonstrations: {disease}.",
                source=source,
                external_id=f"MONDO_REFERENCE:{index:03d}",
                confidence=0.7,
                tags="disease,reference,step30",
                metadata={"reference_only": True},
            )
        for index, pathway in enumerate(pathways, 1):
            _upsert_entity(
                connection,
                entity_id=f"step30:pathway:{index:03d}",
                entity_type="pathway",
                name=pathway,
                summary=f"Reference biological pathway: {pathway}.",
                source=source,
                external_id=f"PATHWAY_REFERENCE:{index:03d}",
                confidence=0.7,
                tags="pathway,reference,step30",
                metadata={"reference_only": True},
            )
        for index, domain in enumerate(domains, 1):
            _upsert_entity(
                connection,
                entity_id=f"step30:domain:{index:03d}",
                entity_type="protein_domain",
                name=domain,
                summary="Reference protein-domain entry for domain-search demonstrations.",
                source=source,
                external_id=f"PFAM_REFERENCE:{index:05d}",
                confidence=0.6,
                tags="protein,domain,reference",
                metadata={"reference_only": True},
            )
        for collection, entity_type, prefix in (
            (organisms, "organism", "organism"),
            (tissues, "tissue", "tissue"),
            (cell_lines, "cell_line", "cell"),
            (assays, "assay", "assay"),
        ):
            for index, name in enumerate(collection, 1):
                _upsert_entity(
                    connection,
                    entity_id=f"step30:{prefix}:{index:03d}",
                    entity_type=entity_type,
                    name=name,
                    summary=f"Reference {entity_type.replace('_', ' ')} entity: {name}.",
                    source=source,
                    external_id=f"REFERENCE:{prefix.upper()}:{index:03d}",
                    confidence=0.65,
                    tags=f"{entity_type},reference,step30",
                    metadata={"reference_only": True},
                )
        for index, gene in enumerate(genes):
            pathway_id = f"step30:pathway:{1 + index % len(pathways):03d}"
            disease_id = f"step30:disease:{1 + index % len(diseases):03d}"
            _upsert_relation(
                connection,
                source_entity_id=f"step30:gene:{gene}",
                target_entity_id=pathway_id,
                relation_type="reference_member_of",
                score=0.6,
                evidence="Step30 reference catalogue",
                metadata={"reference_only": True},
            )
            _upsert_relation(
                connection,
                source_entity_id=f"step30:gene:{gene}",
                target_entity_id=disease_id,
                relation_type="reference_associated_with",
                score=0.5,
                evidence="Step30 reference catalogue",
                metadata={"reference_only": True},
            )
        current_datasets = list_datasets(REPORTS / "datasets.sqlite3", limit=5000)
        current_ids = {f"dataset:{record.dataset_sha256}" for record in current_datasets}
        stale = [
            row[0]
            for row in connection.execute(
                "SELECT entity_id FROM knowledge_entities WHERE entity_type='dataset'"
            ).fetchall()
            if row[0] not in current_ids
        ]
        connection.executemany(
            "DELETE FROM knowledge_entities WHERE entity_id=?", [(item,) for item in stale]
        )
        for record in current_datasets:
            _upsert_entity(
                connection,
                entity_id=f"dataset:{record.dataset_sha256}",
                entity_type="dataset",
                name=f"{record.dataset_name} · {record.dataset_version}",
                summary=f"{record.task_type} dataset with {record.row_count:,} rows and SHA-256 {record.dataset_sha256[:12]}…",
                source=record.source_description,
                external_id=record.dataset_sha256,
                status="registered",
                confidence=1.0,
                tags=f"dataset,{record.task_type},registered,lineage,step30",
                metadata=record.__dict__,
            )
        try:
            dataset_links = connection.execute(
                "SELECT source_dataset_sha256,target_dataset_sha256,relation_type,description FROM dataset_links"
            ).fetchall()
        except sqlite3.OperationalError:
            dataset_links = []
        for source_hash, target_hash, relation_type, description in dataset_links:
            source_id = f"dataset:{source_hash}"
            target_id = f"dataset:{target_hash}"
            if source_id in current_ids and target_id in current_ids:
                _upsert_relation(
                    connection,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relation_type=relation_type,
                    score=1.0,
                    evidence=description or "Step30 dataset linkage",
                    metadata={"reference_only": True},
                )
    return {
        "genes": len(genes),
        "diseases": len(diseases),
        "pathways": len(pathways),
        "domains": len(domains),
        "organisms": len(organisms),
        "tissues": len(tissues),
        "cell_lines": len(cell_lines),
        "assays": len(assays),
    }


def main() -> None:
    initialize_scientific_registries(ROOT)
    fastq = write_fastq()
    assembly_frame, assembly_metrics_payload = write_assembly()
    vcf_frame, vcf_metrics = write_vcf()
    gff_frame, gff_metrics = write_gff()
    expression, sample_metadata = write_expression()
    transcriptomics, proteomics = write_omics()
    microbiome, microbiome_metadata = write_microbiome()
    wetlab = write_wetlab()
    protein_panel = write_protein_panel()
    alignment = write_alignment()
    structures = write_structures()
    generated = {
        "fastq": fastq,
        "assembly_frame": assembly_frame,
        "assembly_metrics": assembly_metrics_payload,
        "vcf_frame": vcf_frame,
        "vcf_metrics": vcf_metrics,
        "gff_frame": gff_frame,
        "gff_metrics": gff_metrics,
        "expression": expression,
        "sample_metadata": sample_metadata,
        "transcriptomics": transcriptomics,
        "proteomics": proteomics,
        "microbiome": microbiome,
        "microbiome_metadata": microbiome_metadata,
        "wetlab": wetlab,
        "protein_panel": protein_panel,
        "alignment": alignment,
        "structures": structures,
    }
    dataset_hashes = seed_datasets(generated)
    experiment_depth = seed_experiment_depth()
    evidence_depth = seed_evidence_depth()
    source_catalog = seed_source_catalog()
    feature_cache = seed_feature_cache()
    knowledge = seed_knowledge_diversity()
    assets = seed_asset_store(ROOT)
    payload = {
        "milestone": "Step 30 Scientific Data Foundation",
        "generated_at_utc": utc_now(),
        "datasets_registered": len(dataset_hashes),
        "dataset_hashes": dataset_hashes,
        "experiment_depth": experiment_depth,
        "evidence_depth": evidence_depth,
        "scientific_source_catalog": source_catalog,
        "feature_cache": feature_cache,
        "knowledge_diversity": knowledge,
        "asset_summary": assets.__dict__,
        "registry_summary": scientific_registry_summary(ROOT),
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(DEMO.rglob("*"))
            if path.is_file()
        },
        "scientific_boundary": "All generated content is reference/simulation data and remains blocked from real scientific release.",
    }
    output = REPORTS / "generated" / "step30_scientific_data_foundation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
