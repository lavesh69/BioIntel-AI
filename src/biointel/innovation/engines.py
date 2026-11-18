from __future__ import annotations

import io
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import calibration_curve
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DNA_COMPLEMENT = str.maketrans("ACGTUNacgtun", "TGCAANtgcaan")
AA20 = "ACDEFGHIKLMNPQRSTVWY"
AA_PROPERTIES = {
    "A": (1.8, 0.00, 89.1), "C": (2.5, 0.00, 121.2), "D": (-3.5, -1.00, 133.1),
    "E": (-3.5, -1.00, 147.1), "F": (2.8, 0.00, 165.2), "G": (-0.4, 0.00, 75.1),
    "H": (-3.2, 0.10, 155.2), "I": (4.5, 0.00, 131.2), "K": (-3.9, 1.00, 146.2),
    "L": (3.8, 0.00, 131.2), "M": (1.9, 0.00, 149.2), "N": (-3.5, 0.00, 132.1),
    "P": (-1.6, 0.00, 115.1), "Q": (-3.5, 0.00, 146.2), "R": (-4.5, 1.00, 174.2),
    "S": (-0.8, 0.00, 105.1), "T": (-0.7, 0.00, 119.1), "V": (4.2, 0.00, 117.1),
    "W": (-0.9, 0.00, 204.2), "Y": (-1.3, 0.00, 181.2),
}


def deterministic_rng(seed: int | str = 93) -> np.random.Generator:
    if isinstance(seed, str):
        seed = sum((index + 1) * ord(char) for index, char in enumerate(seed)) % (2**32 - 1)
    return np.random.default_rng(int(seed))


def clean_sequence(text: str, alphabet: str = "dna") -> str:
    raw = re.sub(r"[^A-Za-z*]", "", text or "").upper()
    allowed = set("ACGTUN" if alphabet == "dna" else AA20 + "X*")
    return "".join(char for char in raw if char in allowed)


def parse_fasta(text: str, alphabet: str = "dna") -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    name = "sequence_1"
    sequence: list[str] = []
    saw_header = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if sequence:
                records.append((name, clean_sequence("".join(sequence), alphabet)))
            name = line[1:].strip() or f"sequence_{len(records) + 1}"
            sequence = []
            saw_header = True
        else:
            sequence.append(line)
    if sequence:
        records.append((name, clean_sequence("".join(sequence), alphabet)))
    if not records and text and not saw_header:
        seq = clean_sequence(text, alphabet)
        if seq:
            records.append((name, seq))
    return [(name, seq) for name, seq in records if seq]


def n50(lengths: Sequence[int]) -> int:
    values = sorted((int(value) for value in lengths if int(value) > 0), reverse=True)
    if not values:
        return 0
    halfway = sum(values) / 2
    running = 0
    for value in values:
        running += value
        if running >= halfway:
            return value
    return values[-1]


def demo_pangenome_graph() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sequences = {
        "1": "ATGCGTACGTTAGC", "2": "AAGTCC", "3": "AAGACC", "4": "TTGCAA",
        "5": "GGCTAACCT", "6": "CCTGGA", "7": "CCTAGA", "8": "TTAACCGG",
        "9": "GATCCGA", "10": "CTTAGGCTA", "11": "ATGGCA", "12": "TGCCTA",
    }
    nodes = pd.DataFrame([
        {"node": node, "sequence": seq, "length": len(seq), "gc": 100 * (seq.count("G") + seq.count("C")) / len(seq)}
        for node, seq in sequences.items()
    ])
    edge_pairs = [
        ("1", "2"), ("1", "3"), ("2", "4"), ("3", "4"), ("4", "5"),
        ("5", "6"), ("5", "7"), ("6", "8"), ("7", "8"), ("8", "9"),
        ("9", "10"), ("9", "11"), ("11", "12"), ("12", "10"),
    ]
    edges = pd.DataFrame([{"source": a, "target": b, "orientation": "++"} for a, b in edge_pairs])
    paths = pd.DataFrame([
        {"path": "Reference", "nodes": "1,2,4,5,6,8,9,10", "population": "Reference", "frequency": 0.44},
        {"path": "Haplotype_A", "nodes": "1,3,4,5,6,8,9,10", "population": "Population A", "frequency": 0.21},
        {"path": "Haplotype_B", "nodes": "1,2,4,5,7,8,9,10", "population": "Population B", "frequency": 0.18},
        {"path": "Haplotype_C", "nodes": "1,3,4,5,7,8,9,11,12,10", "population": "Population C", "frequency": 0.17},
    ])
    return nodes, edges, paths


def parse_gfa(text: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    node_rows: list[dict[str, object]] = []
    edge_rows: list[dict[str, object]] = []
    path_rows: list[dict[str, object]] = []
    for raw in (text or "").splitlines():
        fields = raw.rstrip("\n").split("\t")
        if not fields:
            continue
        if fields[0] == "S" and len(fields) >= 3:
            seq = fields[2] if fields[2] != "*" else ""
            length = len(seq)
            if not length:
                for tag in fields[3:]:
                    if tag.startswith("LN:i:"):
                        length = int(tag.split(":")[-1])
            gc = 100 * (seq.count("G") + seq.count("C")) / max(1, len(seq)) if seq else np.nan
            node_rows.append({"node": fields[1], "sequence": seq, "length": length, "gc": gc})
        elif fields[0] == "L" and len(fields) >= 5:
            edge_rows.append({"source": fields[1], "target": fields[3], "orientation": fields[2] + fields[4]})
        elif fields[0] == "P" and len(fields) >= 3:
            members = [token.rstrip("+-") for token in fields[2].split(",")]
            path_rows.append({"path": fields[1], "nodes": ",".join(members), "population": "Uploaded", "frequency": np.nan})
    if not node_rows:
        raise ValueError("No GFA segment (S) records were found.")
    return pd.DataFrame(node_rows), pd.DataFrame(edge_rows), pd.DataFrame(path_rows)


def graph_layout(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    labels = nodes["node"].astype(str).tolist()
    incoming: dict[str, int] = {label: 0 for label in labels}
    outgoing: dict[str, list[str]] = {label: [] for label in labels}
    for row in edges.itertuples(index=False):
        a, b = str(row.source), str(row.target)
        outgoing.setdefault(a, []).append(b)
        incoming[b] = incoming.get(b, 0) + 1
    roots = [label for label in labels if incoming.get(label, 0) == 0] or labels[:1]
    level = {label: 0 for label in roots}
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        for child in outgoing.get(current, []):
            if child not in level:
                level[child] = level.get(current, 0) + 1
                queue.append(child)
    max_level = max(level.values(), default=0)
    for label in labels:
        level.setdefault(label, max_level + 1)
    grouped: dict[int, list[str]] = defaultdict(list)
    for label in labels:
        grouped[level[label]].append(label)
    rows = []
    for depth, group in sorted(grouped.items()):
        center = (len(group) - 1) / 2
        for index, label in enumerate(group):
            rows.append({"node": label, "x": float(depth), "y": float(center - index)})
    return pd.DataFrame(rows)


def pangenome_metrics(nodes: pd.DataFrame, edges: pd.DataFrame, paths: pd.DataFrame) -> dict[str, float | int]:
    outdegree = edges.groupby("source").size() if not edges.empty else pd.Series(dtype=int)
    indegree = edges.groupby("target").size() if not edges.empty else pd.Series(dtype=int)
    bubbles = set(outdegree[outdegree > 1].index.astype(str)) | set(indegree[indegree > 1].index.astype(str))
    return {
        "nodes": int(len(nodes)),
        "edges": int(len(edges)),
        "paths": int(len(paths)),
        "sequence_bp": int(pd.to_numeric(nodes["length"], errors="coerce").fillna(0).sum()),
        "bubble_nodes": int(len(bubbles)),
        "mean_gc": float(pd.to_numeric(nodes["gc"], errors="coerce").mean()),
    }


def demo_fastq(reads: int = 180, seed: int = 93) -> str:
    rng = deterministic_rng(seed)
    rows: list[str] = []
    for index in range(reads):
        length = int(np.clip(rng.lognormal(mean=9.2, sigma=0.48), 700, 42000))
        bases = rng.choice(list("ACGT"), size=length, p=[0.29, 0.21, 0.21, 0.29])
        q = int(np.clip(rng.normal(18.5, 3.0), 8, 30))
        quality = chr(q + 33) * length
        rows.extend([f"@read_{index+1}", "".join(bases), "+", quality])
    return "\n".join(rows) + "\n"


def parse_fastq_summary(text: str, max_reads: int = 100_000) -> pd.DataFrame:
    lines = (text or "").splitlines()
    if len(lines) < 4:
        raise ValueError("FASTQ content must contain at least one four-line record.")
    rows: list[dict[str, object]] = []
    for offset in range(0, min(len(lines) - 3, max_reads * 4), 4):
        header, seq, plus, qual = lines[offset: offset + 4]
        if not header.startswith("@") or not plus.startswith("+"):
            continue
        seq = clean_sequence(seq, "dna")
        if not seq:
            continue
        qualities = np.array([max(0, ord(char) - 33) for char in qual[: len(seq)]], dtype=float)
        rows.append({
            "read": header[1:].split()[0],
            "length": len(seq),
            "mean_q": float(qualities.mean()) if len(qualities) else np.nan,
            "gc": 100 * (seq.count("G") + seq.count("C")) / len(seq),
        })
    if not rows:
        raise ValueError("No valid FASTQ records were parsed.")
    return pd.DataFrame(rows)


def read_summary_metrics(reads: pd.DataFrame) -> dict[str, float | int]:
    lengths = pd.to_numeric(reads["length"], errors="coerce").dropna().astype(int).tolist()
    return {
        "reads": len(lengths),
        "bases": int(sum(lengths)),
        "n50": n50(lengths),
        "median_length": float(np.median(lengths)) if lengths else 0.0,
        "mean_q": float(pd.to_numeric(reads["mean_q"], errors="coerce").mean()),
        "mean_gc": float(pd.to_numeric(reads["gc"], errors="coerce").mean()),
    }


def assembly_plan(platform: str, genome_type: str, coverage: float, hybrid: bool) -> pd.DataFrame:
    platform_lower = platform.lower()
    genome_lower = genome_type.lower()
    if "hifi" in platform_lower:
        assembler = "hifiasm"
        polish = "Arrow/DeepConsensus-aware review"
    elif "nanopore" in platform_lower:
        assembler = "Flye"
        polish = "Racon → Medaka"
    else:
        assembler = "Canu/Flye comparison"
        polish = "Racon consensus"
    steps = [
        (1, "Read QC", "NanoPlot/FastQC", "Length, quality, yield and contamination review"),
        (2, "Filtering", "Filtlong/fastp", "Remove very short and low-quality reads"),
        (3, "Assembly", assembler, f"Primary assembly for {genome_type.lower()}"),
        (4, "Polishing", polish, "Consensus correction with raw reads"),
        (5, "Evaluation", "QUAST + BUSCO", "Contiguity, completeness and misassembly checks"),
    ]
    if hybrid:
        steps.insert(4, (5, "Short-read polish", "Pilon/Polypolish", "Hybrid correction using accurate short reads"))
    if "microbial" in genome_lower or "bacterial" in genome_lower:
        steps.append((len(steps) + 1, "Circularisation", "Circlator/manual graph review", "Check chromosome/plasmid circularity and overlap"))
    if coverage < 20:
        warning = "Coverage below 20× may produce fragmented or unstable assemblies."
    elif coverage > 150:
        warning = "Very high coverage: downsampling can reduce runtime and repeat-induced artefacts."
    else:
        warning = "Coverage is within a typical exploratory assembly range."
    frame = pd.DataFrame(steps, columns=["step", "stage", "tool", "output"])
    frame["coverage_note"] = warning
    return frame


def fasta_contig_stats(text: str) -> tuple[pd.DataFrame, dict[str, float | int]]:
    records = parse_fasta(text, "dna")
    if not records:
        raise ValueError("No FASTA contigs were found.")
    rows = []
    for name, seq in records:
        rows.append({
            "contig": name,
            "length": len(seq),
            "gc": 100 * (seq.count("G") + seq.count("C")) / max(1, len(seq)),
            "n_fraction": seq.count("N") / max(1, len(seq)),
            "telomere_like": seq.count("TTAGGG") + seq.count("CCCTAA"),
            "end_overlap_30": seq[:30] == seq[-30:] if len(seq) >= 60 else False,
        })
    frame = pd.DataFrame(rows).sort_values("length", ascending=False)
    lengths = frame["length"].astype(int).tolist()
    metrics = {
        "contigs": len(frame), "total_bp": int(sum(lengths)), "n50": n50(lengths),
        "largest": max(lengths), "mean_gc": float(frame["gc"].mean()),
    }
    return frame, metrics


def demo_protein_sequence() -> str:
    return (
        "MKKIGYSAPRQTQKDLKELGVEVVEFDVVEGEGDTLVGKLKELGADVVVVATDSDGTIRGDFK"
        "AEVEKAGADVVVVSMDDTRRQLAELGADVVVTKEDGTVRVEFDPQGERVVAALEHHHHHH"
    )


def protein_design_candidates(
    sequence: str,
    objective: str = "Balanced developability",
    locked_positions: Iterable[int] = (),
    target_positions: Iterable[int] = (),
    top_n: int = 50,
) -> pd.DataFrame:
    seq = clean_sequence(sequence, "protein").replace("*", "")
    if len(seq) < 8:
        raise ValueError("Protein sequence must contain at least eight amino acids.")
    locked = {int(value) for value in locked_positions}
    targets = {int(value) for value in target_positions if int(value) > 0}
    objective_lower = objective.lower()
    rows: list[dict[str, object]] = []
    for position, wild in enumerate(seq, start=1):
        if position in locked:
            continue
        if targets and position not in targets:
            continue
        wild_hydro, wild_charge, wild_mass = AA_PROPERTIES.get(wild, (0.0, 0.0, 120.0))
        neighborhood = seq[max(0, position - 4): min(len(seq), position + 3)]
        hydrophobic_run = sum(AA_PROPERTIES.get(aa, (0, 0, 0))[0] > 2.0 for aa in neighborhood)
        for mutant in AA20:
            if mutant == wild:
                continue
            hydro, charge, mass = AA_PROPERTIES[mutant]
            stability = 1.8 - 0.22 * abs(hydro - wild_hydro) - 0.08 * abs(mass - wild_mass) / 20
            solubility = (wild_hydro - hydro) * 0.38 + (abs(charge) - abs(wild_charge)) * 0.35
            aggregation = -0.35 * max(0.0, hydro - 2.0) - 0.15 * hydrophobic_run
            binding = 0.55 if position in targets else 0.0
            if objective_lower.startswith("stability"):
                score = stability + 0.25 * solubility + 0.1 * aggregation
            elif objective_lower.startswith("solubility"):
                score = solubility + 0.35 * stability + 0.25 * aggregation
            elif objective_lower.startswith("binding"):
                score = binding + 0.45 * stability + 0.2 * solubility
            else:
                score = 0.5 * stability + 0.35 * solubility + 0.25 * aggregation + 0.2 * binding
            confidence = 1 / (1 + math.exp(-score))
            rows.append({
                "mutation": f"{wild}{position}{mutant}", "position": position, "wild": wild, "mutant": mutant,
                "design_score": score, "stability_proxy": stability, "solubility_proxy": solubility,
                "aggregation_proxy": aggregation, "confidence": confidence,
                "note": "Target-site candidate" if position in targets else "Global developability candidate",
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["design_score", "confidence"], ascending=False).head(int(top_n)).reset_index(drop=True)


def apply_mutations(sequence: str, mutations: Sequence[str]) -> str:
    chars = list(clean_sequence(sequence, "protein").replace("*", ""))
    pattern = re.compile(r"^([A-Z])(\d+)([A-Z])$")
    for mutation in mutations:
        match = pattern.match(str(mutation).strip().upper())
        if not match:
            raise ValueError(f"Invalid mutation notation: {mutation}")
        wild, pos, mutant = match.groups()
        index = int(pos) - 1
        if index < 0 or index >= len(chars):
            raise ValueError(f"Mutation outside sequence: {mutation}")
        if chars[index] != wild:
            raise ValueError(f"Wild-type mismatch for {mutation}: sequence contains {chars[index]}")
        chars[index] = mutant
    return "".join(chars)


def demo_crispr_counts(seed: int = 93) -> pd.DataFrame:
    rng = deterministic_rng(seed)
    genes = [f"GENE{i:02d}" for i in range(1, 31)] + ["NTC"]
    rows = []
    strong_negative = {"GENE03", "GENE11", "GENE24"}
    strong_positive = {"GENE07", "GENE18"}
    for gene in genes:
        for guide_index in range(1, 5):
            control = int(rng.lognormal(8.2, 0.32))
            effect = -1.7 if gene in strong_negative else 1.35 if gene in strong_positive else rng.normal(0, 0.25)
            treated = max(1, int(control * (2 ** effect) * rng.lognormal(0, 0.13)))
            rows.append({"guide": f"{gene}_g{guide_index}", "gene": gene, "control": control, "treated": treated})
    return pd.DataFrame(rows)


def crispr_screen_analysis(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int]]:
    required = {"guide", "gene", "control", "treated"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    data = frame.copy()
    for column in ("control", "treated"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["control", "treated"]).copy()
    data = data[(data["control"] >= 0) & (data["treated"] >= 0)]
    control_scale = data["control"].sum() / 1_000_000
    treated_scale = data["treated"].sum() / 1_000_000
    data["control_cpm"] = data["control"] / max(control_scale, 1e-9)
    data["treated_cpm"] = data["treated"] / max(treated_scale, 1e-9)
    data["log2_fc"] = np.log2((data["treated_cpm"] + 1) / (data["control_cpm"] + 1))
    median = float(data["log2_fc"].median())
    mad = float(np.median(np.abs(data["log2_fc"] - median))) or 1.0
    data["robust_z"] = 0.6745 * (data["log2_fc"] - median) / mad
    data["guide_quality"] = np.minimum(data["control"], data["treated"]) >= 50
    gene = data.groupby("gene", as_index=False).agg(
        guides=("guide", "count"), median_log2_fc=("log2_fc", "median"), mean_log2_fc=("log2_fc", "mean"),
        robust_z=("robust_z", "mean"), passing_guides=("guide_quality", "sum"),
    )
    gene["p_value_proxy"] = 2 * stats.norm.sf(np.abs(gene["robust_z"]))
    gene["minus_log10_p"] = -np.log10(np.clip(gene["p_value_proxy"], 1e-12, 1))
    gene["hit_class"] = np.select(
        [gene["median_log2_fc"] <= -0.75, gene["median_log2_fc"] >= 0.75],
        ["Negative-selection hit", "Positive-selection hit"], default="Background",
    )
    gene = gene.sort_values(["p_value_proxy", "median_log2_fc"], ascending=[True, True]).reset_index(drop=True)
    metrics = {
        "guides": len(data), "genes": int(data["gene"].nunique()),
        "qc_pass_rate": float(data["guide_quality"].mean()),
        "negative_hits": int((gene["hit_class"] == "Negative-selection hit").sum()),
        "positive_hits": int((gene["hit_class"] == "Positive-selection hit").sum()),
    }
    return data, gene, metrics


def demo_perturbseq(seed: int = 93) -> tuple[pd.DataFrame, pd.Series]:
    rng = deterministic_rng(seed)
    labels = np.repeat(["NTC", "GENE03", "GENE07", "GENE11"], 45)
    matrix = rng.normal(0, 1, size=(len(labels), 32))
    matrix[labels == "GENE03", :5] -= 1.3
    matrix[labels == "GENE07", 5:11] += 1.15
    matrix[labels == "GENE11", 12:18] -= 0.9
    frame = pd.DataFrame(matrix, columns=[f"marker_{i+1}" for i in range(matrix.shape[1])])
    return frame, pd.Series(labels, name="guide_assignment")


def perturbation_embedding(matrix: pd.DataFrame, labels: Sequence[str]) -> pd.DataFrame:
    numeric = matrix.select_dtypes(include=[np.number]).fillna(0)
    coords = PCA(n_components=2, random_state=93).fit_transform(StandardScaler().fit_transform(numeric))
    return pd.DataFrame({"PC1": coords[:, 0], "PC2": coords[:, 1], "perturbation": list(labels)})


def demo_outbreak_data(seed: int = 93) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = deterministic_rng(seed)
    centers = [
        (28.6139, 77.2090, "Hospital A"), (28.6328, 77.2197, "Hospital B"), (28.5941, 77.2504, "Community"),
    ]
    rows = []
    cluster_labels = []
    for index in range(30):
        cluster = 0 if index < 11 else 1 if index < 21 else 2
        lat, lon, location = centers[cluster]
        rows.append({
            "sample_id": f"ISO-{index+1:03d}", "collection_date": f"2026-06-{(index % 24) + 1:02d}",
            "location": location, "latitude": lat + rng.normal(0, 0.006), "longitude": lon + rng.normal(0, 0.006),
            "species": "Klebsiella pneumoniae", "amr_gene": rng.choice(["blaCTX-M", "blaKPC", "none"], p=[0.42, 0.23, 0.35]),
            "virulence_score": float(np.clip(rng.normal(0.55 + 0.12 * cluster, 0.15), 0, 1)),
        })
        cluster_labels.append(cluster)
    samples = pd.DataFrame(rows)
    matrix = np.zeros((len(samples), len(samples)), dtype=int)
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            if cluster_labels[i] == cluster_labels[j]:
                value = int(rng.integers(0, 10))
            else:
                value = int(rng.integers(24, 110))
            matrix[i, j] = matrix[j, i] = value
    distances = pd.DataFrame(matrix, index=samples["sample_id"], columns=samples["sample_id"])
    return samples, distances


def outbreak_clusters(samples: pd.DataFrame, distances: pd.DataFrame, threshold: float) -> pd.DataFrame:
    ids = samples["sample_id"].astype(str).tolist()
    matrix = distances.reindex(index=ids, columns=ids)
    if matrix.isna().any().any():
        raise ValueError("Distance matrix must contain every sample ID in both rows and columns.")
    parent = {sample: sample for sample in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    links = []
    for i, a in enumerate(ids):
        for j in range(i + 1, len(ids)):
            b = ids[j]
            distance = float(matrix.loc[a, b])
            if distance <= threshold:
                union(a, b)
                links.append({"source": a, "target": b, "snp_distance": distance})
    roots = {}
    labels = []
    for sample in ids:
        root = find(sample)
        roots.setdefault(root, len(roots) + 1)
        labels.append(f"Cluster {roots[root]}")
    result = samples.copy()
    result["outbreak_cluster"] = labels
    result["cluster_size"] = result.groupby("outbreak_cluster")["sample_id"].transform("count")
    return result, pd.DataFrame(links)


PART_LIBRARY = {
    "pLac promoter": "TTTACACTTTATGCTTCCGGCTCGTATGTTGTGTGGAATTGTGAGCGGATAACAATT",
    "pTet promoter": "TCCCTATCAGTGATAGAGATTGACATCCCTATCAGTGATAGAGATACTGAGCAC",
    "Strong RBS": "AAAGAGGAGAAA",
    "Weak RBS": "AAGGAGATATA",
    "GFP CDS": "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTTCAGCGTGTCCGGCGAGGGCGAGGGCGATGCCACCTACGGCAAGCTGACCCTGAAGTTCATCTGCACCACCGGCAAGCTGCCCGTGCCCTGGCCCACCCTCGTGACCACCCTGACCTACGGCGTGCAGTGCTTCAGCCGCTACCCCGACCACATGAAGCAGCACGACTTCTTCAAGTCCGCCATGCCCGAAGGCTACGTCCAGGAGCGCACCATCTTCTTCAAGGACGACGGCAACTACAAGACCCGCGCCGAGGTGAAGTTCGAGGGCGACACCCTGGTGAACCGCATCGAGCTGAAGGGCATCGACTTCAAGGAGGACGGCAACATCCTGGGGCACAAGCTGGAGTACAACTACAACAGCCACAACGTCTATATCATGGCCGACAAGCAGAAGAACGGCATCAAGGTGAACTTCAAGATCCGCCACAACATCGAGGACGGCAGCGTGCAGCTCGCCGACCACTACCAGCAGAACACCCCCATCGGCGACGGCCCCGTGCTGCTGCCCGACAACCACTACCTGAGCACCCAGTCCGCCCTGAGCAAAGACCCCAACGAGAAGCGCGATCACATGGTCCTGCTGGAGTTCGTGACCGCCGCCGGGATCACTCTCGGCATGGACGAGCTGTACAAGTAA",
    "mCherry CDS": "ATGGTGAGCAAGGGCGAGGAGGATAACATGGCCATCATCAAGGAGTTCATGCGCTTCAAGGTGCACATGGAGGGCTCCGTGAACGGCCACGAGTTCGAGATCGAGGGCGAGGGCGAGGGCCGCCCCTACGAGGGCACCCAGACCGCCAAGCTGAAGGTGACCAAGGGCGGCCCCCTGCCCTTCGCCTGGGACATCCTGTCCCCTCAGTTCATGTACGGCTCCAAGGCCTACGTGAAGCACCCCGCCGACATCCCCGACTACTTGAAGCTGTCCTTCCCCGAGGGCTTCAAGTGGGAGCGCGTGATGAACTTCGAGGACGGCGGCGTGGTGACCGTGACCCAGGACTCCTCCCTGCAGGACGGCGAGTTCATCTACAAGGTGAAGCTGCGCGGCACCAACTTCCCCTCCGACGGCCCCGTAATGCAGAAGAAGACCATGGGCTGGGAGGCCTCCTCCGAGCGGATGTACCCCGAGGACGGCGCCCTGAAGGGCGAGATCAAGCAGAGGCTGAAGCTGAAGGACGGCGGCCACTACGACGCTGAGGTCAAGACCACCTACAAGGCCAAGAAGCCCGTGCAGCTGCCCGGCGCCTACAACGTCAACATCAAGTTGGACATCACCTCCCACAACGAGGACTACACCATCGTGGAACAGTACGAACGCGCCGAGGGCCGCCACTCCACCGGCGGCATGGACGAGCTGTACAAGTAA",
    "Double terminator": "CCGGATCCGTCGACCTGCAGGTCGACTCTAGAGGATCCCCGGGTACCGAGCTCGAATTC",
    "Insulator": "GCTAGCGGCCGCTACTAGTATAGCGATCGC",
}


def build_construct(parts: Sequence[str]) -> tuple[str, pd.DataFrame, dict[str, float | int]]:
    unknown = [part for part in parts if part not in PART_LIBRARY]
    if unknown:
        raise ValueError(f"Unknown parts: {', '.join(unknown)}")
    position = 1
    rows = []
    sequences = []
    for part in parts:
        sequence = PART_LIBRARY[part]
        rows.append({"part": part, "start": position, "end": position + len(sequence) - 1, "length": len(sequence)})
        sequences.append(sequence)
        position += len(sequence)
    construct = "".join(sequences)
    enzymes = {"EcoRI": "GAATTC", "BamHI": "GGATCC", "HindIII": "AAGCTT", "XhoI": "CTCGAG", "NotI": "GCGGCCGC"}
    site_rows = []
    for enzyme, motif in enzymes.items():
        for match in re.finditer(motif, construct):
            site_rows.append({"enzyme": enzyme, "position": match.start() + 1, "motif": motif})
    metrics = {
        "length": len(construct), "gc": 100 * (construct.count("G") + construct.count("C")) / max(1, len(construct)),
        "parts": len(parts), "restriction_sites": len(site_rows),
    }
    return construct, pd.DataFrame(rows), metrics | {"site_table": pd.DataFrame(site_rows)}


def simulate_circuit(parts: Sequence[str], inducer_a: float, inducer_b: float, gate: str) -> pd.DataFrame:
    a = np.clip(float(inducer_a), 0, 1)
    b = np.clip(float(inducer_b), 0, 1)
    gate_upper = gate.upper()
    if gate_upper == "AND":
        signal = a * b
    elif gate_upper == "OR":
        signal = 1 - (1 - a) * (1 - b)
    elif gate_upper == "NOT A":
        signal = 1 - a
    elif gate_upper == "NAND":
        signal = 1 - a * b
    else:
        signal = a
    rbs_factor = 1.0 if "Strong RBS" in parts else 0.45
    promoter_factor = 1.15 if "pLac promoter" in parts or "pTet promoter" in parts else 0.25
    expression = 100 * signal * rbs_factor * promoter_factor
    time = np.linspace(0, 12, 49)
    response = expression * (1 - np.exp(-time / 2.4)) * np.exp(-0.012 * time)
    return pd.DataFrame({"time_h": time, "predicted_expression": response})


def demo_variants() -> pd.DataFrame:
    return pd.DataFrame([
        {"chrom":"2","pos":166845522,"ref":"G","alt":"A","gene":"SCN1A","consequence":"stop_gained","gnomad_af":0.00001,"clinvar":"Pathogenic","zygosity":"heterozygous","inheritance":"de_novo"},
        {"chrom":"7","pos":117559593,"ref":"C","alt":"T","gene":"CFTR","consequence":"missense_variant","gnomad_af":0.0003,"clinvar":"Likely pathogenic","zygosity":"heterozygous","inheritance":"maternal"},
        {"chrom":"17","pos":43071077,"ref":"A","alt":"G","gene":"BRCA1","consequence":"splice_acceptor_variant","gnomad_af":0.00002,"clinvar":"Pathogenic","zygosity":"heterozygous","inheritance":"paternal"},
        {"chrom":"X","pos":31165320,"ref":"T","alt":"C","gene":"DMD","consequence":"missense_variant","gnomad_af":0.00008,"clinvar":"Uncertain significance","zygosity":"hemizygous","inheritance":"maternal"},
        {"chrom":"12","pos":25398284,"ref":"C","alt":"A","gene":"KRAS","consequence":"missense_variant","gnomad_af":0.018,"clinvar":"Conflicting","zygosity":"heterozygous","inheritance":"unknown"},
        {"chrom":"1","pos":155205634,"ref":"G","alt":"T","gene":"MSTO1","consequence":"synonymous_variant","gnomad_af":0.12,"clinvar":"Benign","zygosity":"heterozygous","inheritance":"paternal"},
    ])


def parse_vcf(text: str) -> pd.DataFrame:
    rows = []
    header = []
    for raw in (text or "").splitlines():
        if raw.startswith("##"):
            continue
        if raw.startswith("#CHROM"):
            header = raw.lstrip("#").split("\t")
            continue
        if raw.startswith("#") or not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) < 8:
            continue
        info = {token.split("=", 1)[0]: token.split("=", 1)[1] if "=" in token else True for token in fields[7].split(";")}
        rows.append({
            "chrom": fields[0], "pos": int(fields[1]), "ref": fields[3], "alt": fields[4].split(",")[0],
            "gene": info.get("GENE", info.get("SYMBOL", "Unknown")),
            "consequence": info.get("CSQ", info.get("ANN", "unknown")).split("|")[0],
            "gnomad_af": float(info.get("AF", info.get("GNOMAD_AF", 0)) or 0),
            "clinvar": str(info.get("CLNSIG", "Not provided")).replace("_", " "),
            "zygosity": "heterozygous", "inheritance": str(info.get("INHERITANCE", "unknown")),
        })
    if not rows:
        raise ValueError("No variants could be parsed. Include standard VCF columns and optional GENE/CSQ/AF/CLNSIG INFO tags.")
    return pd.DataFrame(rows)


HPO_GENE_MAP = {
    "HP:0001250": {"SCN1A", "DMD"}, "HP:0001263": {"SCN1A", "DMD", "MSTO1"},
    "HP:0001290": {"DMD", "MSTO1"}, "HP:0001945": {"CFTR"}, "HP:0002202": {"CFTR"},
    "HP:0003002": {"BRCA1", "KRAS"},
}


def prioritize_variants(frame: pd.DataFrame, hpo_terms: Sequence[str], inheritance_model: str) -> pd.DataFrame:
    data = frame.copy()
    for column in ["gene", "consequence", "clinvar", "zygosity", "inheritance"]:
        if column not in data:
            data[column] = "unknown"
    data["gnomad_af"] = pd.to_numeric(data.get("gnomad_af", 0), errors="coerce").fillna(0)
    impact_map = {
        "stop_gained": 4.0, "frameshift_variant": 4.0, "splice_acceptor_variant": 3.8,
        "splice_donor_variant": 3.8, "missense_variant": 2.0, "inframe_deletion": 2.2,
        "synonymous_variant": 0.1, "unknown": 0.5,
    }
    clinvar_map = {"pathogenic": 4.0, "likely pathogenic": 3.2, "uncertain significance": 1.0, "conflicting": 0.5, "benign": -3.0}
    phenotype_genes = set().union(*(HPO_GENE_MAP.get(term.strip(), set()) for term in hpo_terms)) if hpo_terms else set()
    rows = []
    model = inheritance_model.lower()
    for row in data.to_dict(orient="records"):
        consequence = str(row.get("consequence", "unknown")).split("&")[0].lower()
        clinvar = str(row.get("clinvar", "Not provided")).lower()
        score = impact_map.get(consequence, 0.8)
        score += next((value for key, value in clinvar_map.items() if key in clinvar), 0.0)
        af = float(row.get("gnomad_af", 0) or 0)
        score += 3.0 if af <= 1e-4 else 2.0 if af <= 1e-3 else 0.8 if af <= 0.01 else -2.0
        gene = str(row.get("gene", "Unknown"))
        phenotype_match = gene in phenotype_genes
        score += 2.5 if phenotype_match else 0.0
        inheritance = str(row.get("inheritance", "unknown")).lower()
        zygosity = str(row.get("zygosity", "unknown")).lower()
        inheritance_match = (
            ("de novo" in model and "de_novo" in inheritance)
            or ("recessive" in model and zygosity in {"homozygous", "compound_het"})
            or ("x-linked" in model and str(row.get("chrom", "")).upper() == "X")
            or ("dominant" in model and zygosity == "heterozygous")
            or model.startswith("any")
        )
        score += 1.5 if inheritance_match else 0.0
        row.update({
            "priority_score": score, "phenotype_match": phenotype_match, "inheritance_match": inheritance_match,
            "evidence_tier": "High" if score >= 8 else "Moderate" if score >= 5 else "Low",
            "acmg_assist": "Review PVS1/PS/PM evidence" if consequence in {"stop_gained", "frameshift_variant", "splice_acceptor_variant", "splice_donor_variant"} else "Review computational/phenotype evidence",
        })
        rows.append(row)
    return pd.DataFrame(rows).sort_values("priority_score", ascending=False).reset_index(drop=True)


def demo_knowledge_graph() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.DataFrame([
        ("SCN1A", "Gene"), ("Epilepsy", "Disease"), ("Sodium channel", "Pathway"), ("Stiripentol", "Drug"),
        ("CFTR", "Gene"), ("Cystic fibrosis", "Disease"), ("Ivacaftor", "Drug"), ("Chloride transport", "Pathway"),
        ("BRCA1", "Gene"), ("Breast cancer", "Disease"), ("Olaparib", "Drug"), ("DNA repair", "Pathway"),
        ("PMID:31160728", "Publication"), ("PMID:20301428", "Publication"), ("NCT03673306", "Trial"),
    ], columns=["node", "type"])
    edges = pd.DataFrame([
        ("SCN1A", "Epilepsy", "associated_with", 0.95, "curated"),
        ("Stiripentol", "Epilepsy", "treats", 0.82, "clinical"),
        ("SCN1A", "Sodium channel", "participates_in", 0.90, "curated"),
        ("CFTR", "Cystic fibrosis", "causes", 0.98, "curated"),
        ("Ivacaftor", "CFTR", "modulates", 0.92, "clinical"),
        ("CFTR", "Chloride transport", "participates_in", 0.94, "curated"),
        ("BRCA1", "Breast cancer", "associated_with", 0.96, "curated"),
        ("Olaparib", "Breast cancer", "treats", 0.88, "clinical"),
        ("BRCA1", "DNA repair", "participates_in", 0.95, "curated"),
        ("PMID:31160728", "SCN1A", "supports", 0.78, "publication"),
        ("PMID:20301428", "CFTR", "supports", 0.80, "publication"),
        ("NCT03673306", "Olaparib", "evaluates", 0.86, "trial"),
    ], columns=["source", "target", "relation", "evidence_score", "evidence_type"])
    return nodes, edges


def knowledge_graph_layout(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    types = nodes["type"].astype(str).unique().tolist()
    type_angles = {kind: 2 * math.pi * index / max(1, len(types)) for index, kind in enumerate(types)}
    rows = []
    for kind, group in nodes.groupby("type", sort=False):
        base = type_angles[str(kind)]
        count = len(group)
        for index, node in enumerate(group["node"].astype(str)):
            angle = base + (index - (count - 1) / 2) * 0.16
            radius = 1.0 + 0.12 * index
            rows.append({"node": node, "type": kind, "x": radius * math.cos(angle), "y": radius * math.sin(angle)})
    return pd.DataFrame(rows)


def evidence_summary(nodes: pd.DataFrame, edges: pd.DataFrame, focus: str) -> dict[str, object]:
    needle = focus.strip().lower()
    selected = set(nodes.loc[nodes["node"].astype(str).str.lower().str.contains(needle, regex=False), "node"].astype(str)) if needle else set(nodes["node"].astype(str))
    connected = edges[edges["source"].astype(str).isin(selected) | edges["target"].astype(str).isin(selected)].copy()
    if connected.empty:
        return {"focus": focus, "relationships": 0, "mean_evidence": 0.0, "summary": "No connected evidence was found."}
    entities = sorted(set(connected["source"].astype(str)) | set(connected["target"].astype(str)))
    strong = connected[connected["evidence_score"] >= 0.85]
    conflicts = connected.groupby(["source", "target"])["relation"].nunique().reset_index(name="relation_count")
    return {
        "focus": focus or "all entities", "relationships": len(connected), "entities": entities,
        "mean_evidence": float(connected["evidence_score"].mean()), "strong_relationships": len(strong),
        "potential_conflicts": int((conflicts["relation_count"] > 1).sum()),
        "summary": f"The local graph links {len(entities)} entities through {len(connected)} relationships; {len(strong)} relationships have evidence score ≥0.85.",
    }


def demo_multiomics(samples: int = 180, seed: int = 93) -> pd.DataFrame:
    rng = deterministic_rng(seed)
    outcome = rng.binomial(1, 0.48, size=samples)
    batch = rng.choice(["Batch_A", "Batch_B", "Batch_C"], size=samples)
    data: dict[str, object] = {"sample_id": [f"S{i+1:03d}" for i in range(samples)], "outcome": outcome, "batch": batch}
    for prefix, count in [("rna", 14), ("protein", 10), ("metabolite", 8), ("methylation", 6)]:
        for index in range(count):
            signal = (1.1 - 0.07 * index) * outcome if index < 4 else 0
            batch_shift = np.where(batch == "Batch_B", 0.35, np.where(batch == "Batch_C", -0.25, 0))
            data[f"{prefix}_{index+1}"] = rng.normal(signal + batch_shift, 1.0, size=samples)
    return pd.DataFrame(data)


def batch_center(frame: pd.DataFrame, feature_columns: Sequence[str], batch_column: str) -> pd.DataFrame:
    corrected = frame.copy()
    overall = corrected[list(feature_columns)].mean()
    for _, index in corrected.groupby(batch_column).groups.items():
        batch_mean = corrected.loc[index, list(feature_columns)].mean()
        corrected.loc[index, list(feature_columns)] = corrected.loc[index, list(feature_columns)] - batch_mean + overall
    return corrected


def biomarker_model(frame: pd.DataFrame, outcome_column: str, batch_column: str | None = None, folds: int = 5) -> dict[str, object]:
    data = frame.copy()
    y = pd.to_numeric(data[outcome_column], errors="coerce")
    valid = y.isin([0, 1])
    data = data.loc[valid].reset_index(drop=True)
    y = y.loc[valid].astype(int).to_numpy()
    excluded = {outcome_column, "sample_id"}
    if batch_column:
        excluded.add(batch_column)
    features = [column for column in data.select_dtypes(include=[np.number]).columns if column not in excluded]
    if len(features) < 2:
        raise ValueError("At least two numeric omics features are required.")
    model_data = data
    if batch_column and batch_column in data.columns:
        model_data = batch_center(data, features, batch_column)
    X = model_data[features].replace([np.inf, -np.inf], np.nan).fillna(model_data[features].median())
    class_counts = pd.Series(y).value_counts()
    safe_folds = max(2, min(int(folds), int(class_counts.min())))
    pipeline = Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=3000, class_weight="balanced", C=0.75, random_state=93)),
    ])
    cv = StratifiedKFold(n_splits=safe_folds, shuffle=True, random_state=93)
    probabilities = cross_val_predict(pipeline, X, y, cv=cv, method="predict_proba")[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    pipeline.fit(X, y)
    coefficients = pipeline.named_steps["model"].coef_[0]
    importance = pd.DataFrame({"feature": features, "coefficient": coefficients, "abs_coefficient": np.abs(coefficients)})
    importance["omics_layer"] = importance["feature"].str.split("_").str[0]
    importance = importance.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)
    fpr, tpr, thresholds = roc_curve(y, probabilities)
    prob_true, prob_pred = calibration_curve(y, probabilities, n_bins=min(10, max(3, len(y) // 20)), strategy="quantile")
    metrics = {
        "roc_auc": float(roc_auc_score(y, probabilities)), "average_precision": float(average_precision_score(y, probabilities)),
        "accuracy": float(accuracy_score(y, predictions)), "balanced_accuracy": float(balanced_accuracy_score(y, predictions)),
        "brier": float(brier_score_loss(y, probabilities)), "folds": safe_folds, "samples": len(y), "features": len(features),
    }
    prediction_frame = pd.DataFrame({"sample_id": data.get("sample_id", pd.Series(range(len(data)))).astype(str), "observed": y, "probability": probabilities, "predicted": predictions})
    return {
        "metrics": metrics, "importance": importance, "predictions": prediction_frame,
        "roc": pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": thresholds}),
        "calibration": pd.DataFrame({"predicted_probability": prob_pred, "observed_frequency": prob_true}),
        "model": pipeline, "features": features,
    }


WORKFLOW_BLOCKS = {
    "Upload FASTQ": {"input": "file", "output": "reads", "cpu": 1, "memory_gb": 1, "minutes": 1},
    "Read QC": {"input": "reads", "output": "qc_reads", "cpu": 4, "memory_gb": 4, "minutes": 8},
    "Trim adapters": {"input": "qc_reads", "output": "clean_reads", "cpu": 4, "memory_gb": 4, "minutes": 12},
    "Long-read assembly": {"input": "clean_reads", "output": "assembly", "cpu": 16, "memory_gb": 64, "minutes": 180},
    "Genome alignment": {"input": "clean_reads", "output": "alignment", "cpu": 12, "memory_gb": 24, "minutes": 55},
    "Variant calling": {"input": "alignment", "output": "variants", "cpu": 8, "memory_gb": 16, "minutes": 45},
    "Variant annotation": {"input": "variants", "output": "annotated_variants", "cpu": 4, "memory_gb": 12, "minutes": 25},
    "Taxonomic classification": {"input": "clean_reads", "output": "taxa", "cpu": 16, "memory_gb": 48, "minutes": 60},
    "AMR screening": {"input": "assembly", "output": "amr_hits", "cpu": 8, "memory_gb": 16, "minutes": 20},
    "Protein design": {"input": "protein", "output": "designed_protein", "cpu": 8, "memory_gb": 16, "minutes": 30},
    "Biomarker model": {"input": "omics_table", "output": "biomarker_report", "cpu": 8, "memory_gb": 16, "minutes": 15},
    "Quality gate": {"input": "any", "output": "approved_asset", "cpu": 1, "memory_gb": 2, "minutes": 3},
    "Generate report": {"input": "any", "output": "report", "cpu": 2, "memory_gb": 4, "minutes": 4},
}

WORKFLOW_TEMPLATES = {
    "Long-read genome assembly": ["Upload FASTQ", "Read QC", "Trim adapters", "Long-read assembly", "AMR screening", "Quality gate", "Generate report"],
    "Rare-disease variant interpretation": ["Upload FASTQ", "Read QC", "Genome alignment", "Variant calling", "Variant annotation", "Quality gate", "Generate report"],
    "Pathogen metagenomics": ["Upload FASTQ", "Read QC", "Trim adapters", "Taxonomic classification", "Quality gate", "Generate report"],
    "Protein engineering": ["Protein design", "Quality gate", "Generate report"],
    "Multi-omics biomarker": ["Biomarker model", "Quality gate", "Generate report"],
}


def validate_workflow(blocks: Sequence[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    if not blocks:
        raise ValueError("Add at least one workflow block.")
    rows = []
    previous_output = None
    warnings = []
    total_cpu_minutes = 0
    peak_memory = 0
    for index, block in enumerate(blocks, start=1):
        spec = WORKFLOW_BLOCKS.get(block)
        if not spec:
            raise ValueError(f"Unknown workflow block: {block}")
        required = str(spec["input"])
        compatible = index == 1 or required in {"any", previous_output} or (required == "qc_reads" and previous_output == "reads") or (required == "clean_reads" and previous_output in {"reads", "qc_reads"})
        if not compatible:
            warnings.append(f"Step {index} ({block}) expects {required}, but previous output is {previous_output}.")
        rows.append({
            "step": index, "block": block, "required_input": required, "output": spec["output"],
            "cpu": spec["cpu"], "memory_gb": spec["memory_gb"], "estimated_minutes": spec["minutes"],
            "compatible": compatible,
        })
        previous_output = str(spec["output"])
        total_cpu_minutes += int(spec["cpu"]) * int(spec["minutes"])
        peak_memory = max(peak_memory, int(spec["memory_gb"]))
    frame = pd.DataFrame(rows)
    summary = {
        "steps": len(frame), "valid": not warnings, "warnings": warnings,
        "estimated_wall_minutes": int(frame["estimated_minutes"].sum()),
        "cpu_minutes": total_cpu_minutes, "peak_memory_gb": peak_memory,
        "final_output": previous_output,
    }
    return frame, summary


def workflow_payload(name: str, blocks: Sequence[str], parameters: dict[str, object] | None = None) -> dict[str, object]:
    frame, summary = validate_workflow(blocks)
    return {
        "schema": "biointel.workflow.v1", "name": name, "blocks": frame.to_dict(orient="records"),
        "parameters": parameters or {}, "summary": summary,
    }
