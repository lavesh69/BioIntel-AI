from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.calibration import calibration_curve
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .engines import (
    AA20,
    AA_PROPERTIES,
    PART_LIBRARY,
    WORKFLOW_BLOCKS,
    apply_mutations,
    clean_sequence,
    deterministic_rng,
    n50,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def benjamini_hochberg(values: Sequence[float]) -> np.ndarray:
    p = np.asarray(values, dtype=float)
    p = np.where(np.isfinite(p), np.clip(p, 0, 1), 1.0)
    order = np.argsort(p)
    ranked = p[order]
    n = len(p)
    adjusted = np.empty(n, dtype=float)
    running = 1.0
    for index in range(n - 1, -1, -1):
        rank = index + 1
        running = min(running, ranked[index] * n / rank)
        adjusted[index] = running
    out = np.empty(n, dtype=float)
    out[order] = np.clip(adjusted, 0, 1)
    return out


def bootstrap_metric_ci(
    y_true: Sequence[int],
    probabilities: Sequence[float],
    metric: str = "roc_auc",
    iterations: int = 300,
    seed: int = 94,
) -> tuple[float, float, float]:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    rng = deterministic_rng(seed)
    values: list[float] = []
    for _ in range(max(30, int(iterations))):
        idx = rng.integers(0, len(y), size=len(y))
        ys, ps = y[idx], p[idx]
        if len(np.unique(ys)) < 2:
            continue
        if metric == "average_precision":
            values.append(float(average_precision_score(ys, ps)))
        else:
            values.append(float(roc_auc_score(ys, ps)))
    if not values:
        return (float("nan"), float("nan"), float("nan"))
    center = float(average_precision_score(y, p) if metric == "average_precision" else roc_auc_score(y, p))
    return center, float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


# ---------------------------------------------------------------------------
# Pangenome / graph genomics
# ---------------------------------------------------------------------------


def _parse_tags(fields: Sequence[str]) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    for token in fields:
        parts = token.split(":", 2)
        if len(parts) != 3:
            continue
        key, kind, value = parts
        if kind == "i":
            try:
                tags[key] = int(value)
            except ValueError:
                tags[key] = value
        elif kind == "f":
            try:
                tags[key] = float(value)
            except ValueError:
                tags[key] = value
        else:
            tags[key] = value
    return tags


def parse_gfa_extended(text: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    for line_number, raw in enumerate((text or "").splitlines(), start=1):
        if not raw.strip() or raw.startswith("#"):
            continue
        fields = raw.rstrip("\n").split("\t")
        rec = fields[0]
        try:
            if rec == "S" and len(fields) >= 3:
                node = str(fields[1])
                if node in seen_nodes:
                    issues.append({"severity": "error", "line": line_number, "issue": f"Duplicate segment {node}"})
                seen_nodes.add(node)
                seq = "" if fields[2] == "*" else clean_sequence(fields[2], "dna")
                tags = _parse_tags(fields[3:])
                length = len(seq) or int(tags.get("LN", 0) or 0)
                nodes.append({
                    "node": node,
                    "sequence": seq,
                    "length": length,
                    "gc": (100 * (seq.count("G") + seq.count("C")) / len(seq)) if seq else np.nan,
                    "tags": json.dumps(tags, sort_keys=True),
                })
            elif rec == "L" and len(fields) >= 6:
                tags = _parse_tags(fields[6:])
                edges.append({
                    "source": str(fields[1]), "source_orient": fields[2],
                    "target": str(fields[3]), "target_orient": fields[4],
                    "orientation": fields[2] + fields[4], "overlap": fields[5],
                    "record_type": "L", "tags": json.dumps(tags, sort_keys=True),
                })
            elif rec == "E" and len(fields) >= 5:
                # GFA2 edge. Segment orientation is encoded on the identifiers.
                source = fields[2].rstrip("+-")
                target = fields[3].rstrip("+-")
                edges.append({
                    "source": source, "source_orient": fields[2][-1:] if fields[2][-1:] in "+-" else "+",
                    "target": target, "target_orient": fields[3][-1:] if fields[3][-1:] in "+-" else "+",
                    "orientation": (fields[2][-1:] + fields[3][-1:]).replace("*", "+"),
                    "overlap": fields[-1], "record_type": "E", "tags": "{}",
                })
            elif rec == "P" and len(fields) >= 3:
                members = [token.rstrip("+-") for token in fields[2].split(",") if token]
                tags = _parse_tags(fields[4:] if len(fields) > 4 else [])
                paths.append({
                    "path": str(fields[1]), "nodes": ",".join(members), "segment_count": len(members),
                    "sample": str(tags.get("SN", "Uploaded")), "haplotype": str(tags.get("HP", "")),
                    "population": str(tags.get("PO", tags.get("SN", "Uploaded"))),
                    "frequency": float(tags.get("AF", np.nan)) if tags.get("AF") is not None else np.nan,
                    "record_type": "P",
                })
            elif rec == "W" and len(fields) >= 7:
                # GFA1 walk: sample, haplotype, sequence, start, end, walk
                walk_tokens = [token for token in re.split(r"[<>]", fields[6]) if token]
                paths.append({
                    "path": f"{fields[1]}:{fields[2]}:{fields[3]}:{fields[4]}-{fields[5]}",
                    "nodes": ",".join(walk_tokens), "segment_count": len(walk_tokens),
                    "sample": fields[1], "haplotype": fields[2], "population": fields[1],
                    "frequency": np.nan, "record_type": "W",
                })
            elif rec not in {"H", "C", "J", "F", "O", "U"}:
                issues.append({"severity": "warning", "line": line_number, "issue": f"Unsupported record type {rec}"})
        except Exception as exc:  # keep malformed rows visible instead of killing the full import
            issues.append({"severity": "error", "line": line_number, "issue": str(exc)})

    node_frame = pd.DataFrame(nodes)
    edge_frame = pd.DataFrame(edges)
    path_frame = pd.DataFrame(paths)
    issue_frame = pd.DataFrame(issues, columns=["severity", "line", "issue"])
    if node_frame.empty:
        raise ValueError("No GFA segment records were found.")
    if not edge_frame.empty:
        missing = sorted((set(edge_frame["source"]) | set(edge_frame["target"])) - set(node_frame["node"]))
        for node in missing:
            issue_frame.loc[len(issue_frame)] = ["error", 0, f"Edge references missing segment {node}"]
    return node_frame, edge_frame, path_frame, issue_frame


def graph_component_labels(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    labels = nodes["node"].astype(str).tolist()
    adjacency: dict[str, set[str]] = {node: set() for node in labels}
    for row in edges.itertuples(index=False):
        a, b = str(row.source), str(row.target)
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    rows: list[dict[str, Any]] = []
    visited: set[str] = set()
    component = 0
    for start in labels:
        if start in visited:
            continue
        component += 1
        queue = deque([start])
        members: list[str] = []
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            members.append(current)
            queue.extend(sorted(adjacency.get(current, set()) - visited))
        for member in members:
            rows.append({"node": member, "component": component, "component_size": len(members), "degree": len(adjacency.get(member, set()))})
    return pd.DataFrame(rows)


def detect_graph_bubbles(nodes: pd.DataFrame, edges: pd.DataFrame, max_depth: int = 12) -> pd.DataFrame:
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    for row in edges.itertuples(index=False):
        outgoing[str(row.source)].append(str(row.target))
        incoming[str(row.target)].append(str(row.source))
    bubbles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for start, branches in outgoing.items():
        unique_branches = list(dict.fromkeys(branches))
        if len(unique_branches) < 2:
            continue
        reachable: list[dict[str, int]] = []
        for branch in unique_branches[:8]:
            distance = {branch: 0}
            queue = deque([branch])
            while queue:
                current = queue.popleft()
                if distance[current] >= max_depth:
                    continue
                for child in outgoing.get(current, []):
                    if child not in distance:
                        distance[child] = distance[current] + 1
                        queue.append(child)
            reachable.append(distance)
        common = set.intersection(*(set(item) for item in reachable)) if reachable else set()
        common.discard(start)
        if not common:
            continue
        end = min(common, key=lambda node: (max(item[node] for item in reachable), sum(item[node] for item in reachable), node))
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        bubbles.append({
            "start": start, "end": end, "branch_count": len(unique_branches),
            "max_branch_depth": max(item[end] for item in reachable),
            "branch_roots": ",".join(unique_branches),
            "confidence": "high" if len(incoming.get(end, [])) >= 2 else "moderate",
        })
    return pd.DataFrame(bubbles)


def pangenome_quality_report(nodes: pd.DataFrame, edges: pd.DataFrame, paths: pd.DataFrame, issues: pd.DataFrame | None = None) -> dict[str, Any]:
    components = graph_component_labels(nodes, edges)
    bubbles = detect_graph_bubbles(nodes, edges)
    degree = components["degree"] if not components.empty else pd.Series(dtype=float)
    sequence_bp = int(pd.to_numeric(nodes.get("length", 0), errors="coerce").fillna(0).sum())
    path_nodes = set()
    if not paths.empty and "nodes" in paths:
        for value in paths["nodes"].fillna("").astype(str):
            path_nodes.update(token for token in value.split(",") if token)
    represented = len(path_nodes.intersection(set(nodes["node"].astype(str))))
    errors = int((issues["severity"] == "error").sum()) if issues is not None and not issues.empty else 0
    warnings = int((issues["severity"] == "warning").sum()) if issues is not None and not issues.empty else 0
    quality = 100.0
    quality -= min(35, errors * 12)
    quality -= min(15, warnings * 3)
    quality -= 15 if components["component"].nunique() > 1 else 0
    quality -= 10 if len(edges) == 0 else 0
    quality -= 10 if len(paths) == 0 else 0
    quality = max(0.0, quality)
    return {
        "nodes": int(len(nodes)), "edges": int(len(edges)), "paths": int(len(paths)), "sequence_bp": sequence_bp,
        "components": int(components["component"].nunique()) if not components.empty else 0,
        "tips": int((degree <= 1).sum()) if len(degree) else 0,
        "branch_nodes": int((degree >= 3).sum()) if len(degree) else 0,
        "bubble_candidates": int(len(bubbles)),
        "cyclomatic_number": int(max(0, len(edges) - len(nodes) + (components["component"].nunique() if not components.empty else 0))),
        "path_node_coverage": represented / max(1, len(nodes)),
        "quality_score": quality,
        "errors": errors, "warnings": warnings,
        "components_table": components, "bubbles_table": bubbles,
    }


def path_comparison(paths: pd.DataFrame, reference_path: str) -> pd.DataFrame:
    if paths.empty:
        return pd.DataFrame()
    mapping = {str(row.path): [token for token in str(row.nodes).split(",") if token] for row in paths.itertuples(index=False)}
    if reference_path not in mapping:
        raise ValueError("Reference path was not found.")
    ref = mapping[reference_path]
    ref_set = set(ref)
    rows = []
    for name, members in mapping.items():
        member_set = set(members)
        union = len(ref_set | member_set)
        rows.append({
            "path": name,
            "segments": len(members),
            "shared_segments": len(ref_set & member_set),
            "reference_only": len(ref_set - member_set),
            "alternate_only": len(member_set - ref_set),
            "jaccard": len(ref_set & member_set) / max(1, union),
            "order_identity": sum(a == b for a, b in zip(ref, members)) / max(1, max(len(ref), len(members))),
        })
    return pd.DataFrame(rows).sort_values(["jaccard", "order_identity"], ascending=False)


# ---------------------------------------------------------------------------
# Long-read QC and assembly review
# ---------------------------------------------------------------------------


def decode_text_bytes(data: bytes, filename: str = "") -> str:
    if filename.lower().endswith(".gz") or data[:2] == b"\x1f\x8b":
        return gzip.decompress(data).decode("utf-8", errors="replace")
    return data.decode("utf-8", errors="replace")


def parse_fastq_advanced(data: bytes | str, filename: str = "", max_reads: int = 100_000) -> pd.DataFrame:
    text = decode_text_bytes(data, filename) if isinstance(data, (bytes, bytearray)) else str(data)
    handle = io.StringIO(text)
    rows: list[dict[str, Any]] = []
    index = 0
    while index < max_reads:
        header = handle.readline()
        if not header:
            break
        sequence = handle.readline().strip()
        plus = handle.readline()
        quality = handle.readline().strip()
        if not plus:
            break
        if not header.startswith("@") or not plus.startswith("+"):
            continue
        seq = clean_sequence(sequence, "dna")
        if not seq:
            continue
        q = np.asarray([max(0, ord(char) - 33) for char in quality[: len(seq)]], dtype=float)
        rows.append({
            "read": header[1:].strip().split()[0], "length": len(seq),
            "mean_q": float(q.mean()) if len(q) else np.nan,
            "q10_fraction": float((q >= 10).mean()) if len(q) else np.nan,
            "q20_fraction": float((q >= 20).mean()) if len(q) else np.nan,
            "q30_fraction": float((q >= 30).mean()) if len(q) else np.nan,
            "gc": 100 * (seq.count("G") + seq.count("C")) / len(seq),
            "n_fraction": seq.count("N") / len(seq),
        })
        index += 1
    if not rows:
        raise ValueError("No valid FASTQ records were parsed.")
    return pd.DataFrame(rows)


def long_read_qc_metrics(reads: pd.DataFrame, genome_size_mb: float | None = None) -> dict[str, Any]:
    lengths = pd.to_numeric(reads["length"], errors="coerce").dropna().astype(int).tolist()
    total = int(sum(lengths))
    sorted_lengths = sorted(lengths, reverse=True)
    def nx(fraction: float) -> int:
        threshold = total * fraction
        running = 0
        for value in sorted_lengths:
            running += value
            if running >= threshold:
                return int(value)
        return 0
    mean_q = float(pd.to_numeric(reads["mean_q"], errors="coerce").mean())
    q20 = float(pd.to_numeric(reads["q20_fraction"], errors="coerce").mean())
    coverage = total / (float(genome_size_mb) * 1_000_000) if genome_size_mb and genome_size_mb > 0 else np.nan
    grade = "A" if mean_q >= 20 and q20 >= 0.8 else "B" if mean_q >= 15 and q20 >= 0.55 else "C" if mean_q >= 10 else "D"
    return {
        "reads": len(lengths), "bases": total, "n50": nx(0.5), "n90": nx(0.9),
        "median_length": float(np.median(lengths)), "longest": max(lengths),
        "mean_q": mean_q, "q20_base_fraction": q20,
        "mean_gc": float(pd.to_numeric(reads["gc"], errors="coerce").mean()),
        "estimated_coverage": float(coverage) if np.isfinite(coverage) else np.nan,
        "qc_grade": grade,
    }


def contig_qc_advanced(fasta_text: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    records: list[tuple[str, str]] = []
    name = None
    seq: list[str] = []
    for raw in (fasta_text or "").splitlines():
        if raw.startswith(">"):
            if name is not None:
                records.append((name, clean_sequence("".join(seq), "dna")))
            name = raw[1:].strip().split()[0] or f"contig_{len(records)+1}"
            seq = []
        else:
            seq.append(raw.strip())
    if name is not None:
        records.append((name, clean_sequence("".join(seq), "dna")))
    records = [(name, sequence) for name, sequence in records if sequence]
    if not records:
        raise ValueError("No FASTA contigs were found.")
    rows: list[dict[str, Any]] = []
    for name, sequence in records:
        length = len(sequence)
        end_k = min(100, max(20, length // 4))
        overlap = 0
        for k in range(min(200, length // 2), 19, -1):
            if sequence[:k] == sequence[-k:]:
                overlap = k
                break
        rows.append({
            "contig": name, "length": length,
            "gc": 100 * (sequence.count("G") + sequence.count("C")) / length,
            "n_per_100kb": 100_000 * sequence.count("N") / length,
            "left_telomere_hits": sequence[:end_k].count("TTAGGG") + sequence[:end_k].count("CCCTAA"),
            "right_telomere_hits": sequence[-end_k:].count("TTAGGG") + sequence[-end_k:].count("CCCTAA"),
            "terminal_overlap_bp": overlap,
            "circular_candidate": overlap >= 20,
        })
    frame = pd.DataFrame(rows).sort_values("length", ascending=False).reset_index(drop=True)
    lengths = frame["length"].astype(int).tolist()
    total = sum(lengths)
    running = 0
    l50 = 0
    for i, value in enumerate(sorted(lengths, reverse=True), start=1):
        running += value
        if running >= total / 2:
            l50 = i
            break
    au_n = float(sum(value * value for value in lengths) / max(1, total))
    summary = {
        "contigs": len(frame), "total_bp": int(total), "n50": n50(lengths), "l50": l50,
        "auN": au_n, "largest": max(lengths), "mean_gc": float(frame["gc"].mean()),
        "circular_candidates": int(frame["circular_candidate"].sum()),
        "telomere_complete_candidates": int(((frame["left_telomere_hits"] > 0) & (frame["right_telomere_hits"] > 0)).sum()),
        "n_per_100kb": float((frame["n_per_100kb"] * frame["length"]).sum() / max(1, total)),
    }
    return frame, summary


def assembly_command_plan(platform: str, genome_type: str, reads_path: str, output_dir: str, threads: int = 8, hybrid_reads: str | None = None) -> pd.DataFrame:
    p = platform.lower()
    g = genome_type.lower()
    if "hifi" in p:
        assembler, assemble = "hifiasm", f'hifiasm -o "{output_dir}/assembly" -t {threads} "{reads_path}"'
    elif "nanopore" in p:
        size_flag = "--meta" if "meta" in g else ""
        assembler, assemble = "flye", f'flye --nano-hq "{reads_path}" --out-dir "{output_dir}/flye" --threads {threads} {size_flag}'.strip()
    else:
        assembler, assemble = "canu", f'canu -p assembly -d "{output_dir}/canu" genomeSize=auto -pacbio "{reads_path}" maxThreads={threads}'
    rows = [
        {"stage": "Read QC", "tool": "fastqc", "command": f'fastqc -t {threads} -o "{output_dir}/fastqc" "{reads_path}"', "required": True},
        {"stage": "Assembly", "tool": assembler, "command": assemble, "required": True},
        {"stage": "Alignment", "tool": "minimap2", "command": f'minimap2 -x map-ont -t {threads} "{output_dir}/assembly.fasta" "{reads_path}" > "{output_dir}/reads.paf"', "required": True},
        {"stage": "Assembly QC", "tool": "quast", "command": f'quast.py "{output_dir}/assembly.fasta" -o "{output_dir}/quast" -t {threads}', "required": True},
        {"stage": "Completeness", "tool": "busco", "command": f'busco -i "{output_dir}/assembly.fasta" -o busco -m genome -c {threads}', "required": False},
    ]
    if hybrid_reads:
        rows.insert(3, {"stage": "Short-read polish", "tool": "pilon", "command": f'pilon --genome "{output_dir}/assembly.fasta" --frags "{hybrid_reads}" --outdir "{output_dir}/pilon"', "required": False})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Protein design
# ---------------------------------------------------------------------------


HYDROPATHY = {aa: AA_PROPERTIES[aa][0] for aa in AA20}
HELIX_PROPENSITY = {"A": 1.45, "L": 1.34, "M": 1.20, "E": 1.51, "K": 1.23, "Q": 1.17, "H": 1.00, "R": 0.79, "V": 1.14, "I": 1.00, "Y": 0.61, "F": 1.12, "W": 1.14, "T": 0.82, "C": 0.77, "G": 0.53, "N": 0.73, "D": 0.98, "S": 0.79, "P": 0.59}


def protein_properties(sequence: str) -> dict[str, float]:
    seq = clean_sequence(sequence, "protein").replace("X", "").replace("*", "")
    if len(seq) < 2:
        raise ValueError("Protein sequence is too short.")
    try:
        from Bio.SeqUtils.ProtParam import ProteinAnalysis
        analysis = ProteinAnalysis(seq)
        aromaticity = float(analysis.aromaticity())
        instability = float(analysis.instability_index())
        gravy = float(analysis.gravy())
        pI = float(analysis.isoelectric_point())
        mw = float(analysis.molecular_weight())
    except Exception:
        aromaticity = sum(seq.count(aa) for aa in "FWY") / len(seq)
        instability = 40.0
        gravy = float(np.mean([HYDROPATHY.get(aa, 0.0) for aa in seq]))
        pI = 7.0
        mw = float(sum(AA_PROPERTIES.get(aa, (0, 0, 110))[2] for aa in seq) - 18 * (len(seq) - 1))
    charge_proxy = sum(AA_PROPERTIES.get(aa, (0, 0, 0))[1] for aa in seq)
    aggregation_windows = 0
    for start in range(max(0, len(seq) - 6)):
        window = seq[start:start + 7]
        if np.mean([HYDROPATHY.get(aa, 0.0) for aa in window]) > 2.0 and sum(aa in "ILVFWY" for aa in window) >= 5:
            aggregation_windows += 1
    liabilities = sum(seq.count(motif) for motif in ["NG", "NS", "NT", "DG", "DP", "DS", "DT", "M"])
    return {
        "length": float(len(seq)), "molecular_weight": mw, "isoelectric_point": pI,
        "gravy": gravy, "aromaticity": aromaticity, "instability_index": instability,
        "charge_proxy": float(charge_proxy), "aggregation_windows": float(aggregation_windows),
        "sequence_liabilities": float(liabilities),
    }


def _blosum_score(wild: str, mutant: str) -> float:
    try:
        from Bio.Align import substitution_matrices
        matrix = substitution_matrices.load("BLOSUM62")
        return float(matrix[wild, mutant])
    except Exception:
        return 4.0 if wild == mutant else -1.0


def advanced_protein_design(
    sequence: str,
    objective: str,
    locked_positions: Iterable[int] = (),
    target_positions: Iterable[int] = (),
    top_n: int = 100,
) -> pd.DataFrame:
    seq = clean_sequence(sequence, "protein").replace("X", "").replace("*", "")
    if len(seq) < 8:
        raise ValueError("Protein sequence must contain at least eight standard amino acids.")
    locked = {int(x) for x in locked_positions}
    targets = {int(x) for x in target_positions}
    objective = objective.lower()
    rows: list[dict[str, Any]] = []
    for position, wild in enumerate(seq, start=1):
        if position in locked or (targets and position not in targets):
            continue
        local = seq[max(0, position - 5): min(len(seq), position + 4)]
        local_hydrophobic = float(np.mean([HYDROPATHY.get(aa, 0.0) for aa in local]))
        local_charge = float(sum(AA_PROPERTIES.get(aa, (0, 0, 0))[1] for aa in local))
        for mutant in AA20:
            if mutant == wild:
                continue
            blosum = _blosum_score(wild, mutant)
            hydro_delta = HYDROPATHY[mutant] - HYDROPATHY[wild]
            charge_delta = AA_PROPERTIES[mutant][1] - AA_PROPERTIES[wild][1]
            helix_delta = HELIX_PROPENSITY[mutant] - HELIX_PROPENSITY[wild]
            conservative = 1 / (1 + math.exp(-(blosum + 1) / 2))
            stability = 0.55 * conservative - 0.16 * abs(hydro_delta) + 0.10 * helix_delta
            solubility = -0.35 * hydro_delta + 0.18 * abs(charge_delta) - 0.08 * max(0, local_hydrophobic - 1.5)
            aggregation = -0.35 * max(0, HYDROPATHY[mutant] - 2.0) - 0.18 * max(0, local_hydrophobic - 1.6)
            electrostatic = -0.12 * abs(local_charge + charge_delta) + 0.10 * abs(local_charge)
            target_bonus = 0.35 if position in targets else 0.0
            motif_penalty = 0.0
            context_mut = list(seq)
            context_mut[position - 1] = mutant
            mut_seq = "".join(context_mut)
            for motif in ["NG", "NS", "NT", "DG", "DP"]:
                if mut_seq[max(0, position - 3):position + 2].count(motif) > seq[max(0, position - 3):position + 2].count(motif):
                    motif_penalty -= 0.25
            if objective.startswith("stability"):
                score = 0.60 * stability + 0.18 * solubility + 0.12 * aggregation + 0.10 * electrostatic + target_bonus + motif_penalty
            elif objective.startswith("solubility"):
                score = 0.55 * solubility + 0.20 * stability + 0.15 * aggregation + 0.10 * electrostatic + target_bonus + motif_penalty
            elif objective.startswith("binding"):
                score = 0.35 * stability + 0.18 * solubility + 0.12 * electrostatic + 0.55 * target_bonus + 0.10 * conservative + motif_penalty
            else:
                score = 0.34 * stability + 0.30 * solubility + 0.18 * aggregation + 0.10 * electrostatic + 0.08 * conservative + target_bonus + motif_penalty
            uncertainty = min(0.95, 0.25 + 0.08 * abs(hydro_delta) + (0.22 if blosum < -2 else 0) + (0.15 if position in {1, len(seq)} else 0))
            rows.append({
                "mutation": f"{wild}{position}{mutant}", "position": position, "wild": wild, "mutant": mutant,
                "design_score": score, "stability_score": stability, "solubility_score": solubility,
                "aggregation_score": aggregation, "electrostatic_score": electrostatic,
                "blosum62": blosum, "conservative_probability": conservative,
                "uncertainty": uncertainty, "confidence": 1 - uncertainty,
                "target_position": position in targets,
                "risk_flag": "high-change" if blosum <= -3 or abs(hydro_delta) > 5 else "review" if blosum < 0 else "conservative",
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    # Pareto front: maximise stability and solubility, minimise uncertainty.
    values = frame[["stability_score", "solubility_score", "confidence"]].to_numpy()
    pareto = np.ones(len(frame), dtype=bool)
    for i in range(len(frame)):
        dominates = np.all(values >= values[i], axis=1) & np.any(values > values[i], axis=1)
        if dominates.any():
            pareto[i] = False
    frame["pareto_optimal"] = pareto
    return frame.sort_values(["pareto_optimal", "design_score", "confidence"], ascending=[False, False, False]).head(int(top_n)).reset_index(drop=True)


def parse_pdb_residues(text: str) -> pd.DataFrame:
    aa3 = {
        "ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G","HIS":"H","ILE":"I",
        "LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V",
    }
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in (text or "").splitlines():
        if not raw.startswith(("ATOM  ", "HETATM")) or raw[12:16].strip() != "CA":
            continue
        residue = raw[17:20].strip()
        chain = raw[21:22].strip() or "_"
        number = raw[22:26].strip()
        insertion = raw[26:27].strip()
        key = (chain, number, insertion)
        if key in seen:
            continue
        seen.add(key)
        try:
            x, y, z = float(raw[30:38]), float(raw[38:46]), float(raw[46:54])
        except ValueError:
            continue
        rows.append({"chain": chain, "residue_number": int(number), "insertion": insertion, "residue": aa3.get(residue, "X"), "x": x, "y": y, "z": z})
    return pd.DataFrame(rows)


def compare_protein_design(sequence: str, mutations: Sequence[str]) -> pd.DataFrame:
    wild = clean_sequence(sequence, "protein").replace("X", "").replace("*", "")
    designed = apply_mutations(wild, mutations)
    before, after = protein_properties(wild), protein_properties(designed)
    rows = []
    for metric in before:
        rows.append({"metric": metric, "wild_type": before[metric], "designed": after[metric], "delta": after[metric] - before[metric]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CRISPR screens and Perturb-seq
# ---------------------------------------------------------------------------


def crispr_replicate_analysis(
    frame: pd.DataFrame,
    control_columns: Sequence[str] | None = None,
    treated_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Replicate-aware pooled CRISPR screen analysis.

    Step 95 uses median-ratio library normalization and an over-dispersed
    negative-binomial Wald approximation at guide level, followed by weighted
    Stouffer aggregation and BH-FDR at gene level. This is a transparent local
    screening model; MAGeCK/edgeR/DESeq2 remain preferred for publication-grade
    specialist analyses.
    """
    data = frame.copy()
    if not {"guide", "gene"}.issubset(data.columns):
        raise ValueError("Guide table must contain guide and gene columns.")
    control_columns = list(control_columns or [c for c in data.columns if c.lower().startswith("control")])
    treated_columns = list(treated_columns or [c for c in data.columns if c.lower().startswith("treated")])
    if not control_columns and "control" in data:
        control_columns = ["control"]
    if not treated_columns and "treated" in data:
        treated_columns = ["treated"]
    if not control_columns or not treated_columns:
        raise ValueError("At least one control and one treated count column are required.")
    count_columns = control_columns + treated_columns
    for column in count_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0).clip(lower=0)
    counts = data[count_columns].astype(float)

    # DESeq-style median-ratio size factors with a library-size fallback.
    positive = counts.replace(0, np.nan)
    geometric = np.exp(np.log(positive).mean(axis=1, skipna=True))
    ratios = counts.div(geometric.replace(0, np.nan), axis=0)
    size_factors = ratios.replace([np.inf, -np.inf], np.nan).median(axis=0, skipna=True)
    fallback = counts.sum(axis=0) / max(float(counts.sum(axis=0).median()), 1.0)
    size_factors = size_factors.replace(0, np.nan).fillna(fallback).replace(0, 1.0)
    normalized = counts.div(size_factors, axis=1)

    control_values = normalized[control_columns].to_numpy(dtype=float)
    treated_values = normalized[treated_columns].to_numpy(dtype=float)
    control_mean = control_values.mean(axis=1)
    treated_mean = treated_values.mean(axis=1)
    control_var = control_values.var(axis=1, ddof=1) if len(control_columns) > 1 else control_mean
    treated_var = treated_values.var(axis=1, ddof=1) if len(treated_columns) > 1 else treated_mean
    pooled_mean = np.maximum((control_mean + treated_mean) / 2.0, 1e-8)
    pooled_var = np.maximum((control_var + treated_var) / 2.0, pooled_mean)
    raw_dispersion = np.maximum((pooled_var - pooled_mean) / np.maximum(pooled_mean**2, 1e-8), 1e-6)
    # Shrink noisy guide dispersions toward the global median.
    global_dispersion = float(np.nanmedian(raw_dispersion[np.isfinite(raw_dispersion)])) if np.isfinite(raw_dispersion).any() else 0.05
    dispersion = 0.35 * raw_dispersion + 0.65 * max(global_dispersion, 1e-6)
    pseudocount = 0.5
    log2_fc = np.log2((treated_mean + pseudocount) / (control_mean + pseudocount))
    var_log = (
        1.0 / (len(treated_columns) * (treated_mean + pseudocount))
        + 1.0 / (len(control_columns) * (control_mean + pseudocount))
        + dispersion * (1.0 / len(treated_columns) + 1.0 / len(control_columns))
    ) / (math.log(2) ** 2)
    standard_error = np.sqrt(np.maximum(var_log, 1e-12))
    z_scores = log2_fc / standard_error
    p_values = 2 * stats.norm.sf(np.abs(z_scores))

    data["control_normalized_mean"] = control_mean
    data["treated_normalized_mean"] = treated_mean
    data["control_mean_logcpm"] = np.log2(control_mean + 1)
    data["treated_mean_logcpm"] = np.log2(treated_mean + 1)
    data["log2_fc"] = log2_fc
    data["standard_error"] = standard_error
    data["wald_z"] = z_scores
    data["dispersion"] = dispersion
    data["baseline_count"] = counts[control_columns].mean(axis=1)
    baseline_threshold = max(20.0, float(np.quantile(data["baseline_count"], 0.05)))
    data["guide_qc_pass"] = data["baseline_count"] >= baseline_threshold
    if "efficiency" in data:
        efficiency = pd.to_numeric(data["efficiency"], errors="coerce")
        data["guide_qc_pass"] &= efficiency.fillna(0) >= 0.2
    if "off_target_score" in data:
        off_target = pd.to_numeric(data["off_target_score"], errors="coerce")
        data["guide_qc_pass"] &= off_target.fillna(0) >= 0.2
    data["p_value"] = np.where(np.isfinite(p_values), p_values, 1.0)
    data["fdr"] = benjamini_hochberg(data["p_value"])

    gene_rows: list[dict[str, Any]] = []
    for gene, group in data.groupby("gene", sort=False):
        signs = np.sign(group["log2_fc"].to_numpy(dtype=float))
        z = stats.norm.isf(np.clip(group["p_value"].to_numpy(dtype=float) / 2, 1e-15, 1 - 1e-15)) * signs
        weights = np.sqrt(np.maximum(group["baseline_count"].to_numpy(dtype=float), 1.0))
        combined_z = float(np.sum(weights * z) / math.sqrt(max(float(np.sum(weights**2)), 1e-12)))
        combined_p = float(2 * stats.norm.sf(abs(combined_z)))
        sign_consistency = float(max((group["log2_fc"] > 0).mean(), (group["log2_fc"] < 0).mean()))
        gene_rows.append({
            "gene": gene,
            "guides": len(group),
            "passing_guides": int(group["guide_qc_pass"].sum()),
            "median_log2_fc": float(group["log2_fc"].median()),
            "mean_log2_fc": float(group["log2_fc"].mean()),
            "combined_z": combined_z,
            "p_value": combined_p,
            "guide_consistency": sign_consistency,
            "median_baseline": float(group["baseline_count"].median()),
            "median_dispersion": float(group["dispersion"].median()),
        })
    genes = pd.DataFrame(gene_rows)
    genes["fdr"] = benjamini_hochberg(genes["p_value"])
    genes["minus_log10_fdr"] = -np.log10(np.clip(genes["fdr"], 1e-15, 1))
    genes["hit_class"] = np.select(
        [
            (genes["fdr"] <= 0.05) & (genes["median_log2_fc"] <= -0.5) & (genes["guide_consistency"] >= 0.6),
            (genes["fdr"] <= 0.05) & (genes["median_log2_fc"] >= 0.5) & (genes["guide_consistency"] >= 0.6),
        ],
        ["Negative-selection hit", "Positive-selection hit"],
        default="Background",
    )
    genes = genes.sort_values(["fdr", "median_log2_fc"], ascending=[True, True]).reset_index(drop=True)
    metrics = {
        "guides": len(data),
        "genes": int(data["gene"].nunique()),
        "control_replicates": len(control_columns),
        "treated_replicates": len(treated_columns),
        "qc_pass_rate": float(data["guide_qc_pass"].mean()),
        "negative_hits": int((genes["hit_class"] == "Negative-selection hit").sum()),
        "positive_hits": int((genes["hit_class"] == "Positive-selection hit").sum()),
        "median_library_size": float(counts.sum(axis=0).median()),
        "normalization": "median_ratio",
        "guide_model": "negative_binomial_wald_approximation",
        "global_dispersion": global_dispersion,
        "size_factors": {str(key): float(value) for key, value in size_factors.items()},
    }
    return data, genes, metrics


def crispr_pathway_enrichment(
    hit_genes: Sequence[str],
    gene_sets: pd.DataFrame,
    background_genes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Hypergeometric pathway enrichment with BH-FDR.

    ``gene_sets`` must contain ``pathway`` and ``gene`` columns. The function
    deliberately requires an explicit or derivable background universe to avoid
    inflated enrichment from an undefined reference set.
    """
    if not {"pathway", "gene"}.issubset(gene_sets.columns):
        raise ValueError("Gene-set table must contain pathway and gene columns.")
    sets = gene_sets[["pathway", "gene"]].dropna().astype(str).drop_duplicates()
    hits = {str(value) for value in hit_genes if str(value)}
    universe = {str(value) for value in (background_genes or sets["gene"].tolist()) if str(value)}
    hits &= universe
    if not hits or not universe:
        return pd.DataFrame(columns=["pathway", "set_size", "hits", "hit_genes", "p_value", "fdr", "fold_enrichment"])
    rows = []
    population = len(universe)
    draws = len(hits)
    for pathway, group in sets.groupby("pathway", sort=False):
        members = set(group["gene"]) & universe
        overlap = sorted(hits & members)
        if not overlap:
            continue
        p_value = float(stats.hypergeom.sf(len(overlap) - 1, population, len(members), draws))
        expected = draws * len(members) / max(population, 1)
        rows.append({
            "pathway": pathway,
            "set_size": len(members),
            "hits": len(overlap),
            "hit_genes": ", ".join(overlap),
            "p_value": p_value,
            "fold_enrichment": len(overlap) / max(expected, 1e-12),
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=["pathway", "set_size", "hits", "hit_genes", "p_value", "fdr", "fold_enrichment"])
    result["fdr"] = benjamini_hochberg(result["p_value"])
    return result.sort_values(["fdr", "p_value", "fold_enrichment"], ascending=[True, True, False]).reset_index(drop=True)

def perturbseq_advanced(matrix: pd.DataFrame, labels: Sequence[str], control_label: str = "NTC", seed: int = 94) -> dict[str, Any]:
    numeric = matrix.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    numeric = numeric.fillna(numeric.median()).fillna(0)
    labels_series = pd.Series(list(labels), name="perturbation")
    if len(numeric) != len(labels_series):
        raise ValueError("Expression rows and guide labels must have the same length.")
    scaled = StandardScaler().fit_transform(numeric)
    from sklearn.decomposition import PCA
    pca = PCA(n_components=min(10, numeric.shape[1], max(2, numeric.shape[0] - 1)), random_state=seed)
    pcs = pca.fit_transform(scaled)
    embedding = pd.DataFrame({"PC1": pcs[:, 0], "PC2": pcs[:, 1], "perturbation": labels_series})
    method = "PCA"
    try:
        import umap
        reducer = umap.UMAP(n_neighbors=min(15, max(3, len(numeric) // 10)), min_dist=0.25, random_state=seed)
        xy = reducer.fit_transform(pcs[:, : min(10, pcs.shape[1])])
        embedding["UMAP1"] = xy[:, 0]
        embedding["UMAP2"] = xy[:, 1]
        method = "UMAP"
    except Exception:
        embedding["UMAP1"] = embedding["PC1"]
        embedding["UMAP2"] = embedding["PC2"]
    control_mask = labels_series.astype(str) == str(control_label)
    if not control_mask.any():
        control_mask = labels_series.astype(str) == labels_series.astype(str).mode().iloc[0]
        control_label = str(labels_series[control_mask].iloc[0])
    de_rows: list[dict[str, Any]] = []
    control = numeric.loc[control_mask.to_numpy()]
    for perturbation in sorted(labels_series.astype(str).unique()):
        if perturbation == control_label:
            continue
        group = numeric.loc[(labels_series.astype(str) == perturbation).to_numpy()]
        for feature in numeric.columns:
            stat = stats.ttest_ind(group[feature], control[feature], equal_var=False, nan_policy="omit")
            de_rows.append({
                "perturbation": perturbation, "feature": feature,
                "mean_shift": float(group[feature].mean() - control[feature].mean()),
                "p_value": float(stat.pvalue) if np.isfinite(stat.pvalue) else 1.0,
            })
    de = pd.DataFrame(de_rows)
    if not de.empty:
        de["fdr"] = de.groupby("perturbation")["p_value"].transform(lambda s: benjamini_hochberg(s.to_numpy()))
        de["minus_log10_fdr"] = -np.log10(np.clip(de["fdr"], 1e-15, 1))
    return {
        "embedding": embedding, "differential": de,
        "variance_explained": pca.explained_variance_ratio_, "embedding_method": method,
        "control_label": control_label,
    }


# ---------------------------------------------------------------------------
# Outbreak genomics
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def outbreak_advanced(
    samples: pd.DataFrame,
    distances: pd.DataFrame,
    snp_threshold: float = 12,
    day_threshold: int = 30,
    distance_km_threshold: float = 50.0,
) -> dict[str, Any]:
    required = {"sample_id", "collection_date", "latitude", "longitude"}
    missing = required - set(samples.columns)
    if missing:
        raise ValueError(f"Sample metadata is missing: {', '.join(sorted(missing))}")
    data = samples.copy()
    data["sample_id"] = data["sample_id"].astype(str)
    data["collection_date"] = pd.to_datetime(data["collection_date"], errors="coerce")
    if data["collection_date"].isna().any():
        raise ValueError("One or more collection dates could not be parsed.")
    ids = data["sample_id"].tolist()
    matrix = distances.copy()
    if "sample_id" in matrix.columns:
        matrix = matrix.set_index("sample_id")
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    matrix = matrix.reindex(index=ids, columns=ids)
    if matrix.isna().any().any():
        raise ValueError("Distance matrix must contain every sample ID in rows and columns.")
    parent = {sample: sample for sample in ids}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    candidate_links: list[dict[str, Any]] = []
    sample_lookup = data.set_index("sample_id")
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            snp = float(matrix.loc[a, b])
            ra, rb = sample_lookup.loc[a], sample_lookup.loc[b]
            days = abs((ra["collection_date"] - rb["collection_date"]).days)
            km = haversine_km(float(ra["latitude"]), float(ra["longitude"]), float(rb["latitude"]), float(rb["longitude"]))
            genomic = snp <= snp_threshold
            temporal = days <= day_threshold
            spatial = km <= distance_km_threshold
            if genomic:
                union(a, b)
            if genomic or (temporal and spatial):
                score = 0.55 * max(0.0, 1 - snp / max(1, snp_threshold * 2)) + 0.25 * max(0.0, 1 - days / max(1, day_threshold * 2)) + 0.20 * max(0.0, 1 - km / max(1, distance_km_threshold * 2))
                candidate_links.append({
                    "source": a, "target": b, "snp_distance": snp, "days_apart": days, "distance_km": km,
                    "genomic_link": genomic, "temporal_link": temporal, "spatial_link": spatial,
                    "link_score": score,
                })
    roots: dict[str, int] = {}
    labels = []
    for sample in ids:
        root = find(sample)
        roots.setdefault(root, len(roots) + 1)
        labels.append(f"Cluster {roots[root]}")
    clustered = data.copy()
    clustered["outbreak_cluster"] = labels
    clustered["cluster_size"] = clustered.groupby("outbreak_cluster")["sample_id"].transform("count")
    links = pd.DataFrame(candidate_links)
    # Kruskal minimum spanning forest per provisional genomic cluster.
    mst_rows: list[dict[str, Any]] = []
    for cluster, group in clustered.groupby("outbreak_cluster"):
        members = group["sample_id"].tolist()
        edges = []
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                edges.append((float(matrix.loc[a, b]), a, b))
        p = {x: x for x in members}
        def f(x: str) -> str:
            while p[x] != x:
                p[x] = p[p[x]]
                x = p[x]
            return x
        for weight, a, b in sorted(edges):
            ra, rb = f(a), f(b)
            if ra != rb:
                p[rb] = ra
                mst_rows.append({"cluster": cluster, "source": a, "target": b, "snp_distance": weight})
    mst = pd.DataFrame(mst_rows)
    cluster_summary = clustered.groupby("outbreak_cluster", as_index=False).agg(
        samples=("sample_id", "count"), first_date=("collection_date", "min"), last_date=("collection_date", "max"),
        locations=("location", "nunique") if "location" in clustered.columns else ("sample_id", "count"),
        amr_positive=("amr_gene", lambda s: int((s.astype(str).str.lower() != "none").sum())) if "amr_gene" in clustered.columns else ("sample_id", "count"),
    )
    cluster_summary["duration_days"] = (cluster_summary["last_date"] - cluster_summary["first_date"]).dt.days
    return {"samples": clustered, "links": links, "mst": mst, "cluster_summary": cluster_summary, "distance_matrix": matrix}


def distance_tree_newick(distances: pd.DataFrame, method: str = "nj") -> str:
    """Build a reproducible Newick tree from a complete symmetric distance matrix.

    The helper uses BioPython when available and performs strict matrix checks so a
    visually plausible tree cannot be produced from malformed input.
    """
    matrix = distances.copy()
    if "sample_id" in matrix.columns:
        matrix = matrix.set_index("sample_id")
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    if set(matrix.index) != set(matrix.columns):
        raise ValueError("Distance matrix row and column identifiers must match.")
    matrix = matrix.reindex(index=matrix.index, columns=matrix.index).astype(float)
    if matrix.isna().any().any():
        raise ValueError("Distance matrix contains missing or non-numeric values.")
    values = matrix.to_numpy(dtype=float)
    if not np.allclose(values, values.T, atol=1e-8):
        raise ValueError("Distance matrix must be symmetric.")
    if np.any(values < 0):
        raise ValueError("Distance matrix cannot contain negative distances.")
    if not np.allclose(np.diag(values), 0.0, atol=1e-8):
        raise ValueError("Distance matrix diagonal must be zero.")
    try:
        from Bio import Phylo
        from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor
    except Exception as exc:  # pragma: no cover - dependency is present in release wheelhouse
        raise RuntimeError("BioPython is required for phylogenetic tree construction.") from exc
    names = list(matrix.index)
    lower = [[float(values[i, j]) for j in range(i + 1)] for i in range(len(names))]
    dm = DistanceMatrix(names=names, matrix=lower)
    constructor = DistanceTreeConstructor()
    method_normalized = str(method).strip().lower()
    tree = constructor.upgma(dm) if method_normalized == "upgma" else constructor.nj(dm)
    handle = io.StringIO()
    Phylo.write(tree, handle, "newick")
    return handle.getvalue().strip()


def newick_tree_layout(newick: str) -> dict[str, pd.DataFrame]:
    """Convert a Newick tree into deterministic node/edge tables for plotting."""
    text = str(newick or "").strip()
    if not text:
        raise ValueError("Newick tree is empty.")
    try:
        from Bio import Phylo
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("BioPython is required for Newick parsing.") from exc
    tree = Phylo.read(io.StringIO(text), "newick")
    depths = tree.depths()
    if not max(depths.values(), default=0.0):
        depths = tree.depths(unit_branch_lengths=True)
    terminals = tree.get_terminals()
    terminal_y = {clade: float(index) for index, clade in enumerate(reversed(terminals))}
    y_positions: dict[Any, float] = {}

    def assign_y(clade: Any) -> float:
        if clade in terminal_y:
            value = terminal_y[clade]
        else:
            children = [assign_y(child) for child in clade.clades]
            value = float(np.mean(children)) if children else 0.0
        y_positions[clade] = value
        return value

    assign_y(tree.root)
    node_ids: dict[Any, str] = {}
    nodes: list[dict[str, Any]] = []
    for index, clade in enumerate(tree.find_clades(order="preorder")):
        node_id = f"node_{index}"
        node_ids[clade] = node_id
        nodes.append({
            "node_id": node_id,
            "label": str(clade.name or ""),
            "x": float(depths.get(clade, 0.0)),
            "y": float(y_positions.get(clade, 0.0)),
            "is_terminal": bool(clade.is_terminal()),
            "confidence": float(clade.confidence) if clade.confidence is not None else np.nan,
        })
    edges: list[dict[str, Any]] = []
    for parent in tree.find_clades(order="preorder"):
        for child in parent.clades:
            edges.append({
                "source": node_ids[parent],
                "target": node_ids[child],
                "x0": float(depths.get(parent, 0.0)),
                "y0": float(y_positions.get(parent, 0.0)),
                "x1": float(depths.get(child, 0.0)),
                "y1": float(y_positions.get(child, 0.0)),
                "branch_length": float(child.branch_length or 0.0),
            })
    return {"nodes": pd.DataFrame(nodes), "edges": pd.DataFrame(edges)}


# ---------------------------------------------------------------------------
# Synthetic biology
# ---------------------------------------------------------------------------


CODON_USAGE = {
    "E. coli": {
        "A":"GCG","R":"CGT","N":"AAC","D":"GAT","C":"TGC","Q":"CAG","E":"GAA","G":"GGC","H":"CAC","I":"ATT",
        "L":"CTG","K":"AAA","M":"ATG","F":"TTT","P":"CCG","S":"TCT","T":"ACC","W":"TGG","Y":"TAT","V":"GTG","*":"TAA",
    },
    "Human": {
        "A":"GCC","R":"CGC","N":"AAC","D":"GAC","C":"TGC","Q":"CAG","E":"GAG","G":"GGC","H":"CAC","I":"ATC",
        "L":"CTG","K":"AAG","M":"ATG","F":"TTC","P":"CCC","S":"AGC","T":"ACC","W":"TGG","Y":"TAC","V":"GTG","*":"TGA",
    },
    "S. cerevisiae": {
        "A":"GCT","R":"AGA","N":"AAC","D":"GAT","C":"TGT","Q":"CAA","E":"GAA","G":"GGT","H":"CAT","I":"ATT",
        "L":"TTG","K":"AAA","M":"ATG","F":"TTT","P":"CCA","S":"TCT","T":"ACT","W":"TGG","Y":"TAT","V":"GTT","*":"TAA",
    },
}


def translate_dna(sequence: str) -> str:
    try:
        from Bio.Seq import Seq
        return str(Seq(clean_sequence(sequence, "dna").replace("U", "T")).translate(to_stop=False))
    except Exception:
        return ""


def codon_optimize(sequence: str, host: str = "E. coli") -> dict[str, Any]:
    dna = clean_sequence(sequence, "dna").replace("U", "T")
    if len(dna) % 3 != 0:
        raise ValueError("Coding sequence length must be divisible by three.")
    protein = translate_dna(dna)
    usage = CODON_USAGE.get(host, CODON_USAGE["E. coli"])
    optimized = "".join(usage.get(aa, codon) for aa, codon in zip(protein, [dna[i:i+3] for i in range(0, len(dna), 3)]))
    return {
        "host": host, "original": dna, "optimized": optimized, "protein": protein,
        "original_gc": 100 * (dna.count("G") + dna.count("C")) / max(1, len(dna)),
        "optimized_gc": 100 * (optimized.count("G") + optimized.count("C")) / max(1, len(optimized)),
        "sequence_identity": sum(a == b for a, b in zip(dna, optimized)) / max(1, len(dna)),
    }


def construct_quality(sequence: str, window: int = 50) -> dict[str, Any]:
    seq = clean_sequence(sequence, "dna").replace("U", "T")
    restriction = {"EcoRI":"GAATTC","BamHI":"GGATCC","HindIII":"AAGCTT","BsaI":"GGTCTC","BsmBI":"CGTCTC","NotI":"GCGGCCGC"}
    sites = []
    for enzyme, motif in restriction.items():
        for match in re.finditer(f"(?={motif})", seq):
            sites.append({"enzyme": enzyme, "position": match.start() + 1, "motif": motif})
    gc_windows = []
    step = max(10, window // 2)
    for start in range(0, max(1, len(seq) - window + 1), step):
        chunk = seq[start:start + window]
        gc_windows.append({"start": start + 1, "end": start + len(chunk), "gc": 100 * (chunk.count("G") + chunk.count("C")) / max(1, len(chunk))})
    homopolymers = []
    for match in re.finditer(r"(A{7,}|C{7,}|G{7,}|T{7,})", seq):
        homopolymers.append({"position": match.start() + 1, "sequence": match.group(0), "length": len(match.group(0))})
    repeats = []
    k = 12
    seen: dict[str, int] = {}
    for i in range(max(0, len(seq) - k + 1)):
        token = seq[i:i+k]
        if token in seen and i - seen[token] >= k:
            repeats.append({"motif": token, "first": seen[token] + 1, "second": i + 1})
        else:
            seen[token] = i
    gc_values = [row["gc"] for row in gc_windows] or [0]
    score = 100.0 - min(30, len(homopolymers) * 8) - min(25, len(repeats) * 2) - min(25, sum(gc < 25 or gc > 75 for gc in gc_values) * 5)
    return {
        "length": len(seq), "gc": 100 * (seq.count("G") + seq.count("C")) / max(1, len(seq)),
        "quality_score": max(0.0, score), "restriction_sites": pd.DataFrame(sites),
        "gc_windows": pd.DataFrame(gc_windows), "homopolymers": pd.DataFrame(homopolymers),
        "repeats": pd.DataFrame(repeats).drop_duplicates() if repeats else pd.DataFrame(columns=["motif","first","second"]),
    }


def gibson_primer_plan(parts: Sequence[str], overlap_bp: int = 25, primer_body_bp: int = 20) -> pd.DataFrame:
    selected = [(name, PART_LIBRARY[name]) for name in parts if name in PART_LIBRARY]
    if not selected:
        return pd.DataFrame()
    complement = str.maketrans("ACGT", "TGCA")
    rows = []
    for index, (name, seq) in enumerate(selected):
        previous = selected[index - 1][1] if index > 0 else ""
        following = selected[index + 1][1] if index < len(selected) - 1 else ""
        left_overlap = previous[-overlap_bp:] if previous else ""
        right_overlap = following[:overlap_bp] if following else ""
        forward = left_overlap + seq[:primer_body_bp]
        reverse_body = seq[-primer_body_bp:].translate(complement)[::-1]
        reverse_overlap = right_overlap.translate(complement)[::-1]
        reverse = reverse_overlap + reverse_body
        rows.append({"part": name, "forward_primer": forward, "reverse_primer": reverse, "forward_length": len(forward), "reverse_length": len(reverse)})
    return pd.DataFrame(rows)


def genbank_flatfile(name: str, sequence: str, architecture: pd.DataFrame) -> str:
    seq = clean_sequence(sequence, "dna").replace("U", "T").lower()
    lines = [f"LOCUS       {name[:16]:<16}{len(seq):>11} bp    DNA     linear   SYN 09-JUL-2026", "FEATURES             Location/Qualifiers"]
    for row in architecture.itertuples(index=False):
        lines.append(f"     misc_feature    {int(row.start)+1}..{int(row.end)}")
        lines.append(f"                     /label=\"{row.part}\"")
    lines.extend(["ORIGIN"])
    for start in range(0, len(seq), 60):
        chunk = seq[start:start+60]
        groups = " ".join(chunk[i:i+10] for i in range(0, len(chunk), 10))
        lines.append(f"{start+1:>9} {groups}")
    lines.append("//")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Rare-disease research interpretation
# ---------------------------------------------------------------------------


def parse_vcf_extended(text: str) -> pd.DataFrame:
    samples: list[str] = []
    rows: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        if raw.startswith("#CHROM"):
            fields = raw.split("\t")
            samples = fields[9:]
            continue
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) < 8:
            continue
        info: dict[str, Any] = {}
        for token in fields[7].split(";"):
            key, _, value = token.partition("=")
            info[key] = value if value else True
        fmt_keys = fields[8].split(":") if len(fields) > 8 else []
        sample_values = fields[9:] if len(fields) > 9 else []
        genotype_map = {}
        for sample, value in zip(samples, sample_values):
            genotype_map[sample] = dict(zip(fmt_keys, value.split(":")))
        first_gt = next((entry.get("GT", "") for entry in genotype_map.values()), "")
        zygosity = "homozygous" if first_gt in {"1/1", "1|1"} else "heterozygous" if "1" in first_gt else "reference/unknown"
        ann = str(info.get("ANN", info.get("CSQ", "unknown"))).split(",")[0]
        ann_fields = ann.split("|")
        consequence = ann_fields[1] if len(ann_fields) > 1 and info.get("ANN") else ann_fields[0]
        gene = str(info.get("GENE", info.get("SYMBOL", ann_fields[3] if len(ann_fields) > 3 else "Unknown")))
        rows.append({
            "chrom": fields[0], "pos": int(fields[1]), "id": fields[2], "ref": fields[3], "alt": fields[4].split(",")[0],
            "qual": pd.to_numeric(fields[5], errors="coerce"), "filter": fields[6], "gene": gene,
            "consequence": consequence or "unknown", "gnomad_af": float(str(info.get("GNOMAD_AF", info.get("AF", 0))).split(",")[0] or 0),
            "clinvar": str(info.get("CLNSIG", "Not provided")).replace("_", " "),
            "cadd": pd.to_numeric(info.get("CADD", info.get("CADD_PHRED", np.nan)), errors="coerce"),
            "revel": pd.to_numeric(info.get("REVEL", np.nan), errors="coerce"),
            "spliceai": pd.to_numeric(str(info.get("SPLICEAI", np.nan)).split("|")[-1], errors="coerce"),
            "zygosity": zygosity, "inheritance": str(info.get("INHERITANCE", "unknown")),
            "sample_genotypes": json.dumps(genotype_map, sort_keys=True),
        })
    if not rows:
        raise ValueError("No variants could be parsed from the VCF.")
    return pd.DataFrame(rows)



def trio_segregation_assessment(
    frame: pd.DataFrame,
    *,
    proband: str,
    mother: str,
    father: str,
) -> pd.DataFrame:
    """Annotate multi-sample VCF rows with transparent Mendelian segregation checks."""
    data = frame.copy()
    if "sample_genotypes" not in data.columns:
        raise ValueError("Trio assessment requires the sample_genotypes field from a multi-sample VCF.")

    def alleles(value: Any) -> tuple[int | None, int | None]:
        gt = str(value or "").split(":", 1)[0].replace("|", "/")
        pieces = gt.split("/")
        if len(pieces) != 2:
            return (None, None)
        parsed: list[int | None] = []
        for piece in pieces:
            try:
                parsed.append(int(piece) if piece != "." else None)
            except ValueError:
                parsed.append(None)
        return parsed[0], parsed[1]

    rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        try:
            calls = json.loads(str(row.get("sample_genotypes", "{}")))
        except json.JSONDecodeError:
            calls = {}
        p_gt = alleles((calls.get(proband) or {}).get("GT", ""))
        m_gt = alleles((calls.get(mother) or {}).get("GT", ""))
        f_gt = alleles((calls.get(father) or {}).get("GT", ""))
        p_alt = any(value not in {None, 0} for value in p_gt)
        m_alt = any(value not in {None, 0} for value in m_gt)
        f_alt = any(value not in {None, 0} for value in f_gt)
        p_hom_alt = p_gt[0] not in {None, 0} and p_gt[0] == p_gt[1]
        m_het = 0 in m_gt and any(value not in {None, 0} for value in m_gt)
        f_het = 0 in f_gt and any(value not in {None, 0} for value in f_gt)
        complete = all(value is not None for gt in (p_gt, m_gt, f_gt) for value in gt)
        if not complete:
            pattern = "incomplete_calls"
            support = False
            inconsistent = False
        elif p_alt and not m_alt and not f_alt:
            pattern = "de_novo_candidate"
            support = True
            inconsistent = False
        elif p_hom_alt and m_het and f_het:
            pattern = "recessive_homozygous_candidate"
            support = True
            inconsistent = False
        elif p_alt and m_alt and f_alt:
            pattern = "biparental_or_common_inheritance"
            support = True
            inconsistent = False
        elif p_alt and m_alt:
            pattern = "maternal_inheritance"
            support = True
            inconsistent = False
        elif p_alt and f_alt:
            pattern = "paternal_inheritance"
            support = True
            inconsistent = False
        elif not p_alt and (m_alt or f_alt):
            pattern = "not_transmitted"
            support = False
            inconsistent = False
        else:
            pattern = "reference_or_unresolved"
            support = False
            inconsistent = bool(p_alt and not (m_alt or f_alt))
        out = row.to_dict()
        out.update({
            "proband_gt": "/".join("." if value is None else str(value) for value in p_gt),
            "mother_gt": "/".join("." if value is None else str(value) for value in m_gt),
            "father_gt": "/".join("." if value is None else str(value) for value in f_gt),
            "segregation_pattern": pattern,
            "segregation_support": support,
            "mendelian_inconsistency": inconsistent,
            "inheritance": pattern,
        })
        rows.append(out)
    return pd.DataFrame(rows)

def acmg_assistance(row: pd.Series, phenotype_match: bool, inheritance_match: bool) -> dict[str, Any]:
    consequence = str(row.get("consequence", "")).lower()
    clinvar = str(row.get("clinvar", "")).lower()
    af = float(pd.to_numeric(row.get("gnomad_af", 0), errors="coerce") or 0)
    cadd = float(pd.to_numeric(row.get("cadd", np.nan), errors="coerce"))
    revel = float(pd.to_numeric(row.get("revel", np.nan), errors="coerce"))
    spliceai = float(pd.to_numeric(row.get("spliceai", np.nan), errors="coerce"))
    criteria: list[str] = []
    points = 0
    if any(term in consequence for term in ["stop_gained", "frameshift", "splice_acceptor", "splice_donor", "start_lost"]):
        criteria.append("PVS1_supporting")
        points += 4
    if af <= 1e-4:
        criteria.append("PM2_supporting")
        points += 2
    if "pathogenic" in clinvar and "conflicting" not in clinvar:
        criteria.append("ClinVar_pathogenic_support")
        points += 3
    if (np.isfinite(cadd) and cadd >= 20) or (np.isfinite(revel) and revel >= 0.7) or (np.isfinite(spliceai) and spliceai >= 0.5):
        criteria.append("PP3_supporting")
        points += 1
    if phenotype_match:
        criteria.append("PP4_supporting")
        points += 1
    if inheritance_match:
        criteria.append("Segregation_model_support")
        points += 1
    if "benign" in clinvar:
        criteria.append("Benign_evidence_present")
        points -= 5
    tier = "High review priority" if points >= 7 else "Moderate review priority" if points >= 4 else "Low review priority"
    return {"criteria": criteria, "acmg_points_proxy": points, "acmg_assist_tier": tier}


def prioritize_variants_advanced(frame: pd.DataFrame, hpo_terms: Sequence[str], inheritance_model: str, hpo_gene_map: dict[str, set[str]] | None = None) -> pd.DataFrame:
    from .engines import HPO_GENE_MAP
    map_ = hpo_gene_map or HPO_GENE_MAP
    data = frame.copy()
    for column, default in [("gene", "Unknown"), ("consequence", "unknown"), ("clinvar", "Not provided"), ("zygosity", "unknown"), ("inheritance", "unknown")]:
        if column not in data:
            data[column] = default
    for column in ["gnomad_af", "cadd", "revel", "spliceai"]:
        if column not in data:
            data[column] = np.nan if column != "gnomad_af" else 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce")
    phenotype_genes = set().union(*(map_.get(term.strip(), set()) for term in hpo_terms)) if hpo_terms else set()
    rows = []
    model = inheritance_model.lower()
    for _, row in data.iterrows():
        gene = str(row.get("gene", "Unknown"))
        phenotype_match = gene in phenotype_genes
        zygosity = str(row.get("zygosity", "")).lower()
        inheritance = str(row.get("inheritance", "")).lower()
        chrom = str(row.get("chrom", "")).upper().replace("CHR", "")
        inheritance_match = (
            model.startswith("any")
            or ("de novo" in model and "de_novo" in inheritance)
            or ("dominant" in model and zygosity == "heterozygous")
            or ("recessive" in model and zygosity in {"homozygous", "compound_het", "compound heterozygous"})
            or ("x-linked" in model and chrom == "X")
        )
        assist = acmg_assistance(row, phenotype_match, inheritance_match)
        consequence = str(row.get("consequence", "")).lower()
        impact = 4 if any(x in consequence for x in ["stop", "frameshift", "splice_acceptor", "splice_donor"]) else 2.5 if "missense" in consequence else 1.0
        rarity = 3 if float(row.get("gnomad_af", 0) or 0) <= 1e-4 else 2 if float(row.get("gnomad_af", 0) or 0) <= 1e-3 else 0
        computational = 0
        if np.isfinite(row.get("cadd", np.nan)):
            computational += min(2, float(row["cadd"]) / 20)
        if np.isfinite(row.get("revel", np.nan)):
            computational += float(row["revel"])
        priority = impact + rarity + computational + (2 if phenotype_match else 0) + (1.5 if inheritance_match else 0) + max(0, assist["acmg_points_proxy"] * 0.4)
        out = row.to_dict()
        out.update({
            "phenotype_match": phenotype_match, "inheritance_match": inheritance_match,
            "priority_score": priority, "acmg_criteria": ", ".join(assist["criteria"]),
            "acmg_assist_tier": assist["acmg_assist_tier"], "acmg_points_proxy": assist["acmg_points_proxy"],
            "evidence_tier": "High" if priority >= 10 else "Moderate" if priority >= 6 else "Low",
        })
        rows.append(out)
    return pd.DataFrame(rows).sort_values(["priority_score", "gnomad_af"], ascending=[False, True]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Biomedical knowledge graphs
# ---------------------------------------------------------------------------


def normalize_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = nodes.copy()
    e = edges.copy()
    if "node" not in n or "type" not in n:
        raise ValueError("Node table requires node and type columns.")
    if not {"source", "target", "relation"}.issubset(e.columns):
        raise ValueError("Edge table requires source, target and relation columns.")
    n["node"] = n["node"].astype(str).str.strip()
    n["type"] = n["type"].astype(str).str.strip().replace("", "Unknown")
    n = n.drop_duplicates("node").reset_index(drop=True)
    for column, default in [("evidence_score", 0.5), ("evidence_type", "unspecified"), ("citation", ""), ("direction", "supporting")]:
        if column not in e:
            e[column] = default
    e["evidence_score"] = pd.to_numeric(e["evidence_score"], errors="coerce").fillna(0).clip(0, 1)
    e["source"] = e["source"].astype(str).str.strip()
    e["target"] = e["target"].astype(str).str.strip()
    known = set(n["node"])
    issues = []
    for row in e.itertuples(index=False):
        if row.source not in known or row.target not in known:
            issues.append({"severity": "error", "issue": f"Unknown endpoint: {row.source} -> {row.target}"})
    duplicate_count = int(e.duplicated(["source", "target", "relation", "citation"]).sum())
    if duplicate_count:
        issues.append({"severity": "warning", "issue": f"{duplicate_count} duplicate evidence rows"})
    e = e.drop_duplicates(["source", "target", "relation", "citation"]).reset_index(drop=True)
    return n, e, pd.DataFrame(issues, columns=["severity", "issue"])


def knowledge_graph_paths(edges: pd.DataFrame, source: str, target: str, max_depth: int = 4, max_paths: int = 50) -> pd.DataFrame:
    adjacency: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for row in edges.itertuples(index=False):
        adjacency[str(row.source)].append((str(row.target), str(row.relation), float(row.evidence_score)))
        adjacency[str(row.target)].append((str(row.source), f"inverse:{row.relation}", float(row.evidence_score)))
    queue = deque([(source, [source], [], [])])
    rows = []
    while queue and len(rows) < max_paths:
        node, path, relations, scores = queue.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for neighbour, relation, score in adjacency.get(node, []):
            if neighbour in path:
                continue
            new_path = path + [neighbour]
            new_relations = relations + [relation]
            new_scores = scores + [score]
            if neighbour == target:
                rows.append({
                    "path": " → ".join(new_path), "relations": " | ".join(new_relations),
                    "steps": len(new_relations), "minimum_evidence": min(new_scores),
                    "mean_evidence": float(np.mean(new_scores)), "path_score": float(np.prod(new_scores) ** (1 / len(new_scores))),
                })
            else:
                queue.append((neighbour, new_path, new_relations, new_scores))
    return pd.DataFrame(rows).sort_values(["path_score", "steps"], ascending=[False, True]) if rows else pd.DataFrame()


def graph_conflicts(edges: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (source, target), group in edges.groupby(["source", "target"], sort=False):
        directions = set(group["direction"].astype(str).str.lower())
        relations = set(group["relation"].astype(str))
        if len(directions) > 1 or len(relations) > 1:
            rows.append({
                "source": source, "target": target, "relations": ", ".join(sorted(relations)),
                "directions": ", ".join(sorted(directions)), "records": len(group),
                "mean_evidence": float(group["evidence_score"].mean()),
                "conflict": "directional" if len(directions) > 1 else "semantic",
            })
    return pd.DataFrame(rows)


def graph_research_gaps(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    degree = defaultdict(int)
    citation_count = defaultdict(int)
    for row in edges.itertuples(index=False):
        degree[str(row.source)] += 1
        degree[str(row.target)] += 1
        if str(getattr(row, "citation", "")).strip():
            citation_count[str(row.source)] += 1
            citation_count[str(row.target)] += 1
    rows = []
    for row in nodes.itertuples(index=False):
        node = str(row.node)
        d = degree[node]
        citations = citation_count[node]
        rows.append({
            "node": node, "type": row.type, "degree": d, "cited_edges": citations,
            "gap_score": (2 if d == 0 else 1 / d) + (1 if citations == 0 else 0),
            "recommendation": "Add curated evidence" if d == 0 else "Improve citation coverage" if citations == 0 else "Review low-connectivity evidence" if d <= 1 else "Adequately connected",
        })
    return pd.DataFrame(rows).sort_values("gap_score", ascending=False)


# ---------------------------------------------------------------------------
# Multi-omics biomarker modelling
# ---------------------------------------------------------------------------


class BatchMeanCenterer(BaseEstimator, TransformerMixin):
    """Leakage-safe within-fold batch mean centering.

    The transformer is fitted inside each scikit-learn CV split. It learns the
    training-fold global and batch-specific means, applies those values to test
    samples, and removes the categorical batch column before feature selection.
    Unknown external batches are left on the global scale instead of borrowing
    information from the validation cohort.
    """

    def __init__(self, batch_column: str | None = None):
        self.batch_column = batch_column

    def fit(self, X: pd.DataFrame, y: Any = None) -> "BatchMeanCenterer":
        frame = pd.DataFrame(X).copy()
        if self.batch_column and self.batch_column in frame:
            self.feature_columns_ = [column for column in frame.columns if column != self.batch_column]
            numeric = frame[self.feature_columns_].apply(pd.to_numeric, errors="coerce")
            self.global_mean_ = numeric.mean()
            self.batch_means_ = {
                str(batch): numeric.loc[index].mean()
                for batch, index in frame.groupby(self.batch_column, dropna=False).groups.items()
            }
        else:
            self.feature_columns_ = list(frame.columns)
            self.global_mean_ = frame.apply(pd.to_numeric, errors="coerce").mean()
            self.batch_means_ = {}
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        frame = pd.DataFrame(X).copy()
        missing = [column for column in self.feature_columns_ if column not in frame]
        if missing:
            raise ValueError(f"Batch correction input is missing features: {', '.join(missing[:8])}")
        numeric = frame[self.feature_columns_].apply(pd.to_numeric, errors="coerce")
        if self.batch_column and self.batch_column in frame:
            corrected = numeric.copy()
            labels = frame[self.batch_column].astype(str)
            for batch in labels.unique():
                index = labels[labels == batch].index
                batch_mean = self.batch_means_.get(str(batch))
                if batch_mean is not None:
                    corrected.loc[index] = numeric.loc[index] - batch_mean + self.global_mean_
            numeric = corrected
        return numeric

    def get_feature_names_out(self, input_features: Sequence[str] | None = None) -> np.ndarray:
        return np.asarray(self.feature_columns_, dtype=object)


def _model_spec(model_name: str, seed: int, batch_column: str | None = None) -> tuple[Pipeline, dict[str, list[Any]]]:
    name = model_name.lower()
    prefix = [("batch_center", BatchMeanCenterer(batch_column))]
    if name == "random forest":
        estimator = RandomForestClassifier(class_weight="balanced", random_state=seed, n_jobs=1)
        pipeline = Pipeline(prefix + [
            ("impute", SimpleImputer(strategy="median")),
            ("select", SelectKBest(f_classif, k="all")),
            ("model", estimator),
        ])
        grid = {"select__k": ["all", 10, 20], "model__n_estimators": [200], "model__max_depth": [None, 6], "model__min_samples_leaf": [1, 3]}
    elif name == "gradient boosting":
        estimator = GradientBoostingClassifier(random_state=seed)
        pipeline = Pipeline(prefix + [
            ("impute", SimpleImputer(strategy="median")),
            ("select", SelectKBest(f_classif, k="all")),
            ("model", estimator),
        ])
        grid = {"select__k": ["all", 10, 20], "model__n_estimators": [100, 200], "model__learning_rate": [0.03, 0.08], "model__max_depth": [2, 3]}
    else:
        penalty = "l1" if "l1" in name else "l2"
        estimator = LogisticRegression(max_iter=4000, class_weight="balanced", solver="saga", l1_ratio=1.0 if penalty == "l1" else 0.0, random_state=seed)
        pipeline = Pipeline(prefix + [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("select", SelectKBest(f_classif, k="all")),
            ("model", estimator),
        ])
        grid = {"select__k": ["all", 10, 20], "model__C": [0.05, 0.2, 0.75, 2.0]}
    return pipeline, grid


def biomarker_model_advanced(
    frame: pd.DataFrame,
    outcome_column: str,
    batch_column: str | None = None,
    model_name: str = "Logistic L1",
    outer_folds: int = 5,
    inner_folds: int = 3,
    permutations: int = 50,
    seed: int = 94,
) -> dict[str, Any]:
    data = frame.copy()
    y_series = pd.to_numeric(data[outcome_column], errors="coerce")
    valid = y_series.isin([0, 1])
    data = data.loc[valid].reset_index(drop=True)
    y = y_series.loc[valid].astype(int).to_numpy()
    excluded = {outcome_column, "sample_id"}
    if batch_column:
        excluded.add(batch_column)
    features = [c for c in data.select_dtypes(include=[np.number]).columns if c not in excluded]
    if len(features) < 2:
        raise ValueError("At least two numeric feature columns are required.")
    if batch_column and batch_column not in data:
        raise ValueError(f"Batch column was not found: {batch_column}")
    model_input_columns = [*features, *([batch_column] if batch_column else [])]
    X = data[model_input_columns].copy()
    for column in features:
        X[column] = pd.to_numeric(X[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    class_min = int(pd.Series(y).value_counts().min())
    outer_n = max(2, min(int(outer_folds), class_min))
    inner_n = max(2, min(int(inner_folds), max(2, class_min - 1)))
    outer = StratifiedKFold(n_splits=outer_n, shuffle=True, random_state=seed)
    outer_splits = list(outer.split(X, y))
    oof = np.zeros(len(y), dtype=float)
    fold_rows: list[dict[str, Any]] = []
    best_params: list[dict[str, Any]] = []
    base_pipeline, grid = _model_spec(model_name, seed, batch_column)
    # Remove impossible k values.
    grid["select__k"] = [k for k in grid.get("select__k", ["all"]) if k == "all" or int(k) <= len(features)] or ["all"]
    for fold, (train, test) in enumerate(outer_splits, start=1):
        inner = StratifiedKFold(n_splits=min(inner_n, int(pd.Series(y[train]).value_counts().min())), shuffle=True, random_state=seed + fold)
        search = GridSearchCV(clone(base_pipeline), grid, scoring="roc_auc", cv=inner, n_jobs=1, refit=True)
        search.fit(X.iloc[train], y[train])
        prob = search.predict_proba(X.iloc[test])[:, 1]
        oof[test] = prob
        pred = (prob >= 0.5).astype(int)
        fold_rows.append({
            "fold": fold, "samples": len(test), "roc_auc": roc_auc_score(y[test], prob),
            "average_precision": average_precision_score(y[test], prob),
            "balanced_accuracy": balanced_accuracy_score(y[test], pred), "brier": brier_score_loss(y[test], prob),
        })
        best_params.append(search.best_params_)
    predictions = (oof >= 0.5).astype(int)
    roc_auc, roc_low, roc_high = bootstrap_metric_ci(y, oof, "roc_auc", 250, seed)
    ap, ap_low, ap_high = bootstrap_metric_ci(y, oof, "average_precision", 250, seed + 1)
    # Lock the modal hyperparameter configuration before permutation testing.
    param_json = [json.dumps(item, sort_keys=True) for item in best_params]
    modal = json.loads(pd.Series(param_json).mode().iloc[0]) if param_json else {}
    rng = deterministic_rng(seed + 2)
    perm_scores = []
    for _ in range(max(0, int(permutations))):
        shuffled = rng.permutation(y)
        perm_oof = np.zeros(len(y), dtype=float)
        valid_permutation = True
        for train, test in outer_splits:
            if len(np.unique(shuffled[train])) < 2 or len(np.unique(shuffled[test])) < 2:
                valid_permutation = False
                break
            perm_model = clone(base_pipeline).set_params(**modal)
            perm_model.fit(X.iloc[train], shuffled[train])
            perm_oof[test] = perm_model.predict_proba(X.iloc[test])[:, 1]
        if valid_permutation:
            perm_scores.append(float(roc_auc_score(shuffled, perm_oof)))
    permutation_p = (1 + sum(score >= roc_auc for score in perm_scores)) / (1 + len(perm_scores)) if perm_scores else np.nan
    final_model = clone(base_pipeline).set_params(**modal)
    final_model.fit(X, y)
    final_model.biointel_input_columns = list(model_input_columns)
    final_model.biointel_feature_columns = list(features)
    final_model.biointel_batch_column = batch_column
    try:
        importance_result = permutation_importance(final_model, X, y, scoring="roc_auc", n_repeats=8, random_state=seed, n_jobs=1)
        importance = pd.DataFrame({"feature": model_input_columns, "importance": importance_result.importances_mean, "importance_sd": importance_result.importances_std})
        if batch_column:
            importance = importance[importance["feature"] != batch_column].reset_index(drop=True)
    except Exception:
        importance = pd.DataFrame({"feature": features, "importance": np.nan, "importance_sd": np.nan})
    importance["omics_layer"] = importance["feature"].str.split("_").str[0]
    importance = importance.sort_values("importance", ascending=False).reset_index(drop=True)
    fpr, tpr, thresholds = roc_curve(y, oof)
    precision, recall, pr_thresholds = precision_recall_curve(y, oof)
    obs, pred_prob = calibration_curve(y, oof, n_bins=min(10, max(4, len(y) // 20)), strategy="quantile")
    cm = confusion_matrix(y, predictions)
    return {
        "metrics": {
            "samples": len(y), "features": len(features), "model": model_name,
            "roc_auc": roc_auc, "roc_auc_ci_low": roc_low, "roc_auc_ci_high": roc_high,
            "average_precision": ap, "ap_ci_low": ap_low, "ap_ci_high": ap_high,
            "balanced_accuracy": balanced_accuracy_score(y, predictions), "brier": brier_score_loss(y, oof),
            "permutation_p": permutation_p, "outer_folds": outer_n, "inner_folds": inner_n,
            "batch_correction": "within-fold" if batch_column else "not_requested",
            "permutation_mode": "locked_pipeline_full_refit" if permutations else "not_run",
            "permutation_iterations_completed": len(perm_scores),
        },
        "predictions": pd.DataFrame({"sample_id": data.get("sample_id", pd.Series(range(len(data)))).astype(str), "observed": y, "probability": oof, "predicted": predictions}),
        "fold_metrics": pd.DataFrame(fold_rows), "importance": importance,
        "roc": pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": thresholds}),
        "pr": pd.DataFrame({"recall": recall, "precision": precision, "threshold": np.r_[pr_thresholds, np.nan]}),
        "calibration": pd.DataFrame({"predicted_probability": pred_prob, "observed_frequency": obs}),
        "confusion_matrix": cm, "best_parameters": modal, "model": final_model, "features": features,
        "model_input_columns": model_input_columns, "batch_column": batch_column,
    }


def external_validate_biomarker(model: Any, feature_columns: Sequence[str], frame: pd.DataFrame, outcome_column: str) -> dict[str, Any]:
    data = frame.copy()
    model_inputs = list(getattr(model, "biointel_input_columns", list(feature_columns)))
    missing = [column for column in model_inputs if column not in data]
    if missing:
        raise ValueError(f"External cohort is missing {len(missing)} locked model inputs: {', '.join(missing[:8])}")
    y = pd.to_numeric(data[outcome_column], errors="coerce")
    valid = y.isin([0, 1])
    X = data.loc[valid, model_inputs]
    yv = y.loc[valid].astype(int).to_numpy()
    probabilities = model.predict_proba(X)[:, 1]
    return {
        "samples": len(yv), "roc_auc": float(roc_auc_score(yv, probabilities)),
        "average_precision": float(average_precision_score(yv, probabilities)),
        "brier": float(brier_score_loss(yv, probabilities)),
        "predictions": pd.DataFrame({"observed": yv, "probability": probabilities}),
    }


# ---------------------------------------------------------------------------
# Workflow DAG validation and local execution
# ---------------------------------------------------------------------------


@dataclass
class WorkflowRunResult:
    run_id: str
    status: str
    started_at: float
    finished_at: float
    steps: list[dict[str, Any]]
    output_directory: str



def workflow_dag_from_blocks(blocks: Sequence[str]) -> pd.DataFrame:
    rows = []
    previous = ""
    for index, block in enumerate(blocks, start=1):
        rows.append({"id": f"step_{index:02d}", "block": block, "depends_on": previous, "condition": "always", "enabled": True})
        previous = f"step_{index:02d}"
    return pd.DataFrame(rows)


def validate_workflow_dag(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"id", "block", "depends_on", "condition", "enabled"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Workflow table is missing: {', '.join(sorted(missing))}")
    data = frame.copy()
    data["id"] = data["id"].astype(str).str.strip()
    data["block"] = data["block"].astype(str).str.strip()
    data["depends_on"] = data["depends_on"].fillna("").astype(str).str.strip()
    data["enabled"] = data["enabled"].astype(bool)
    if data["id"].duplicated().any():
        raise ValueError("Workflow step IDs must be unique.")
    enabled = data[data["enabled"]].copy()
    ids = set(enabled["id"])
    warnings = []
    for row in enabled.itertuples(index=False):
        if row.block not in WORKFLOW_BLOCKS:
            warnings.append(f"{row.id}: unknown block {row.block}")
        dependencies = [token.strip() for token in str(row.depends_on).split(",") if token.strip()]
        for dep in dependencies:
            if dep not in ids:
                warnings.append(f"{row.id}: missing dependency {dep}")
    # Kahn topological ordering.
    indegree = {row.id: 0 for row in enabled.itertuples(index=False)}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for row in enabled.itertuples(index=False):
        for dep in [token.strip() for token in str(row.depends_on).split(",") if token.strip()]:
            if dep in indegree:
                indegree[row.id] += 1
                outgoing[dep].append(row.id)
    queue = deque(sorted([node for node, degree in indegree.items() if degree == 0]))
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in outgoing.get(node, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    cycle = len(order) != len(enabled)
    if cycle:
        warnings.append("Workflow contains a dependency cycle.")
    order_index = {node: i + 1 for i, node in enumerate(order)}
    data["execution_order"] = data["id"].map(order_index)
    cpu_minutes = 0.0
    peak_memory = 0.0
    wall_minutes = 0.0
    for row in enabled.itertuples(index=False):
        spec = WORKFLOW_BLOCKS.get(row.block, {})
        cpu = float(spec.get("cpu", 1))
        memory = float(spec.get("memory_gb", 1))
        minutes = float(spec.get("minutes", 1))
        cpu_minutes += cpu * minutes
        wall_minutes += minutes
        peak_memory = max(peak_memory, memory)
    summary = {
        "valid": not cycle and not any("missing dependency" in warning or "unknown block" in warning for warning in warnings),
        "steps": len(enabled), "warnings": warnings, "execution_order": order,
        "cpu_minutes": round(cpu_minutes, 1), "estimated_wall_minutes": round(wall_minutes, 1),
        "peak_memory_gb": peak_memory,
    }
    return data.sort_values("execution_order", na_position="last"), summary


def execute_internal_workflow(
    frame: pd.DataFrame,
    output_root: str | Path,
    workflow_name: str,
    resume: bool = True,
) -> WorkflowRunResult:
    """Execute a real, resumable local workflow with persisted provenance.

    Step 95 keeps the historical return type for page/API compatibility while
    delegating execution to the quality10 v3 engine. Unlike the former marker
    runner, registered built-in blocks now parse inputs, produce scientific
    tables/reports, hash artifacts and persist a relational run registry.
    """
    from datetime import datetime

    from biointel.quality10.executor import execute_workflow_v3

    result = execute_workflow_v3(
        frame,
        output_root,
        workflow_name,
        parameters={"fail_on_quality_gate": False},
        resume=resume,
        retries=1,
        fail_fast=True,
        registry_path=Path(output_root).expanduser().resolve() / "workflow_runs.sqlite3",
        source_kind="demo",
        synthetic=True,
    )
    started = datetime.fromisoformat(result.started_at).timestamp()
    finished = datetime.fromisoformat(result.finished_at).timestamp()
    return WorkflowRunResult(
        run_id=result.run_id,
        status=result.status,
        started_at=started,
        finished_at=finished,
        steps=result.steps,
        output_directory=result.output_directory,
    )

def workflow_payload_advanced(name: str, dag: pd.DataFrame, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    validated, summary = validate_workflow_dag(dag)
    return {
        "schema": "biointel.workflow.v2",
        "name": name,
        "steps": validated.fillna("").to_dict(orient="records"),
        "parameters": parameters or {},
        "validation": {key: value for key, value in summary.items() if key != "execution_order"},
    }
