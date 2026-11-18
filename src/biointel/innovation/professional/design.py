from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.integrate import solve_ivp
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler

from .common import (
    _normalise_identifier, _numeric, _safe_run, _split_tokens,
    hardware_profile, runtime_capability_scan, stable_frame_hash, stable_payload_hash,
)

# ---------------------------------------------------------------------------
# Protein design and mutation engineering
# ---------------------------------------------------------------------------


AA_GROUPS = {
    "hydrophobic": set("AILMFWVY"),
    "charged": set("DEKR"),
    "polar": set("NQSTH"),
    "special": set("CGP"),
}


def protein_runtime_readiness() -> pd.DataFrame:
    capabilities = runtime_capability_scan()
    wanted = capabilities[capabilities["capability"].str.contains("Protein|Structure", case=False, regex=True)].copy()
    profile = hardware_profile()
    gpu = profile["gpu"]
    wanted["gpu_detected"] = bool(gpu.get("detected"))
    wanted["gpu_memory_mb"] = gpu.get("memory_mb")
    wanted["readiness"] = np.where(
        wanted["detected"] & (wanted["executable"].isin(["FoldX"]) | bool(gpu.get("detected"))),
        "Runtime ready",
        np.where(wanted["detected"], "Runtime detected; GPU/model assets require review", "Not installed"),
    )
    return wanted


def protein_structure_quality(plddt: Sequence[float] | pd.Series, pae: np.ndarray | None = None, clashes: int | None = None) -> dict[str, Any]:
    values = _numeric(pd.Series(plddt), default=np.nan).dropna()
    report = {
        "residues": int(len(values)),
        "mean_plddt": float(values.mean()) if len(values) else None,
        "fraction_plddt_ge_90": float((values >= 90).mean()) if len(values) else None,
        "fraction_plddt_lt_50": float((values < 50).mean()) if len(values) else None,
        "clashes": clashes,
    }
    if pae is not None:
        array = np.asarray(pae, dtype=float)
        finite = array[np.isfinite(array)]
        report["mean_pae"] = float(finite.mean()) if finite.size else None
        report["fraction_pae_le_5"] = float((finite <= 5).mean()) if finite.size else None
    else:
        report["mean_pae"] = None
        report["fraction_pae_le_5"] = None
    blockers: list[str] = []
    if report["mean_plddt"] is not None and report["mean_plddt"] < 70:
        blockers.append("Low mean pLDDT")
    if report["fraction_plddt_lt_50"] is not None and report["fraction_plddt_lt_50"] > 0.20:
        blockers.append("Large low-confidence region")
    if clashes is not None and clashes > max(5, len(values) * 0.02):
        blockers.append("Steric clash burden")
    report["quality_status"] = "Review" if blockers else "Pass screening"
    report["blockers"] = blockers
    report["boundary"] = "Confidence metrics do not demonstrate activity, binding, stability, expression, or safety."
    report["report_sha256"] = stable_payload_hash(report)
    return report


def protein_mutation_library(sequence: str, candidates: pd.DataFrame, top_n: int = 12, max_pairs: int = 40) -> pd.DataFrame:
    sequence = re.sub(r"[^A-Z]", "", str(sequence).upper())
    if not sequence or candidates.empty or "mutation" not in candidates:
        return pd.DataFrame()
    score_column = next((column for column in ("consensus_score", "design_score", "score", "confidence") if column in candidates), None)
    ranked = candidates.copy()
    if score_column:
        ranked[score_column] = pd.to_numeric(ranked[score_column], errors="coerce").fillna(0)
        ranked = ranked.sort_values(score_column, ascending=False)
    ranked = ranked.head(max(1, int(top_n)))
    parsed: list[tuple[str, int, str, float]] = []
    for row in ranked.itertuples(index=False):
        mutation = str(getattr(row, "mutation", ""))
        match = re.fullmatch(r"([A-Z])(\d+)([A-Z])", mutation)
        if not match:
            continue
        original, position_text, alternate = match.groups()
        position = int(position_text)
        if position < 1 or position > len(sequence) or sequence[position - 1] != original:
            continue
        score = float(getattr(row, score_column, 0.0)) if score_column else 0.0
        parsed.append((mutation, position, alternate, score))
    records: list[dict[str, Any]] = []
    for mutation, position, alternate, score in parsed:
        variant = sequence[: position - 1] + alternate + sequence[position:]
        records.append({
            "variant_id": mutation,
            "mutation_count": 1,
            "mutations": mutation,
            "sequence": variant,
            "source_score": score,
            "distance_between_mutations": np.nan,
            "compatibility_flag": "Single mutation",
        })
    pair_count = 0
    for index, left in enumerate(parsed):
        for right in parsed[index + 1:]:
            if pair_count >= max_pairs:
                break
            if left[1] == right[1]:
                continue
            variant_chars = list(sequence)
            variant_chars[left[1] - 1] = left[2]
            variant_chars[right[1] - 1] = right[2]
            distance = abs(left[1] - right[1])
            same_group = any(sequence[left[1] - 1] in group and sequence[right[1] - 1] in group for group in AA_GROUPS.values())
            records.append({
                "variant_id": f"{left[0]}+{right[0]}",
                "mutation_count": 2,
                "mutations": f"{left[0]};{right[0]}",
                "sequence": "".join(variant_chars),
                "source_score": (left[3] + right[3]) / 2,
                "distance_between_mutations": distance,
                "compatibility_flag": "Structure review" if distance <= 5 or same_group else "Lower local interaction risk",
            })
            pair_count += 1
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["sequence_sha256"] = frame["sequence"].map(lambda value: sha256(value.encode()).hexdigest())
    return frame


def protein_active_learning_queue(candidates: pd.DataFrame, assay_results: pd.DataFrame | None = None) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    frame = candidates.copy()
    score_column = next((column for column in ("consensus_score", "design_score", "score") if column in frame), None)
    confidence_column = next((column for column in ("confidence", "model_confidence") if column in frame), None)
    frame["predicted_score"] = _numeric(frame[score_column]) if score_column else 0.0
    frame["confidence"] = np.clip(_numeric(frame[confidence_column], 0.5), 0.0, 1.0) if confidence_column else 0.5
    frame["uncertainty"] = 1.0 - frame["confidence"]
    if assay_results is not None and not assay_results.empty and "mutation" in frame and "mutation" in assay_results:
        result = assay_results.copy()
        observed_column = next((column for column in ("observed_activity", "activity", "response", "result") if column in result), None)
        if observed_column:
            result[observed_column] = pd.to_numeric(result[observed_column], errors="coerce")
            frame = frame.merge(result[["mutation", observed_column]], on="mutation", how="left")
            frame["observed_result"] = frame[observed_column]
        else:
            frame["observed_result"] = np.nan
    else:
        frame["observed_result"] = np.nan
    frame["novelty_proxy"] = frame.get("mutation", pd.Series(frame.index.astype(str), index=frame.index)).astype(str).map(lambda value: (int(sha256(value.encode()).hexdigest()[:8], 16) % 1000) / 1000)
    frame["acquisition_score"] = 0.45 * frame["predicted_score"].rank(pct=True) + 0.35 * frame["uncertainty"] + 0.20 * frame["novelty_proxy"]
    frame.loc[frame["observed_result"].notna(), "acquisition_score"] = 0.0
    frame["queue_priority"] = pd.cut(frame["acquisition_score"], [-0.01, 0.4, 0.7, 1.01], labels=["Low", "Moderate", "High"])
    return frame.sort_values("acquisition_score", ascending=False)
# ---------------------------------------------------------------------------
# CRISPR screen and Perturb-seq
# ---------------------------------------------------------------------------


def guide_sequence_qc(guides: pd.DataFrame) -> pd.DataFrame:
    if guides.empty:
        return pd.DataFrame()
    frame = guides.copy()
    sequence_column = next((column for column in ("sequence", "guide_sequence", "sgRNA", "sgrna") if column in frame), None)
    if sequence_column is None:
        frame["sequence_qc"] = "No sequence column"
        return frame
    sequences = frame[sequence_column].fillna("").astype(str).str.upper().str.replace(r"[^ACGT]", "", regex=True)
    frame["sequence_length"] = sequences.str.len()
    frame["gc_fraction"] = sequences.map(lambda value: (value.count("G") + value.count("C")) / len(value) if value else np.nan)
    frame["homopolymer_max"] = sequences.map(lambda value: max((len(match.group(0)) for match in re.finditer(r"(A+|C+|G+|T+)", value)), default=0))
    frame["poly_t_termination_risk"] = sequences.str.contains("TTTT")
    frame["gc_risk"] = (frame["gc_fraction"] < 0.30) | (frame["gc_fraction"] > 0.75)
    frame["sequence_qc"] = np.select(
        [frame["sequence_length"].ne(20), frame["poly_t_termination_risk"], frame["homopolymer_max"] >= 5, frame["gc_risk"]],
        ["Unexpected spacer length", "Poly-T termination risk", "Long homopolymer", "GC outside common design range"],
        default="Pass local sequence screen",
    )
    frame["boundary"] = "Local sequence QC is not genome-wide off-target search or experimentally calibrated efficiency prediction."
    return frame


def crispr_library_plan(genes: int, guides_per_gene: int, controls: int, representation: int, sequencing_reads_per_guide: int) -> dict[str, Any]:
    genes = max(1, int(genes))
    guides_per_gene = max(1, int(guides_per_gene))
    controls = max(0, int(controls))
    representation = max(50, int(representation))
    sequencing_reads_per_guide = max(50, int(sequencing_reads_per_guide))
    guides = genes * guides_per_gene + controls
    cells = guides * representation
    reads = guides * sequencing_reads_per_guide
    report = {
        "total_guides": guides,
        "minimum_transduced_cells": cells,
        "recommended_starting_cells": int(math.ceil(cells * 1.5)),
        "minimum_sequencing_reads": reads,
        "recommended_sequencing_reads": int(math.ceil(reads * 1.25)),
        "representation": representation,
        "assumption": "Planning estimate; viability, MOI, selection loss and bottlenecks must be measured in the actual system.",
    }
    report["plan_sha256"] = stable_payload_hash(report)
    return report


def perturbseq_pseudobulk(expression: pd.DataFrame, labels: Sequence[str], groups: Sequence[str] | None = None) -> pd.DataFrame:
    if expression.empty:
        return pd.DataFrame()
    labels_series = pd.Series(list(labels), index=expression.index[: len(labels)], name="perturbation")
    frame = expression.loc[labels_series.index].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    if groups is None:
        group_series = pd.Series("all", index=frame.index, name="group")
    else:
        group_series = pd.Series(list(groups), index=frame.index[: len(groups)], name="group").reindex(frame.index).fillna("unknown")
    metadata = pd.concat([labels_series, group_series], axis=1)
    records: list[pd.Series] = []
    for (perturbation, group), indexes in metadata.groupby(["perturbation", "group"]).groups.items():
        aggregate = frame.loc[indexes].sum(axis=0)
        aggregate["perturbation"] = perturbation
        aggregate["group"] = group
        aggregate["cell_count"] = len(indexes)
        records.append(aggregate)
    result = pd.DataFrame(records)
    leading = [column for column in ("perturbation", "group", "cell_count") if column in result]
    return result[leading + [column for column in result.columns if column not in leading]]


def paired_guide_library(guides: pd.DataFrame, max_pairs: int = 200) -> pd.DataFrame:
    if guides.empty:
        return pd.DataFrame()
    guide_col = next((column for column in ("guide", "guide_id", "sgRNA", "sgrna") if column in guides), None)
    gene_col = next((column for column in ("gene", "target_gene", "target") if column in guides), None)
    if guide_col is None:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    records = guides[[guide_col] + ([gene_col] if gene_col else [])].drop_duplicates().to_dict("records")
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            if len(rows) >= max_pairs:
                break
            same_gene = bool(gene_col and str(left.get(gene_col)) == str(right.get(gene_col)))
            pair_name = f"{left[guide_col]}__{right[guide_col]}"
            rows.append({
                "pair_id": pair_name,
                "guide_a": left[guide_col],
                "guide_b": right[guide_col],
                "gene_a": left.get(gene_col, ""),
                "gene_b": right.get(gene_col, ""),
                "same_gene": same_gene,
                "design_class": "Within-gene redundancy" if same_gene else "Combinatorial interaction",
                "pair_sha256": sha256(pair_name.encode()).hexdigest(),
            })
    return pd.DataFrame(rows)
# ---------------------------------------------------------------------------
# Synthetic biology and genetic circuits
# ---------------------------------------------------------------------------


def simulate_circuit_ode(
    duration: float = 24.0,
    inducer: float = 1.0,
    production_rate: float = 5.0,
    degradation_rate: float = 0.35,
    hill_k: float = 0.5,
    hill_n: float = 2.0,
    burden: float = 0.15,
) -> pd.DataFrame:
    duration = max(float(duration), 0.1)
    inducer = max(float(inducer), 0.0)
    production_rate = max(float(production_rate), 0.0)
    degradation_rate = max(float(degradation_rate), 1e-6)
    hill_k = max(float(hill_k), 1e-6)
    hill_n = max(float(hill_n), 0.1)
    burden = float(np.clip(burden, 0.0, 0.95))
    activation = inducer ** hill_n / (hill_k ** hill_n + inducer ** hill_n) if inducer > 0 else 0.0
    effective_production = production_rate * activation * (1.0 - burden)

    def rhs(_: float, state: np.ndarray) -> list[float]:
        reporter = max(float(state[0]), 0.0)
        return [effective_production - degradation_rate * reporter]

    times = np.linspace(0, duration, max(50, int(duration * 10) + 1))
    solution = solve_ivp(rhs, (0.0, duration), [0.0], t_eval=times, rtol=1e-7, atol=1e-9)
    frame = pd.DataFrame({"time": solution.t, "reporter": solution.y[0]})
    frame["steady_state_estimate"] = effective_production / degradation_rate
    frame["model"] = "Deterministic one-state Hill activation"
    return frame


def simulate_circuit_gillespie(
    duration: float = 24.0,
    production_rate: float = 4.0,
    degradation_rate: float = 0.25,
    seed: int = 42,
    max_events: int = 200_000,
) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    time = 0.0
    molecules = 0
    rows = [{"time": time, "molecules": molecules}]
    events = 0
    while time < duration and events < max_events:
        birth = max(production_rate, 0.0)
        death = max(degradation_rate, 0.0) * molecules
        total = birth + death
        if total <= 0:
            break
        time += float(rng.exponential(1.0 / total))
        if time > duration:
            break
        if rng.random() < birth / total:
            molecules += 1
        elif molecules > 0:
            molecules -= 1
        events += 1
        rows.append({"time": time, "molecules": molecules})
    frame = pd.DataFrame(rows)
    frame["simulation_seed"] = int(seed)
    frame["event_count"] = events
    return frame


def circuit_parameter_sensitivity(base_parameters: Mapping[str, float], perturbation: float = 0.10) -> pd.DataFrame:
    perturbation = float(np.clip(perturbation, 0.01, 0.50))
    base = dict(base_parameters)
    required = {"inducer", "production_rate", "degradation_rate", "hill_k", "hill_n", "burden"}
    if not required.issubset(base):
        raise ValueError(f"Missing parameters: {sorted(required - set(base))}")
    base_frame = simulate_circuit_ode(duration=24.0, **base)
    baseline = float(base_frame["reporter"].iloc[-1])
    rows = []
    for parameter in sorted(required):
        for direction, factor in (("down", 1 - perturbation), ("up", 1 + perturbation)):
            changed = dict(base)
            changed[parameter] = max(0.0, float(changed[parameter]) * factor)
            result = simulate_circuit_ode(duration=24.0, **changed)
            endpoint = float(result["reporter"].iloc[-1])
            rows.append({
                "parameter": parameter,
                "direction": direction,
                "baseline_endpoint": baseline,
                "perturbed_endpoint": endpoint,
                "relative_change": (endpoint - baseline) / max(abs(baseline), 1e-9),
            })
    return pd.DataFrame(rows).sort_values("relative_change", key=lambda values: values.abs(), ascending=False)


def dna_assembly_plan(sequence: str, method: str = "Gibson", target_fragment_bp: int = 1500, overlap_bp: int = 30) -> pd.DataFrame:
    sequence = re.sub(r"[^ACGT]", "", str(sequence).upper())
    if not sequence:
        return pd.DataFrame()
    target_fragment_bp = max(200, int(target_fragment_bp))
    overlap_bp = int(np.clip(overlap_bp, 15, 80))
    if method.lower() in {"golden gate", "moclo"}:
        overlap_bp = 4
    records = []
    start = 0
    fragment = 1
    while start < len(sequence):
        end = min(len(sequence), start + target_fragment_bp)
        fragment_sequence = sequence[max(0, start - (overlap_bp if start else 0)): min(len(sequence), end + (overlap_bp if end < len(sequence) else 0))]
        records.append({
            "fragment": fragment,
            "core_start_1based": start + 1,
            "core_end_1based": end,
            "fragment_length": len(fragment_sequence),
            "left_overlap_bp": overlap_bp if start else 0,
            "right_overlap_bp": overlap_bp if end < len(sequence) else 0,
            "gc_fraction": (fragment_sequence.count("G") + fragment_sequence.count("C")) / len(fragment_sequence),
            "fragment_sha256": sha256(fragment_sequence.encode()).hexdigest(),
        })
        fragment += 1
        start = end
    return pd.DataFrame(records)


def sbol3_like_export(name: str, sequence: str, chassis: str, parts: pd.DataFrame) -> dict[str, Any]:
    sequence = re.sub(r"[^ACGT]", "", str(sequence).upper())
    components = []
    for index, row in parts.reset_index(drop=True).iterrows():
        component_name = str(row.get("part", row.get("name", f"part_{index+1}")))
        components.append({
            "@id": f"urn:biointel:component:{_normalise_identifier(component_name)}:{index+1}",
            "@type": "sbol:Component",
            "displayId": component_name,
            "role": str(row.get("type", row.get("role", "unspecified"))),
            "length": int(pd.to_numeric(pd.Series([row.get("length", 0)]), errors="coerce").fillna(0).iloc[0]),
        })
    document = {
        "@context": {"sbol": "http://sbols.org/v3#", "biointel": "urn:biointel:"},
        "@id": f"urn:biointel:design:{_normalise_identifier(name)}",
        "@type": "sbol:Component",
        "name": name,
        "chassis": chassis,
        "sequence": {"elements": sequence, "encoding": "IUPAC DNA", "sha256": sha256(sequence.encode()).hexdigest()},
        "components": components,
        "boundary": "SBOL3-like JSON-LD export; validate with an SBOL3 library before regulated exchange.",
    }
    document["document_sha256"] = stable_payload_hash(document)
    return document
